#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import queue
import re
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


MCP_BASE_URL = "http://127.0.0.1:41596"
FOLDER_API_URL = "http://127.0.0.1:41595/api/folder/list"
DEFAULT_SUCCESS_TAG = "已同步UIBook"
BLOCK_START = "<!-- UIBOOK_AI_ANALYSIS_START -->"
BLOCK_END = "<!-- UIBOOK_AI_ANALYSIS_END -->"
AI_HEADING_EN = "## AI Screen Analysis"
AI_HEADING_ZH = "## AI 页面分析"
SUPPORTED_EXTS = {"jpg", "jpeg", "png", "webp", "gif", "avif"}
WINDOW_CHOICES = ("today", "yesterday", "last3d", "last7d")


class MCPClient:
    def __init__(self, base_url: str = MCP_BASE_URL, timeout: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._sse_response = None
        self._message_endpoint = None
        self._reader_thread = None
        self._events: dict[int, queue.Queue[Any]] = {}
        self._next_id = 1
        self._stop = threading.Event()

    def connect(self) -> None:
        request = urllib.request.Request(
            f"{self.base_url}/sse",
            headers={"Accept": "text/event-stream"},
            method="GET",
        )
        self._sse_response = urllib.request.urlopen(request, timeout=self.timeout)
        self._reader_thread = threading.Thread(target=self._read_events, daemon=True)
        self._reader_thread.start()

        started = time.time()
        while not self._message_endpoint:
            if time.time() - started > self.timeout:
                raise TimeoutError("Timed out waiting for Eagle MCP SSE endpoint")
            time.sleep(0.05)

    def close(self) -> None:
        self._stop.set()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if not self._message_endpoint:
            self.connect()

        request_id = self._next_id
        self._next_id += 1
        result_queue: queue.Queue[Any] = queue.Queue(maxsize=1)
        self._events[request_id] = result_queue

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        request = urllib.request.Request(
            self._message_endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            if response.status >= 400:
                raise RuntimeError(f"MCP POST failed: HTTP {response.status}")

        try:
            result = result_queue.get(timeout=self.timeout)
        except queue.Empty as exc:
            self._events.pop(request_id, None)
            raise TimeoutError(f"MCP request timed out for tool {name}") from exc

        if isinstance(result, Exception):
            raise result
        return result

    def _read_events(self) -> None:
        event_name = "message"
        data_lines: list[str] = []
        while not self._stop.is_set():
            try:
                raw_line = self._sse_response.readline()
            except Exception:
                break
            if not raw_line:
                break
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if line == "":
                self._dispatch_event(event_name, "\n".join(data_lines))
                event_name = "message"
                data_lines = []
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())

    def _dispatch_event(self, event_name: str, data: str) -> None:
        if not data:
            return
        if event_name == "endpoint":
            self._message_endpoint = f"{self.base_url}{data}"
            return
        if event_name != "message":
            return
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return
        request_id = payload.get("id")
        if request_id is None:
            return
        event_queue = self._events.pop(request_id, None)
        if not event_queue:
            return
        if payload.get("error"):
            event_queue.put(RuntimeError(payload["error"].get("message", "Unknown MCP error")))
            return
        event_queue.put(payload.get("result"))


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text("utf-8"))


def get_uibook_storage_dir() -> Path:
    return Path.home() / "Library/Application Support/Eagle/plugins/uibook-sync"


def get_success_tag(repo: Path) -> str:
    config_path = get_uibook_storage_dir() / "config.json"
    config = load_json(config_path)
    success_tag = str(config.get("successTag") or "").strip()
    if success_tag:
        return success_tag

    source_path = repo / "uibook-sync" / "js" / "plugin.js"
    if source_path.exists():
        match = re.search(r"successTag:\s*'([^']+)'", source_path.read_text("utf-8"))
        if match:
            return match.group(1).strip()

    return DEFAULT_SUCCESS_TAG


def get_library_path(client: MCPClient) -> Path:
    result = client.call_tool("get_app_info", {})
    payload = parse_mcp_text_payload(result)
    data = payload.get("data") if isinstance(payload, dict) else {}
    library_path = Path(str(data.get("libraryPath") or "")).expanduser()
    if not library_path.exists():
        raise RuntimeError("Unable to resolve Eagle library path from get_app_info")
    return library_path


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo:
            return value.astimezone()
        local_tz = datetime.now().astimezone().tzinfo
        return value.replace(tzinfo=local_tz)
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000.0
        return datetime.fromtimestamp(timestamp).astimezone()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone()
        except ValueError:
            pass
        if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", text):
            return datetime.strptime(text, "%Y-%m-%d %H:%M").astimezone()
    return None


def is_same_day(value: Any, now: datetime) -> bool:
    dt = parse_timestamp(value)
    if not dt:
        return False
    return dt.date() == now.date()


