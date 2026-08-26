import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "release.py"
SPEC = importlib.util.spec_from_file_location("eagle_uibook_release", MODULE_PATH)
release = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(release)


def write_package(root, version="0.4.0", compatibility=None):
    root = Path(root)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    script = root / "scripts" / "worker.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    manifest = {
        "name": "eagle-uibook-vision-notes",
        "version": version,
        "releasedAt": "2026-08-26",
        "compatibility": compatibility
        or {
            "mirrorSchemaVersion": 3,
            "reviewSchemaVersion": 1,
            "policyVersion": "2026-08-17.1",
        },
        "integrity": {
            "algorithm": "sha256",
            "files": {"scripts/worker.py": release.sha256_file(script)},
        },
    }
    (root / "skill-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


class ReleaseTests(unittest.TestCase):
    def test_integrity_reports_modified_file(self):
        with tempfile.TemporaryDirectory() as directory:
            package = write_package(Path(directory) / "package")
            report = release.describe_release(package)
            self.assertEqual("valid", report["integrity"]["status"])
            (package / "scripts" / "worker.py").write_text("changed\n", encoding="utf-8")
            report = release.describe_release(package)
            self.assertEqual("invalid", report["integrity"]["status"])
            self.assertEqual("modified", report["integrity"]["files"][0]["status"])

    def test_release_comparison_reports_update_and_schema_break(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed = release.describe_release(write_package(root / "installed", version="0.4.0"))
            newer = release.describe_release(write_package(root / "newer", version="0.5.0"))
            incompatible = release.describe_release(
                write_package(
                    root / "incompatible",
                    version="0.5.0",
                    compatibility={
                        "mirrorSchemaVersion": 4,
                        "reviewSchemaVersion": 1,
                        "policyVersion": "2026-08-17.1",
                    },
                )
            )
            self.assertEqual("outdated", release.compare_releases(installed, newer)["status"])
            self.assertEqual("incompatible", release.compare_releases(installed, incompatible)["status"])


if __name__ == "__main__":
    unittest.main()
