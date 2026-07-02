# Section Featured Pattern Notes

This reference captures the first real-sample Pattern Layer findings from the Eagle folder `Section_Featured 产品功能亮点`.

Use it as a research guide when analyzing section-level screenshots that visually behave like product feature sections. Do not treat these names as final UIBook taxonomy values yet; they are candidate patterns validated by one folder-level sample.

## Source Sample

- Sample date: 2026-06-29
- Source folder: `Section_Featured 产品功能亮点`
- Sample size: 30 recent Eagle items
- Usable section screenshots: 29 images
- Excluded from promotion: 1 unsupported video placeholder
- Research artifact: `docs/pattern-layer-section-featured-discovery.html`

## Promotion Rule Used

Promote candidates by this key:

```text
message_intent + structure_pattern
```

Do not split the first-pass cluster by `content_style`, visual style, product category, or concrete screenshot subject. Those fields are useful modifiers and evidence, but they should not break apart examples that share the same cognitive task and reusable structure.

## Candidate Clusters

| Candidate cluster key | Count | Common modifiers | Use when visible evidence shows |
|---|---:|---|---|
| `capability-overview / equal-card-grid` | 9 | grid or bento; illustration-led, screenshot-led, text-led, data-led, mixed-media | Multiple equal-weight cards communicate a broad set of product capabilities. |
| `workflow-explainer / multi-panel-workflow-dashboard` | 5 | grid or split; mostly screenshot-led | Multiple panels explain a complex feature, system state, workflow, or operating model. |
| `single-capability-deep-dive / centered-product-panel` | 4 | centered, grid, or split; screenshot-led | One important capability is anchored by a large product mockup or product-like panel. |
| `proof-backed-benefit / dashboard-proof-panel` | 3 | split or grid; data-led | A feature claim is made concrete through metrics, charts, financial values, or dashboard data. |

## How To Apply During Eagle Analysis

For `Section_Featured` or similar feature sections, decide in this order:

```text
visible evidence -> message_intent -> structure_pattern -> layout_variant -> content_style -> confidence
```

Use these guardrails:

- If the section is a broad set of equal feature cards, prefer `capability-overview / equal-card-grid` even when the cards use screenshots, icons, metrics, avatars, or illustrations.
- If the section shows multiple product panels that imply process, sequence, states, or system operation, consider `workflow-explainer / multi-panel-workflow-dashboard`.
- If one product surface dominates and the surrounding text explains one capability, consider `single-capability-deep-dive / centered-product-panel`.
- If the visual object behaves as proof through visible numbers, charts, financial values, or measurable dashboard output, consider `proof-backed-benefit / dashboard-proof-panel`.
- Keep concrete subjects such as phone mockups, desktop dashboards, avatar grids, diagrams, scenery, or screenshots in `Evidence` or `Visual Memory Cues`; do not add them to `similarity_signature`.
- Use `pattern_confidence: medium` when the section could plausibly fit two clusters. Explain the ambiguity in the confidence reason.

## Naming Notes

Prefer names that describe reusable shape:

- `equal-card-grid`
- `multi-panel-workflow-dashboard`
- `centered-product-panel`
- `dashboard-proof-panel`

Avoid names that repeat the intent or overfit a product:

- `feature-icons`
- `screenshot-feature`
- `token-savings-panel`
- `conversion-proof-grid`
- `dark-dashboard-section`

## Non-Promoted Observations

Keep these as observations until they appear at least 3 times across sufficiently different products or brands:

- `ecosystem-capability / app-ecosystem-grid`
- `comparison-support / two-card-comparison-panel`
- `workflow-explainer / process-diagram-panel`
- `single-capability-deep-dive / split-copy-product-panel`
- `use-case-gallery / visual-example-grid`

## Long Page Reminder

Do not apply this reference to a long full-page screenshot as a single Pattern Layer signature. For long pages, write the normal visual analysis only in v1, unless the user explicitly asks for experimental page-level pattern analysis.