def matches_window(value: Any, now: datetime, window: str) -> bool:
    dt = parse_timestamp(value)
    if not dt:
        return False
    day_delta = (now.date() - dt.date()).days
    if day_delta < 0:
        return False
    if window == "today":
        return day_delta == 0
    if window == "yesterday":
        return day_delta == 1
    if window == "last3d":
        return 0 <= day_delta <= 2
    if window == "last7d":
        return 0 <= day_delta <= 6
    raise ValueError(f"Unsupported window: {window}")


def get_window_label(window: str) -> str:
    return {
        "today": "today",
        "yesterday": "yesterday",
        "last3d": "last 3 days",
        "last7d": "last 7 days",
    }[window]


def get_file_timestamp(path: Path) -> datetime | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    raw = getattr(stat, "st_birthtime", None)
    if raw is None:
        raw = stat.st_mtime
    return parse_timestamp(raw)


def find_original_image_file(info_dir: Path) -> Path | None:
    if not info_dir.exists() or not info_dir.is_dir():
        return None
    for child in sorted(info_dir.iterdir()):
        if not child.is_file():
            continue
        ext = child.suffix.lower().lstrip(".")
        if ext not in SUPPORTED_EXTS:
            continue
        if "_thumbnail" in child.stem.lower():
            continue
        return child
    return None


def get_synced_records_for_window(window: str) -> dict[str, dict[str, Any]]:
    state_path = get_uibook_storage_dir() / "state.json"
    state = load_json(state_path)
    logs = state.get("logs") or []
    now = datetime.now().astimezone()
    by_id: dict[str, dict[str, Any]] = {}
    for entry in logs:
        if not isinstance(entry, dict):
            continue
        if entry.get("status") not in {"success", "duplicate"}:
            continue
        item_id = entry.get("itemId")
        if item_id and matches_window(entry.get("at"), now, window):
            by_id[str(item_id)] = entry
    return by_id


def get_recent_image_records_for_window(client: MCPClient, window: str) -> dict[str, dict[str, Any]]:
    library_path = get_library_path(client)
    images_dir = library_path / "images"
    now = datetime.now().astimezone()
    by_id: dict[str, dict[str, Any]] = {}
    if not images_dir.exists():
        return by_id

    for info_dir in images_dir.glob("*.info"):
        item_id = info_dir.name.removesuffix(".info")
        if not item_id:
            continue
        image_path = find_original_image_file(info_dir)
        if not image_path:
            continue
        added_at = get_file_timestamp(info_dir) or get_file_timestamp(image_path)
        if not added_at or not matches_window(added_at, now, window):
            continue
        by_id[item_id] = {
            "itemId": item_id,
            "filePath": str(image_path),
            "addedAt": added_at.isoformat(),
            "source": "recent-image",
        }
    return by_id


def parse_sync_annotation_date(annotation: str) -> datetime | None:
    for line in str(annotation or "").splitlines():
        line = line.strip()
        if not line.startswith("- 同步于 "):
            continue
        match = re.match(r"^- 同步于 (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) ", line)
        if not match:
            continue
        return parse_timestamp(match.group(1))
    return None


def parse_mcp_text_payload(result: Any) -> Any:
    content = result.get("content") if isinstance(result, dict) else None
    if not isinstance(content, list):
        return result
    for item in content:
        if item.get("type") != "text":
            continue
        text = item.get("text", "")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return result


def fetch_folder_tree(timeout: float) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        FOLDER_API_URL,
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Unable to fetch Eagle folder tree from {FOLDER_API_URL}: {exc}") from exc

    if isinstance(payload, dict):
        folders = payload.get("data")
        if payload.get("status") != "success" or not isinstance(folders, list):
            raise RuntimeError(f"Invalid Eagle folder API payload from {FOLDER_API_URL}")
        return folders
    if isinstance(payload, list):
        return payload
    raise RuntimeError(f"Unexpected Eagle folder API payload from {FOLDER_API_URL}")


def flatten_folders(
    folders: list[dict[str, Any]],
    parent_path: str = "",
) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for folder in folders:
        if not isinstance(folder, dict):
            continue
        folder_id = str(folder.get("id") or "")
        name = str(folder.get("name") or "").strip()
        if not folder_id or not name:
            continue
        path = f"{parent_path}/{name}" if parent_path else name
        flattened.append(
            {
                "id": folder_id,
                "name": name,
                "path": path,
                "description": str(folder.get("description") or ""),
                "iconColor": folder.get("iconColor"),
                "children": folder.get("children") or [],
            }
        )
        children = folder.get("children")
        if isinstance(children, list) and children:
            flattened.extend(flatten_folders(children, path))
    return flattened


def build_folder_lookup(timeout: float) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    flattened = flatten_folders(fetch_folder_tree(timeout))
    by_id = {folder["id"]: folder for folder in flattened}
    return flattened, by_id


def normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def is_section_sized(width: Any, height: Any) -> bool:
    try:
        w = int(width or 0)
        h = int(height or 0)
    except (TypeError, ValueError):
        return False
    if w <= 0 or h <= 0:
        return False
    ratio = w / h
    # Retina screenshots scale the pixels, but keep the viewport aspect ratio.
    return 1.45 <= ratio <= 2.1 and h <= 3200


def is_long_page(width: Any, height: Any) -> bool:
    try:
        w = int(width or 0)
        h = int(height or 0)
    except (TypeError, ValueError):
        return False
    if w <= 0 or h <= 0:
        return False
    return h > int(w * 1.2)


def folder_kind_priority(item: dict[str, Any]) -> tuple[list[str], str]:
    width = item.get("width")
    height = item.get("height")
    if is_long_page(width, height):
        return ["Page"], "Long or scroll-like image; prefer Page folders"
    if is_section_sized(width, height):
        return ["Section", "Page"], "Single-screen 16:9-ish image; prefer Section folders before Page folders"
    return ["Page", "Section"], "Non-section-sized image; prefer Page folders before Section folders"


def requires_visual_folder_review(item: dict[str, Any]) -> bool:
    return True


def infer_folder_topic(item: dict[str, Any]) -> tuple[str | None, str]:
    url = str(item.get("url") or "").strip().lower()
    name = str(item.get("name") or "").strip().lower()
    text = f"{url} {name}"
    patterns = [
        ("About", ["/about", " about ", "about "]),
        ("Pricing", ["/pricing", " pricing"]),
        ("Login", ["/login", "/signin", "/sign-in", " login"]),
        ("Sign up", ["/signup", "/sign-up", "/register", " sign up", " signup"]),
        ("Book demo", ["/demo", "/book-demo", "/bookdemo", " book demo"]),
        ("Report", ["/report", " report"]),
        ("Settings", ["/settings", " settings"]),
        ("Playground", ["/playground", " playground"]),
        ("Onboarding", ["/onboarding", " onboarding"]),
        ("Home", ["/home", " homepage", " home "]),
        ("Press list", ["/press", " press "]),
    ]
    for topic, needles in patterns:
        if any(needle in text for needle in needles):
            return topic, f"Matched URL or item name pattern for {topic}"
    return None, "No strong URL or item-name topic match"


def choose_suggested_folder(item: dict[str, Any], flattened_folders: list[dict[str, Any]]) -> dict[str, Any]:
    folder_kinds, size_reason = folder_kind_priority(item)
    primary_folder_kind = folder_kinds[0]
    needs_visual_review = requires_visual_folder_review(item)
    topic, topic_reason = infer_folder_topic(item)
    candidates: list[dict[str, Any]] = []

    if topic:
        for folder_kind in folder_kinds:
            exact_name = f"{folder_kind}_{topic}"
            exact_matches = [folder for folder in flattened_folders if normalize_token(folder["name"]) == normalize_token(exact_name)]
            if len(exact_matches) == 1:
                return {
                    "suggestedFolderId": exact_matches[0]["id"],
                    "suggestedFolderName": exact_matches[0]["name"],
                    "suggestedFolderPath": exact_matches[0]["path"],
                    "reason": f"{topic_reason}; {size_reason}; resolved the semantically best folder match for {exact_name}",
                    "alternatives": [folder["path"] for folder in candidates if folder["path"] != exact_matches[0]["path"]],
                    "folderKind": folder_kind,
                    "folderKindPriority": folder_kinds,
                    "requiresVisualFolderReview": needs_visual_review,
                    "topic": topic,
                    "matchType": "exact",
                }
            if len(exact_matches) > 1:
                candidates.extend(exact_matches)

    for folder_kind in folder_kinds:
        fallback_names = [f"{folder_kind}_Gerneral", f"{folder_kind}_General"]
        fallback_matches = [
            folder
            for folder in flattened_folders
            if any(normalize_token(folder["name"]) == normalize_token(name) for name in fallback_names)
        ]
        if len(fallback_matches) == 1:
            return {
                "suggestedFolderId": fallback_matches[0]["id"],
                "suggestedFolderName": fallback_matches[0]["name"],
                "suggestedFolderPath": fallback_matches[0]["path"],
                "reason": f"{topic_reason}; {size_reason}; fell back to weak general folder {fallback_matches[0]['name']}",
                "alternatives": [folder["path"] for folder in candidates if folder["path"] != fallback_matches[0]["path"]],
                "folderKind": folder_kind,
                "folderKindPriority": folder_kinds,
                "requiresVisualFolderReview": needs_visual_review,
                "topic": topic,
                "matchType": "fallback_general",
            }
        if len(fallback_matches) > 1:
            candidates.extend(fallback_matches)

    return {
        "suggestedFolderId": None,
        "suggestedFolderName": None,
        "suggestedFolderPath": None,
        "reason": f"{topic_reason}; {size_reason}",
        "alternatives": [folder["path"] for folder in candidates],
        "folderKind": primary_folder_kind,
        "folderKindPriority": folder_kinds,
        "requiresVisualFolderReview": needs_visual_review,
        "topic": topic,
        "matchType": "none",
    }


