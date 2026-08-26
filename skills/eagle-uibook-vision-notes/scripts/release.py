#!/usr/bin/env python3
"""Read and verify the Eagle UIBook Vision Notes release package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


DEFAULT_SKILL_DIR = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "skill-manifest.json"
REQUIRED_COMPATIBILITY_KEYS = (
    "mirrorSchemaVersion",
    "reviewSchemaVersion",
    "policyVersion",
)


class ReleaseError(RuntimeError):
    """Raised when a release package cannot be trusted or compared."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(skill_dir: Path) -> dict[str, Any]:
    manifest_path = skill_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ReleaseError(f"Release manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ReleaseError(f"Release manifest is not valid JSON: {manifest_path}") from error

    if not isinstance(manifest, dict):
        raise ReleaseError("Release manifest must be a JSON object")
    if not isinstance(manifest.get("name"), str) or not manifest["name"].strip():
        raise ReleaseError("Release manifest is missing name")
    if not isinstance(manifest.get("version"), str) or not parse_version(manifest["version"]):
        raise ReleaseError("Release manifest version must use semantic versioning, for example 0.4.0")
    compatibility = manifest.get("compatibility")
    if not isinstance(compatibility, dict):
        raise ReleaseError("Release manifest is missing compatibility")
    missing = [key for key in REQUIRED_COMPATIBILITY_KEYS if compatibility.get(key) in (None, "")]
    if missing:
        raise ReleaseError("Release manifest is missing compatibility fields: " + ", ".join(missing))
    files = ((manifest.get("integrity") or {}).get("files"))
    if not isinstance(files, dict) or not files:
        raise ReleaseError("Release manifest is missing integrity file checksums")
    return manifest


def parse_version(value: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-[0-9A-Za-z.-]+)?", value.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def integrity_report(skill_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    expected_files = manifest["integrity"]["files"]
    files = []
    valid = True
    for relative_path, expected_sha256 in sorted(expected_files.items()):
        path = skill_dir / relative_path
        if not path.is_file():
            files.append({"path": relative_path, "status": "missing"})
            valid = False
            continue
        actual_sha256 = sha256_file(path)
        status = "valid" if actual_sha256 == expected_sha256 else "modified"
        files.append(
            {
                "path": relative_path,
                "status": status,
                "expectedSha256": expected_sha256,
                "actualSha256": actual_sha256,
            }
        )
        valid = valid and status == "valid"
    return {"status": "valid" if valid else "invalid", "files": files}


def describe_release(skill_dir: Path) -> dict[str, Any]:
    resolved_dir = skill_dir.expanduser().resolve()
    manifest = load_manifest(resolved_dir)
    return {
        "skillDir": str(resolved_dir),
        "name": manifest["name"],
        "version": manifest["version"],
        "releasedAt": manifest.get("releasedAt"),
        "source": manifest.get("source") or {},
        "compatibility": manifest["compatibility"],
        "integrity": integrity_report(resolved_dir, manifest),
    }


def compare_releases(installed: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    if installed["name"] != source["name"]:
        return {"status": "incompatible", "reason": "Skill names do not match."}
    if installed["compatibility"] != source["compatibility"]:
        return {
            "status": "incompatible",
            "reason": "Stored-data compatibility differs; follow the newer release migration notes before updating.",
        }
    installed_version = parse_version(installed["version"])
    source_version = parse_version(source["version"])
    assert installed_version and source_version
    if installed_version == source_version:
        return {"status": "current", "reason": "Release versions and compatibility match."}
    if installed_version < source_version:
        return {"status": "outdated", "reason": "The source copy has a newer compatible release."}
    return {"status": "ahead_of_source", "reason": "The installed copy is newer than the selected source copy."}


def print_report(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return

    release = payload["release"]
    compatibility = release["compatibility"]
    print(f"{release['name']} v{release['version']} ({release.get('releasedAt') or 'undated'})")
    print(
        "Contracts: "
        f"Mirror v{compatibility['mirrorSchemaVersion']} · "
        f"Review v{compatibility['reviewSchemaVersion']} · "
        f"Policy {compatibility['policyVersion']}"
    )
    print(f"Integrity: {release['integrity']['status']}")
    for file in release["integrity"]["files"]:
        print(f"- {file['path']}: {file['status']}")
    comparison = payload.get("comparison")
    if comparison:
        print(f"Comparison: {comparison['status']} · {comparison['reason']}")


def cmd_version(args: argparse.Namespace) -> int:
    print_report({"release": describe_release(Path(args.skill_dir))}, args.json)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    installed = describe_release(Path(args.skill_dir))
    payload: dict[str, Any] = {"release": installed}
    exit_code = 0
    if installed["integrity"]["status"] != "valid":
        payload["comparison"] = {
            "status": "integrity_failed",
            "reason": "Repair or reinstall this Skill copy before running an analysis.",
        }
        exit_code = 2
    elif args.source:
        source = describe_release(Path(args.source))
        payload["source"] = source
        payload["comparison"] = compare_releases(installed, source)
        if source["integrity"]["status"] != "valid":
            payload["comparison"] = {
                "status": "source_integrity_failed",
                "reason": "The selected source copy is incomplete or modified.",
            }
            exit_code = 2
        elif payload["comparison"]["status"] in {"outdated", "incompatible"}:
            exit_code = 1
    else:
        payload["comparison"] = {
            "status": "source_not_checked",
            "reason": "Pass --source to compare this installed Skill with a checked-out source copy.",
        }
    print_report(payload, args.json)
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect the Eagle UIBook Vision Notes release package.")
    parser.add_argument("--skill-dir", default=str(DEFAULT_SKILL_DIR), help="Skill directory to inspect")
    subparsers = parser.add_subparsers(dest="command", required=True)

    version = subparsers.add_parser("version", help="Show the installed Skill release and integrity state")
    version.add_argument("--json", action="store_true", help="Emit JSON instead of plain text")
    version.set_defaults(func=cmd_version)

    doctor = subparsers.add_parser("doctor", help="Verify this Skill and optionally compare it with a source copy")
    doctor.add_argument("--source", help="Path to another eagle-uibook-vision-notes Skill directory")
    doctor.add_argument("--json", action="store_true", help="Emit JSON instead of plain text")
    doctor.set_defaults(func=cmd_doctor)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        return args.func(args)
    except ReleaseError as error:
        print(f"Release check failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
