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


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
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


def discover_candidates(items: list[dict[str, Any]], synced_records: dict[str, dict[str, Any]], window: str) -> list[dict[str, Any]]:
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
        if item_id not in synced_records and not annotation_matches_window:
            continue
        file_path = Path(str(item.get("filePath") or ""))
        ext = file_path.suffix.lower().lstrip(".") or str(item.get("ext") or "").lower()
        item["scanInfo"] = {
            "hasLocalImage": file_path.exists(),
            "supportedImage": ext in SUPPORTED_EXTS,
            "windowSyncLog": synced_records.get(item_id),
            "annotationMatchesWindow": annotation_matches_window,
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


def render_candidate(item: dict[str, Any]) -> dict[str, Any]:
    scan_info = item.get("scanInfo") or {}
    log = scan_info.get("windowSyncLog") or {}
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
        "entityType": log.get("entityType"),
        "remoteId": log.get("remoteId"),
    }


def get_rendered_candidates(client: MCPClient, repo: Path, window: str, limit: int | None) -> tuple[str, dict[str, dict[str, Any]], list[dict[str, Any]]]:
    success_tag = get_success_tag(repo)
    synced_records = get_synced_records_for_window(window)
    tagged_items = list_tagged_items(client, success_tag)
    candidates = discover_candidates(tagged_items, synced_records, window)
    if limit is not None:
        candidates = candidates[: limit]
    rendered = [render_candidate(item) for item in candidates]
    return success_tag, synced_records, rendered


def cmd_scan(args: argparse.Namespace) -> int:
    repo = Path(args.repo).expanduser().resolve()
    client = MCPClient(timeout=args.timeout)
    try:
        success_tag, synced_records, rendered = get_rendered_candidates(client, repo, args.window, args.limit)

        if args.json:
            json.dump(
                {
                    "successTag": success_tag,
                    "window": args.window,
                    "windowLabel": get_window_label(args.window),
                    "syncedRecordCount": len(synced_records),
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
        print(f"Candidates: {len(rendered)}")
        for item in rendered:
            print(f"- {item['id']} | {item['name']}")
            print(f"  image: {item['filePath']}")
            print(f"  syncedAt: {item['syncedAt'] or '—'}")
            print(f"  entityType: {item['entityType'] or '—'}")
            print(f"  remoteId: {item['remoteId'] or '—'}")
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
            _, synced_records, rendered = get_rendered_candidates(client, repo, window, None)
            summary.append(
                {
                    "window": window,
                    "windowLabel": get_window_label(window),
                    "syncedRecordCount": len(synced_records),
                    "candidateCount": len(rendered),
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
            print(f"- {item['window']}: {item['candidateCount']} candidates ({item['windowLabel']})")
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
        description="Scan today's UIBook-synced Eagle items and apply a conversation-generated AI analysis block."
    )
    subparsers = parser.add_subparsers(dest="command")

    scan = subparsers.add_parser("scan", help="List today's UIBook-synced Eagle items for conversation-based analysis")
    scan.add_argument("--repo", required=True, help="Path to the eagle-export-plugin repository")
    scan.add_argument("--window", choices=WINDOW_CHOICES, default="today", help="Time window for synced items (default: today)")
    scan.add_argument("--limit", type=int, default=None, help="Limit the number of candidates")
    scan.add_argument("--json", action="store_true", help="Emit JSON instead of plain text")
    scan.add_argument("--timeout", type=float, default=60.0, help="MCP timeout in seconds")
    scan.set_defaults(func=cmd_scan)

    windows = subparsers.add_parser("windows", help="Show candidate counts for each supported time window")
    windows.add_argument("--repo", required=True, help="Path to the eagle-export-plugin repository")
    windows.add_argument("--json", action="store_true", help="Emit JSON instead of plain text")
    windows.add_argument("--timeout", type=float, default=60.0, help="MCP timeout in seconds")
    windows.set_defaults(func=cmd_windows)

    apply_cmd = subparsers.add_parser("apply", help="Write a ready-made AI analysis block back to Eagle annotation")
    apply_cmd.add_argument("--repo", required=True, help="Path to the eagle-export-plugin repository")
    apply_cmd.add_argument("--item-id", required=True, help="Eagle item ID to update")
    apply_cmd.add_argument("--analysis-file", help="Path to a markdown file containing the complete analysis block")
    apply_cmd.add_argument("--dry-run", action="store_true", help="Print the merged annotation without writing")
    apply_cmd.add_argument("--timeout", type=float, default=60.0, help="MCP timeout in seconds")
    apply_cmd.set_defaults(func=cmd_apply)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        args = parser.parse_args(["scan", *sys.argv[1:]])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
