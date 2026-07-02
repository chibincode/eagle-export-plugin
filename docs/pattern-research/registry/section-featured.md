# Pattern Registry: Section_Featured

Status: active research  
Source folder: `Section_Featured 产品功能亮点`  
Initial sample: 30 recent Eagle items reviewed on 2026-06-29  
Evidence board: [Section Featured Pattern Discovery](../../pattern-layer-section-featured-discovery.html)

## Registry Rules

- Use `section_type + message_intent + structure_pattern` as the stable registry key.
- Keep `content_style` as a modifier, not as the primary pattern.
- A pattern should repeat across multiple brands before it becomes `candidate`.
- `adopted` means stable enough to guide product Smart Discovery later.
- These entries are research records, not UIBook frontend filters.

## Candidate Patterns

### `features.capability-overview.equal-card-grid`

- status: `candidate`
- section_type: `Features`
- message_intent: `capability-overview`
- structure_pattern: `equal-card-grid`
- first_seen: `2026-06-29`
- sample_count: `9`
- evidence_ranks: `10, 11, 15, 20, 21, 23, 26, 27, 30`
- layout_variants_seen: `grid`, `bento`
- content_styles_seen: `illustration-led`, `screenshot-led`, `text-led`, `data-led`, `mixed-media`

Definition:

Multiple equal-weight cards communicate a broad set of product capabilities. The cards can use different material strategies, but the reusable pattern is the equal-card structure plus capability overview intent.

Use when:

- several features are presented as peers
- each card has its own title or visual subject
- the section helps the viewer quickly scan a capability set

Avoid when:

- one product screenshot dominates and the cards are only supporting details
- the cards compare two or three choices rather than explain a capability range

### `features.workflow-explainer.multi-panel-workflow-dashboard`

- status: `candidate`
- section_type: `Features`
- message_intent: `workflow-explainer`
- structure_pattern: `multi-panel-workflow-dashboard`
- first_seen: `2026-06-29`
- sample_count: `5`
- evidence_ranks: `3, 8, 13, 25, 28`
- layout_variants_seen: `grid`, `split`
- content_styles_seen: `screenshot-led`

Definition:

Multiple panels explain how a complex feature, system state, workflow, or operating model works. It may not show explicit numbered steps, but the panels create a process or system explanation.

Use when:

- several product panels imply a process, sequence, or system model
- the section explains complexity rather than only listing capabilities
- screenshots or diagrams show different operating states

Avoid when:

- panels are merely equal feature cards with no workflow implication
- the section is a simple gallery of examples

### `features.single-capability-deep-dive.centered-product-panel`

- status: `candidate`
- section_type: `Features`
- message_intent: `single-capability-deep-dive`
- structure_pattern: `centered-product-panel`
- first_seen: `2026-06-29`
- sample_count: `4`
- evidence_ranks: `2, 7, 17, 22`
- layout_variants_seen: `centered`, `grid`, `split`
- content_styles_seen: `screenshot-led`

Definition:

One important capability is anchored by a large product mockup or product-like panel. The viewer understands the feature mainly through one dominant product surface.

Use when:

- a single product surface carries the explanation
- surrounding text supports one capability rather than a broad feature set
- the screenshot or mockup is the central proof object

Avoid when:

- the section primarily compares options
- multiple panels imply a workflow or sequence

### `features.proof-backed-benefit.dashboard-proof-panel`

- status: `candidate`
- section_type: `Features`
- message_intent: `proof-backed-benefit`
- structure_pattern: `dashboard-proof-panel`
- first_seen: `2026-06-29`
- sample_count: `3`
- evidence_ranks: `1, 24, 29`
- layout_variants_seen: `split`, `grid`
- content_styles_seen: `data-led`

Definition:

A feature claim is made concrete through visible metrics, charts, financial values, or dashboard data. The product visual behaves as evidence, not only decoration.

Use when:

- visible numbers or charts support the feature claim
- a dashboard, table, KPI row, or financial value is the main proof object
- the benefit would be weaker without the data panel

Avoid when:

- the screenshot is product UI but does not contain measurable evidence
- the section shows analytics only as a decorative background

## Observations Not Yet Promoted

| registry_key | status | why held |
|---|---|---|
| `features.ecosystem-capability.app-ecosystem-grid` | observation | only 2 examples in first sample |
| `features.comparison-support.two-card-comparison-panel` | observation | only 1 example in first sample |
| `features.workflow-explainer.process-diagram-panel` | observation | only 1 example in first sample |
| `features.single-capability-deep-dive.split-copy-product-panel` | observation | only 2 examples in first sample |
| `features.use-case-gallery.visual-example-grid` | observation | only 2 examples in first sample |