def list_tagged_items(client: MCPClient, success_tag: str) -> list[dict[str, Any]]:
    page_size = 100
    offset = 0
    items: list[dict[str, Any]] = []
    while True:
        result = client.call_tool(
            "item_get",
            {
                "tags": [success_tag],
                "fullDetails": True,
                "limit": page_size,
                "offset": offset,
            },
        )
        payload = parse_mcp_text_payload(result)
        batch = payload.get("data") if isinstance(payload, dict) else []
        if not isinstance(batch, list) or not batch:
            break
        items.extend(batch)
        if len(batch) < page_size:
            break
        offset += len(batch)
    return items


def get_items_by_ids(client: MCPClient, ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []

    items: list[dict[str, Any]] = []
    batch_size = 100
    for start in range(0, len(ids), batch_size):
        batch_ids = ids[start : start + batch_size]
        result = client.call_tool(
            "item_get",
            {
                "ids": batch_ids,
                "fullDetails": True,
                "limit": len(batch_ids),
            },
        )
        payload = parse_mcp_text_payload(result)
        batch = payload.get("data") if isinstance(payload, dict) else []
        if isinstance(batch, list):
            items.extend(batch)
    return items


def get_item_by_id(client: MCPClient, item_id: str) -> dict[str, Any]:
    result = client.call_tool(
        "item_get",
        {"ids": [item_id], "fullDetails": True, "limit": 1},
    )
    payload = parse_mcp_text_payload(result)
    items = payload.get("data") if isinstance(payload, dict) else []
    if not items:
        raise RuntimeError(f"Item not found: {item_id}")
    return items[0]


def discover_candidates(
    items: list[dict[str, Any]],
    synced_records: dict[str, dict[str, Any]],
    recent_records: dict[str, dict[str, Any]],
    window: str,
    only_unfiled: bool = False,
) -> list[dict[str, Any]]:
    now = datetime.now().astimezone()
    candidates = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        if not item_id:
            continue
        sync_dt = parse_sync_annotation_date(item.get("annotation", ""))
        annotation_matches_window = bool(sync_dt and matches_window(sync_dt, now, window))
        recent_record = recent_records.get(item_id)
        if item_id not in synced_records and not annotation_matches_window and not recent_record:
            continue
        file_path_value = str(item.get("filePath") or "")
        if not file_path_value and recent_record:
            file_path_value = str(recent_record.get("filePath") or "")
        file_path = Path(file_path_value)
        ext = file_path.suffix.lower().lstrip(".") or str(item.get("ext") or "").lower()
        has_local_image = file_path.exists()
        supported_image = ext in SUPPORTED_EXTS
        if not has_local_image or not supported_image:
            continue
        folder_ids = item.get("folders")
        if not isinstance(folder_ids, list):
            folder_ids = []
        if only_unfiled and folder_ids:
            continue
        if recent_record and not item.get("filePath"):
            item["filePath"] = recent_record.get("filePath")
        candidate_source = "synced"
        if recent_record and (item_id in synced_records or annotation_matches_window):
            candidate_source = "synced+recent"
        elif recent_record:
            candidate_source = "recent"
        item["scanInfo"] = {
            "hasLocalImage": has_local_image,
            "supportedImage": supported_image,
            "windowSyncLog": synced_records.get(item_id),
            "annotationMatchesWindow": annotation_matches_window,
            "recentImageRecord": recent_record,
            "candidateSource": candidate_source,
        }
        candidates.append(item)
    return candidates


def merge_annotation(existing: str, new_block: str) -> str:
    text = str(existing or "")
    pattern = re.compile(
        rf"\n*{re.escape(BLOCK_START)}.*?{re.escape(BLOCK_END)}\n*",
        re.DOTALL,
    )
    text = re.sub(pattern, "\n", text).strip()
    text = re.sub(r"\n*(## AI Screen Analysis|## AI 页面分析)\n.*$", "\n", text, flags=re.DOTALL).strip()
    if text:
        return f"{text}\n\n{new_block.strip()}".strip()
    return new_block.strip()


def read_analysis_block(args: argparse.Namespace) -> str:
    if args.analysis_file:
        text = Path(args.analysis_file).read_text("utf-8")
    else:
        text = sys.stdin.read()
    text = text.strip()
    has_markers = BLOCK_START in text and BLOCK_END in text
    has_heading = AI_HEADING_EN in text or AI_HEADING_ZH in text
    if not has_markers and not has_heading:
        raise RuntimeError("Analysis block must include AI block markers or an AI analysis heading")
    if has_markers and text.index(BLOCK_START) > text.index(BLOCK_END):
        raise RuntimeError("Invalid analysis block marker order")
    return text


def has_ai_analysis(annotation: Any) -> bool:
    text = str(annotation or "")
    return (
        BLOCK_START in text
        or AI_HEADING_EN in text
        or AI_HEADING_ZH in text
    )


def update_annotation(client: MCPClient, item_id: str, annotation: str) -> None:
    client.call_tool(
        "item_update",
        {
            "items": [
                {
                    "id": item_id,
                    "annotation": annotation,
                }
            ]
        },
    )


def add_item_to_folder(client: MCPClient, item_id: str, folder_id: str) -> None:
    client.call_tool(
        "item_add_to_folders",
        {
            "ids": [item_id],
            "folders": [folder_id],
        },
    )


def remove_item_from_folders(client: MCPClient, item_id: str, folder_ids: list[str]) -> None:
    if not folder_ids:
        return
    client.call_tool(
        "item_remove_from_folders",
        {
            "ids": [item_id],
            "folders": folder_ids,
        },
    )


def get_folder_action(
    current_folder_paths: list[str],
    suggestion: dict[str, Any],
) -> tuple[str, bool]:
    suggested_path = suggestion.get("suggestedFolderPath")
    if current_folder_paths:
        return "keep_locked", False
    if not suggested_path:
        return "review_unfiled", True
    if suggestion.get("requiresVisualFolderReview"):
        return "review_unfiled", True
    if suggestion.get("matchType") == "fallback_general":
        return "review_unfiled", True
    return "assign", True


def render_candidate(
    item: dict[str, Any],
    folder_lookup: dict[str, dict[str, Any]],
    flattened_folders: list[dict[str, Any]],
) -> dict[str, Any]:
    scan_info = item.get("scanInfo") or {}
    log = scan_info.get("windowSyncLog") or {}
    recent = scan_info.get("recentImageRecord") or {}
    folder_ids = item.get("folders")
    if not isinstance(folder_ids, list):
        folder_ids = []
    folder_meta = [folder_lookup.get(str(folder_id)) for folder_id in folder_ids]
    folder_meta = [folder for folder in folder_meta if folder]
    folder_paths = [folder["path"] for folder in folder_meta]
    suggestion = choose_suggested_folder(item, flattened_folders)
    folder_action, folder_action_needed = get_folder_action(folder_paths, suggestion)
    has_analysis = has_ai_analysis(item.get("annotation"))
    analysis_action = "refresh_analysis" if has_analysis else "write_analysis"
    analysis_action_needed = not has_analysis
    candidate_complete = has_analysis and not folder_action_needed
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "filePath": item.get("filePath"),
        "thumbnailPath": item.get("thumbnailPath"),
        "url": item.get("url"),
        "width": item.get("width"),
        "height": item.get("height"),
        "annotation": item.get("annotation"),
        "hasLocalImage": scan_info.get("hasLocalImage"),
        "supportedImage": scan_info.get("supportedImage"),
        "syncedAt": log.get("at"),
        "addedAt": recent.get("addedAt"),
        "entityType": log.get("entityType"),
        "remoteId": log.get("remoteId"),
        "candidateSource": scan_info.get("candidateSource"),
        "folderIds": folder_ids,
        "folderNames": [folder["name"] for folder in folder_meta],
        "folderPaths": folder_paths,
        "isUnfiled": len(folder_ids) == 0,
        "suggestedFolderId": suggestion.get("suggestedFolderId"),
        "suggestedFolderName": suggestion.get("suggestedFolderName"),
        "suggestedFolderPath": suggestion.get("suggestedFolderPath"),
        "suggestedFolderReason": suggestion.get("reason"),
        "suggestedFolderMatchType": suggestion.get("matchType"),
        "requiresVisualFolderReview": suggestion.get("requiresVisualFolderReview"),
        "folderAction": folder_action,
        "folderActionNeeded": folder_action_needed,
        "hasAiAnalysis": has_analysis,
        "analysisAction": analysis_action,
        "analysisActionNeeded": analysis_action_needed,
        "candidateComplete": candidate_complete,
        "existingFolderLocked": len(folder_ids) > 0,
    }


