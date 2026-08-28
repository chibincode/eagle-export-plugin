import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "uibook_contract.py"
SPEC = importlib.util.spec_from_file_location("uibook_contract", MODULE_PATH)
contract = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(contract)


def taxonomy():
    rows = [
        ("page_type", "Homepage", None),
        ("section_type", "Hero", None),
        ("industry", "AI Technology", None),
        ("layout", "Split", None),
        ("elements", "Button", None),
        ("style", "Modern", "era"),
        ("style", "Minimal", "generic"),
        ("style", "Futuristic", "era"),
        ("style", "Graphic", "surface"),
        ("style", "Professional", "generic"),
        ("style_blocklist", "Responsive", None),
        ("colors", "White", None),
        ("typography", "Sans-serif", None),
    ]
    return contract.build_taxonomy(
        [
            {
                "category": category,
                "value": value,
                "description": None,
                "dimension": dimension,
                "display_order": index,
            }
            for index, (category, value, dimension) in enumerate(rows)
        ]
    )


def mirror(styles, confidence=None):
    return {
        "schemaVersion": 2,
        "sourceItemId": "ITEM",
        "imageFingerprint": "sha256:image",
        "entityType": "website",
        "uiContext": "English text 中文 Context：中文文本",
        "contentMap": [],
        "classification": {
            "pageType": "Homepage",
            "sectionTypes": [],
            "containedSectionTypes": [],
            "industries": ["AI Technology"],
            "layouts": [],
            "elements": ["Button"],
            "styles": styles,
            "colors": ["White"],
            "typography": ["Sans-serif"],
        },
        "confidence": {"styles": confidence or {}},
        "evidence": {
            "pageType": ["Root URL and complete page framing are visible."],
            "industries": {"AI Technology": ["AI product copy is visible."]},
            "elements": {"Button": ["A labeled primary button is visible."]},
            "styles": {
                f'{style["dimension"]}:{style["value"]}': [f'{style["value"]} evidence.']
                for style in styles
            },
            "colors": {"White": ["White covers the page background."]},
            "typography": {"Sans-serif": ["Headings and body use sans-serif forms."]},
        },
    }


