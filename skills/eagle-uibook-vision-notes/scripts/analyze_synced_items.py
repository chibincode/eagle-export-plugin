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