def get_rendered_candidates(
    client: MCPClient,
    repo: Path,
    window: str,
    limit: int | None,
    only_unfiled: bool = False,
) -> tuple[str, dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    success_tag = get_success_tag(repo)
    synced_records = get_synced_records_for_window(window)
    recent_records = get_recent_image_records_for_window(client, window)
    tagged_items = list_tagged_items(client, success_tag)
    flattened_folders, folder_lookup = build_folder_lookup(client.timeout)
    tagged_ids = {str(item.get("id") or "") for item in tagged_items}
    missing_recent_ids = [item_id for item_id in recent_records if item_id not in tagged_ids]
    recent_items = get_items_by_ids(client, missing_recent_ids)
    candidates = discover_candidates(
        tagged_items + recent_items,
        synced_records,
        recent_records,
        window,
        only_unfiled=only_unfiled,
    )
    if limit is not None:
        candidates = candidates[: limit]
    rendered = [render_candidate(item, folder_lookup, flattened_folders) for item in candidates]
    return success_tag, synced_records, recent_records, rendered


def cmd_scan(args: argparse.Namespace) -> int:
    repo = Path(args.repo).expanduser().resolve()
    client = MCPClient(timeout=args.timeout)
    try:
        success_tag, synced_records, recent_records, rendered = get_rendered_candidates(
            client,
            repo,
            args.window,
            args.limit,
            only_unfiled=args.only_unfiled,
        )

        if args.json:
            json.dump(
                {
                    "successTag": success_tag,
                    "window": args.window,
                    "windowLabel": get_window_label(args.window),
                    "syncedRecordCount": len(synced_records),
                    "recentImageCount": len(recent_records),
                    "onlyUnfiled": args.only_unfiled,
                    "candidates": rendered,
                },
                sys.stdout,
                ensure_ascii=False,
                indent=2,
            )
            sys.stdout.write("\n")
            return 0

        print(f"Success tag: {success_tag}")
        print(f"Window: {get_window_label(args.window)}")
        print(f"Matched synced ids from local state: {len(synced_records)}")
        print(f"Matched recent local images: {len(recent_records)}")
        print(f"Only unfiled: {'yes' if args.only_unfiled else 'no'}")
        print(f"Candidates: {len(rendered)}")
        print(f"Needs AI analysis: {sum(1 for item in rendered if item.get('analysisActionNeeded'))}")
        print(f"Complete: {sum(1 for item in rendered if item.get('candidateComplete'))}")
        for item in rendered:
            print(f"- {item['id']} | {item['name']}")
            print(f"  image: {item['filePath']}")
            print(f"  syncedAt: {item['syncedAt'] or '—'}")
            print(f"  addedAt: {item['addedAt'] or '—'}")
            print(f"  entityType: {item['entityType'] or '—'}")
            print(f"  remoteId: {item['remoteId'] or '—'}")
            print(f"  source: {item['candidateSource'] or '—'}")
            print(f"  folders: {', '.join(item['folderPaths']) if item['folderPaths'] else '—'}")
            print(f"  suggestedFolder: {item['suggestedFolderPath'] or '—'}")
            print(f"  requiresVisualFolderReview: {'yes' if item.get('requiresVisualFolderReview') else 'no'}")
            print(f"  folderAction: {item['folderAction']}")
            print(f"  hasAiAnalysis: {'yes' if item.get('hasAiAnalysis') else 'no'}")
            print(f"  analysisAction: {item['analysisAction']}")
            print(f"  complete: {'yes' if item.get('candidateComplete') else 'no'}")
        return 0
    finally:
        client.close()


def cmd_windows(args: argparse.Namespace) -> int:
    repo = Path(args.repo).expanduser().resolve()
    client = MCPClient(timeout=args.timeout)
    try:
        summary = []
        success_tag = get_success_tag(repo)
        for window in WINDOW_CHOICES:
            _, synced_records, recent_records, rendered = get_rendered_candidates(
                client,
                repo,
                window,
                None,
                only_unfiled=args.only_unfiled,
            )
            summary.append(
                {
                    "window": window,
                    "windowLabel": get_window_label(window),
                    "syncedRecordCount": len(synced_records),
                    "recentImageCount": len(recent_records),
                    "candidateCount": len(rendered),
                    "needsAnalysisCount": sum(1 for item in rendered if item.get("analysisActionNeeded")),
                    "completeCount": sum(1 for item in rendered if item.get("candidateComplete")),
                    "unfiledOnly": args.only_unfiled,
                }
            )

        if args.json:
            json.dump(
                {
                    "successTag": success_tag,
                    "windows": summary,
                },
                sys.stdout,
                ensure_ascii=False,
                indent=2,
            )
            sys.stdout.write("\n")
            return 0

        print(f"Success tag: {success_tag}")
        for item in summary:
            print(
                f"- {item['window']}: {item['candidateCount']} candidates "
                f"({item['windowLabel']}, synced={item['syncedRecordCount']}, recent={item['recentImageCount']}, "
                f"needsAnalysis={item['needsAnalysisCount']}, complete={item['completeCount']}, "
                f"unfiledOnly={'yes' if item['unfiledOnly'] else 'no'})"
            )
        return 0
    finally:
        client.close()


def cmd_folders(args: argparse.Namespace) -> int:
    flattened, _ = build_folder_lookup(args.timeout)
    if args.json:
        json.dump({"folders": flattened}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    print(f"Folders: {len(flattened)}")
    for folder in flattened:
        print(f"- {folder['id']} | {folder['path']}")
    return 0


def resolve_folder_id(
    flattened_folders: list[dict[str, Any]],
    folder_id: str | None,
    folder_name: str | None,
) -> dict[str, Any]:
    if folder_id:
        for folder in flattened_folders:
            if folder["id"] == folder_id:
                return folder
        raise RuntimeError(f"Folder id not found: {folder_id}")

    if not folder_name:
        raise RuntimeError("Provide either --folder-id or --folder-name")

    exact_path = [folder for folder in flattened_folders if folder["path"] == folder_name]
    if len(exact_path) == 1:
        return exact_path[0]
    if len(exact_path) > 1:
        raise RuntimeError(f"Folder path matched multiple folders unexpectedly: {folder_name}")

    exact_name = [folder for folder in flattened_folders if folder["name"] == folder_name]
    if len(exact_name) == 1:
        return exact_name[0]
    if len(exact_name) > 1:
        matches = ", ".join(folder["path"] for folder in exact_name)
        raise RuntimeError(f"Folder name is ambiguous, use full path or id instead: {matches}")

    raise RuntimeError(f"Folder not found: {folder_name}")


def cmd_assign_folder(args: argparse.Namespace) -> int:
    client = MCPClient(timeout=args.timeout)
    try:
        flattened, folder_lookup = build_folder_lookup(client.timeout)
        folder = resolve_folder_id(flattened, args.folder_id, args.folder_name)
        item = get_item_by_id(client, args.item_id)
        current_folders = item.get("folders")
        if not isinstance(current_folders, list):
            current_folders = []
        current_folder_meta = [folder_lookup.get(str(folder_id)) for folder_id in current_folders]
        current_folder_meta = [entry for entry in current_folder_meta if entry]
        remove_folder_ids: list[str] = []
        if args.replace_parent_folders:
            for current_folder in current_folder_meta:
                current_path = current_folder["path"]
                if current_folder["id"] == folder["id"]:
                    continue
                if folder["path"].startswith(f"{current_path}/"):
                    remove_folder_ids.append(current_folder["id"])
        if folder["id"] in current_folders and not remove_folder_ids:
            print(f"[skipped] {args.item_id} already in {folder['path']}")
            return 0
        if args.dry_run:
            print(
                json.dumps(
                    {
                        "itemId": args.item_id,
                        "itemName": item.get("name"),
                        "currentFolderIds": current_folders,
                        "currentFolderPaths": [entry["path"] for entry in current_folder_meta],
                        "targetFolderId": folder["id"],
                        "targetFolderName": folder["name"],
                        "targetFolderPath": folder["path"],
                        "removeFolderIds": remove_folder_ids,
                        "removeFolderPaths": [folder_lookup[folder_id]["path"] for folder_id in remove_folder_ids if folder_id in folder_lookup],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        remove_item_from_folders(client, args.item_id, remove_folder_ids)
        add_item_to_folder(client, args.item_id, folder["id"])
        if remove_folder_ids:
            removed = ", ".join(folder_lookup[folder_id]["path"] for folder_id in remove_folder_ids if folder_id in folder_lookup)
            print(f"[folder-reassigned] {args.item_id} -> {folder['path']} (removed: {removed})")
        else:
            print(f"[folder-added] {args.item_id} -> {folder['path']}")
        return 0
    finally:
        client.close()


def cmd_suggest_folder(args: argparse.Namespace) -> int:
    client = MCPClient(timeout=args.timeout)
    try:
        flattened, _ = build_folder_lookup(client.timeout)
        item = get_item_by_id(client, args.item_id)
        current_folders = item.get("folders")
        if not isinstance(current_folders, list):
            current_folders = []
        result = choose_suggested_folder(item, flattened)
        current_folder_meta = [folder for folder in flattened if folder["id"] in {str(folder_id) for folder_id in current_folders}]
        current_folder_paths = [folder["path"] for folder in current_folder_meta]
        if current_folder_paths and not args.allow_filed:
            result = {
                **result,
                "action": "keep_locked",
                "actionable": False,
                "note": "Existing folders are locked by default. Re-run with --allow-filed only when you intentionally want a correction suggestion.",
            }
        elif current_folder_paths and args.allow_filed:
            suggested_path = result.get("suggestedFolderPath")
            correction_needed = bool(suggested_path and suggested_path not in current_folder_paths)
            result = {
                **result,
                "action": "review_correction" if correction_needed else "keep",
                "actionable": correction_needed,
                "note": "Filed-item correction review is explicitly enabled for this request.",
            }
        else:
            folder_action, folder_action_needed = get_folder_action([], result)
            result = {
                **result,
                "action": folder_action,
                "actionable": folder_action_needed,
            }
        payload = {
            "itemId": args.item_id,
            "itemName": item.get("name"),
            "url": item.get("url"),
            "width": item.get("width"),
            "height": item.get("height"),
            "currentFolderPaths": current_folder_paths,
            **result,
        }
        if args.json:
            json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
            return 0
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    finally:
        client.close()


def cmd_apply(args: argparse.Namespace) -> int:
    repo = Path(args.repo).expanduser().resolve()
    _ = get_success_tag(repo)
    block = read_analysis_block(args)
    client = MCPClient(timeout=args.timeout)
    try:
        item = get_item_by_id(client, args.item_id)
        merged = merge_annotation(str(item.get("annotation") or ""), block)
        if args.dry_run:
            print(merged)
            return 0
        update_annotation(client, args.item_id, merged)
        print(f"[updated] {args.item_id}")
        return 0
    finally:
        client.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan recent Eagle image items and recent UIBook-synced items, then apply a conversation-generated AI analysis block."
    )
    subparsers = parser.add_subparsers(dest="command")

    scan = subparsers.add_parser("scan", help="List recent Eagle image items and recent UIBook-synced items for conversation-based analysis")
    scan.add_argument("--repo", required=True, help="Path to the eagle-export-plugin repository")
    scan.add_argument("--window", choices=WINDOW_CHOICES, default="today", help="Time window for recent items (default: today)")
    scan.add_argument("--limit", type=int, default=None, help="Limit the number of candidates")
    scan.add_argument("--only-unfiled", action="store_true", help="Only include candidates that are not in any Eagle folder")
    scan.add_argument("--json", action="store_true", help="Emit JSON instead of plain text")
    scan.add_argument("--timeout", type=float, default=60.0, help="MCP timeout in seconds")
    scan.set_defaults(func=cmd_scan)

    windows = subparsers.add_parser("windows", help="Show candidate counts for each supported time window")
    windows.add_argument("--repo", required=True, help="Path to the eagle-export-plugin repository")
    windows.add_argument("--only-unfiled", action="store_true", help="Only count candidates that are not in any Eagle folder")
    windows.add_argument("--json", action="store_true", help="Emit JSON instead of plain text")
    windows.add_argument("--timeout", type=float, default=60.0, help="MCP timeout in seconds")
    windows.set_defaults(func=cmd_windows)

    folders = subparsers.add_parser("folders", help="List Eagle folders for AI-assisted folder assignment")
    folders.add_argument("--json", action="store_true", help="Emit JSON instead of plain text")
    folders.add_argument("--timeout", type=float, default=60.0, help="MCP timeout in seconds")
    folders.set_defaults(func=cmd_folders)

    suggest_cmd = subparsers.add_parser("suggest-folder", help="Suggest the semantically best existing folder path for an item using folder names, full paths, and URL heuristics")
    suggest_cmd.add_argument("--item-id", required=True, help="Eagle item ID to inspect")
    suggest_cmd.add_argument("--allow-filed", action="store_true", help="Allow correction suggestions for items that already have folders")
    suggest_cmd.add_argument("--json", action="store_true", help="Emit JSON instead of plain text")
    suggest_cmd.add_argument("--timeout", type=float, default=60.0, help="Timeout in seconds")
    suggest_cmd.set_defaults(func=cmd_suggest_folder)

    apply_cmd = subparsers.add_parser("apply", help="Write a ready-made AI analysis block back to Eagle annotation")
    apply_cmd.add_argument("--repo", required=True, help="Path to the eagle-export-plugin repository")
    apply_cmd.add_argument("--item-id", required=True, help="Eagle item ID to update")
    apply_cmd.add_argument("--analysis-file", help="Path to a markdown file containing the complete analysis block")
    apply_cmd.add_argument("--dry-run", action="store_true", help="Print the merged annotation without writing")
    apply_cmd.add_argument("--timeout", type=float, default=60.0, help="MCP timeout in seconds")
    apply_cmd.set_defaults(func=cmd_apply)

    assign_cmd = subparsers.add_parser("assign-folder", help="Add an Eagle item to an existing folder after conversation-based classification")
    assign_cmd.add_argument("--item-id", required=True, help="Eagle item ID to update")
    assign_cmd.add_argument("--folder-id", help="Target Eagle folder id")
    assign_cmd.add_argument("--folder-name", help="Target Eagle folder path or exact folder name")
    assign_cmd.add_argument("--replace-parent-folders", action="store_true", help="Remove broader current parent folders when moving the item into a more accurate folder path")
    assign_cmd.add_argument("--dry-run", action="store_true", help="Preview the resolved folder assignment without writing")
    assign_cmd.add_argument("--timeout", type=float, default=60.0, help="MCP timeout in seconds")
    assign_cmd.set_defaults(func=cmd_assign_folder)

    return parser


def main() -> int:
    parser = build_parser()
    try:
        args = parser.parse_args()
        if not getattr(args, "command", None):
            args = parser.parse_args(["scan", *sys.argv[1:]])
        return args.func(args)
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