class ContractTests(unittest.TestCase):
    def test_local_analysis_context_preserves_legacy_cloud_sync_boundary(self):
        context = contract.build_local_analysis_context(taxonomy(), "page")
        self.assertEqual(context["analysisMode"], "eagle_local")
        self.assertEqual(context["entityType"], "website")
        self.assertEqual(context["pipeline"][0]["outputs"][0], "uiContext")
        self.assertEqual(context["contentMapLimit"], 8)
        self.assertEqual(context["legacyCloudSync"], "unchanged")
        self.assertEqual(
            context["cloudOnlyInputs"]["tag_corrections"],
            "not_read_by_local_public_key_mode",
        )

    def test_thin_context_is_flagged_for_local_parity_review(self):
        source = mirror([])
        source["schemaVersion"] = 3
        source["analysisModel"] = "test-model"
        source["analyzedAt"] = "2026-08-28T00:00:00+08:00"
        source["taxonomySnapshot"] = taxonomy()["snapshot"]
        source["policyVersion"] = contract.POLICY_VERSION
        source["uiContext"] = {"en": "Short context.", "zh": "很短的上下文。"}
        source["contentCoverage"] = "single_screen"
        source["colorWeights"] = {"White": 100}
        source["validation"] = {}
        result = contract.audit_mirror_data(source, taxonomy())
        self.assertIn("thin_ui_context", [issue["code"] for issue in result["validation"]["issues"]])

    def test_stale_analysis_policy_is_reported(self):
        source = mirror([])
        source["policyVersion"] = "2026-08-17.1"
        result = contract.audit_mirror_data(source, taxonomy())
        self.assertIn("stale_policy_version", [issue["code"] for issue in result["validation"]["issues"]])

    def test_v2_context_is_adapted_without_mutating_source(self):
        source = mirror([])
        adapted = contract.adapt_mirror_data(source)
        self.assertEqual(adapted["uiContext"], {"en": "English text", "zh": "中文文本"})
        self.assertIsInstance(source["uiContext"], str)

    def test_modern_minimal_uses_higher_confidence(self):
        styles = [
            {"dimension": "era", "value": "Modern"},
            {"dimension": "generic", "value": "Minimal"},
        ]
        result = contract.audit_mirror_data(
            mirror(styles, {"era:Modern": "high", "generic:Minimal": "medium"}), taxonomy()
        )
        values = [style["value"] for style in result["suggested"]["classification"]["styles"]]
        self.assertEqual(values, ["Modern"])
        self.assertIn("modern_minimal_conflict", [issue["code"] for issue in result["validation"]["issues"]])

    def test_modern_minimal_tie_keeps_minimal(self):
        styles = [
            {"dimension": "era", "value": "Modern"},
            {"dimension": "generic", "value": "Minimal"},
        ]
        result = contract.audit_mirror_data(mirror(styles), taxonomy())
        self.assertEqual(
            [style["value"] for style in result["suggested"]["classification"]["styles"]],
            ["Minimal"],
        )
        expected = contract.default_expected_from_mirror(mirror(styles), taxonomy())
        self.assertIn("classification.styles", contract.expected_diff_fields(mirror(styles), expected))

    def test_generic_styles_are_reordered_after_distinctive(self):
        styles = [
            {"dimension": "generic", "value": "Minimal"},
            {"dimension": "surface", "value": "Graphic"},
        ]
        result = contract.audit_mirror_data(mirror(styles), taxonomy())
        self.assertEqual(
            [style["value"] for style in result["suggested"]["classification"]["styles"]],
            ["Graphic", "Minimal"],
        )

    def test_unknown_value_is_reported(self):
        source = mirror([])
        source["classification"]["elements"] = ["Unknown Widget"]
        result = contract.audit_mirror_data(source, taxonomy())
        self.assertIn("unknown_taxonomy_value", [issue["code"] for issue in result["validation"]["issues"]])

    def test_v3_requires_contract_metadata_and_complete_content_map(self):
        source = mirror([])
        source["schemaVersion"] = 3
        source["uiContext"] = {"en": "English", "zh": "中文"}
        source["contentMap"] = [{"order": 1, "region": "Hero", "position": "top", "summaryEn": "Visible hero"}]
        source["colorWeights"] = {"White": 75}
        source["validation"] = {}
        result = contract.audit_mirror_data(source, taxonomy())
        codes = [issue["code"] for issue in result["validation"]["issues"]]
        self.assertIn("missing_required_field", codes)
        self.assertIn("incomplete_content_map_entry", codes)
        self.assertIn("color_weight_total", codes)

    def test_review_block_preserves_analysis_and_manual_notes(self):
        source = "manual\n\n## UIBook Mirror Data\n```json\n{}\n```\n\nAI text"
        review = contract.build_review_payload(
            source_item_id="ITEM",
            mirror=mirror([]),
            expected=contract.default_expected_from_mirror(mirror([]), taxonomy()),
            taxonomy=taxonomy(),
        )
        merged = contract.merge_review_block(source, review)
        self.assertIn("manual", merged)
        self.assertIn("## UIBook Mirror Data", merged)
        self.assertIn("AI text", merged)
        self.assertEqual(contract.extract_human_review(merged)["status"], "draft")
        replaced = contract.merge_review_block(merged, {**review, "status": "applied"})
        self.assertEqual(replaced.count(contract.REVIEW_HEADING), 1)

    def test_expected_tags_preserve_dimensions(self):
        expected = contract.default_expected_from_mirror(
            mirror([{"dimension": "surface", "value": "Graphic"}]), taxonomy()
        )
        tags = contract.expected_to_tags(expected)
        self.assertIn("uibook:page:Homepage", tags)
        self.assertIn("uibook:style:surface:Graphic", tags)
        self.assertIn("uibook:elements:Button", tags)


if __name__ == "__main__":
    unittest.main()
