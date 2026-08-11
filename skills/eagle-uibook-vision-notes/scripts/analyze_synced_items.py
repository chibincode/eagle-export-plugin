#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import queue
import re
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


MCP_BASE_URL = "http://127.0.0.1:41596"
FOLDER_API_URL = "http://127.0.0.1:41595/api/folder/list"
ITEM_UPDATE_API_URL = "http://127.0.0.1:41595/api/item/update"
DEFAULT_SUCCESS_TAG = "已同步UIBook"
BLOCK_START = "<!-- UIBOOK_AI_ANALYSIS_START -->"
BLOCK_END = "<!-- UIBOOK_AI_ANALYSIS_END -->"
AI_HEADING_EN = "## AI Screen Analysis"
AI_HEADING_ZH = "## AI 页面分析"
MIRROR_DATA_HEADING = "## UIBook Mirror Data"
ANNOTATION_UTF16_HARD_LIMIT = 20_000
SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SUPPORTED_EXTS = {"jpg", "jpeg", "png", "webp", "gif", "avif"}
WINDOW_CHOICES = ("today", "yesterday", "last3d", "last7d")
UIBOOK_SCHEMA_V1 = 1
UIBOOK_SCHEMA_V2 = 2
V1_MANAGED_UIBOOK_TAG_PREFIXES = (
    "uibook:page:",
    "uibook:section:",
    "uibook:contains-section:",
    "uibook:style:",
)
V2_ONLY_UIBOOK_TAG_PREFIXES = (
    "uibook:layout:",
    "uibook:elements:",
    "uibook:industry:",
    "uibook:typography:",
    "uibook:colors:",
)
V2_MANAGED_UIBOOK_TAG_PREFIXES = (
    *V1_MANAGED_UIBOOK_TAG_PREFIXES,
    *V2_ONLY_UIBOOK_TAG_PREFIXES,
)
PUBLIC_TAXONOMY_CATEGORIES = (
    "page_type",
    "section_type",
    "industry",
    "layout",
    "elements",
    "style",
    "colors",
    "typography",
)
V2_CLASSIFICATION_FIELDS = (
    "pageType",
    "sectionTypes",
    "containedSectionTypes",
    "industries",
    "layouts",
    "elements",
    "styles",
    "colors",
    "typography",
)
V2_MAPPED_LIST_FIELDS = (
    "sectionTypes",
    "containedSectionTypes",
    "industries",
    "layouts",
    "elements",
    "styles",
    "colors",
    "typography",
)
NEUTRAL_COLOR_VALUES = {"white", "black", "gray"}
MAX_SECTION_TYPES = 2
MAX_INDUSTRIES = 3
MAX_LAYOUTS = 3
MAX_ELEMENTS = 20
MAX_WEBSITE_STYLES = 6
MAX_SECTION_STYLES = 4
MAX_COLORS = 8
MAX_TYPOGRAPHY = 2
MIN_COLOR_MIRROR_PERCENTAGE = 1.0
MIN_NEUTRAL_COLOR_TAG_PERCENTAGE = 15.0
MIN_CHROMATIC_COLOR_TAG_PERCENTAGE = 3.0
MIRROR_ENTITY_TYPES = {"website", "section"}
TAG_AUDIT_READ_ONLY_TOOLS = {"tag_count", "tag_get", "tag_group_get", "item_count", "item_get"}
TAG_AUDIT_FORBIDDEN_TOOLS = (
    "tag_update",
    "tag_merge",
    "item_add_tags",
    "item_remove_tags",
    "tag_group_create",
    "tag_group_update",
    "tag_group_delete",
    "tag_group_add_tags",
    "tag_group_remove_tags",
)
TAG_BUCKETS = (
    "页面 / 流程",
    "组件",
    "视觉风格",
    "行业 / 领域",
    "状态",
    "设备 / 平台",
    "来源 / 系统标签",
    "未归类长尾",
)
TAG_BUCKET_KEYWORDS: dict[str, tuple[str, ...]] = {
    "状态": (
        "状态",
        "空状态",
        "empty",
        "错误",
        "error",
        "网络错误",
        "loading",
        "加载",
        "骨架",
        "权限",
        "成功",
        "失败",
        "disabled",
    ),
    "组件": (
        "组件",
        "button",
        "input",
        "field",
        "tab",
        "导航",
        "搜索",
        "筛选",
        "filter",
        "dropdown",
        "card",
        "卡片",
        "表单",
        "form",
        "icon",
        "图标",
        "logo",
        "cta",
        "menu",
        "modal",
        "弹窗",
        "segmented",
    ),
    "页面 / 流程": (
        "登录",
        "注册",
        "首页",
        "个人中心",
        "详情",
        "列表",
        "定价",
        "pricing",
        "checkout",
        "支付",
        "onboarding",
        "新手",
        "引导",
        "dashboard",
        "report",
        "settings",
        "设置",
        "profile",
        "portfolio",
        "作品集",
        "hero",
        "landing",
    ),
    "视觉风格": (
        "风格",
        "clean",
        "minimal",
        "modern",
        "neutral",
        "bento",
        "dark",
        "light",
        "渐变",
        "gradient",
        "插画",
        "illustration",
        "3d",
        "玻璃",
        "动效",
        "配色",
        "color",
        "色彩",
        "商务",
        "梦幻",
        "极简",
        "简洁",
        "playful",
    ),
    "行业 / 领域": (
        "行业",
        "saas",
        "电商",
        "金融",
        "物流",
        "化学",
        "科技",
        "ai工具",
        "ai 工具",
        "shopify",
        "教育",
        "美食",
        "医疗",
        "truck",
        "卡车",
        "互联网",
    ),
    "设备 / 平台": (
        "移动端",
        "mobile",
        "desktop",
        "device",
        "web",
        "app",
        "ios",
        "android",
        "小程序",
        "ipad",
        "mac",
    ),
}
SOURCE_SYSTEM_KEYWORDS = (
    "已图压压缩",
    "已同步uibook",
    "已传",
    "imported by",
    "processed with ai autotagger",
    "| ai",
    "导出于",
    "capture:",
    "captured_at:",
    "autoscreenshot",
    "uibook",
)


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

    def update_item_fields(
        self,
        item_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        payload = json.dumps(
            {
                "id": item_id,
                **fields,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            ITEM_UPDATE_API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                result = json.loads(
                    response.read().decode("utf-8")
                )
        except Exception as exc:
            raise RuntimeError(
                f"Eagle item HTTP update failed for {item_id}: {exc}"
            ) from exc
        if (
            not isinstance(result, dict)
            or result.get("status") != "success"
        ):
            raise RuntimeError(
                "Eagle item HTTP update returned an unexpected response "
                f"for {item_id}: {result!r}"
            )
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


def call_tag_audit_tool(
    client: MCPClient,
    name: str,
    arguments: dict[str, Any],
    calls: list[dict[str, Any]],
) -> Any:
    if name not in TAG_AUDIT_READ_ONLY_TOOLS:
        raise RuntimeError(f"tag-audit refuses to call non-read-only MCP tool: {name}")
    calls.append({"name": name, "arguments": arguments})
    return parse_mcp_text_payload(client.call_tool(name, arguments))


def payload_count(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("count"), int):
        return data["count"]
    for key in ("countValue", "totalCount"):
        if isinstance(payload.get(key), int):
            return payload[key]
    return None


def tag_count_value(tag: dict[str, Any]) -> int:
    value = tag.get("count")
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def tag_name_value(tag: dict[str, Any]) -> str:
    return str(tag.get("name") or "").strip()


def lower_tag_name(name: str) -> str:
    return name.strip().lower()


def is_export_time_tag(name: str) -> bool:
    return bool(re.search(r"(^|\s)-?\s*导出于\s+\d{4}-\d{2}-\d{2}", name))


def is_ai_generated_tag(name: str) -> bool:
    lowered = lower_tag_name(name)
    return "| ai" in lowered or "processed with ai autotagger" in lowered


def is_source_system_tag(name: str) -> bool:
    lowered = lower_tag_name(name)
    return any(keyword in lowered for keyword in SOURCE_SYSTEM_KEYWORDS)


def classify_tag_bucket(tag: dict[str, Any]) -> str:
    name = tag_name_value(tag)
    lowered = lower_tag_name(name)
    if is_source_system_tag(name):
        return "来源 / 系统标签"

    for bucket in ("状态", "组件", "页面 / 流程", "视觉风格", "行业 / 领域", "设备 / 平台"):
        if any(keyword in lowered for keyword in TAG_BUCKET_KEYWORDS[bucket]):
            return bucket

    if tag_count_value(tag) <= 5:
        return "未归类长尾"
    return "未归类长尾"


def canonical_tag_name(name: str) -> str:
    lowered = lower_tag_name(name)
    lowered = re.sub(r"[\s_\-｜|/·:：]+", "", lowered)
    lowered = lowered.replace("风格", "").replace("状态", "").replace("组件", "")
    return lowered


def build_bucket_summary(tags: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    buckets = {
        bucket: {
            "tagCount": 0,
            "totalUsage": 0,
            "lowUsageCount": 0,
            "topTags": [],
            "sampleTags": [],
        }
        for bucket in TAG_BUCKETS
    }
    grouped: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in TAG_BUCKETS}

    for tag in tags:
        bucket = classify_tag_bucket(tag)
        grouped[bucket].append(tag)

    for bucket, bucket_tags in grouped.items():
        sorted_tags = sorted(bucket_tags, key=tag_count_value, reverse=True)
        buckets[bucket] = {
            "tagCount": len(bucket_tags),
            "totalUsage": sum(tag_count_value(tag) for tag in bucket_tags),
            "lowUsageCount": sum(1 for tag in bucket_tags if tag_count_value(tag) <= 5),
            "topTags": sorted_tags[:12],
            "sampleTags": sorted_tags[:30],
        }
    return buckets


def build_merge_candidates(tags: list[dict[str, Any]], limit: int = 50) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for tag in tags:
        name = tag_name_value(tag)
        if not name:
            continue
        key = canonical_tag_name(name)
        if not key:
            continue
        groups.setdefault(key, []).append(tag)

    candidates = []
    for group in groups.values():
        distinct_names = {tag_name_value(tag) for tag in group}
        if len(distinct_names) <= 1:
            continue
        sorted_group = sorted(group, key=tag_count_value, reverse=True)
        target = tag_name_value(sorted_group[0])
        candidates.append(
            {
                "target": target,
                "sourceTags": [
                    {"name": tag_name_value(tag), "count": tag_count_value(tag)}
                    for tag in sorted_group
                ],
                "reason": "大小写、分隔符或语义前缀近似",
                "totalUsage": sum(tag_count_value(tag) for tag in sorted_group),
            }
        )

    return sorted(candidates, key=lambda item: item["totalUsage"], reverse=True)[:limit]


def suggest_rename(name: str) -> str | None:
    stripped = name.strip()
    if not stripped or is_source_system_tag(stripped):
        return None

    industry_match = re.fullmatch(r"(.{1,24})行业", stripped)
    if industry_match and not stripped.startswith("行业-"):
        return f"行业-{industry_match.group(1).strip()}"

    style_match = re.fullmatch(r"(.{1,24})\s*风格", stripped, flags=re.IGNORECASE)
    if style_match and not stripped.startswith("风格-"):
        return f"风格-{style_match.group(1).strip()}"

    device_match = re.fullmatch(r"(.{1,24})\s+Device Type", stripped, flags=re.IGNORECASE)
    if device_match:
        return f"设备-{device_match.group(1).strip()}"

    color_scheme_match = re.fullmatch(r"(.{1,24})\s+Color Scheme", stripped, flags=re.IGNORECASE)
    if color_scheme_match:
        return f"视觉风格-{color_scheme_match.group(1).strip()} 配色"

    app_match = re.fullmatch(r"App-(.{1,24})", stripped, flags=re.IGNORECASE)
    if app_match:
        return f"行业-{app_match.group(1).strip()}"

    return None


def build_rename_candidates(tags: list[dict[str, Any]], limit: int = 80) -> list[dict[str, Any]]:
    candidates = []
    for tag in tags:
        name = tag_name_value(tag)
        target = suggest_rename(name)
        if not target or target == name:
            continue
        candidates.append(
            {
                "from": name,
                "to": target,
                "count": tag_count_value(tag),
                "reason": "统一到设计语义前缀",
            }
        )
    return sorted(candidates, key=lambda item: item["count"], reverse=True)[:limit]


def build_system_tag_candidates(tags: list[dict[str, Any]], limit: int = 120) -> list[dict[str, Any]]:
    candidates = []
    for tag in tags:
        name = tag_name_value(tag)
        if not is_source_system_tag(name):
            continue
        reason = "系统流程标签"
        if is_export_time_tag(name):
            reason = "导出时间被写入标签，建议改为备注或系统元数据"
        elif is_ai_generated_tag(name):
            reason = "AI 自动生成标签，建议单独分组或移出人工设计语义"
        candidates.append(
            {
                "name": name,
                "count": tag_count_value(tag),
                "reason": reason,
            }
        )
    return sorted(candidates, key=lambda item: item["count"], reverse=True)[:limit]


def build_archive_candidates(tags: list[dict[str, Any]], limit: int = 120) -> list[dict[str, Any]]:
    candidates = []
    for tag in tags:
        name = tag_name_value(tag)
        count = tag_count_value(tag)
        if is_export_time_tag(name):
            reason = "导出时间标签，应从设计检索标签中归档"
        elif count <= 1 and classify_tag_bucket(tag) == "未归类长尾":
            reason = "单次使用且未命中设计语义主轴"
        elif count <= 5 and is_ai_generated_tag(name):
            reason = "低频 AI 自动标签"
        else:
            continue
        candidates.append({"name": name, "count": count, "reason": reason})
    return sorted(candidates, key=lambda item: (item["count"], item["name"]), reverse=True)[:limit]


def get_top_tags(tags: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    return sorted(tags, key=tag_count_value, reverse=True)[:limit]


def pct(numerator: int | float, denominator: int | float | None) -> str:
    if not denominator:
        return "0.0%"
    return f"{(float(numerator) / float(denominator)) * 100:.1f}%"


def md_escape(value: Any) -> str:
    return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ").strip()


def render_tag_list(tags: list[dict[str, Any]], limit: int = 8) -> str:
    if not tags:
        return "—"
    return "、".join(f"{md_escape(tag_name_value(tag))} ({tag_count_value(tag)})" for tag in tags[:limit])


def write_tag_audit_markdown(report: dict[str, Any], path: Path) -> None:
    overview = report["overview"]
    confusion = report["confusionSources"]
    suggestions = report["suggestions"]
    buckets = report["buckets"]
    lines = [
        "# Eagle 标签只读诊断报告",
        "",
        f"- 生成时间：{report['generatedAt']}",
        f"- 资料库路径：{md_escape(report.get('libraryPath')) if report.get('libraryPath') else '未读取（为保持只调用计划内 MCP 工具）'}",
        f"- 输出原则：只读诊断，不重命名、不合并、不删除、不打标签。",
        "",
        "## 只读执行范围",
        "",
        "| 项 | 内容 |",
        "| --- | --- |",
        f"| 已调用 MCP 工具 | {', '.join(call['name'] for call in report['mcpCalls'])} |",
        f"| 明确未调用 | {', '.join(TAG_AUDIT_FORBIDDEN_TOOLS)} |",
        "",
        "## 总览",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| 标签总数 | {overview['tagCount']} |",
        f"| tag_get 返回标签数 | {overview['tagListCount']} |",
        f"| 素材总数 | {overview['itemCount']} |",
        f"| 无标签素材 | {overview['untaggedItemCount']} ({overview['untaggedItemRatio']}) |",
        f"| 标签组 | {overview['tagGroupCount']} |",
        f"| 使用次数 <= 1 的标签 | {overview['singletonTagCount']} ({overview['singletonTagRatio']}) |",
        f"| 使用次数 <= 5 的标签 | {overview['lowUsageTagCount']} ({overview['lowUsageTagRatio']}) |",
        "",
        "## 设计语义分桶",
        "",
        "| 分桶 | 标签数 | 使用次数合计 | 低频标签 | Top 标签 |",
        "| --- | ---: | ---: | ---: | --- |",
    ]

    for bucket in TAG_BUCKETS:
        bucket_info = buckets[bucket]
        lines.append(
            "| "
            + " | ".join(
                [
                    md_escape(bucket),
                    str(bucket_info["tagCount"]),
                    str(bucket_info["totalUsage"]),
                    str(bucket_info["lowUsageCount"]),
                    render_tag_list(bucket_info["topTags"], 6),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 混乱来源",
            "",
            "| 来源 | 数量 | 说明 | 样例 |",
            "| --- | ---: | --- | --- |",
            f"| 导出时间类标签 | {confusion['exportLikeCount']} | 导出记录被写成标签，容易按日期持续膨胀 | {render_tag_list(confusion['exportLikeTags'], 5)} |",
            f"| AI 自动标签 | {confusion['aiGeneratedLikeCount']} | 自动识别标签和人工设计语义混在一起 | {render_tag_list(confusion['aiGeneratedLikeTags'], 5)} |",
            f"| 系统 / 来源标签 | {confusion['systemLikeCount']} | 同步、压缩、导入来源等应独立管理 | {render_tag_list(confusion['systemLikeTags'], 5)} |",
            f"| 近似重复组 | {confusion['nearDuplicateGroupCount']} | 大小写、分隔符或语义前缀相近 | {md_escape('; '.join(' / '.join(item['name'] for item in group['sourceTags'][:4]) for group in suggestions['mergeCandidates'][:3]) or '—')} |",
            "",
            "## 设计语义建议",
            "",
            "### 建议合并预览",
            "",
            "| 建议保留 | 待合并标签 | 合计使用 | 原因 |",
            "| --- | --- | ---: | --- |",
        ]
    )

    for item in suggestions["mergeCandidates"][:20]:
        sources = "、".join(f"{md_escape(tag['name'])} ({tag['count']})" for tag in item["sourceTags"])
        lines.append(f"| {md_escape(item['target'])} | {sources} | {item['totalUsage']} | {md_escape(item['reason'])} |")
    if not suggestions["mergeCandidates"]:
        lines.append("| — | — | 0 | 暂无明显候选 |")

    lines.extend(
        [
            "",
            "### 建议改名预览",
            "",
            "| 当前标签 | 建议标签 | 使用次数 | 原因 |",
            "| --- | --- | ---: | --- |",
        ]
    )
    for item in suggestions["renameCandidates"][:30]:
        lines.append(f"| {md_escape(item['from'])} | {md_escape(item['to'])} | {item['count']} | {md_escape(item['reason'])} |")
    if not suggestions["renameCandidates"]:
        lines.append("| — | — | 0 | 暂无明显候选 |")

    lines.extend(
        [
            "",
            "### 建议转为系统标签",
            "",
            "| 标签 | 使用次数 | 原因 |",
            "| --- | ---: | --- |",
        ]
    )
    for item in suggestions["systemTagCandidates"][:30]:
        lines.append(f"| {md_escape(item['name'])} | {item['count']} | {md_escape(item['reason'])} |")
    if not suggestions["systemTagCandidates"]:
        lines.append("| — | 0 | 暂无明显候选 |")

    lines.extend(
        [
            "",
            "### 建议忽略 / 归档",
            "",
            "| 标签 | 使用次数 | 原因 |",
            "| --- | ---: | --- |",
        ]
    )
    for item in suggestions["archiveCandidates"][:30]:
        lines.append(f"| {md_escape(item['name'])} | {item['count']} | {md_escape(item['reason'])} |")
    if not suggestions["archiveCandidates"]:
        lines.append("| — | 0 | 暂无明显候选 |")

    lines.extend(
        [
            "",
            "## 无标签素材样本",
            "",
            "| ID | 名称 | 格式 | 文件夹数 |",
            "| --- | --- | --- | ---: |",
        ]
    )
    for item in report["untaggedSamples"]:
        folders = item.get("folders") if isinstance(item.get("folders"), list) else []
        lines.append(
            f"| {md_escape(item.get('id'))} | {md_escape(item.get('name'))} | {md_escape(item.get('ext'))} | {len(folders)} |"
        )

    lines.extend(
        [
            "",
            "## 后续污染源",
            "",
            "`exportitem/js/plugin.js` 当前会把 `- 导出于 YYYY-MM-DD HH:mm (uibook)` 同时写入备注和标签。后续清理写回前，建议先把导出记录只保留在备注或专用系统元数据里，避免新导出继续制造日期标签。",
            "",
            "## 下一步",
            "",
            "这份报告只提供候选清单。重命名、合并、移除、标签组迁移需要在下一轮单独确认后再执行。",
            "",
        ]
    )
    path.write_text("\n".join(lines), "utf-8")


def write_tag_audit_html(report: dict[str, Any], path: Path) -> None:
    report_json = json.dumps(report, ensure_ascii=False).replace("</", "<\\/")
    template = r'''<!DOCTYPE html>
<html lang="zh-Hans">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Eagle 标签诊断报告</title>
  <style>
    :root {
      --paper: #f6f3ec;
      --ink: #181713;
      --muted: #6c685d;
      --line: rgba(24, 23, 19, 0.14);
      --panel: rgba(255, 255, 255, 0.74);
      --panel-strong: rgba(255, 255, 255, 0.92);
      --teal: #006d77;
      --red: #b23a48;
      --amber: #b7791f;
      --green: #2f6f4e;
      --blue: #2b5b84;
      --shadow: 0 18px 48px rgba(35, 31, 24, 0.12);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        linear-gradient(90deg, rgba(24,23,19,0.035) 1px, transparent 1px) 0 0 / 24px 24px,
        linear-gradient(0deg, rgba(24,23,19,0.03) 1px, transparent 1px) 0 0 / 24px 24px,
        var(--paper);
      font-family: ui-serif, "Songti SC", "STSong", Georgia, serif;
    }

    button, input, select {
      font: inherit;
    }

    .shell {
      width: min(1440px, calc(100% - 40px));
      margin: 0 auto;
      padding: 32px 0 44px;
    }

    .topbar {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 20px;
      align-items: end;
      padding-bottom: 22px;
      border-bottom: 2px solid var(--ink);
    }

    h1 {
      margin: 0;
      font-size: clamp(34px, 5.8vw, 76px);
      line-height: 0.92;
      letter-spacing: 0;
      max-width: 900px;
    }

    .meta {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
      text-align: right;
      line-height: 1.35;
    }

    .read-only {
      display: inline-flex;
      justify-content: center;
      align-items: center;
      padding: 8px 11px;
      color: #fff;
      background: var(--green);
      border-radius: 2px;
      font-weight: 700;
      text-align: center;
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(7, minmax(126px, 1fr));
      gap: 10px;
      margin: 18px 0;
    }

    .metric {
      min-height: 104px;
      padding: 14px;
      background: var(--panel-strong);
      border: 1px solid var(--line);
      box-shadow: 0 1px 0 rgba(255,255,255,0.72) inset;
    }

    .metric b {
      display: block;
      font-size: 25px;
      line-height: 1;
      margin-bottom: 10px;
    }

    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }

    .layout {
      display: grid;
      grid-template-columns: 260px minmax(0, 1fr);
      gap: 16px;
      align-items: start;
    }

    .sidebar {
      position: sticky;
      top: 14px;
      display: grid;
      gap: 10px;
      padding: 12px;
      background: rgba(255, 255, 255, 0.48);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }

    .bucket-button,
    .tab-button {
      width: 100%;
      padding: 9px 10px;
      color: var(--ink);
      background: transparent;
      border: 1px solid transparent;
      text-align: left;
      cursor: pointer;
    }

    .bucket-button:hover,
    .tab-button:hover {
      background: rgba(0, 109, 119, 0.08);
    }

    .bucket-button.active,
    .tab-button.active {
      border-color: var(--ink);
      background: var(--ink);
      color: #fff;
    }

    .bucket-button small {
      display: block;
      margin-top: 3px;
      opacity: 0.74;
    }

    .main {
      display: grid;
      gap: 16px;
    }

    .panel {
      padding: 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }

    .panel h2 {
      margin: 0 0 14px;
      font-size: 22px;
      line-height: 1.1;
    }

    .panel h3 {
      margin: 0 0 10px;
      font-size: 16px;
    }

    .controls {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) 180px;
      gap: 10px;
      margin-bottom: 12px;
    }

    .input,
    .select {
      width: 100%;
      height: 40px;
      padding: 0 12px;
      color: var(--ink);
      background: rgba(255,255,255,0.86);
      border: 1px solid var(--line);
      border-radius: 0;
      outline: none;
    }

    .input:focus,
    .select:focus {
      border-color: var(--teal);
      box-shadow: 0 0 0 3px rgba(0,109,119,0.12);
    }

    .bucket-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }

    .bucket-card {
      padding: 12px;
      min-height: 146px;
      background: rgba(255,255,255,0.7);
      border: 1px solid var(--line);
      display: grid;
      gap: 10px;
      align-content: start;
    }

    .bucket-card strong {
      font-size: 15px;
    }

    .bar {
      height: 8px;
      background: rgba(24, 23, 19, 0.09);
      overflow: hidden;
    }

    .bar i {
      display: block;
      height: 100%;
      background: var(--teal);
    }

    .tag-cloud {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .chip {
      display: inline-flex;
      align-items: center;
      max-width: 100%;
      padding: 4px 7px;
      background: rgba(24,23,19,0.06);
      border: 1px solid rgba(24,23,19,0.08);
      color: var(--ink);
      font-size: 12px;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }

    .chip.system { background: rgba(178, 58, 72, 0.11); border-color: rgba(178, 58, 72, 0.24); }
    .chip.ai { background: rgba(43, 91, 132, 0.12); border-color: rgba(43, 91, 132, 0.22); }
    .chip.export { background: rgba(183, 121, 31, 0.14); border-color: rgba(183, 121, 31, 0.24); }

    .tabs {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
      margin-bottom: 12px;
    }

    .table-wrap {
      overflow: auto;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.58);
      max-height: 560px;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }

    th,
    td {
      padding: 9px 10px;
      border-bottom: 1px solid rgba(24,23,19,0.09);
      text-align: left;
      vertical-align: top;
    }

    th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: #fdfbf6;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    td.num,
    th.num {
      text-align: right;
      white-space: nowrap;
    }

    .muted {
      color: var(--muted);
    }

    .warning {
      border-left: 5px solid var(--amber);
      background: rgba(183, 121, 31, 0.1);
    }

    .danger {
      border-left: 5px solid var(--red);
      background: rgba(178, 58, 72, 0.08);
    }

    .split {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }

    @media (max-width: 1100px) {
      .metrics,
      .bucket-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .layout {
        grid-template-columns: 1fr;
      }

      .sidebar {
        position: static;
      }
    }

    @media (max-width: 720px) {
      .shell {
        width: min(100% - 24px, 1440px);
        padding-top: 18px;
      }

      .topbar,
      .controls,
      .split {
        grid-template-columns: 1fr;
      }

      .meta {
        text-align: left;
      }

      .metrics,
      .bucket-grid,
      .tabs {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div>
        <h1>Eagle 标签诊断报告</h1>
      </div>
      <div class="meta">
        <span class="read-only">只读报告</span>
        <span id="generatedAt"></span>
        <span id="toolScope"></span>
      </div>
    </header>

    <section class="metrics" id="metrics"></section>

    <div class="layout">
      <aside class="sidebar" id="bucketNav"></aside>
      <section class="main">
        <section class="panel">
          <h2>设计语义分桶</h2>
          <div class="bucket-grid" id="bucketGrid"></div>
        </section>

        <section class="panel">
          <h2>全标签检索</h2>
          <div class="controls">
            <input class="input" id="tagSearch" type="search" placeholder="搜索标签、分桶、系统来源...">
            <select class="select" id="usageFilter">
              <option value="all">全部使用次数</option>
              <option value="1">只看 <= 1</option>
              <option value="5">只看 <= 5</option>
              <option value="20">只看 <= 20</option>
            </select>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>标签</th>
                  <th>分桶</th>
                  <th class="num">使用次数</th>
                </tr>
              </thead>
              <tbody id="tagRows"></tbody>
            </table>
          </div>
        </section>

        <section class="panel">
          <h2>建议预览</h2>
          <div class="tabs" id="tabs"></div>
          <div class="table-wrap">
            <table>
              <thead id="suggestionHead"></thead>
              <tbody id="suggestionRows"></tbody>
            </table>
          </div>
        </section>

        <section class="split">
          <div class="panel warning">
            <h3>混乱来源</h3>
            <div id="confusion"></div>
          </div>
          <div class="panel danger">
            <h3>后续污染源</h3>
            <p><code>exportitem/js/plugin.js</code> 当前会把 <code>- 导出于 YYYY-MM-DD HH:mm (uibook)</code> 同时写入备注和标签。后续清理写回前，建议先把导出记录只保留在备注或专用系统元数据里。</p>
          </div>
        </section>

        <section class="panel">
          <h2>无标签素材样本</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>名称</th>
                  <th>格式</th>
                  <th class="num">文件夹数</th>
                </tr>
              </thead>
              <tbody id="sampleRows"></tbody>
            </table>
          </div>
        </section>
      </section>
    </div>
  </main>

  <script id="report-data" type="application/json">__REPORT_JSON__</script>
  <script>
    const report = JSON.parse(document.getElementById('report-data').textContent);
    const state = { bucket: '全部', query: '', usage: 'all', tab: 'mergeCandidates' };
    const suggestionTabs = [
      ['mergeCandidates', '建议合并'],
      ['renameCandidates', '建议改名'],
      ['systemTagCandidates', '转系统标签'],
      ['archiveCandidates', '忽略 / 归档'],
    ];

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      })[char]);
    }

    function tagClass(name) {
      const text = String(name || '').toLowerCase();
      if (text.includes('导出于')) return 'chip export';
      if (text.includes('| ai') || text.includes('autotagger')) return 'chip ai';
      if (text.includes('已同步') || text.includes('已图压') || text.includes('imported by')) return 'chip system';
      return 'chip';
    }

    function renderMetrics() {
      const o = report.overview;
      const metrics = [
        [o.tagCount, '标签总数'],
        [o.itemCount, '素材总数'],
        [o.untaggedItemCount, `无标签素材 · ${o.untaggedItemRatio}`],
        [o.tagGroupCount, '标签组'],
        [o.singletonTagCount, `单次标签 · ${o.singletonTagRatio}`],
        [o.lowUsageTagCount, `低频标签 · ${o.lowUsageTagRatio}`],
        [report.confusionSources.exportLikeCount, '导出时间标签'],
      ];
      document.getElementById('metrics').innerHTML = metrics.map(([value, label]) => `
        <div class="metric"><b>${escapeHtml(value)}</b><span>${escapeHtml(label)}</span></div>
      `).join('');
      document.getElementById('generatedAt').textContent = report.generatedAt;
      document.getElementById('toolScope').textContent = `MCP: ${report.mcpCalls.map(call => call.name).join(', ')}`;
    }

    function renderBuckets() {
      const buckets = Object.entries(report.buckets);
      const maxUsage = Math.max(...buckets.map(([, bucket]) => bucket.totalUsage), 1);
      document.getElementById('bucketNav').innerHTML = [
        ['全部', { tagCount: report.allTags.length, lowUsageCount: report.overview.lowUsageTagCount }],
        ...buckets,
      ].map(([name, bucket]) => `
        <button class="bucket-button ${state.bucket === name ? 'active' : ''}" data-bucket="${escapeHtml(name)}">
          ${escapeHtml(name)}
          <small>${bucket.tagCount} tags · ${bucket.lowUsageCount} low</small>
        </button>
      `).join('');

      document.getElementById('bucketGrid').innerHTML = buckets.map(([name, bucket]) => {
        const pct = Math.max(2, Math.round(bucket.totalUsage / maxUsage * 100));
        const chips = (bucket.topTags || []).slice(0, 6).map(tag => (
          `<span class="${tagClass(tag.name)}">${escapeHtml(tag.name)} · ${escapeHtml(tag.count)}</span>`
        )).join('');
        return `
          <article class="bucket-card">
            <strong>${escapeHtml(name)}</strong>
            <span class="muted">${bucket.tagCount} 个标签 · ${bucket.totalUsage} 次使用 · ${bucket.lowUsageCount} 个低频</span>
            <div class="bar"><i style="width:${pct}%"></i></div>
            <div class="tag-cloud">${chips}</div>
          </article>
        `;
      }).join('');

      document.querySelectorAll('[data-bucket]').forEach(button => {
        button.onclick = () => {
          state.bucket = button.dataset.bucket;
          renderBuckets();
          renderTagRows();
        };
      });
    }

    function renderTagRows() {
      const query = state.query.trim().toLowerCase();
      const maxUsage = state.usage === 'all' ? Infinity : Number(state.usage);
      const rows = report.allTags
        .filter(tag => state.bucket === '全部' || tag.bucket === state.bucket)
        .filter(tag => !query || `${tag.name} ${tag.bucket}`.toLowerCase().includes(query))
        .filter(tag => tag.count <= maxUsage)
        .slice(0, 500);

      document.getElementById('tagRows').innerHTML = rows.map(tag => `
        <tr>
          <td><span class="${tagClass(tag.name)}">${escapeHtml(tag.name)}</span></td>
          <td>${escapeHtml(tag.bucket)}</td>
          <td class="num">${escapeHtml(tag.count)}</td>
        </tr>
      `).join('') || '<tr><td colspan="3" class="muted">没有匹配标签。</td></tr>';
    }

    function renderSuggestions() {
      document.getElementById('tabs').innerHTML = suggestionTabs.map(([key, label]) => `
        <button class="tab-button ${state.tab === key ? 'active' : ''}" data-tab="${key}">
          ${escapeHtml(label)} (${(report.suggestions[key] || []).length})
        </button>
      `).join('');

      document.querySelectorAll('[data-tab]').forEach(button => {
        button.onclick = () => {
          state.tab = button.dataset.tab;
          renderSuggestions();
        };
      });

      const items = report.suggestions[state.tab] || [];
      let head = '';
      let body = '';
      if (state.tab === 'mergeCandidates') {
        head = '<tr><th>建议保留</th><th>待合并标签</th><th class="num">合计使用</th><th>原因</th></tr>';
        body = items.map(item => `
          <tr>
            <td>${escapeHtml(item.target)}</td>
            <td>${item.sourceTags.map(tag => `<span class="${tagClass(tag.name)}">${escapeHtml(tag.name)} · ${escapeHtml(tag.count)}</span>`).join(' ')}</td>
            <td class="num">${escapeHtml(item.totalUsage)}</td>
            <td>${escapeHtml(item.reason)}</td>
          </tr>
        `).join('');
      } else if (state.tab === 'renameCandidates') {
        head = '<tr><th>当前标签</th><th>建议标签</th><th class="num">使用次数</th><th>原因</th></tr>';
        body = items.map(item => `
          <tr><td>${escapeHtml(item.from)}</td><td>${escapeHtml(item.to)}</td><td class="num">${escapeHtml(item.count)}</td><td>${escapeHtml(item.reason)}</td></tr>
        `).join('');
      } else {
        head = '<tr><th>标签</th><th class="num">使用次数</th><th>原因</th></tr>';
        body = items.map(item => `
          <tr><td>${escapeHtml(item.name)}</td><td class="num">${escapeHtml(item.count)}</td><td>${escapeHtml(item.reason)}</td></tr>
        `).join('');
      }
      document.getElementById('suggestionHead').innerHTML = head;
      document.getElementById('suggestionRows').innerHTML = body || '<tr><td colspan="4" class="muted">暂无候选。</td></tr>';
    }

    function renderConfusion() {
      const c = report.confusionSources;
      const groups = [
        ['导出时间类标签', c.exportLikeCount, c.exportLikeTags],
        ['AI 自动标签', c.aiGeneratedLikeCount, c.aiGeneratedLikeTags],
        ['系统 / 来源标签', c.systemLikeCount, c.systemLikeTags],
      ];
      document.getElementById('confusion').innerHTML = groups.map(([label, count, tags]) => `
        <p><strong>${escapeHtml(label)}</strong> · ${escapeHtml(count)}</p>
        <div class="tag-cloud">${(tags || []).slice(0, 8).map(tag => `<span class="${tagClass(tag.name)}">${escapeHtml(tag.name)} · ${escapeHtml(tag.count)}</span>`).join('')}</div>
      `).join('');
    }

    function renderSamples() {
      document.getElementById('sampleRows').innerHTML = (report.untaggedSamples || []).map(item => `
        <tr>
          <td>${escapeHtml(item.id)}</td>
          <td>${escapeHtml(item.name)}</td>
          <td>${escapeHtml(item.ext)}</td>
          <td class="num">${Array.isArray(item.folders) ? item.folders.length : 0}</td>
        </tr>
      `).join('');
    }

    function bindControls() {
      document.getElementById('tagSearch').oninput = event => {
        state.query = event.target.value;
        renderTagRows();
      };
      document.getElementById('usageFilter').onchange = event => {
        state.usage = event.target.value;
        renderTagRows();
      };
    }

    renderMetrics();
    renderBuckets();
    renderTagRows();
    renderSuggestions();
    renderConfusion();
    renderSamples();
    bindControls();
  </script>
</body>
</html>
'''
    path.write_text(template.replace("__REPORT_JSON__", report_json), "utf-8")


def build_tag_audit_report(
    repo: Path,
    client: MCPClient,
    sample_size: int,
) -> dict[str, Any]:
    calls: list[dict[str, Any]] = []
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")

    tag_count_payload = call_tag_audit_tool(client, "tag_count", {}, calls)
    tags_payload = call_tag_audit_tool(client, "tag_get", {}, calls)
    tag_groups_payload = call_tag_audit_tool(client, "tag_group_get", {}, calls)
    item_count_payload = call_tag_audit_tool(client, "item_count", {}, calls)
    untagged_payload = call_tag_audit_tool(client, "item_get", {"isUntagged": True, "limit": sample_size}, calls)

    tags = tags_payload.get("data") if isinstance(tags_payload, dict) else []
    if not isinstance(tags, list):
        tags = []
    tag_groups = tag_groups_payload.get("data") if isinstance(tag_groups_payload, dict) else []
    if not isinstance(tag_groups, list):
        tag_groups = []
    untagged_samples = untagged_payload.get("data") if isinstance(untagged_payload, dict) else []
    if not isinstance(untagged_samples, list):
        untagged_samples = []

    tag_count = payload_count(tag_count_payload) or len(tags)
    item_count = payload_count(item_count_payload) or 0
    untagged_count = payload_count(untagged_payload) or len(untagged_samples)
    singleton_tags = [tag for tag in tags if tag_count_value(tag) <= 1]
    low_usage_tags = [tag for tag in tags if tag_count_value(tag) <= 5]
    export_like_tags = [tag for tag in tags if is_export_time_tag(tag_name_value(tag))]
    ai_generated_like_tags = [tag for tag in tags if is_ai_generated_tag(tag_name_value(tag))]
    system_like_tags = [tag for tag in tags if is_source_system_tag(tag_name_value(tag))]
    buckets = build_bucket_summary(tags)
    merge_candidates = build_merge_candidates(tags)
    rename_candidates = build_rename_candidates(tags)
    system_tag_candidates = build_system_tag_candidates(tags)
    archive_candidates = build_archive_candidates(tags)

    return {
        "generatedAt": generated_at,
        "repo": str(repo),
        "libraryPath": None,
        "readOnly": True,
        "readOnlyTools": sorted(TAG_AUDIT_READ_ONLY_TOOLS),
        "forbiddenToolsNotUsed": list(TAG_AUDIT_FORBIDDEN_TOOLS),
        "mcpCalls": calls,
        "allTags": [
            {
                "name": tag_name_value(tag),
                "count": tag_count_value(tag),
                "bucket": classify_tag_bucket(tag),
            }
            for tag in sorted(tags, key=tag_count_value, reverse=True)
        ],
        "overview": {
            "tagCount": tag_count,
            "tagListCount": len(tags),
            "itemCount": item_count,
            "untaggedItemCount": untagged_count,
            "untaggedItemRatio": pct(untagged_count, item_count),
            "tagGroupCount": len(tag_groups),
            "singletonTagCount": len(singleton_tags),
            "singletonTagRatio": pct(len(singleton_tags), tag_count),
            "lowUsageTagCount": len(low_usage_tags),
            "lowUsageTagRatio": pct(len(low_usage_tags), tag_count),
            "totalTagUsage": sum(tag_count_value(tag) for tag in tags),
        },
        "buckets": buckets,
        "confusionSources": {
            "exportLikeCount": len(export_like_tags),
            "exportLikeTags": get_top_tags(export_like_tags, 40),
            "aiGeneratedLikeCount": len(ai_generated_like_tags),
            "aiGeneratedLikeTags": get_top_tags(ai_generated_like_tags, 40),
            "systemLikeCount": len(system_like_tags),
            "systemLikeTags": get_top_tags(system_like_tags, 40),
            "nearDuplicateGroupCount": len(merge_candidates),
        },
        "suggestions": {
            "mergeCandidates": merge_candidates,
            "renameCandidates": rename_candidates,
            "systemTagCandidates": system_tag_candidates,
            "archiveCandidates": archive_candidates,
        },
        "untaggedSamples": untagged_samples,
        "raw": {
            "tagCountPayload": tag_count_payload,
            "itemCountPayload": item_count_payload,
            "tagGroups": tag_groups,
            "tags": tags,
        },
    }


def cmd_tag_audit(args: argparse.Namespace) -> int:
    repo = Path(args.repo).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = repo / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    client = MCPClient(timeout=args.timeout)
    try:
        report = build_tag_audit_report(repo, client, max(0, args.sample_size))
    finally:
        client.close()

    date_key = datetime.now().astimezone().date().isoformat()
    md_path = output_dir / f"eagle-tag-audit-{date_key}.md"
    json_path = output_dir / f"eagle-tag-audit-{date_key}.json"
    html_path = output_dir / f"eagle-tag-audit-{date_key}.html"
    write_tag_audit_markdown(report, md_path)
    write_tag_audit_html(report, html_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")

    print(f"Markdown report: {md_path}")
    print(f"JSON report: {json_path}")
    print(f"HTML report: {html_path}")
    print(
        "Summary: "
        f"{report['overview']['tagCount']} tags, "
        f"{report['overview']['untaggedItemCount']} untagged items, "
        f"{report['overview']['lowUsageTagCount']} low-usage tags, "
        f"{report['confusionSources']['exportLikeCount']} export-time tags, "
        f"{report['confusionSources']['aiGeneratedLikeCount']} AI-generated tags"
    )
    return 0


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


def annotation_sha256(annotation: Any) -> str:
    return hashlib.sha256(
        str(annotation or "").encode("utf-8")
    ).hexdigest()


def normalize_legacy_annotation_sha256(value: Any) -> str | None:
    if value is None:
        return None
    digest = str(value).strip()
    if not SHA256_HEX_PATTERN.fullmatch(digest):
        raise RuntimeError(
            "--legacy-annotation-sha256 must be exactly 64 lowercase "
            "hexadecimal characters"
        )
    return digest


def annotation_metrics(annotation: Any) -> dict[str, int]:
    text = str(annotation or "")
    return {
        "codePoints": len(text),
        "utf16CodeUnits": len(text.encode("utf-16-le")) // 2,
        "utf8Bytes": len(text.encode("utf-8")),
        "limitUtf16CodeUnits": ANNOTATION_UTF16_HARD_LIMIT,
    }


def preflight_annotation(annotation: Any) -> dict[str, int]:
    metrics = annotation_metrics(annotation)
    if (
        metrics["utf16CodeUnits"]
        > metrics["limitUtf16CodeUnits"]
    ):
        raise RuntimeError(
            "Merged Eagle annotation exceeds the hard preflight limit "
            f"({metrics['utf16CodeUnits']} UTF-16 code units > "
            f"{metrics['limitUtf16CodeUnits']}); no Eagle tags or "
            "annotation were written"
        )
    return metrics


def merge_annotation_with_info(
    existing: str,
    new_block: str,
    legacy_annotation_sha256: str | None = None,
) -> tuple[str, dict[str, Any]]:
    text = str(existing or "")
    expected_legacy_hash = normalize_legacy_annotation_sha256(
        legacy_annotation_sha256
    )
    current_hash = annotation_sha256(text)
    migration_info: dict[str, Any] = {
        "requested": expected_legacy_hash is not None,
        "performed": False,
        "mode": "not-required",
        "currentAnnotationSha256": current_hash,
        "currentAnnotationLength": annotation_metrics(text),
    }
    marker_pattern = re.compile(
        rf"\n*{re.escape(BLOCK_START)}.*?{re.escape(BLOCK_END)}\n*",
        re.DOTALL,
    )
    start_count = text.count(BLOCK_START)
    end_count = text.count(BLOCK_END)
    if start_count or end_count:
        if start_count != end_count:
            raise RuntimeError(
                "Refusing to replace an AI block with unmatched analysis markers"
            )
        text, replacement_count = marker_pattern.subn("\n", text)
        if replacement_count != start_count:
            raise RuntimeError(
                "Refusing to replace an AI block whose analysis markers could "
                "not be paired safely"
            )
        if expected_legacy_hash is not None:
            raise RuntimeError(
                "--legacy-annotation-sha256 is only valid for an "
                "unbounded markerless legacy AI block"
            )
        migration_info["mode"] = "marker-wrapped"
        text = text.strip()
        if text:
            return (
                f"{text}\n\n{new_block.strip()}".strip(),
                migration_info,
            )
        return new_block.strip(), migration_info

    heading_match = re.search(
        r"(?m)^## (?:AI Screen Analysis|AI 页面分析)[ \t]*$",
        text,
    )
    if heading_match:
        mirror_boundary = re.compile(
            rf"(?ms)^{re.escape(MIRROR_DATA_HEADING)}[ \t]*\n+"
            r"[ \t]*```json[ \t]*\n.*?^[ \t]*```[ \t]*(?:\n|$)"
        ).search(text, heading_match.end())
        if not mirror_boundary:
            if expected_legacy_hash is None:
                raise RuntimeError(
                    "Refusing to replace a markerless legacy AI block "
                    "because it has no bounded UIBook Mirror Data JSON "
                    "section; manual notes after the AI block cannot be "
                    "distinguished safely. Current complete annotation "
                    f"SHA-256: {current_hash}. To explicitly replace from "
                    "the AI heading to the end, rerun with "
                    f"--legacy-annotation-sha256 {current_hash}"
                )
            if expected_legacy_hash != current_hash:
                raise RuntimeError(
                    "--legacy-annotation-sha256 does not exactly match "
                    "the current complete Eagle annotation "
                    f"({expected_legacy_hash} != {current_hash})"
                )
            prefix = text[: heading_match.start()].rstrip()
            migration_info.update(
                {
                    "performed": True,
                    "mode": "exact-sha256-replace-heading-to-end",
                    "preservedPrefixCodePoints": len(prefix),
                }
            )
            if prefix:
                return (
                    f"{prefix}\n\n{new_block.strip()}".strip(),
                    migration_info,
                )
            return new_block.strip(), migration_info
        if expected_legacy_hash is not None:
            raise RuntimeError(
                "--legacy-annotation-sha256 is only valid for an "
                "unbounded markerless legacy AI block"
            )
        migration_info["mode"] = "markerless-bounded"
        prefix = text[: heading_match.start()].rstrip()
        suffix = text[mirror_boundary.end() :].lstrip()
        text = "\n\n".join(
            part
            for part in (prefix, suffix)
            if part
        ).strip()
    elif expected_legacy_hash is not None:
        raise RuntimeError(
            "--legacy-annotation-sha256 is only valid for an "
            "unbounded markerless legacy AI block"
        )
    else:
        migration_info["mode"] = "append"

    if text:
        return (
            f"{text}\n\n{new_block.strip()}".strip(),
            migration_info,
        )
    return new_block.strip(), migration_info


def merge_annotation(
    existing: str,
    new_block: str,
    legacy_annotation_sha256: str | None = None,
) -> str:
    merged, _ = merge_annotation_with_info(
        existing,
        new_block,
        legacy_annotation_sha256,
    )
    return merged


def save_legacy_annotation_backup(
    annotation: Any,
    backup_file: str,
) -> dict[str, Any]:
    text = str(annotation or "")
    path = Path(backup_file).expanduser().resolve()
    created = False
    try:
        with path.open(
            "x",
            encoding="utf-8",
            newline="",
        ) as handle:
            handle.write(text)
        created = True
    except FileExistsError:
        with path.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as handle:
            existing = handle.read()
        if existing != text:
            raise RuntimeError(
                "Legacy annotation backup already exists with different "
                f"content: {path}"
            )
    return {
        "path": str(path),
        "created": created,
        "verified": True,
        "sha256": annotation_sha256(text),
        "length": annotation_metrics(text),
    }


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


def extract_embedded_mirror_data(annotation: Any) -> tuple[dict[str, Any] | None, str | None]:
    text = str(annotation or "")
    pattern = re.compile(
        rf"(?ms)^{re.escape(MIRROR_DATA_HEADING)}[ \t]*\n+"
        r"[ \t]*```json[ \t]*\n(?P<payload>.*?)^[ \t]*```[ \t]*(?:\n|$)"
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return None, "missing_v2_mirror"
    if len(matches) != 1:
        return None, "multiple_mirror_blocks"
    try:
        payload = json.loads(
            matches[0].group("payload"),
            parse_constant=reject_nonfinite_json_constant,
        )
    except (json.JSONDecodeError, ValueError):
        return None, "invalid_mirror_json"
    if not isinstance(payload, dict):
        return None, "invalid_mirror_root"
    return payload, None


def expected_v2_managed_tags(mirror: dict[str, Any], item_id: str) -> list[str]:
    if mirror.get("schemaVersion") != UIBOOK_SCHEMA_V2:
        raise RuntimeError("schema_v2_required")
    if str(mirror.get("sourceItemId") or "").strip() != item_id:
        raise RuntimeError("mirror_item_mismatch")

    entity_type = str(mirror.get("entityType") or "").strip()
    if entity_type not in MIRROR_ENTITY_TYPES:
        raise RuntimeError("invalid_mirror_entity_type")
    classification = mirror.get("classification")
    if not isinstance(classification, dict) or set(classification) != set(
        V2_CLASSIFICATION_FIELDS
    ):
        raise RuntimeError("invalid_v2_classification")

    def string_list(field: str) -> list[str]:
        values = classification.get(field)
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value.strip()
            for value in values
        ):
            raise RuntimeError(f"invalid_v2_{field}")
        return [value.strip() for value in values]

    page_type = classification.get("pageType")
    section_types = string_list("sectionTypes")
    contained_section_types = string_list("containedSectionTypes")
    industries = string_list("industries")
    layouts = string_list("layouts")
    elements = string_list("elements")
    colors = string_list("colors")
    typography = string_list("typography")

    if entity_type == "website":
        if not isinstance(page_type, str) or not page_type.strip():
            raise RuntimeError("invalid_v2_page_type")
        if section_types or layouts:
            raise RuntimeError("invalid_v2_website_boundaries")
    else:
        if page_type is not None or not section_types or contained_section_types:
            raise RuntimeError("invalid_v2_section_boundaries")

    tags: set[str] = set()
    if isinstance(page_type, str) and page_type.strip():
        tags.add(f"uibook:page:{page_type.strip()}")
    tags.update(f"uibook:section:{value}" for value in section_types)
    tags.update(
        f"uibook:contains-section:{value}"
        for value in contained_section_types
    )
    tags.update(f"uibook:industry:{value}" for value in industries)
    tags.update(f"uibook:layout:{value}" for value in layouts)
    tags.update(f"uibook:elements:{value}" for value in elements)
    tags.update(f"uibook:typography:{value}" for value in typography)

    styles = classification.get("styles")
    if not isinstance(styles, list):
        raise RuntimeError("invalid_v2_styles")
    for style in styles:
        if not isinstance(style, dict) or set(style) != {"dimension", "value"}:
            raise RuntimeError("invalid_v2_styles")
        dimension = str(style.get("dimension") or "").strip()
        value = str(style.get("value") or "").strip()
        if not dimension or not value:
            raise RuntimeError("invalid_v2_styles")
        tags.add(f"uibook:style:{dimension}:{value}")

    color_weights = mirror.get("colorWeights")
    if not isinstance(color_weights, dict) or set(color_weights) != set(colors):
        raise RuntimeError("invalid_v2_color_weights")
    for color in colors:
        percentage = color_weights[color]
        if isinstance(percentage, bool) or not isinstance(percentage, (int, float)):
            raise RuntimeError("invalid_v2_color_weights")
        percentage = float(percentage)
        if not math.isfinite(percentage):
            raise RuntimeError("invalid_v2_color_weights")
        threshold = (
            MIN_NEUTRAL_COLOR_TAG_PERCENTAGE
            if color.casefold() in NEUTRAL_COLOR_VALUES
            else MIN_CHROMATIC_COLOR_TAG_PERCENTAGE
        )
        if percentage >= threshold:
            tags.add(f"uibook:colors:{color}")
    return sorted(tags)


def inspect_uibook_preparation(item: dict[str, Any]) -> dict[str, Any]:
    has_analysis = has_ai_analysis(item.get("annotation"))
    mirror, issue = extract_embedded_mirror_data(item.get("annotation"))
    expected_tags: list[str] = []
    schema_version = mirror.get("schemaVersion") if mirror else None
    if mirror is not None:
        try:
            expected_tags = expected_v2_managed_tags(
                mirror,
                str(item.get("id") or "").strip(),
            )
        except RuntimeError as exc:
            issue = str(exc)

    current_managed_tags = sorted(
        tag
        for tag in item_tag_names(item)
        if is_managed_uibook_tag(tag, V2_MANAGED_UIBOOK_TAG_PREFIXES)
    )
    missing_tags = sorted(set(expected_tags) - set(current_managed_tags))
    stale_tags = sorted(set(current_managed_tags) - set(expected_tags))
    has_v2_mirror = mirror is not None and issue is None
    has_uibook_tags = (
        has_v2_mirror
        and bool(expected_tags)
        and not missing_tags
        and not stale_tags
    )
    complete = has_analysis and has_v2_mirror and has_uibook_tags
    if not has_analysis:
        issue = "missing_ai_analysis"
    elif has_v2_mirror and not has_uibook_tags:
        issue = "uibook_tags_out_of_sync"

    return {
        "hasAiAnalysis": has_analysis,
        "hasV2Mirror": has_v2_mirror,
        "mirrorSchemaVersion": schema_version,
        "hasUibookTags": has_uibook_tags,
        "uibookPreparationComplete": complete,
        "uibookPreparationIssue": None if complete else issue,
        "expectedUibookTags": expected_tags,
        "currentManagedUibookTags": current_managed_tags,
        "missingUibookTags": missing_tags,
        "staleUibookTags": stale_tags,
    }


def reject_nonfinite_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite number {value}")


def read_json_document(path_value: str, label: str) -> Any:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f"{label} file not found: {path}")
    try:
        return json.loads(
            path.read_text("utf-8"),
            parse_constant=reject_nonfinite_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"{label} file is not valid JSON: {path}: {exc}") from exc


def taxonomy_option_rows(payload: Any) -> list[dict[str, Any]]:
    candidate = payload
    if isinstance(payload, dict):
        for key in ("categories", "configOptions", "config_options", "options", "data"):
            value = payload.get(key)
            if isinstance(value, (list, dict)):
                candidate = value
                break

    rows: list[dict[str, Any]] = []
    if isinstance(candidate, list):
        for row in candidate:
            if isinstance(row, dict):
                rows.append(dict(row))
    elif isinstance(candidate, dict):
        for category, entries in candidate.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, str):
                    rows.append({"category": category, "value": entry})
                elif isinstance(entry, dict):
                    row = dict(entry)
                    row.setdefault("category", category)
                    rows.append(row)

    normalized = []
    for row in rows:
        category = str(row.get("category") or "").strip()
        value = str(row.get("value") or "").strip()
        if category not in PUBLIC_TAXONOMY_CATEGORIES or not value:
            continue
        normalized.append(
            {
                "category": category,
                "value": value,
                "dimension": (
                    str(row.get("dimension") or "").strip()
                    if category == "style"
                    else ""
                ),
            }
        )
    if not normalized:
        raise RuntimeError(
            "Taxonomy file has no usable public UIBook config_options"
        )
    return normalized


def taxonomy_content_hash(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    categories = payload.get("categories")
    if not isinstance(categories, dict):
        return None
    canonical = {
        "schemaVersion": payload.get("schemaVersion", 1),
        "categories": categories,
    }
    serialized = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(serialized).hexdigest()}"


def taxonomy_rows_hash(rows: list[dict[str, Any]]) -> str:
    canonical_rows = sorted(
        {
            (
                str(row["category"]),
                str(row["value"]),
                str(row.get("dimension") or ""),
            )
            for row in rows
        }
    )
    serialized = json.dumps(
        canonical_rows,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(serialized).hexdigest()}"


def get_taxonomy_snapshot(payload: Any, rows: list[dict[str, Any]]) -> str:
    computed = taxonomy_content_hash(payload) or taxonomy_rows_hash(rows)
    if isinstance(payload, dict):
        for key in ("taxonomySnapshot", "snapshotHash", "snapshot", "version"):
            value = str(payload.get(key) or "").strip()
            if value:
                if value != computed:
                    raise RuntimeError(
                        "Taxonomy snapshot hash does not match taxonomy contents "
                        f"({value!r} != {computed!r})"
                    )
                return value

    return computed


def validate_tag_component(value: str, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise RuntimeError(f"{field} must not be empty")
    if any(character in text for character in ("\r", "\n", ":")):
        raise RuntimeError(f"{field} contains a reserved tag character: {text!r}")
    return text


def build_taxonomy_lookups(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str], dict[tuple[str, str], tuple[str, str]]]:
    pages: dict[str, str] = {}
    sections: dict[str, str] = {}
    styles: dict[tuple[str, str], tuple[str, str]] = {}

    for row in rows:
        category = str(row["category"])
        value = validate_tag_component(str(row["value"]), f"{category}.value")
        value_key = value.casefold()
        if category == "page_type":
            pages.setdefault(value_key, value)
            continue
        if category == "section_type":
            sections.setdefault(value_key, value)
            continue
        if category != "style":
            continue

        dimension = validate_tag_component(
            str(row.get("dimension") or ""),
            "style.dimension",
        )
        key = (dimension.casefold(), value_key)
        existing = styles.get(key)
        canonical = (dimension, value)
        if existing and existing != canonical:
            raise RuntimeError(
                f"Conflicting style taxonomy entries for {dimension}/{value}"
            )
        styles[key] = canonical

    return pages, sections, styles


def build_category_taxonomy_lookups(
    rows: list[dict[str, Any]],
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, tuple[str, str]],
]:
    category_lookups: dict[str, dict[str, str]] = {
        category: {}
        for category in PUBLIC_TAXONOMY_CATEGORIES
    }
    style_by_value: dict[str, tuple[str, str]] = {}

    for row in rows:
        category = str(row["category"])
        value = validate_tag_component(
            str(row["value"]),
            f"{category}.value",
        )
        value_key = value.casefold()
        existing = category_lookups[category].get(value_key)
        if existing and existing != value:
            raise RuntimeError(
                f"Conflicting {category} taxonomy entries for {value!r}"
            )
        category_lookups[category][value_key] = value
        if category != "style":
            continue

        dimension = validate_tag_component(
            str(row.get("dimension") or ""),
            "style.dimension",
        )
        canonical_style = (dimension, value)
        existing_style = style_by_value.get(value_key)
        if existing_style and existing_style != canonical_style:
            raise RuntimeError(
                f"Style value {value!r} maps to multiple dimensions"
            )
        style_by_value[value_key] = canonical_style

    missing = [
        category
        for category, lookup in category_lookups.items()
        if not lookup
    ]
    if missing:
        raise RuntimeError(
            "Taxonomy snapshot is missing required public categories: "
            + ", ".join(missing)
        )
    return category_lookups, style_by_value


def mirror_string_list(
    classification: dict[str, Any],
    field: str,
) -> list[str]:
    value = classification.get(field, [])
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RuntimeError(f"classification.{field} must be an array of strings")
    return [item.strip() for item in value if item.strip()]


def canonical_taxonomy_value(
    lookup: dict[str, str],
    value: str,
    field: str,
) -> str:
    canonical = lookup.get(value.casefold())
    if canonical is None:
        raise RuntimeError(
            f"{field} is not present in the supplied UIBook taxonomy: {value!r}"
        )
    return canonical


def require_taggable_confidence(value: Any, field: str) -> str:
    confidence = str(value or "").strip().casefold()
    if confidence not in {"high", "medium"}:
        raise RuntimeError(
            f"{field} must be 'high' or 'medium' to create an official tag"
        )
    return confidence


def validate_mirror_v1_payload(
    mirror: Any,
    taxonomy: Any,
) -> dict[str, Any]:
    if not isinstance(mirror, dict):
        raise RuntimeError("Mirror file root must be a JSON object")

    rows = taxonomy_option_rows(taxonomy)
    taxonomy_snapshot = get_taxonomy_snapshot(taxonomy, rows)
    mirror_snapshot = str(mirror.get("taxonomySnapshot") or "").strip()
    if not mirror_snapshot:
        raise RuntimeError("mirror.taxonomySnapshot is required")
    if mirror_snapshot != taxonomy_snapshot:
        raise RuntimeError(
            "Mirror taxonomySnapshot does not match the supplied taxonomy file "
            f"({mirror_snapshot!r} != {taxonomy_snapshot!r})"
        )

    entity_type = str(mirror.get("entityType") or "").strip()
    if entity_type not in MIRROR_ENTITY_TYPES:
        raise RuntimeError(
            "mirror.entityType must be exactly 'website' or 'section'"
        )
    source_item_id = str(mirror.get("sourceItemId") or "").strip()
    if not source_item_id:
        raise RuntimeError("mirror.sourceItemId is required")
    image_fingerprint = str(mirror.get("imageFingerprint") or "").strip()
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", image_fingerprint):
        raise RuntimeError(
            "mirror.imageFingerprint must use sha256:<64 hexadecimal characters>"
        )

    ui_context = mirror.get("uiContext")
    if not isinstance(ui_context, str) or not ui_context.strip():
        raise RuntimeError("mirror.uiContext must be a non-empty string")
    content_map = mirror.get("contentMap")
    if not isinstance(content_map, list):
        raise RuntimeError("mirror.contentMap must be an array")
    confidence = mirror.get("confidence")
    if not isinstance(confidence, dict):
        raise RuntimeError("mirror.confidence must be an object")
    evidence = mirror.get("evidence")
    if not isinstance(evidence, dict):
        raise RuntimeError("mirror.evidence must be an object")
    unmapped = mirror.get("unmapped")
    if not isinstance(unmapped, list):
        raise RuntimeError("mirror.unmapped must be an array")

    classification = mirror.get("classification")
    if not isinstance(classification, dict):
        raise RuntimeError("mirror.classification must be an object")

    page_type_value = classification.get("pageType")
    if page_type_value is not None and not isinstance(page_type_value, str):
        raise RuntimeError("classification.pageType must be a string or null")
    page_type = str(page_type_value or "").strip()
    section_types = mirror_string_list(classification, "sectionTypes")
    contained_section_types = mirror_string_list(
        classification,
        "containedSectionTypes",
    )
    styles_value = classification.get("styles", [])
    if not isinstance(styles_value, list):
        raise RuntimeError("classification.styles must be an array")

    if entity_type == "website" and section_types:
        raise RuntimeError(
            "Website mirrors must use containedSectionTypes, not sectionTypes"
        )
    if entity_type == "section" and (page_type or contained_section_types):
        raise RuntimeError(
            "Section mirrors cannot set pageType or containedSectionTypes"
        )
    if entity_type == "website" and not page_type:
        raise RuntimeError("Website mirrors require classification.pageType")
    if entity_type == "section" and not section_types:
        raise RuntimeError(
            "Section mirrors require at least one classification.sectionTypes value"
        )
    if len(section_types) > 2:
        raise RuntimeError("classification.sectionTypes may contain at most 2 values")
    style_limit = 6 if entity_type == "website" else 4
    if len(styles_value) > style_limit:
        raise RuntimeError(
            f"{entity_type} mirrors may contain at most {style_limit} styles"
        )
    if entity_type == "website":
        require_taggable_confidence(
            confidence.get("pageType"),
            "confidence.pageType",
        )
        if contained_section_types:
            require_taggable_confidence(
                confidence.get("containedSectionTypes"),
                "confidence.containedSectionTypes",
            )
    else:
        require_taggable_confidence(
            confidence.get("sectionTypes"),
            "confidence.sectionTypes",
        )

    pages, sections, styles = build_taxonomy_lookups(rows)
    desired_tags: set[str] = set()
    normalized_page_type: str | None = None
    normalized_section_types: list[str] = []
    normalized_contained_section_types: list[str] = []
    normalized_styles: list[dict[str, str]] = []

    if page_type:
        normalized_page_type = canonical_taxonomy_value(
            pages,
            page_type,
            "classification.pageType",
        )
        desired_tags.add(f"uibook:page:{normalized_page_type}")

    for value in section_types:
        canonical = canonical_taxonomy_value(
            sections,
            value,
            "classification.sectionTypes",
        )
        normalized_section_types.append(canonical)
        desired_tags.add(f"uibook:section:{canonical}")

    for value in contained_section_types:
        canonical = canonical_taxonomy_value(
            sections,
            value,
            "classification.containedSectionTypes",
        )
        normalized_contained_section_types.append(canonical)
        desired_tags.add(f"uibook:contains-section:{canonical}")

    for index, style in enumerate(styles_value):
        if not isinstance(style, dict):
            raise RuntimeError(
                f"classification.styles[{index}] must be an object"
            )
        dimension = str(style.get("dimension") or "").strip()
        value = str(style.get("value") or "").strip()
        if not dimension or not value:
            raise RuntimeError(
                f"classification.styles[{index}] needs dimension and value"
            )
        require_taggable_confidence(
            style.get("confidence"),
            f"classification.styles[{index}].confidence",
        )
        canonical = styles.get((dimension.casefold(), value.casefold()))
        if canonical is None:
            raise RuntimeError(
                "classification.styles"
                f"[{index}] is not present in the supplied UIBook taxonomy: "
                f"{dimension!r}/{value!r}"
            )
        canonical_dimension, canonical_value = canonical
        normalized_styles.append(
            {
                "dimension": canonical_dimension,
                "value": canonical_value,
            }
        )
        desired_tags.add(
            f"uibook:style:{canonical_dimension}:{canonical_value}"
        )

    normalized_classification = {
        "pageType": normalized_page_type,
        "sectionTypes": sorted(set(normalized_section_types)),
        "containedSectionTypes": sorted(
            set(normalized_contained_section_types)
        ),
        "styles": [
            {"dimension": dimension, "value": value}
            for dimension, value in sorted(
                {
                    (style["dimension"], style["value"])
                    for style in normalized_styles
                }
            )
        ],
    }
    desired_by_category = {
        "pageType": (
            [f"uibook:page:{normalized_page_type}"]
            if normalized_page_type
            else []
        ),
        "sectionTypes": [
            f"uibook:section:{value}"
            for value in normalized_classification["sectionTypes"]
        ],
        "containedSectionTypes": [
            f"uibook:contains-section:{value}"
            for value in normalized_classification["containedSectionTypes"]
        ],
        "styles": [
            f"uibook:style:{style['dimension']}:{style['value']}"
            for style in normalized_classification["styles"]
        ],
    }
    mirror_data = {
        "schemaVersion": UIBOOK_SCHEMA_V1,
        "taxonomySnapshot": taxonomy_snapshot,
        "sourceItemId": source_item_id,
        "imageFingerprint": image_fingerprint,
        "entityType": entity_type,
        "uiContext": ui_context.strip(),
        "contentMap": content_map,
        "classification": normalized_classification,
        "confidence": confidence,
        "evidence": evidence,
        "unmapped": unmapped,
        "managedPrefixes": list(V1_MANAGED_UIBOOK_TAG_PREFIXES),
        "desiredByCategory": desired_by_category,
        "suppressedColorTags": [],
        "managedTags": sorted(desired_tags),
    }

    return {
        "schemaVersion": UIBOOK_SCHEMA_V1,
        "taxonomySnapshot": taxonomy_snapshot,
        "sourceItemId": source_item_id,
        "imageFingerprint": image_fingerprint,
        "entityType": entity_type,
        "desiredTags": sorted(desired_tags),
        "managedPrefixes": list(V1_MANAGED_UIBOOK_TAG_PREFIXES),
        "desiredByCategory": desired_by_category,
        "suppressedColorTags": [],
        "unmapped": unmapped,
        "normalizedClassification": normalized_classification,
        "mirrorData": mirror_data,
    }


def require_exact_object_keys(
    value: Any,
    expected_keys: set[str],
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{field} must be an object")
    actual_keys = set(value)
    missing = sorted(expected_keys - actual_keys)
    unexpected = sorted(actual_keys - expected_keys)
    if missing or unexpected:
        raise RuntimeError(
            f"{field} keys do not match schema v2: "
            f"missing={missing}, unexpected={unexpected}"
        )
    return value


def require_required_object_keys(
    value: Any,
    required_keys: set[str],
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{field} must be an object")
    missing = sorted(required_keys - set(value))
    if missing:
        raise RuntimeError(
            f"{field} is missing required schema v2 keys: {missing}"
        )
    return value


def require_unique_string_list(
    value: Any,
    field: str,
) -> list[str]:
    if not isinstance(value, list):
        raise RuntimeError(f"{field} must be an array of strings")
    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise RuntimeError(
                f"{field}[{index}] must be a non-empty string"
            )
        text = item.strip()
        key = text.casefold()
        if key in seen:
            raise RuntimeError(f"{field} contains duplicate value {text!r}")
        seen.add(key)
        normalized.append(text)
    return normalized


def require_evidence_list(
    value: Any,
    field: str,
    *,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        raise RuntimeError(f"{field} must be an array of evidence strings")
    evidence = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise RuntimeError(
                f"{field}[{index}] must be a non-empty evidence string"
            )
        evidence.append(item.strip())
    if not evidence and not allow_empty:
        raise RuntimeError(f"{field} must contain at least one evidence string")
    return evidence


def canonicalize_category_values(
    values: list[str],
    lookup: dict[str, str],
    field: str,
) -> list[str]:
    return [
        canonical_taxonomy_value(lookup, value, field)
        for value in values
    ]


def validate_v2_value_metadata(
    field: str,
    canonical_keys: list[str],
    confidence: dict[str, Any],
    evidence: dict[str, Any],
) -> tuple[dict[str, str], dict[str, list[str]]]:
    confidence_map = require_exact_object_keys(
        confidence.get(field),
        set(canonical_keys),
        f"confidence.{field}",
    )
    evidence_map = require_exact_object_keys(
        evidence.get(field),
        set(canonical_keys),
        f"evidence.{field}",
    )
    normalized_confidence: dict[str, str] = {}
    normalized_evidence: dict[str, list[str]] = {}
    for key in canonical_keys:
        try:
            normalized_confidence[key] = require_taggable_confidence(
                confidence_map[key],
                f"confidence.{field}[{key!r}]",
            )
        except RuntimeError as exc:
            raise RuntimeError(
                f"{exc}; low-confidence values belong only in unmapped"
            ) from exc
        normalized_evidence[key] = require_evidence_list(
            evidence_map[key],
            f"evidence.{field}[{key!r}]",
        )
    return normalized_confidence, normalized_evidence


def validate_v2_unmapped(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise RuntimeError("mirror.unmapped must be an array")
    normalized = []
    required = {"category", "term", "confidence", "reason", "evidence"}
    for index, entry in enumerate(value):
        item = require_exact_object_keys(
            entry,
            required,
            f"unmapped[{index}]",
        )
        category = str(item.get("category") or "").strip()
        if not category:
            raise RuntimeError(f"unmapped[{index}].category is required")
        term = str(item.get("term") or "").strip()
        if not term:
            raise RuntimeError(f"unmapped[{index}].term is required")
        confidence = str(item.get("confidence") or "").strip().casefold()
        if confidence != "low":
            raise RuntimeError(
                f"unmapped[{index}].confidence must be exactly 'low'"
            )
        reason = str(item.get("reason") or "").strip()
        if not reason:
            raise RuntimeError(f"unmapped[{index}].reason is required")
        entry_evidence = require_evidence_list(
            item.get("evidence"),
            f"unmapped[{index}].evidence",
            allow_empty=True,
        )
        normalized.append(
            {
                "category": category,
                "term": term,
                "confidence": "low",
                "reason": reason,
                "evidence": entry_evidence,
            }
        )
    return normalized


def validate_mirror_v2_payload(
    mirror: Any,
    taxonomy: Any,
) -> dict[str, Any]:
    if not isinstance(mirror, dict):
        raise RuntimeError("Mirror file root must be a JSON object")

    rows = taxonomy_option_rows(taxonomy)
    taxonomy_snapshot = get_taxonomy_snapshot(taxonomy, rows)
    category_lookups, style_by_value = build_category_taxonomy_lookups(rows)
    mirror_snapshot = str(mirror.get("taxonomySnapshot") or "").strip()
    if not mirror_snapshot:
        raise RuntimeError("mirror.taxonomySnapshot is required")
    if mirror_snapshot != taxonomy_snapshot:
        raise RuntimeError(
            "Mirror taxonomySnapshot does not match the supplied taxonomy file "
            f"({mirror_snapshot!r} != {taxonomy_snapshot!r})"
        )

    source_item_id = str(mirror.get("sourceItemId") or "").strip()
    if not source_item_id:
        raise RuntimeError("mirror.sourceItemId is required")
    image_fingerprint = str(mirror.get("imageFingerprint") or "").strip()
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", image_fingerprint):
        raise RuntimeError(
            "mirror.imageFingerprint must use sha256:<64 hexadecimal characters>"
        )
    entity_type = str(mirror.get("entityType") or "").strip()
    if entity_type not in MIRROR_ENTITY_TYPES:
        raise RuntimeError(
            "mirror.entityType must be exactly 'website' or 'section'"
        )
    ui_context = mirror.get("uiContext")
    if not isinstance(ui_context, str) or not ui_context.strip():
        raise RuntimeError("mirror.uiContext must be a non-empty string")
    content_map = mirror.get("contentMap")
    if not isinstance(content_map, list) or not content_map:
        raise RuntimeError("mirror.contentMap must be a non-empty array")

    classification = require_exact_object_keys(
        mirror.get("classification"),
        set(V2_CLASSIFICATION_FIELDS),
        "mirror.classification",
    )
    confidence_fields = {
        "contentCoverage",
        "pageType",
        *V2_MAPPED_LIST_FIELDS,
    }
    confidence = require_exact_object_keys(
        mirror.get("confidence"),
        confidence_fields,
        "mirror.confidence",
    )
    evidence_fields = {
        "pageType",
        *V2_MAPPED_LIST_FIELDS,
    }
    evidence = require_required_object_keys(
        mirror.get("evidence"),
        evidence_fields,
        "mirror.evidence",
    )
    content_coverage_confidence = require_taggable_confidence(
        confidence.get("contentCoverage"),
        "confidence.contentCoverage",
    )
    unmapped = validate_v2_unmapped(mirror.get("unmapped"))

    page_type_value = classification["pageType"]
    if page_type_value is not None and (
        not isinstance(page_type_value, str) or not page_type_value.strip()
    ):
        raise RuntimeError(
            "classification.pageType must be a non-empty string or null"
        )
    page_type = str(page_type_value or "").strip()
    raw_values = {
        field: require_unique_string_list(
            classification[field],
            f"classification.{field}",
        )
        for field in (
            "sectionTypes",
            "containedSectionTypes",
            "industries",
            "layouts",
            "elements",
            "colors",
            "typography",
        )
    }

    raw_styles = classification["styles"]
    if not isinstance(raw_styles, list):
        raise RuntimeError("classification.styles must be an array")
    normalized_styles: list[dict[str, str]] = []
    style_keys_seen: set[str] = set()
    for index, style in enumerate(raw_styles):
        item = require_exact_object_keys(
            style,
            {"dimension", "value"},
            f"classification.styles[{index}]",
        )
        dimension = str(item.get("dimension") or "").strip()
        value = str(item.get("value") or "").strip()
        if not dimension or not value:
            raise RuntimeError(
                f"classification.styles[{index}] needs dimension and value"
            )
        canonical = style_by_value.get(value.casefold())
        if canonical is None:
            raise RuntimeError(
                "classification.styles"
                f"[{index}] is not present in the style taxonomy: {value!r}"
            )
        canonical_dimension, canonical_value = canonical
        if dimension.casefold() != canonical_dimension.casefold():
            raise RuntimeError(
                "classification.styles"
                f"[{index}].dimension does not match taxonomy "
                f"({dimension!r} != {canonical_dimension!r})"
            )
        style_key = f"{canonical_dimension}:{canonical_value}"
        if style_key.casefold() in style_keys_seen:
            raise RuntimeError(
                f"classification.styles contains duplicate {style_key!r}"
            )
        style_keys_seen.add(style_key.casefold())
        normalized_styles.append(
            {
                "dimension": canonical_dimension,
                "value": canonical_value,
            }
        )

    if entity_type == "website":
        if not page_type:
            raise RuntimeError(
                "Website schema v2 mirrors require classification.pageType"
            )
        if raw_values["sectionTypes"]:
            raise RuntimeError(
                "Website schema v2 mirrors require sectionTypes=[]"
            )
        if raw_values["layouts"]:
            raise RuntimeError(
                "Website schema v2 mirrors require layouts=[]"
            )
    else:
        if page_type:
            raise RuntimeError(
                "Section schema v2 mirrors require pageType=null"
            )
        if raw_values["containedSectionTypes"]:
            raise RuntimeError(
                "Section schema v2 mirrors require containedSectionTypes=[]"
            )
        if not raw_values["sectionTypes"]:
            raise RuntimeError(
                "Section schema v2 mirrors require 1-2 sectionTypes"
            )

    if len(raw_values["sectionTypes"]) > MAX_SECTION_TYPES:
        raise RuntimeError(
            f"classification.sectionTypes may contain at most {MAX_SECTION_TYPES} values"
        )
    if len(raw_values["containedSectionTypes"]) > len(
        category_lookups["section_type"]
    ):
        raise RuntimeError(
            "classification.containedSectionTypes exceeds the section_type taxonomy"
        )
    caps = {
        "industries": MAX_INDUSTRIES,
        "layouts": MAX_LAYOUTS,
        "elements": MAX_ELEMENTS,
        "colors": MAX_COLORS,
        "typography": MAX_TYPOGRAPHY,
    }
    for field, cap in caps.items():
        if len(raw_values[field]) > cap:
            raise RuntimeError(
                f"classification.{field} may contain at most {cap} values"
            )
    style_limit = (
        MAX_WEBSITE_STYLES
        if entity_type == "website"
        else MAX_SECTION_STYLES
    )
    if len(normalized_styles) > style_limit:
        raise RuntimeError(
            f"{entity_type} mirrors may contain at most {style_limit} styles"
        )

    normalized_page_type = (
        canonical_taxonomy_value(
            category_lookups["page_type"],
            page_type,
            "classification.pageType",
        )
        if page_type
        else None
    )
    normalized_classification: dict[str, Any] = {
        "pageType": normalized_page_type,
        "sectionTypes": canonicalize_category_values(
            raw_values["sectionTypes"],
            category_lookups["section_type"],
            "classification.sectionTypes",
        ),
        "containedSectionTypes": canonicalize_category_values(
            raw_values["containedSectionTypes"],
            category_lookups["section_type"],
            "classification.containedSectionTypes",
        ),
        "industries": canonicalize_category_values(
            raw_values["industries"],
            category_lookups["industry"],
            "classification.industries",
        ),
        "layouts": canonicalize_category_values(
            raw_values["layouts"],
            category_lookups["layout"],
            "classification.layouts",
        ),
        "elements": canonicalize_category_values(
            raw_values["elements"],
            category_lookups["elements"],
            "classification.elements",
        ),
        "styles": normalized_styles,
        "colors": canonicalize_category_values(
            raw_values["colors"],
            category_lookups["colors"],
            "classification.colors",
        ),
        "typography": canonicalize_category_values(
            raw_values["typography"],
            category_lookups["typography"],
            "classification.typography",
        ),
    }

    if normalized_page_type:
        normalized_page_confidence = require_taggable_confidence(
            confidence.get("pageType"),
            "confidence.pageType",
        )
        normalized_page_evidence = require_evidence_list(
            evidence.get("pageType"),
            "evidence.pageType",
        )
    else:
        if confidence.get("pageType") is not None:
            raise RuntimeError(
                "confidence.pageType must be null when pageType is null"
            )
        normalized_page_confidence = None
        normalized_page_evidence = require_evidence_list(
            evidence.get("pageType"),
            "evidence.pageType",
            allow_empty=True,
        )
        if normalized_page_evidence:
            raise RuntimeError(
                "evidence.pageType must be [] when pageType is null"
            )

    metadata_keys = {
        "sectionTypes": normalized_classification["sectionTypes"],
        "containedSectionTypes": normalized_classification[
            "containedSectionTypes"
        ],
        "industries": normalized_classification["industries"],
        "layouts": normalized_classification["layouts"],
        "elements": normalized_classification["elements"],
        "styles": [
            f"{style['dimension']}:{style['value']}"
            for style in normalized_styles
        ],
        "colors": normalized_classification["colors"],
        "typography": normalized_classification["typography"],
    }
    normalized_confidence: dict[str, Any] = {
        "contentCoverage": content_coverage_confidence,
        "pageType": normalized_page_confidence,
    }
    normalized_evidence: dict[str, Any] = {
        key: value
        for key, value in evidence.items()
        if key not in evidence_fields
    }
    normalized_evidence.update({
        "pageType": normalized_page_evidence,
    })
    for field, keys in metadata_keys.items():
        field_confidence, field_evidence = validate_v2_value_metadata(
            field,
            keys,
            confidence,
            evidence,
        )
        normalized_confidence[field] = field_confidence
        normalized_evidence[field] = field_evidence

    raw_color_weights = require_exact_object_keys(
        mirror.get("colorWeights"),
        set(normalized_classification["colors"]),
        "mirror.colorWeights",
    )
    normalized_color_weights: dict[str, float | int] = {}
    for color in normalized_classification["colors"]:
        percentage = raw_color_weights[color]
        if isinstance(percentage, bool) or not isinstance(
            percentage,
            (int, float),
        ):
            raise RuntimeError(
                f"colorWeights[{color!r}] must be a number"
            )
        numeric_percentage = float(percentage)
        if (
            not math.isfinite(numeric_percentage)
            or numeric_percentage < MIN_COLOR_MIRROR_PERCENTAGE
            or numeric_percentage > 100
        ):
            raise RuntimeError(
                f"colorWeights[{color!r}] must be between "
                f"{MIN_COLOR_MIRROR_PERCENTAGE:g} and 100"
            )
        normalized_color_weights[color] = (
            int(numeric_percentage)
            if numeric_percentage.is_integer()
            else numeric_percentage
        )

    ordered_colors = sorted(
        normalized_classification["colors"],
        key=lambda color: (
            -float(normalized_color_weights[color]),
            color,
        ),
    )
    normalized_classification["colors"] = ordered_colors
    normalized_color_weights = {
        color: normalized_color_weights[color]
        for color in ordered_colors
    }

    desired_by_category: dict[str, list[str]] = {
        field: []
        for field in V2_CLASSIFICATION_FIELDS
    }
    if normalized_page_type:
        desired_by_category["pageType"] = [
            f"uibook:page:{normalized_page_type}"
        ]
    desired_by_category["sectionTypes"] = [
        f"uibook:section:{value}"
        for value in normalized_classification["sectionTypes"]
    ]
    desired_by_category["containedSectionTypes"] = [
        f"uibook:contains-section:{value}"
        for value in normalized_classification["containedSectionTypes"]
    ]
    desired_by_category["industries"] = [
        f"uibook:industry:{value}"
        for value in normalized_classification["industries"]
    ]
    desired_by_category["layouts"] = [
        f"uibook:layout:{value}"
        for value in normalized_classification["layouts"]
    ]
    desired_by_category["elements"] = [
        f"uibook:elements:{value}"
        for value in normalized_classification["elements"]
    ]
    desired_by_category["styles"] = [
        f"uibook:style:{style['dimension']}:{style['value']}"
        for style in normalized_styles
    ]
    desired_by_category["typography"] = [
        f"uibook:typography:{value}"
        for value in normalized_classification["typography"]
    ]

    suppressed_color_tags = []
    for color in ordered_colors:
        tag = f"uibook:colors:{color}"
        percentage = float(normalized_color_weights[color])
        threshold = (
            MIN_NEUTRAL_COLOR_TAG_PERCENTAGE
            if color.casefold() in NEUTRAL_COLOR_VALUES
            else MIN_CHROMATIC_COLOR_TAG_PERCENTAGE
        )
        if percentage >= threshold:
            desired_by_category["colors"].append(tag)
        else:
            suppressed_color_tags.append(tag)

    desired_tags = sorted(
        {
            tag
            for tags in desired_by_category.values()
            for tag in tags
        }
    )
    mirror_data = {
        "schemaVersion": UIBOOK_SCHEMA_V2,
        "taxonomySnapshot": taxonomy_snapshot,
        "sourceItemId": source_item_id,
        "imageFingerprint": image_fingerprint,
        "entityType": entity_type,
        "uiContext": ui_context.strip(),
        "contentMap": content_map,
        "classification": normalized_classification,
        "colorWeights": normalized_color_weights,
        "confidence": normalized_confidence,
        "evidence": normalized_evidence,
        "unmapped": unmapped,
    }
    return {
        "schemaVersion": UIBOOK_SCHEMA_V2,
        "taxonomySnapshot": taxonomy_snapshot,
        "sourceItemId": source_item_id,
        "imageFingerprint": image_fingerprint,
        "entityType": entity_type,
        "desiredTags": desired_tags,
        "managedPrefixes": list(V2_MANAGED_UIBOOK_TAG_PREFIXES),
        "desiredByCategory": desired_by_category,
        "suppressedColorTags": suppressed_color_tags,
        "unmapped": unmapped,
        "normalizedClassification": normalized_classification,
        "mirrorData": mirror_data,
    }


def validate_mirror_payload(
    mirror: Any,
    taxonomy: Any,
) -> dict[str, Any]:
    if not isinstance(mirror, dict):
        raise RuntimeError("Mirror file root must be a JSON object")
    raw_schema_version = mirror.get("schemaVersion", UIBOOK_SCHEMA_V1)
    if isinstance(raw_schema_version, bool) or not isinstance(
        raw_schema_version,
        int,
    ):
        raise RuntimeError("mirror.schemaVersion must be integer 1 or 2")
    if raw_schema_version == UIBOOK_SCHEMA_V1:
        return validate_mirror_v1_payload(mirror, taxonomy)
    if raw_schema_version == UIBOOK_SCHEMA_V2:
        return validate_mirror_v2_payload(mirror, taxonomy)
    raise RuntimeError("mirror.schemaVersion must be integer 1 or 2")


def attach_mirror_data(block: str, mirror_data: dict[str, Any]) -> str:
    text = str(block or "").strip()
    section_pattern = re.compile(
        rf"\n*{re.escape(MIRROR_DATA_HEADING)}\n+\s*```json\n.*?\n```\n*",
        re.DOTALL,
    )
    text = re.sub(section_pattern, "\n", text).strip()
    machine_section = (
        f"{MIRROR_DATA_HEADING}\n\n"
        "```json\n"
        f"{json.dumps(mirror_data, ensure_ascii=False, separators=(',', ':'))}\n"
        "```"
    )
    if BLOCK_END in text:
        return text.replace(
            BLOCK_END,
            f"{machine_section}\n{BLOCK_END}",
            1,
        )
    return f"{text}\n\n{machine_section}".strip()


def item_tag_names(item: dict[str, Any]) -> list[str]:
    tags = item.get("tags")
    if not isinstance(tags, list):
        return []
    names = []
    seen = set()
    for tag in tags:
        if isinstance(tag, str):
            name = tag.strip()
        elif isinstance(tag, dict):
            name = str(tag.get("name") or "").strip()
        else:
            name = ""
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def is_managed_uibook_tag(
    tag: str,
    managed_prefixes: list[str] | tuple[str, ...],
) -> bool:
    return any(tag.startswith(prefix) for prefix in managed_prefixes)


def ensure_schema_tag_compatibility(
    schema_version: int,
    current_tags: list[str],
) -> None:
    if schema_version != UIBOOK_SCHEMA_V1:
        return
    v2_only_tags = sorted(
        tag
        for tag in current_tags
        if is_managed_uibook_tag(
            tag,
            V2_ONLY_UIBOOK_TAG_PREFIXES,
        )
    )
    if v2_only_tags:
        raise RuntimeError(
            "Schema v1 refuses to run because the Eagle item already has "
            f"schema v2-only managed tags: {v2_only_tags}"
        )


def build_uibook_tag_diff(
    current_tags: list[str],
    desired_tags: list[str],
    managed_prefixes: list[str] | tuple[str, ...],
) -> dict[str, list[str]]:
    current = list(dict.fromkeys(tag for tag in current_tags if tag))
    desired = sorted(set(desired_tags))
    current_set = set(current)
    desired_set = set(desired)
    to_add = sorted(desired_set - current_set)
    to_remove = sorted(
        tag
        for tag in current
        if is_managed_uibook_tag(tag, managed_prefixes)
        and tag not in desired_set
    )
    to_remove_set = set(to_remove)
    preserved = [tag for tag in current if tag not in to_remove_set]
    return {
        "desired": desired,
        "toAdd": to_add,
        "toRemove": to_remove,
        "preserved": preserved,
    }


def add_item_tags(
    client: MCPClient,
    item_id: str,
    tags: list[str],
) -> None:
    if not tags:
        return
    current = get_item_by_id(client, item_id)
    combined = list(
        dict.fromkeys(
            [
                *item_tag_names(current),
                *tags,
            ]
        )
    )
    client.update_item_fields(item_id, {"tags": combined})


def remove_item_tags(
    client: MCPClient,
    item_id: str,
    tags: list[str],
) -> None:
    if not tags:
        return
    removed = set(tags)
    current = get_item_by_id(client, item_id)
    remaining = [
        tag
        for tag in item_tag_names(current)
        if tag not in removed
    ]
    client.update_item_fields(item_id, {"tags": remaining})


def verify_managed_uibook_tags(
    item: dict[str, Any],
    desired_tags: list[str],
    managed_prefixes: list[str] | tuple[str, ...],
) -> None:
    actual_tags = set(item_tag_names(item))
    desired_set = set(desired_tags)
    missing = sorted(desired_set - actual_tags)
    stale = sorted(
        tag
        for tag in actual_tags
        if is_managed_uibook_tag(tag, managed_prefixes)
        and tag not in desired_set
    )
    if missing or stale:
        raise RuntimeError(
            "Eagle tag verification failed: "
            f"missing={missing}, stale={stale}"
        )


def verify_desired_uibook_tags(
    item: dict[str, Any],
    desired_tags: list[str],
) -> None:
    actual_tags = set(item_tag_names(item))
    missing = sorted(set(desired_tags) - actual_tags)
    if missing:
        raise RuntimeError(
            f"Eagle tag-add verification failed before removal: missing={missing}"
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def verify_mirror_item_binding(
    item: dict[str, Any],
    item_id: str,
    mirror_result: dict[str, Any],
) -> None:
    source_item_id = str(mirror_result["sourceItemId"])
    if source_item_id != item_id:
        raise RuntimeError(
            "Mirror sourceItemId does not match --item-id "
            f"({source_item_id!r} != {item_id!r})"
        )
    actual_item_id = str(item.get("id") or "").strip()
    if actual_item_id and actual_item_id != item_id:
        raise RuntimeError(
            "Eagle item response id does not match --item-id "
            f"({actual_item_id!r} != {item_id!r})"
        )
    file_path = Path(str(item.get("filePath") or "")).expanduser()
    if not file_path.is_file():
        raise RuntimeError(
            f"Cannot verify mirror image fingerprint; file missing: {file_path}"
        )
    actual_fingerprint = sha256_file(file_path)
    expected_fingerprint = str(mirror_result["imageFingerprint"])
    if actual_fingerprint.casefold() != expected_fingerprint.casefold():
        raise RuntimeError(
            "Mirror imageFingerprint does not match the current Eagle image "
            f"({expected_fingerprint!r} != {actual_fingerprint!r})"
        )


def reconcile_managed_uibook_tags(
    client: MCPClient,
    item_id: str,
    desired_tags: list[str],
    to_add: list[str],
    to_remove: list[str],
    managed_prefixes: list[str] | tuple[str, ...],
) -> None:
    add_item_tags(client, item_id, to_add)
    after_add = get_item_by_id(client, item_id)
    verify_desired_uibook_tags(after_add, desired_tags)

    remove_item_tags(client, item_id, to_remove)
    after_remove = get_item_by_id(client, item_id)
    verify_managed_uibook_tags(
        after_remove,
        desired_tags,
        managed_prefixes,
    )


def normalize_annotation_for_verification(value: Any) -> str:
    text = str(value or "")
    text = text.replace(BLOCK_START, "").replace(BLOCK_END, "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def update_annotation(client: MCPClient, item_id: str, annotation: str) -> None:
    client.update_item_fields(
        item_id,
        {"annotation": annotation},
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
    preparation = inspect_uibook_preparation(item)
    if not preparation["hasAiAnalysis"]:
        analysis_action = "write_analysis"
    elif not preparation["hasV2Mirror"]:
        analysis_action = "upgrade_to_v2"
    elif not preparation["hasUibookTags"]:
        analysis_action = "repair_uibook_tags"
    else:
        analysis_action = "none"
    analysis_action_needed = not preparation["uibookPreparationComplete"]
    candidate_complete = (
        preparation["uibookPreparationComplete"]
        and not folder_action_needed
    )
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
        **preparation,
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


def cmd_self_test(_args: argparse.Namespace) -> int:
    def expect_runtime_error(
        callback: Any,
        expected_text: str,
    ) -> None:
        try:
            callback()
        except RuntimeError as exc:
            assert expected_text in str(exc), str(exc)
        else:
            raise AssertionError(
                f"Expected RuntimeError containing {expected_text!r}"
            )

    script_path = Path(__file__).resolve()
    fixture_directories = (
        script_path.parent / "fixtures",
        script_path.parent.parent / "fixtures",
    )

    def read_fixture(name: str) -> dict[str, Any]:
        for directory in fixture_directories:
            path = directory / name
            if path.is_file():
                payload = read_json_document(
                    str(path),
                    f"Self-test fixture {name}",
                )
                if not isinstance(payload, dict):
                    raise RuntimeError(
                        f"Self-test fixture {name} must be a JSON object"
                    )
                return payload
        searched = ", ".join(
            str(directory / name)
            for directory in fixture_directories
        )
        raise RuntimeError(
            f"Self-test fixture {name} not found; searched: {searched}"
        )

    taxonomy = {
        "schemaVersion": 1,
        "categories": {
            "page_type": [
                {"value": "Homepage", "dimension": None},
                {"value": "Pricing", "dimension": None},
            ],
            "section_type": [
                {"value": "Features", "dimension": None},
                {"value": "Testimonials", "dimension": None},
                {"value": "FAQ", "dimension": None},
            ],
            "industry": [
                {"value": "SaaS", "dimension": None},
                {"value": "Finance", "dimension": None},
                {"value": "Technology", "dimension": None},
                {"value": "Marketing", "dimension": None},
            ],
            "layout": [
                {"value": "Grid", "dimension": None},
                {"value": "Split", "dimension": None},
                {"value": "Centered", "dimension": None},
                {"value": "Bento", "dimension": None},
            ],
            "elements": [
                {"value": "Grid", "dimension": None},
                {"value": "Illustration", "dimension": None},
                {"value": "Card", "dimension": None},
            ],
            "style": [
                {"value": "Illustration", "dimension": "surface"},
                {"value": "Playful", "dimension": "mood"},
                {"value": "Minimal", "dimension": "generic"},
                {"value": "Bold", "dimension": "mood"},
                {"value": "Professional", "dimension": "generic"},
                {"value": "Animation", "dimension": "motion"},
                {"value": "Dark Mode", "dimension": "theme"},
            ],
            "colors": [
                {"value": "White", "dimension": None},
                {"value": "Black", "dimension": None},
                {"value": "Gray", "dimension": None},
                {"value": "Blue", "dimension": None},
                {"value": "Purple", "dimension": None},
                {"value": "Red", "dimension": None},
                {"value": "Green", "dimension": None},
                {"value": "Yellow", "dimension": None},
                {"value": "Orange", "dimension": None},
            ],
            "typography": [
                {"value": "Sans-serif", "dimension": None},
                {"value": "Serif", "dimension": None},
                {"value": "Monospace", "dimension": None},
            ],
        },
    }
    taxonomy["snapshotHash"] = taxonomy_content_hash(taxonomy)
    assert isinstance(taxonomy["snapshotHash"], str)
    fingerprint = (
        "sha256:"
        "e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855"
    )

    page_mirror = {
        "schemaVersion": UIBOOK_SCHEMA_V2,
        "taxonomySnapshot": taxonomy["snapshotHash"],
        "sourceItemId": "ITEM",
        "imageFingerprint": fingerprint,
        "entityType": "website",
        "uiContext": "A SaaS homepage with illustrated feature flows.",
        "contentMap": [
            {"region": "hero", "evidence": "Primary headline and CTA"},
            {"region": "features", "evidence": "Illustrated feature cards"},
        ],
        "classification": {
            "pageType": "Homepage",
            "sectionTypes": [],
            "containedSectionTypes": ["Features"],
            "industries": ["SaaS"],
            "layouts": [],
            "elements": ["Grid", "Illustration"],
            "styles": [
                {"dimension": "surface", "value": "Illustration"},
                {"dimension": "mood", "value": "Playful"},
            ],
            "colors": ["White", "Blue", "Purple"],
            "typography": ["Sans-serif"],
        },
        "colorWeights": {
            "White": 10,
            "Blue": 4,
            "Purple": 2,
        },
        "confidence": {
            "contentCoverage": "high",
            "pageType": "high",
            "sectionTypes": {},
            "containedSectionTypes": {"Features": "high"},
            "industries": {"SaaS": "high"},
            "layouts": {},
            "elements": {
                "Grid": "medium",
                "Illustration": "high",
            },
            "styles": {
                "surface:Illustration": "high",
                "mood:Playful": "medium",
            },
            "colors": {
                "White": "high",
                "Blue": "high",
                "Purple": "medium",
            },
            "typography": {"Sans-serif": "high"},
        },
        "evidence": {
            "pageType": ["Navigation, page-level hero, and footer are visible."],
            "sectionTypes": {},
            "containedSectionTypes": {
                "Features": ["Parallel capability cards appear mid-page."]
            },
            "industries": {
                "SaaS": ["The product UI and copy describe a software service."]
            },
            "layouts": {},
            "elements": {
                "Grid": ["Feature cards use repeated grid cells."],
                "Illustration": ["Custom vector scenes appear beside copy."],
            },
            "styles": {
                "surface:Illustration": [
                    "Illustration is the primary visual material."
                ],
                "mood:Playful": ["Rounded forms and lively artwork are visible."],
            },
            "colors": {
                "White": ["White covers major page surfaces."],
                "Blue": ["Blue appears on primary actions and accents."],
                "Purple": ["Purple appears as a small illustration accent."],
            },
            "typography": {
                "Sans-serif": ["Headings and body copy use sans-serif forms."]
            },
        },
        "unmapped": [
            {
                "category": "styles",
                "term": "Soft organic",
                "confidence": "low",
                "reason": "No exact UIBook style option matches.",
                "evidence": ["Several blobs have soft organic contours."],
            }
        ],
    }
    page_mirror = read_fixture("page-v2.json")
    assert page_mirror["taxonomySnapshot"] == taxonomy["snapshotHash"]
    assert page_mirror["imageFingerprint"] == fingerprint
    page_result = validate_mirror_payload(page_mirror, taxonomy)
    assert page_result["schemaVersion"] == UIBOOK_SCHEMA_V2
    assert page_result["managedPrefixes"] == list(
        V2_MANAGED_UIBOOK_TAG_PREFIXES
    )
    assert "uibook:elements:Grid" in page_result["desiredTags"]
    assert "uibook:elements:Illustration" in page_result["desiredTags"]
    assert (
        "uibook:style:surface:Illustration"
        in page_result["desiredTags"]
    )
    assert "uibook:colors:Blue" in page_result["desiredTags"]
    assert "uibook:colors:White" not in page_result["desiredTags"]
    assert "uibook:colors:Purple" not in page_result["desiredTags"]
    assert page_result["suppressedColorTags"] == [
        "uibook:colors:White",
        "uibook:colors:Purple",
    ]
    assert page_result["desiredByCategory"]["layouts"] == []

    annotation_only_status = inspect_uibook_preparation(
        {
            "id": "ITEM",
            "annotation": f"{AI_HEADING_EN}\n\nLegacy note only.",
            "tags": [],
        }
    )
    assert not annotation_only_status["uibookPreparationComplete"]
    assert annotation_only_status["uibookPreparationIssue"] == "missing_v2_mirror"

    complete_annotation = attach_mirror_data(
        f"{BLOCK_START}\n{AI_HEADING_EN}\n{BLOCK_END}",
        page_result["mirrorData"],
    )
    complete_status = inspect_uibook_preparation(
        {
            "id": "ITEM",
            "annotation": complete_annotation,
            "tags": page_result["desiredTags"],
        }
    )
    assert complete_status["uibookPreparationComplete"]
    assert complete_status["hasV2Mirror"]
    assert complete_status["hasUibookTags"]

    missing_tag_status = inspect_uibook_preparation(
        {
            "id": "ITEM",
            "annotation": complete_annotation,
            "tags": page_result["desiredTags"][1:],
        }
    )
    assert not missing_tag_status["uibookPreparationComplete"]
    assert missing_tag_status["uibookPreparationIssue"] == "uibook_tags_out_of_sync"

    v1_mirror = json.loads(json.dumps(page_result["mirrorData"]))
    v1_mirror["schemaVersion"] = UIBOOK_SCHEMA_V1
    v1_status = inspect_uibook_preparation(
        {
            "id": "ITEM",
            "annotation": attach_mirror_data(
                f"{AI_HEADING_EN}\n",
                v1_mirror,
            ),
            "tags": page_result["desiredTags"],
        }
    )
    assert not v1_status["uibookPreparationComplete"]
    assert v1_status["uibookPreparationIssue"] == "schema_v2_required"

    section_mirror = json.loads(json.dumps(page_mirror))
    section_mirror["entityType"] = "section"
    section_mirror["classification"] = {
        "pageType": None,
        "sectionTypes": ["Features"],
        "containedSectionTypes": [],
        "industries": ["SaaS"],
        "layouts": ["Grid"],
        "elements": ["Grid", "Illustration"],
        "styles": [
            {"dimension": "surface", "value": "Illustration"},
        ],
        "colors": ["White", "Blue"],
        "typography": ["Sans-serif"],
    }
    section_mirror["colorWeights"] = {"White": 15, "Blue": 3}
    section_mirror["confidence"] = {
        "contentCoverage": "high",
        "pageType": None,
        "sectionTypes": {"Features": "high"},
        "containedSectionTypes": {},
        "industries": {"SaaS": "high"},
        "layouts": {"Grid": "high"},
        "elements": {"Grid": "high", "Illustration": "high"},
        "styles": {"surface:Illustration": "high"},
        "colors": {"White": "high", "Blue": "high"},
        "typography": {"Sans-serif": "high"},
    }
    section_mirror["evidence"] = {
        "pageType": [],
        "sectionTypes": {
            "Features": ["Several parallel product capabilities are visible."]
        },
        "containedSectionTypes": {},
        "industries": {
            "SaaS": ["The section presents a software product."]
        },
        "layouts": {"Grid": ["Content is arranged in repeated cells."]},
        "elements": {
            "Grid": ["The visible component is a card grid."],
            "Illustration": ["Each card includes an illustration."],
        },
        "styles": {
            "surface:Illustration": [
                "Illustrations dominate the visual material."
            ]
        },
        "colors": {
            "White": ["White covers the section background."],
            "Blue": ["Blue accents cover visible controls."],
        },
        "typography": {
            "Sans-serif": ["Visible headings use sans-serif letterforms."]
        },
    }
    section_mirror = read_fixture("section-v2.json")
    assert section_mirror["taxonomySnapshot"] == taxonomy["snapshotHash"]
    assert section_mirror["imageFingerprint"] == fingerprint
    section_result = validate_mirror_payload(section_mirror, taxonomy)
    assert "uibook:section:Features" in section_result["desiredTags"]
    assert "uibook:layout:Grid" in section_result["desiredTags"]
    assert "uibook:elements:Grid" in section_result["desiredTags"]
    assert "uibook:colors:White" in section_result["desiredTags"]
    assert "uibook:colors:Blue" in section_result["desiredTags"]

    missing_field = json.loads(json.dumps(page_mirror))
    del missing_field["classification"]["typography"]
    expect_runtime_error(
        lambda: validate_mirror_payload(missing_field, taxonomy),
        "keys do not match schema v2",
    )

    missing_evidence = json.loads(json.dumps(page_mirror))
    del missing_evidence["evidence"]["elements"]["Grid"]
    expect_runtime_error(
        lambda: validate_mirror_payload(missing_evidence, taxonomy),
        "evidence.elements keys do not match",
    )

    low_confidence = json.loads(json.dumps(page_mirror))
    low_confidence["confidence"]["elements"]["Grid"] = "low"
    expect_runtime_error(
        lambda: validate_mirror_payload(low_confidence, taxonomy),
        "low-confidence values belong only in unmapped",
    )

    invented_value = json.loads(json.dumps(page_mirror))
    invented_value["classification"]["elements"][0] = "Invented"
    expect_runtime_error(
        lambda: validate_mirror_payload(invented_value, taxonomy),
        "classification.elements is not present",
    )

    entity_overreach = json.loads(json.dumps(page_mirror))
    entity_overreach["classification"]["layouts"] = ["Grid"]
    expect_runtime_error(
        lambda: validate_mirror_payload(entity_overreach, taxonomy),
        "require layouts=[]",
    )

    cardinality = json.loads(json.dumps(page_mirror))
    cardinality["classification"]["elements"] = [
        f"Element {index}"
        for index in range(MAX_ELEMENTS + 1)
    ]
    expect_runtime_error(
        lambda: validate_mirror_payload(cardinality, taxonomy),
        f"at most {MAX_ELEMENTS} values",
    )

    too_many_styles = json.loads(json.dumps(page_mirror))
    too_many_styles["classification"]["styles"] = [
        {"dimension": "surface", "value": "Illustration"},
        {"dimension": "mood", "value": "Playful"},
        {"dimension": "generic", "value": "Minimal"},
        {"dimension": "mood", "value": "Bold"},
        {"dimension": "generic", "value": "Professional"},
        {"dimension": "motion", "value": "Animation"},
        {"dimension": "theme", "value": "Dark Mode"},
    ]
    expect_runtime_error(
        lambda: validate_mirror_payload(too_many_styles, taxonomy),
        f"at most {MAX_WEBSITE_STYLES} styles",
    )

    too_many_section_types = json.loads(json.dumps(section_mirror))
    too_many_section_types["classification"]["sectionTypes"] = [
        "Features",
        "Testimonials",
        "FAQ",
    ]
    expect_runtime_error(
        lambda: validate_mirror_payload(
            too_many_section_types,
            taxonomy,
        ),
        f"at most {MAX_SECTION_TYPES} values",
    )

    too_many_industries = json.loads(json.dumps(page_mirror))
    too_many_industries["classification"]["industries"] = [
        "SaaS",
        "Finance",
        "Technology",
        "Marketing",
    ]
    expect_runtime_error(
        lambda: validate_mirror_payload(too_many_industries, taxonomy),
        f"at most {MAX_INDUSTRIES} values",
    )

    too_many_layouts = json.loads(json.dumps(section_mirror))
    too_many_layouts["classification"]["layouts"] = [
        "Grid",
        "Split",
        "Centered",
        "Bento",
    ]
    expect_runtime_error(
        lambda: validate_mirror_payload(too_many_layouts, taxonomy),
        f"at most {MAX_LAYOUTS} values",
    )

    too_many_colors = json.loads(json.dumps(page_mirror))
    too_many_colors["classification"]["colors"] = [
        "White",
        "Black",
        "Gray",
        "Blue",
        "Purple",
        "Red",
        "Green",
        "Yellow",
        "Orange",
    ]
    expect_runtime_error(
        lambda: validate_mirror_payload(too_many_colors, taxonomy),
        f"at most {MAX_COLORS} values",
    )

    too_many_typography = json.loads(json.dumps(page_mirror))
    too_many_typography["classification"]["typography"] = [
        "Sans-serif",
        "Serif",
        "Monospace",
    ]
    expect_runtime_error(
        lambda: validate_mirror_payload(too_many_typography, taxonomy),
        f"at most {MAX_TYPOGRAPHY} values",
    )

    low_coverage_color = json.loads(json.dumps(page_mirror))
    low_coverage_color["colorWeights"]["Purple"] = 0.5
    expect_runtime_error(
        lambda: validate_mirror_payload(low_coverage_color, taxonomy),
        "must be between 1 and 100",
    )

    non_finite_color = json.loads(json.dumps(page_mirror))
    non_finite_color["colorWeights"]["Blue"] = float("nan")
    expect_runtime_error(
        lambda: validate_mirror_payload(non_finite_color, taxonomy),
        "must be between 1 and 100",
    )

    wrong_style_dimension = json.loads(json.dumps(page_mirror))
    wrong_style_dimension["classification"]["styles"][0][
        "dimension"
    ] = "mood"
    expect_runtime_error(
        lambda: validate_mirror_payload(
            wrong_style_dimension,
            taxonomy,
        ),
        "dimension does not match taxonomy",
    )

    wrong_category = json.loads(json.dumps(section_mirror))
    wrong_category["classification"]["layouts"] = ["Card"]
    expect_runtime_error(
        lambda: validate_mirror_payload(wrong_category, taxonomy),
        "classification.layouts is not present",
    )

    v1_mirror = {
        "schemaVersion": UIBOOK_SCHEMA_V1,
        "taxonomySnapshot": taxonomy["snapshotHash"],
        "sourceItemId": "ITEM",
        "imageFingerprint": fingerprint,
        "entityType": "website",
        "uiContext": "A legacy v1 homepage mirror.",
        "contentMap": [{"region": "hero"}],
        "classification": {
            "pageType": "Homepage",
            "sectionTypes": [],
            "containedSectionTypes": ["Features"],
            "styles": [
                {
                    "dimension": "mood",
                    "value": "Playful",
                    "confidence": "high",
                }
            ],
        },
        "confidence": {
            "pageType": "high",
            "containedSectionTypes": "high",
        },
        "evidence": {
            "pageType": ["A full page frame is visible."]
        },
        "unmapped": [],
    }
    v1_result = validate_mirror_payload(v1_mirror, taxonomy)
    assert v1_result["managedPrefixes"] == list(
        V1_MANAGED_UIBOOK_TAG_PREFIXES
    )
    assert all(
        not is_managed_uibook_tag(
            tag,
            V2_ONLY_UIBOOK_TAG_PREFIXES,
        )
        for tag in v1_result["desiredTags"]
    )
    expect_runtime_error(
        lambda: ensure_schema_tag_compatibility(
            UIBOOK_SCHEMA_V1,
            ["manual-tag", "uibook:industry:SaaS"],
        ),
        "schema v2-only managed tags",
    )
    ensure_schema_tag_compatibility(
        UIBOOK_SCHEMA_V1,
        ["manual-tag", "uibook:page:Homepage"],
    )

    current_tags = [
        "manual-tag",
        "已同步UIBook",
        "uibook:page:Pricing",
        "uibook:layout:Split",
        "uibook:industry:Finance",
    ]
    tag_diff = build_uibook_tag_diff(
        current_tags,
        page_result["desiredTags"],
        page_result["managedPrefixes"],
    )
    assert "manual-tag" in tag_diff["preserved"]
    assert "已同步UIBook" in tag_diff["preserved"]
    assert "uibook:layout:Split" in tag_diff["toRemove"]
    assert "uibook:industry:Finance" in tag_diff["toRemove"]

    attached = attach_mirror_data(
        f"{BLOCK_START}\n## AI Screen Analysis\nConcrete analysis\n{BLOCK_END}",
        page_result["mirrorData"],
    )
    assert attached.count(MIRROR_DATA_HEADING) == 1
    compact_mirror_json = json.dumps(
        page_result["mirrorData"],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    assert f"```json\n{compact_mirror_json}\n```" in attached
    assert '"schemaVersion":2' in attached
    assert set(page_result["mirrorData"]) == {
        "schemaVersion",
        "taxonomySnapshot",
        "sourceItemId",
        "imageFingerprint",
        "entityType",
        "uiContext",
        "contentMap",
        "classification",
        "colorWeights",
        "confidence",
        "evidence",
        "unmapped",
    }
    assert not {
        "managedPrefixes",
        "desiredByCategory",
        "suppressedColorTags",
        "managedTags",
    } & set(page_result["mirrorData"])

    unicode_metrics = annotation_metrics("A😀")
    assert unicode_metrics == {
        "codePoints": 2,
        "utf16CodeUnits": 3,
        "utf8Bytes": 5,
        "limitUtf16CodeUnits": ANNOTATION_UTF16_HARD_LIMIT,
    }
    exact_limit_metrics = preflight_annotation(
        "😀" * (ANNOTATION_UTF16_HARD_LIMIT // 2)
    )
    assert (
        exact_limit_metrics["utf16CodeUnits"]
        == ANNOTATION_UTF16_HARD_LIMIT
    )
    expect_runtime_error(
        lambda: preflight_annotation(
            "😀" * ((ANNOTATION_UTF16_HARD_LIMIT // 2) + 1)
        ),
        "no Eagle tags or annotation were written",
    )

    replacement_block = (
        f"{BLOCK_START}\n"
        "## AI Screen Analysis\n"
        "Replacement analysis\n"
        f"{BLOCK_END}"
    )
    marker_wrapped_existing = (
        "Manual before\n\n"
        f"{BLOCK_START}\n"
        "## AI Screen Analysis\n"
        "Old analysis\n\n"
        "## UIBook Mirror Data\n\n"
        "```json\n"
        '{"schemaVersion": 2}\n'
        "```\n"
        f"{BLOCK_END}\n\n"
        "Manual after"
    )
    marker_wrapped_merged = merge_annotation(
        marker_wrapped_existing,
        replacement_block,
    )
    assert "Manual before" in marker_wrapped_merged
    assert "Manual after" in marker_wrapped_merged
    assert "Old analysis" not in marker_wrapped_merged
    assert marker_wrapped_merged.count(MIRROR_DATA_HEADING) == 0

    expect_runtime_error(
        lambda: merge_annotation(
            (
                "Manual before\n\n"
                f"{BLOCK_START}\n"
                "## AI Screen Analysis\n"
                "Old analysis"
            ),
            replacement_block,
        ),
        "unmatched analysis markers",
    )

    markerless_bounded_existing = (
        "Manual before\n\n"
        "## AI Screen Analysis\n"
        "Old analysis\n\n"
        "## UIBook Mirror Data\n\n"
        "```json\n"
        '{"schemaVersion": 1}\n'
        "```\n\n"
        "Manual after"
    )
    markerless_bounded_merged = merge_annotation(
        markerless_bounded_existing,
        replacement_block,
    )
    assert "Manual before" in markerless_bounded_merged
    assert "Manual after" in markerless_bounded_merged
    assert "Old analysis" not in markerless_bounded_merged

    expect_runtime_error(
        lambda: merge_annotation(
            "Manual before\n\n## AI Screen Analysis\nOld analysis\n\nManual after",
            replacement_block,
        ),
        "no bounded UIBook Mirror Data",
    )

    unbounded_legacy = (
        "Manual prefix\n\n"
        "## AI Screen Analysis\n"
        "Old unbounded analysis\n\n"
        "Potentially ambiguous trailing text"
    )
    legacy_digest = annotation_sha256(unbounded_legacy)
    exact_legacy_merged, exact_legacy_info = (
        merge_annotation_with_info(
            unbounded_legacy,
            replacement_block,
            legacy_digest,
        )
    )
    assert exact_legacy_info["performed"] is True
    assert (
        exact_legacy_info["mode"]
        == "exact-sha256-replace-heading-to-end"
    )
    assert "Manual prefix" in exact_legacy_merged
    assert "Old unbounded analysis" not in exact_legacy_merged
    assert "Potentially ambiguous trailing text" not in exact_legacy_merged
    expect_runtime_error(
        lambda: merge_annotation(
            unbounded_legacy,
            replacement_block,
            "0" * 64,
        ),
        "does not exactly match",
    )
    expect_runtime_error(
        lambda: merge_annotation(
            unbounded_legacy,
            replacement_block,
            legacy_digest.upper(),
        ),
        "64 lowercase hexadecimal",
    )
    expect_runtime_error(
        lambda: merge_annotation(
            markerless_bounded_existing,
            replacement_block,
            annotation_sha256(markerless_bounded_existing),
        ),
        "only valid for an unbounded markerless legacy AI block",
    )

    with tempfile.TemporaryDirectory(
        prefix="eagle-uibook-v2-selftest-"
    ) as temporary_directory:
        temporary_path = Path(temporary_directory)
        empty_image = temporary_path / "empty-image.png"
        empty_image.touch()
        binding_item = {
            "id": "ITEM",
            "filePath": str(empty_image),
            "tags": current_tags,
        }
        verify_mirror_item_binding(
            binding_item,
            "ITEM",
            page_result,
        )

        backup_path = temporary_path / "legacy-annotation.md"
        created_backup = save_legacy_annotation_backup(
            unbounded_legacy,
            str(backup_path),
        )
        assert created_backup["created"] is True
        assert created_backup["sha256"] == legacy_digest
        with backup_path.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as backup_handle:
            assert backup_handle.read() == unbounded_legacy
        reused_backup = save_legacy_annotation_backup(
            unbounded_legacy,
            str(backup_path),
        )
        assert reused_backup["created"] is False
        expect_runtime_error(
            lambda: save_legacy_annotation_backup(
                f"{unbounded_legacy}\nchanged",
                str(backup_path),
            ),
            "already exists with different content",
        )

    class RecordingClient:
        def __init__(self, apply_adds: bool = True) -> None:
            self.calls: list[tuple[str, dict[str, Any]]] = []
            self.apply_adds = apply_adds
            self.tags = list(current_tags)

        def update_item_fields(
            self,
            item_id: str,
            fields: dict[str, Any],
        ) -> dict[str, Any]:
            self.calls.append(
                (
                    "item_update_http",
                    {
                        "id": item_id,
                        **fields,
                    },
                )
            )
            if self.apply_adds and isinstance(
                fields.get("tags"),
                list,
            ):
                self.tags = [
                    str(tag)
                    for tag in fields["tags"]
                ]
            return {"status": "success"}

        def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            self.calls.append((name, arguments))
            if name == "item_get":
                payload = {
                    "data": [
                        {
                            "id": "ITEM",
                            "filePath": str(script_path),
                            "tags": list(self.tags),
                        }
                    ]
                }
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(payload),
                        }
                    ]
                }
            return {}

    recording_client = RecordingClient()
    reconcile_managed_uibook_tags(
        recording_client,
        "ITEM",
        page_result["desiredTags"],
        tag_diff["toAdd"],
        tag_diff["toRemove"],
        page_result["managedPrefixes"],
    )
    assert [name for name, _ in recording_client.calls] == [
        "item_get",
        "item_update_http",
        "item_get",
        "item_get",
        "item_update_http",
        "item_get",
    ]

    failed_add_client = RecordingClient(apply_adds=False)
    expect_runtime_error(
        lambda: reconcile_managed_uibook_tags(
            failed_add_client,
            "ITEM",
            page_result["desiredTags"],
            tag_diff["toAdd"],
            tag_diff["toRemove"],
            page_result["managedPrefixes"],
        ),
        "before removal",
    )
    assert [
        name
        for name, _ in failed_add_client.calls
    ].count("item_update_http") == 1

    tampered_taxonomy = json.loads(json.dumps(taxonomy))
    tampered_taxonomy["categories"]["page_type"][0]["value"] = "Changed"
    expect_runtime_error(
        lambda: validate_mirror_payload(
            page_mirror,
            tampered_taxonomy,
        ),
        "does not match taxonomy contents",
    )

    flat_taxonomy = {
        "configOptions": [
            {
                **option,
                "category": category,
            }
            for category, options in taxonomy["categories"].items()
            for option in options
        ]
    }
    flat_rows = taxonomy_option_rows(flat_taxonomy)
    flat_taxonomy["snapshotHash"] = taxonomy_rows_hash(flat_rows)
    flat_mirror = json.loads(json.dumps(page_mirror))
    flat_mirror["taxonomySnapshot"] = flat_taxonomy["snapshotHash"]
    validate_mirror_payload(flat_mirror, flat_taxonomy)

    forged_flat_taxonomy = json.loads(json.dumps(flat_taxonomy))
    forged_flat_taxonomy["snapshotHash"] = f"sha256:{'0' * 64}"
    expect_runtime_error(
        lambda: validate_mirror_payload(
            flat_mirror,
            forged_flat_taxonomy,
        ),
        "does not match taxonomy contents",
    )

    mixed_taxonomy = json.loads(json.dumps(taxonomy))
    mixed_taxonomy["configOptions"] = [
        {
            "category": "page_type",
            "value": "Forged Page",
            "dimension": None,
        }
    ]
    mixed_result = validate_mirror_payload(page_mirror, mixed_taxonomy)
    assert (
        mixed_result["normalizedClassification"]["pageType"]
        == "Homepage"
    )

    print(
        json.dumps(
            {
                "status": "passed",
                "checks": [
                    "valid schema v2 Page",
                    "valid schema v2 Section",
                    "category-specific Grid and Illustration matching",
                    "required schema v2 fields",
                    "per-value confidence and evidence",
                    "low-confidence unmapped-only gate",
                    "invented taxonomy rejection",
                    "Page and Section entity boundaries",
                    "UIBook cardinality caps",
                    "style dimension derivation and validation",
                    "color mirror and tag thresholds",
                    "schema v1 compatibility",
                    "schema v1 fail-closed over v2-only tags",
                    "schema-specific diff and verification",
                    "verified add-before-remove ordering",
                    "persistent v2 Page and Section fixtures",
                    "compact v2 embedded mirror contract",
                    "schema v2 and managed tags required for scan completion",
                    "annotation-only and schema v1 completion rejection",
                    "UTF-16 annotation hard preflight",
                    "annotation mirror data and item binding",
                    "marker and markerless manual-note preservation",
                    "unbounded markerless annotation fail-closed",
                    "exact-hash legacy migration and exclusive backup",
                    "taxonomy snapshot integrity",
                    "flat and mixed taxonomy source integrity",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    repo = Path(args.repo).expanduser().resolve()
    _ = get_success_tag(repo)
    if (
        args.legacy_backup_file
        and not args.legacy_annotation_sha256
    ):
        raise RuntimeError(
            "--legacy-backup-file requires "
            "--legacy-annotation-sha256"
        )
    if not args.mirror_file or not args.taxonomy_file:
        raise RuntimeError(
            "UIBook preparation requires both --mirror-file and "
            "--taxonomy-file; annotation-only apply is disabled"
        )
    block = read_analysis_block(args)
    mirror = read_json_document(args.mirror_file, "Mirror")
    taxonomy = read_json_document(args.taxonomy_file, "Taxonomy")
    mirror_result = validate_mirror_payload(mirror, taxonomy)
    if mirror_result["schemaVersion"] != UIBOOK_SCHEMA_V2:
        raise RuntimeError(
            "UIBook preparation requires schemaVersion 2; schema v1 apply "
            "is disabled"
        )
    block = attach_mirror_data(block, mirror_result["mirrorData"])

    client = MCPClient(timeout=args.timeout)
    try:
        item = get_item_by_id(client, args.item_id)
        verify_mirror_item_binding(
            item,
            args.item_id,
            mirror_result,
        )
        current_annotation = str(item.get("annotation") or "")
        merged, legacy_migration = merge_annotation_with_info(
            current_annotation,
            block,
            args.legacy_annotation_sha256,
        )
        annotation_preflight = preflight_annotation(merged)
        legacy_migration["backupRequiredOnApply"] = bool(
            legacy_migration["performed"]
        )
        legacy_migration["backupFileProvided"] = bool(
            args.legacy_backup_file
        )
        if (
            args.legacy_backup_file
            and not legacy_migration["performed"]
        ):
            raise RuntimeError(
                "--legacy-backup-file is only valid when an unbounded "
                "markerless legacy annotation is migrated with an exact "
                "SHA-256 match"
            )
        if (
            legacy_migration["performed"]
            and not args.dry_run
            and not args.legacy_backup_file
        ):
            raise RuntimeError(
                "Applying an exact-hash markerless legacy migration "
                "requires --legacy-backup-file before any Eagle write"
            )
        tag_diff = build_uibook_tag_diff(
            item_tag_names(item),
            mirror_result["desiredTags"],
            mirror_result["managedPrefixes"],
        )
        if args.dry_run:
            json.dump(
                {
                    "itemId": args.item_id,
                    "schemaVersion": mirror_result["schemaVersion"],
                    "taxonomySnapshot": mirror_result["taxonomySnapshot"],
                    "entityType": mirror_result["entityType"],
                    "managedPrefixes": mirror_result["managedPrefixes"],
                    "desiredByCategory": mirror_result[
                        "desiredByCategory"
                    ],
                    **tag_diff,
                    "unmapped": mirror_result["unmapped"],
                    "suppressedColorTags": mirror_result[
                        "suppressedColorTags"
                    ],
                    "normalizedClassification": mirror_result[
                        "normalizedClassification"
                    ],
                    "annotationMetrics": annotation_preflight,
                    "legacyMigration": legacy_migration,
                    "mergedAnnotation": merged,
                },
                sys.stdout,
                ensure_ascii=False,
                indent=2,
            )
            sys.stdout.write("\n")
            return 0

        legacy_backup: dict[str, Any] | None = None
        if legacy_migration["performed"]:
            legacy_backup = save_legacy_annotation_backup(
                current_annotation,
                args.legacy_backup_file,
            )

        reconcile_managed_uibook_tags(
            client,
            args.item_id,
            mirror_result["desiredTags"],
            tag_diff["toAdd"],
            tag_diff["toRemove"],
            mirror_result["managedPrefixes"],
        )

        update_annotation(client, args.item_id, merged)
        verified_item = get_item_by_id(client, args.item_id)
        if normalize_annotation_for_verification(
            verified_item.get("annotation")
        ) != normalize_annotation_for_verification(merged):
            raise RuntimeError("Eagle annotation verification failed after item_update")
        verify_managed_uibook_tags(
            verified_item,
            mirror_result["desiredTags"],
            mirror_result["managedPrefixes"],
        )
        json.dump(
            {
                "status": "updated-and-verified",
                "itemId": args.item_id,
                "schemaVersion": mirror_result["schemaVersion"],
                "taxonomySnapshot": mirror_result["taxonomySnapshot"],
                "managedPrefixes": mirror_result["managedPrefixes"],
                "desiredByCategory": mirror_result[
                    "desiredByCategory"
                ],
                **tag_diff,
                "unmapped": mirror_result["unmapped"],
                "suppressedColorTags": mirror_result[
                    "suppressedColorTags"
                ],
                "annotationMetrics": annotation_preflight,
                "legacyMigration": legacy_migration,
                "legacyBackup": legacy_backup,
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write("\n")
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

    tag_audit = subparsers.add_parser("tag-audit", help="Generate a read-only Eagle tag health report")
    tag_audit.add_argument("--repo", default=".", help="Path to the eagle-export-plugin repository")
    tag_audit.add_argument("--output-dir", default="reports", help="Directory for generated Markdown and JSON reports")
    tag_audit.add_argument("--sample-size", type=int, default=10, help="Number of untagged item samples to include")
    tag_audit.add_argument("--timeout", type=float, default=60.0, help="MCP timeout in seconds")
    tag_audit.set_defaults(func=cmd_tag_audit)

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

    apply_cmd = subparsers.add_parser("apply", help="Validate and write a complete schema-v2 UIBook analysis, managed tags, and Eagle annotation")
    apply_cmd.add_argument("--repo", required=True, help="Path to the eagle-export-plugin repository")
    apply_cmd.add_argument("--item-id", required=True, help="Eagle item ID to update")
    apply_cmd.add_argument("--analysis-file", help="Path to a markdown file containing the complete analysis block")
    apply_cmd.add_argument("--mirror-file", required=True, help="Required schema-v2 UIBook mirror JSON with uiContext, contentMap, and taxonomy classifications")
    apply_cmd.add_argument("--taxonomy-file", required=True, help="Required read-only eight-category UIBook config_options snapshot used to validate mirror classifications")
    apply_cmd.add_argument("--legacy-annotation-sha256", help="Exact lowercase SHA-256 of the complete current annotation; permits replacing an otherwise unbounded markerless legacy AI block from its heading to the end")
    apply_cmd.add_argument("--legacy-backup-file", help="Required for a non-dry-run exact-hash legacy migration; saves the complete current annotation with exclusive creation before any Eagle write")
    apply_cmd.add_argument("--dry-run", action="store_true", help="Print schema-specific managed prefixes, tag diff, suppressed colors, and merged annotation without writing")
    apply_cmd.add_argument("--timeout", type=float, default=60.0, help="MCP timeout in seconds")
    apply_cmd.set_defaults(func=cmd_apply)

    self_test = subparsers.add_parser("self-test", help="Run pure local checks for UIBook mirror validation and tag reconciliation")
    self_test.set_defaults(func=cmd_self_test)

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
