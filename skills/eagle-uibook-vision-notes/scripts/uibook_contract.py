#!/usr/bin/env python3
"""Shared UIBook analysis contract, read-only audit, and human-review helpers.

This module deliberately contains no model calls.  It can validate historical
Mirror Data, build deterministic suggestions, and render a separate review
block without rewriting the original AI analysis.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import ssl
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


MIRROR_SCHEMA_VERSION = 3
REVIEW_SCHEMA_VERSION = 1
POLICY_VERSION = "2026-08-17.1"

MIRROR_HEADING = "## UIBook Mirror Data"
REVIEW_HEADING = "## UIBook Human Review"
REVIEW_START = "<!-- UIBOOK_HUMAN_REVIEW_START -->"
REVIEW_END = "<!-- UIBOOK_HUMAN_REVIEW_END -->"

TAXONOMY_CATEGORIES = {
    "pageType": "page_type",
    "sectionTypes": "section_type",
    "containedSectionTypes": "section_type",
    "industries": "industry",
    "layouts": "layout",
    "elements": "elements",
    "styles": "style",
    "colors": "colors",
    "typography": "typography",
}
BLOCKLIST_BY_FIELD = {
    "pageType": "page_type_blocklist",
    "elements": "element_blocklist",
    "styles": "style_blocklist",
}
STYLE_FALLBACK_VALUES = ("Modern", "Minimal", "Professional")
CONFIDENCE_SCORES = {"low": 1.0, "medium": 2.0, "high": 3.0}
CONTENT_MAP_LIMITS = {"website": 8, "page": 8, "section": 4}
FIELD_LIMITS = {
    "website": {
        "pageType": (1, 1),
        "industries": (0, 3),
        "styles": (0, 6),
        "typography": (0, 2),
    },
    "page": {
        "pageType": (1, 1),
        "industries": (0, 3),
        "styles": (0, 6),
        "typography": (0, 2),
    },
    "section": {
        "sectionTypes": (1, 2),
        "industries": (0, 3),
        "layouts": (0, 3),
        "styles": (0, 4),
        "typography": (0, 2),
    },
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _extract_json_block(annotation: str, heading: str) -> dict[str, Any]:
    match = re.search(
        rf"{re.escape(heading)}\s*```json\s*(\{{.*?\}})\s*```",
        str(annotation or ""),
        flags=re.DOTALL,
    )
    if not match:
        return {}
    try:
        payload = json.loads(match.group(1))
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


def extract_mirror_data(annotation: str) -> dict[str, Any]:
    return _extract_json_block(annotation, MIRROR_HEADING)


def extract_human_review(annotation: str) -> dict[str, Any]:
    return _extract_json_block(annotation, REVIEW_HEADING)


def _split_legacy_context(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {
            "en": str(value.get("en") or value.get("english") or "").strip(),
            "zh": str(value.get("zh") or value.get("chinese") or "").strip(),
        }
    text = str(value or "").strip()
    for separator in ("中文 Context：", "Chinese Context:", "中文 Context:"):
        if separator in text:
            english, chinese = text.split(separator, 1)
            return {"en": english.strip(), "zh": chinese.strip()}
    return {"en": text, "zh": ""}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    value = parsed
            except json.JSONDecodeError:
                pass
    if not isinstance(value, list):
        value = [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        lowered = text.casefold()
        if text and lowered not in seen:
            seen.add(lowered)
            result.append(text)
    return result


def _normalize_content_map(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for index, entry in enumerate(value, start=1):
        if not isinstance(entry, dict):
            continue
        region = entry.get("region") or entry.get("type") or f"Region {index}"
        result.append(
            {
                "order": int(entry.get("order") or index),
                "region": str(region),
                "regionZh": str(entry.get("regionZh") or ""),
                "position": str(entry.get("position") or ""),
                "summaryEn": str(entry.get("summaryEn") or entry.get("summary") or ""),
                "summaryZh": str(entry.get("summaryZh") or ""),
            }
        )
    return result


def _normalize_styles(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in value:
        if isinstance(entry, dict):
            dimension = str(entry.get("dimension") or "").strip()
            style_value = str(entry.get("value") or "").strip()
        else:
            dimension = ""
            style_value = str(entry or "").strip()
        key = style_value.casefold()
        if style_value and key not in seen:
            seen.add(key)
            result.append({"dimension": dimension, "value": style_value})
    return result


def normalize_classification(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "pageType": str(source.get("pageType") or "").strip() or None,
        "sectionTypes": _string_list(source.get("sectionTypes")),
        "containedSectionTypes": _string_list(source.get("containedSectionTypes")),
        "industries": _string_list(source.get("industries")),
        "layouts": _string_list(source.get("layouts")),
        "elements": _string_list(source.get("elements")),
        "styles": _normalize_styles(source.get("styles")),
        "colors": _string_list(source.get("colors")),
        "typography": _string_list(source.get("typography")),
    }


def adapt_mirror_data(mirror: dict[str, Any]) -> dict[str, Any]:
    """Normalize v2/v3 Mirror Data into the v3 in-memory shape."""
    source = mirror if isinstance(mirror, dict) else {}
    entity_type = str(source.get("entityType") or "section").lower()
    if entity_type == "page":
        entity_type = "website"
    return {
        "schemaVersion": int(source.get("schemaVersion") or 2),
        "sourceItemId": str(source.get("sourceItemId") or ""),
        "imageFingerprint": str(source.get("imageFingerprint") or ""),
        "entityType": entity_type,
        "analysisModel": str(source.get("analysisModel") or source.get("model") or ""),
        "analyzedAt": str(source.get("analyzedAt") or ""),
        "taxonomySnapshot": str(source.get("taxonomySnapshot") or ""),
        "policyVersion": str(source.get("policyVersion") or ""),
        "uiContext": _split_legacy_context(source.get("uiContext")),
        "contentMap": _normalize_content_map(source.get("contentMap")),
        "contentCoverage": str(source.get("contentCoverage") or ""),
        "classification": normalize_classification(source.get("classification")),
        "colorWeights": copy.deepcopy(source.get("colorWeights") or {}),
        "confidence": copy.deepcopy(source.get("confidence") or {}),
        "evidence": copy.deepcopy(source.get("evidence") or {}),
        "unmapped": copy.deepcopy(source.get("unmapped") or []),
        "validation": copy.deepcopy(source.get("validation") or {}),
    }


def mirror_fingerprint(mirror: dict[str, Any]) -> str:
    return sha256_json(mirror if isinstance(mirror, dict) else {})


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text("utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        values[key.strip()] = raw_value.strip().strip('"').strip("'")
    return values


def verified_ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except (ImportError, OSError):
        return ssl.create_default_context()


def resolve_uibook_env(repo: Path | None = None, explicit: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    configured = os.environ.get("UIBOOK_ENV_FILE")
    if configured:
        candidates.append(Path(configured).expanduser())
    if repo:
        repo = Path(repo).expanduser().resolve()
        candidates.extend((repo.parent / "uibook" / ".env", repo / "uibook" / ".env"))
    candidates.append(Path.cwd().parent / "uibook" / ".env")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def build_taxonomy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_rows = [
        {
            "category": str(row.get("category") or ""),
            "value": str(row.get("value") or ""),
            "description": row.get("description"),
            "dimension": row.get("dimension"),
            "display_order": row.get("display_order"),
        }
        for row in rows
        if row.get("category") and row.get("value")
    ]
    normalized_rows.sort(
        key=lambda row: (
            row["category"],
            row["display_order"] if isinstance(row["display_order"], int) else 10**9,
            row["value"].casefold(),
        )
    )
    by_category: dict[str, list[dict[str, Any]]] = {}
    for row in normalized_rows:
        by_category.setdefault(row["category"], []).append(row)
    style_dimensions = {
        row["value"].casefold(): str(row.get("dimension") or "")
        for row in by_category.get("style", [])
    }
    return {
        "rows": normalized_rows,
        "byCategory": by_category,
        "styleDimensions": style_dimensions,
        "snapshot": sha256_json(normalized_rows),
        "policyVersion": POLICY_VERSION,
    }


def fetch_taxonomy(env_path: Path, timeout: float = 15.0) -> dict[str, Any]:
    env = load_env_file(Path(env_path))
    base_url = env.get("VITE_SUPABASE_URL") or env.get("SUPABASE_URL")
    api_key = env.get("VITE_SUPABASE_PUBLISHABLE_KEY") or env.get("SUPABASE_ANON_KEY")
    if not base_url or not api_key:
        raise RuntimeError(f"UIBook env is missing Supabase URL/key: {env_path}")
    query = urllib.parse.urlencode(
        {
            "select": "category,value,description,dimension,display_order",
            "order": "category,display_order",
        }
    )
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/rest/v1/config_options?{query}",
        headers={
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout, context=verified_ssl_context()) as response:
        rows = json.loads(response.read().decode("utf-8"))
    if not isinstance(rows, list):
        raise RuntimeError("UIBook config_options returned an invalid payload")
    return build_taxonomy(rows)


def _confidence_score(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return CONFIDENCE_SCORES.get(str(value or "").strip().lower(), 0.0)


def _style_confidence(confidence: dict[str, Any], style: dict[str, str]) -> float:
    style_confidence = confidence.get("styles") if isinstance(confidence, dict) else {}
    if not isinstance(style_confidence, dict):
        return 0.0
    dimension = style.get("dimension") or ""
    value = style.get("value") or ""
    for key in (f"{dimension}:{value}", value):
        if key in style_confidence:
            return _confidence_score(style_confidence[key])
    lowered = {str(key).casefold(): item for key, item in style_confidence.items()}
    return _confidence_score(lowered.get(f"{dimension}:{value}".casefold(), lowered.get(value.casefold())))


def _has_evidence(evidence: Any) -> bool:
    if isinstance(evidence, str):
        return bool(evidence.strip())
    if isinstance(evidence, list):
        return any(_has_evidence(item) for item in evidence)
    if isinstance(evidence, dict):
        return any(_has_evidence(item) for item in evidence.values())
    return False


def _issue(code: str, severity: str, field: str, message: str, **details: Any) -> dict[str, Any]:
    payload = {"code": code, "severity": severity, "field": field, "message": message}
    if details:
        payload["details"] = details
    return payload


def _taxonomy_maps(taxonomy: dict[str, Any] | None) -> tuple[dict[str, dict[str, str]], dict[str, set[str]]]:
    allowed: dict[str, dict[str, str]] = {}
    blocklists: dict[str, set[str]] = {}
    for category, rows in (taxonomy or {}).get("byCategory", {}).items():
        canonical = {str(row["value"]).casefold(): str(row["value"]) for row in rows}
        if category.endswith("_blocklist"):
            blocklists[category] = set(canonical)
        else:
            allowed[category] = canonical
    return allowed, blocklists


def audit_mirror_data(mirror: dict[str, Any], taxonomy: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = adapt_mirror_data(mirror)
    suggested = copy.deepcopy(normalized)
    issues: list[dict[str, Any]] = []
    entity_type = normalized["entityType"] if normalized["entityType"] in {"website", "section"} else "section"
    classification = suggested["classification"]
    allowed, blocklists = _taxonomy_maps(taxonomy)

    if normalized["schemaVersion"] < MIRROR_SCHEMA_VERSION:
        issues.append(_issue("legacy_schema", "info", "schemaVersion", "Mirror Data is legacy v2 and was audited read-only."))
    elif normalized["schemaVersion"] > MIRROR_SCHEMA_VERSION:
        issues.append(_issue("future_schema", "warning", "schemaVersion", "Mirror Data uses a newer schema than this auditor."))
    else:
        required_values = {
            "sourceItemId": normalized["sourceItemId"],
            "imageFingerprint": normalized["imageFingerprint"],
            "analysisModel": normalized["analysisModel"],
            "analyzedAt": normalized["analyzedAt"],
            "taxonomySnapshot": normalized["taxonomySnapshot"],
            "policyVersion": normalized["policyVersion"],
            "uiContext.en": normalized["uiContext"]["en"],
            "uiContext.zh": normalized["uiContext"]["zh"],
            "contentCoverage": normalized["contentCoverage"],
        }
        for field, value in required_values.items():
            if not value:
                issues.append(_issue("missing_required_field", "error", field, f"Mirror Data v3 requires {field}."))
        for field in ("confidence", "evidence", "validation"):
            if field not in mirror or not isinstance(mirror.get(field), dict):
                issues.append(_issue("missing_required_field", "error", field, f"Mirror Data v3 requires an object at {field}."))
        for index, entry in enumerate(normalized["contentMap"], start=1):
            for field in ("region", "position", "summaryEn", "summaryZh"):
                if not entry.get(field):
                    issues.append(
                        _issue(
                            "incomplete_content_map_entry",
                            "error",
                            f"contentMap[{index - 1}].{field}",
                            f"Content Map entry {index} requires {field}.",
                        )
                    )

        if not isinstance(normalized["colorWeights"], dict):
            issues.append(_issue("invalid_color_weights", "error", "colorWeights", "colorWeights must be an object."))
        else:
            weights = list(normalized["colorWeights"].values())
            if any(not isinstance(weight, (int, float)) or weight < 0 for weight in weights):
                issues.append(_issue("invalid_color_weights", "error", "colorWeights", "Color weights must be non-negative numbers."))
            elif weights and abs(sum(float(weight) for weight in weights) - 100.0) > 1.0:
                issues.append(_issue("color_weight_total", "warning", "colorWeights", "Color weights should total approximately 100."))

    if taxonomy:
        current_snapshot = taxonomy.get("snapshot") or ""
        if normalized.get("taxonomySnapshot") and normalized["taxonomySnapshot"] != current_snapshot:
            issues.append(
                _issue(
                    "stale_taxonomy_snapshot",
                    "warning",
                    "taxonomySnapshot",
                    "The analysis used a different UIBook taxonomy snapshot.",
                    stored=normalized["taxonomySnapshot"],
                    current=current_snapshot,
                )
            )
    else:
        issues.append(_issue("taxonomy_unavailable", "warning", "taxonomy", "Live UIBook taxonomy was unavailable; structural checks only."))

    for field, category in TAXONOMY_CATEGORIES.items():
        if field == "styles":
            continue
        raw_values = [classification[field]] if field == "pageType" else list(classification[field])
        values = [value for value in raw_values if value]
        canonical_values: list[str] = []
        for value in values:
            lowered = value.casefold()
            if taxonomy and lowered not in allowed.get(category, {}):
                issues.append(_issue("unknown_taxonomy_value", "error", field, f'"{value}" is not in current UIBook {category}.', value=value))
                continue
            blocklist_name = BLOCKLIST_BY_FIELD.get(field)
            if blocklist_name and lowered in blocklists.get(blocklist_name, set()):
                issues.append(_issue("blocked_taxonomy_value", "error", field, f'"{value}" is blocked by UIBook.', value=value))
                continue
            canonical_values.append(allowed.get(category, {}).get(lowered, value))
        if field == "pageType":
            classification[field] = canonical_values[0] if canonical_values else None
        else:
            classification[field] = canonical_values

    style_allowed = allowed.get("style", {})
    style_dimensions = (taxonomy or {}).get("styleDimensions", {})
    sanitized_styles: list[dict[str, str]] = []
    for style in classification["styles"]:
        value = style["value"]
        lowered = value.casefold()
        if taxonomy and lowered not in style_allowed:
            issues.append(_issue("unknown_taxonomy_value", "error", "styles", f'"{value}" is not in current UIBook style.', value=value))
            continue
        if lowered in blocklists.get("style_blocklist", set()):
            issues.append(_issue("blocked_taxonomy_value", "error", "styles", f'"{value}" is blocked by UIBook.', value=value))
            continue
        canonical_value = style_allowed.get(lowered, value)
        canonical_dimension = style_dimensions.get(lowered, style.get("dimension") or "")
        if taxonomy and style.get("dimension") != canonical_dimension:
            issues.append(
                _issue(
                    "style_dimension_mismatch",
                    "warning",
                    "styles",
                    f'"{canonical_value}" belongs to {canonical_dimension or "unassigned"}, not {style.get("dimension") or "unassigned"}.',
                    value=canonical_value,
                    storedDimension=style.get("dimension") or "",
                    currentDimension=canonical_dimension,
                )
            )
        sanitized_styles.append({"dimension": canonical_dimension, "value": canonical_value})
    classification["styles"] = sanitized_styles

    limits = FIELD_LIMITS[entity_type]
    for field, (minimum, maximum) in limits.items():
        value = classification[field]
        count = 1 if field == "pageType" and value else len(value) if isinstance(value, list) else 0
        if count < minimum:
            issues.append(_issue("missing_required_value", "error", field, f"{field} requires at least {minimum} value."))
        if count > maximum:
            issues.append(_issue("category_limit_exceeded", "error", field, f"{field} allows at most {maximum} values.", count=count, maximum=maximum))

    map_limit = CONTENT_MAP_LIMITS[entity_type]
    if len(normalized["contentMap"]) > map_limit:
        issues.append(
            _issue(
                "content_map_limit_exceeded",
                "warning",
                "contentMap",
                f"{entity_type} Content Map allows at most {map_limit} entries.",
                count=len(normalized["contentMap"]),
                maximum=map_limit,
            )
        )

    styles = classification["styles"]
    style_by_name = {style["value"].casefold(): style for style in styles}
    modern = style_by_name.get("modern")
    minimal = style_by_name.get("minimal")
    if modern and minimal:
        modern_score = _style_confidence(normalized["confidence"], modern)
        minimal_score = _style_confidence(normalized["confidence"], minimal)
        winner = modern if modern_score > minimal_score else minimal
        loser = minimal if winner is modern else modern
        classification["styles"] = [style for style in styles if style["value"].casefold() != loser["value"].casefold()]
        styles = classification["styles"]
        issues.append(
            _issue(
                "modern_minimal_conflict",
                "error",
                "styles",
                f'Modern and Minimal are mutually exclusive; keep "{winner["value"]}" by confidence (ties keep Minimal).',
                kept=winner["value"],
                removed=loser["value"],
                modernConfidence=modern_score,
                minimalConfidence=minimal_score,
            )
        )

    eras = [style for style in styles if style.get("dimension") == "era"]
    if any(style["value"].casefold() == "modern" for style in eras) and any(
        style["value"].casefold() in {"retro", "futuristic"} for style in eras
    ):
        issues.append(_issue("modern_with_distinctive_era", "warning", "styles", "Modern appears with a more distinctive era and needs human review."))

    by_dimension: dict[str, list[str]] = {}
    for style in styles:
        dimension = style.get("dimension") or "unassigned"
        by_dimension.setdefault(dimension, []).append(style["value"])
    for dimension, values in by_dimension.items():
        if len(values) > 1:
            issues.append(
                _issue(
                    "multiple_styles_same_dimension",
                    "warning",
                    "styles",
                    f"Multiple {dimension} styles need human review: {', '.join(values)}.",
                    dimension=dimension,
                    values=values,
                )
            )

    fallback_names = {value.casefold() for value in STYLE_FALLBACK_VALUES}
    first_fallback = next((index for index, style in enumerate(styles) if style["value"].casefold() in fallback_names), None)
    if first_fallback is not None and any(style["value"].casefold() not in fallback_names for style in styles[first_fallback + 1 :]):
        issues.append(_issue("generic_style_precedes_distinctive", "warning", "styles", "Generic fallback styles must follow distinctive styles."))
        classification["styles"] = [style for style in styles if style["value"].casefold() not in fallback_names] + [
            style for style in styles if style["value"].casefold() in fallback_names
        ]
        styles = classification["styles"]

    fallback_styles = [style for style in styles if style["value"].casefold() in fallback_names]
    if len(fallback_styles) > 2:
        ranked = sorted(
            enumerate(fallback_styles),
            key=lambda pair: (-_style_confidence(normalized["confidence"], pair[1]), pair[0]),
        )
        keep_names = {pair[1]["value"].casefold() for pair in ranked[:2]}
        classification["styles"] = [
            style for style in styles if style["value"].casefold() not in fallback_names or style["value"].casefold() in keep_names
        ]
        issues.append(_issue("generic_style_limit_exceeded", "error", "styles", "At most two Modern/Minimal/Professional fallback styles are allowed."))

    evidence = normalized["evidence"] if isinstance(normalized["evidence"], dict) else {}
    evidence_keys = {
        "pageType": [classification["pageType"]] if classification["pageType"] else [],
        "sectionTypes": classification["sectionTypes"],
        "containedSectionTypes": classification["containedSectionTypes"],
        "industries": classification["industries"],
        "layouts": classification["layouts"],
        "elements": classification["elements"],
        "colors": classification["colors"],
        "typography": classification["typography"],
    }
    for field, values in evidence_keys.items():
        field_evidence = evidence.get(field)
        for value in values:
            if isinstance(field_evidence, dict):
                match = next((item for key, item in field_evidence.items() if str(key).casefold() == value.casefold()), None)
            else:
                match = field_evidence
            if not _has_evidence(match):
                issues.append(_issue("missing_taxonomy_evidence", "warning", field, f'"{value}" has no concrete evidence.', value=value))
    style_evidence = evidence.get("styles") if isinstance(evidence.get("styles"), dict) else {}
    for style in classification["styles"]:
        keys = (f'{style.get("dimension") or ""}:{style["value"]}', style["value"])
        match = next(
            (item for key, item in style_evidence.items() if str(key).casefold() in {candidate.casefold() for candidate in keys}),
            None,
        )
        if not _has_evidence(match):
            issues.append(_issue("missing_taxonomy_evidence", "warning", "styles", f'"{style["value"]}" has no concrete evidence.', value=style["value"]))

    errors = sum(1 for issue in issues if issue["severity"] == "error")
    warnings = sum(1 for issue in issues if issue["severity"] == "warning")
    status = "invalid" if errors else "needs_review" if warnings else "valid"
    validation = {
        "status": status,
        "policyVersion": POLICY_VERSION,
        "taxonomySnapshot": (taxonomy or {}).get("snapshot") or "",
        "auditedAt": now_iso(),
        "issueCounts": {"error": errors, "warning": warnings, "info": len(issues) - errors - warnings},
        "issues": issues,
    }
    suggested["schemaVersion"] = MIRROR_SCHEMA_VERSION
    suggested["policyVersion"] = POLICY_VERSION
    suggested["taxonomySnapshot"] = (taxonomy or {}).get("snapshot") or normalized.get("taxonomySnapshot") or ""
    suggested["validation"] = validation
    return {"validation": validation, "normalized": normalized, "suggested": suggested}


def default_expected_from_mirror(mirror: dict[str, Any], taxonomy: dict[str, Any] | None = None) -> dict[str, Any]:
    audit = audit_mirror_data(mirror, taxonomy)
    suggested = audit["suggested"]
    return {
        "uiContext": copy.deepcopy(suggested["uiContext"]),
        "contentMap": copy.deepcopy(suggested["contentMap"]),
        "contentCoverage": suggested["contentCoverage"],
        "classification": copy.deepcopy(suggested["classification"]),
        "colorWeights": copy.deepcopy(suggested["colorWeights"]),
    }


def expected_diff_fields(mirror: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    source = adapt_mirror_data(mirror)
    candidate = {
        "uiContext": _split_legacy_context((expected or {}).get("uiContext")),
        "contentMap": _normalize_content_map((expected or {}).get("contentMap")),
        "contentCoverage": str((expected or {}).get("contentCoverage") or ""),
        "classification": normalize_classification((expected or {}).get("classification")),
        "colorWeights": copy.deepcopy((expected or {}).get("colorWeights") or {}),
    }
    fields: list[str] = []
    for field in ("uiContext", "contentMap", "contentCoverage", "colorWeights"):
        if canonical_json(source[field]) != canonical_json(candidate[field]):
            fields.append(field)
    for field in normalize_classification({}):
        if canonical_json(source["classification"][field]) != canonical_json(candidate["classification"][field]):
            fields.append(f"classification.{field}")
    return fields


def review_revision(review: dict[str, Any]) -> str:
    source = {key: value for key, value in review.items() if key not in {"revision", "updatedAt", "appliedAt"}}
    return sha256_json(source)


def build_review_payload(
    *,
    source_item_id: str,
    mirror: dict[str, Any],
    expected: dict[str, Any],
    taxonomy: dict[str, Any] | None,
    status: str = "draft",
    existing_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in {"draft", "applied", "conflict"}:
        raise ValueError(f"Unsupported review status: {status}")
    timestamp = now_iso()
    review = {
        "schemaVersion": REVIEW_SCHEMA_VERSION,
        "status": status,
        "sourceItemId": source_item_id,
        "sourceAnalysisFingerprint": mirror_fingerprint(mirror),
        "sourceImageFingerprint": str(mirror.get("imageFingerprint") or ""),
        "taxonomySnapshot": (taxonomy or {}).get("snapshot") or "",
        "policyVersion": POLICY_VERSION,
        "expected": copy.deepcopy(expected),
        "createdAt": (existing_review or {}).get("createdAt") or timestamp,
        "updatedAt": timestamp,
        "appliedAt": timestamp if status == "applied" else (existing_review or {}).get("appliedAt"),
    }
    review["revision"] = review_revision(review)
    return review


def render_review_block(review: dict[str, Any]) -> str:
    return (
        f"{REVIEW_START}\n{REVIEW_HEADING}\n\n```json\n"
        f"{canonical_json(review)}\n"
        f"```\n{REVIEW_END}"
    )


def merge_review_block(annotation: str, review: dict[str, Any]) -> str:
    text = str(annotation or "")
    marker_pattern = re.compile(
        rf"\n*{re.escape(REVIEW_START)}.*?{re.escape(REVIEW_END)}\n*",
        flags=re.DOTALL,
    )
    text = re.sub(marker_pattern, "\n", text)
    heading_pattern = re.compile(
        rf"\n*{re.escape(REVIEW_HEADING)}\s*```json\s*\{{.*?\}}\s*```\n*",
        flags=re.DOTALL,
    )
    text = re.sub(heading_pattern, "\n", text).strip()
    block = render_review_block(review)
    return f"{text}\n\n{block}".strip() if text else block


def expected_to_tags(expected: dict[str, Any]) -> list[str]:
    classification = normalize_classification((expected or {}).get("classification"))
    tags: list[str] = []
    if classification["pageType"]:
        tags.append(f'uibook:page:{classification["pageType"]}')
    tags.extend(f"uibook:section:{value}" for value in classification["sectionTypes"])
    tags.extend(f"uibook:contains-section:{value}" for value in classification["containedSectionTypes"])
    tags.extend(f"uibook:industry:{value}" for value in classification["industries"])
    tags.extend(f"uibook:layout:{value}" for value in classification["layouts"])
    tags.extend(f"uibook:elements:{value}" for value in classification["elements"])
    for style in classification["styles"]:
        if style["dimension"]:
            tags.append(f'uibook:style:{style["dimension"]}:{style["value"]}')
        else:
            tags.append(f'uibook:style:{style["value"]}')
    tags.extend(f"uibook:colors:{value}" for value in classification["colors"])
    tags.extend(f"uibook:typography:{value}" for value in classification["typography"])
    return list(dict.fromkeys(tags))


def tag_diff(current_tags: list[str], expected: dict[str, Any]) -> dict[str, list[str]]:
    current_uibook = [tag for tag in current_tags if str(tag).startswith("uibook:")]
    desired = expected_to_tags(expected)
    current_set = set(current_uibook)
    desired_set = set(desired)
    return {
        "add": [tag for tag in desired if tag not in current_set],
        "remove": [tag for tag in current_uibook if tag not in desired_set],
        "keep": [tag for tag in current_uibook if tag in desired_set],
    }


def merge_expected_tags(current_tags: list[str], expected: dict[str, Any]) -> list[str]:
    unrelated = [tag for tag in current_tags if not str(tag).startswith("uibook:")]
    return unrelated + expected_to_tags(expected)
