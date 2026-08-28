# UIBook Mirror Data v3

`UIBook Mirror Data` is the machine-readable contract produced from the same
visual evidence as the human-readable Eagle note. It is not a second analysis.

For new Eagle-local analyses, generate `uiContext`, `contentMap`, and
`contentCoverage` first according to
[local-analysis-parity.md](local-analysis-parity.md), then produce
`classification` from the same screenshot evidence and live public taxonomy.
The legacy Lovable cloud-analysis sync remains a separate, unchanged mode.

## Required shape

```json
{
  "schemaVersion": 3,
  "sourceItemId": "EAGLE_ITEM_ID",
  "imageFingerprint": "sha256:...",
  "entityType": "website",
  "analysisModel": "gpt-5.6-sol",
  "analyzedAt": "2026-08-17T12:00:00+08:00",
  "taxonomySnapshot": "sha256:...",
  "policyVersion": "2026-08-17.1",
  "uiContext": { "en": "...", "zh": "..." },
  "contentMap": [],
  "contentCoverage": "single_screen",
  "classification": {
    "pageType": "Homepage",
    "sectionTypes": [],
    "containedSectionTypes": ["Hero"],
    "industries": ["AI Technology"],
    "layouts": [],
    "elements": ["Button"],
    "styles": [{ "dimension": "surface", "value": "Graphic" }],
    "colors": ["White", "Black"],
    "typography": ["Sans-serif"]
  },
  "colorWeights": { "White": 80, "Black": 20 },
  "confidence": {},
  "evidence": {},
  "unmapped": [],
  "validation": {
    "status": "valid",
    "policyVersion": "2026-08-17.1",
    "taxonomySnapshot": "sha256:...",
    "issues": []
  }
}
```

## Compatibility and validation

- v2 remains readable and is never rewritten merely because it was audited.
- v3 must use the live UIBook `config_options` values and dimensions represented
  by `taxonomySnapshot`.
- `Modern` and `Minimal` are mutually exclusive. Keep the higher-confidence
  value; ties and missing confidence keep `Minimal`.
- `Modern` with `Retro` or `Futuristic`, and any other repeated style dimension,
  requires human review rather than silent removal.
- Generic fallback styles must follow distinctive styles. At most two of
  `Modern`, `Minimal`, and `Professional` may remain.
- Content Map entries preserve `order`, `region`, optional `regionZh`,
  `position`, `summaryEn`, and `summaryZh`.
- Website Content Map has at most 8 entries; Section has at most 4.
- Every selected taxonomy value must have screenshot-specific evidence.

The pure validator lives in `scripts/uibook_contract.py`. It does not call a
model or modify Eagle.

Human corrections live in a separate `## UIBook Human Review` v1 block. The
original AI analysis and Mirror Data stay unchanged for traceability.
