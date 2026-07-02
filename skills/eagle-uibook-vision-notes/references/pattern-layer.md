# UIBook Pattern Layer

This reference defines the Eagle-only Pattern Layer that sits above the existing UIBook taxonomy.

The goal is Smart Discovery: make section inspiration searchable by design intent and reusable structure, not only by classic labels such as `section_type`, `layout`, `elements`, or `style`.

## Scope

- v1 applies to section-level screenshots first.
- Use it for screenshots that are visually a single section, are filed under `Section_*`, or are strongly suggested for a `Section_*` folder after visual inspection.
- Do not force page-level narrative patterns yet. For long page screenshots, full-page scroll captures, or screenshots containing multiple stacked page sections, skip Pattern Layer entirely and keep the normal visual analysis unless the user explicitly asks for experimental page-pattern analysis.
- Keep the storage Eagle-only. Do not add UIBook database fields, filters, or frontend UI for this layer.

## Required Fields

Every section-level Pattern Layer must include these fields:

```md
section_type:
message_intent:
structure_pattern:
layout_variant:
information_sequence:
content_style:
interaction_implication:
design_language_modifier:
similarity_signature:
discovery_note:
evidence:
confidence:
```

## Field Meanings

- `section_type`: existing UIBook taxonomy, such as `Hero`, `Features`, `Pricing`, `Testimonials`, `CTA`, `Stats & Metrics`, `Logos`, or `How it works`.
- `message_intent`: the user's cognition task, such as `attention-capture`, `value-proposition`, `process-explainer`, `capability-overview`, `trust-building`, `comparison`, `conversion-push`, `complexity-reduction`, or `deep-dive-showcase`.
- `structure_pattern`: the reusable structural shape, such as `horizontal-step-flow`, `equal-card-grid`, `centered-product-panel`, `annotated-mockup-panel`, `uniform-logo-grid`, `three-plan-card-matrix`, or `centered-action-band`.
- `layout_variant`: the placement variant or spatial arrangement, such as `3-column grid`, `split`, `centered`, `bento`, `timeline`, `carousel`, `full-bleed`, or `stacked`. This is a modifier, not a core clustering field.
- `information_sequence`: the visible order of meaning, such as `headline -> proof -> CTA`, `image -> caption -> details`, or `step label -> explanation -> visual proof`.
- `content_style`: the primary material strategy, such as `text-led`, `icon-led`, `illustration-led`, `screenshot-led`, `photo-led`, `data-led`, `logo-led`, `video-led`, `3d-led`, or `mixed-media`.
- `interaction_implication`: visible or implied interaction, such as `tabs`, `carousel`, `chat-flow`, `command-input`, `onboarding-selection`, `before-after`, `progress-loading`, or `none-visible`.
- `design_language_modifier`: the visual language modifier, such as `dark-cinematic`, `light-editorial`, `dense-dashboard`, `spacious-premium`, `technical-blueprint`, `playful`, `minimal-monochrome`, or `tactile-object-led`.
- `similarity_signature`: stable combination key for future Smart Discovery.
- `discovery_note`: the intent a user could search for to find this reference.
- `evidence`: at least 3 concrete visible details from the screenshot.
- `confidence`: `high`, `medium`, or `low`, with a short reason.

## Decision Rules

- Decide `message_intent` before `content_style`. The same screenshot-led visual can support a process explainer, a deep feature showcase, or trust proof.
- `content_style` is a material strategy, not the final pattern.
- `layout_variant` is also a modifier. Use it to describe where the structure sits, not to define the core pattern.
- Core similarity should use `section_type / message_intent / structure_pattern`.
- Never claim the pattern is proven to convert, perform better, or be more effective unless data is visible in the screenshot.
- Use visible screenshot evidence first. URL, file name, and Eagle folder are secondary hints only.
- Long pages are out of scope for v1 Pattern Layer. Do not compress multiple page sections into one fake `section_type`, `message_intent`, or `structure_pattern`.
- Concrete screenshot subjects, such as dashboard mockups, avatar grids, photos, diagrams, and logo arrays, belong in `evidence`, not in `similarity_signature`.
- If two sections share structure and intent but differ in color or style, they should still share a close `similarity_signature`.
- If two sections share style but solve different cognition tasks, they should not be considered close patterns.
- Avoid one-off poetic pattern names. Prefer compact, reusable nouns that could group at least 3 examples later.
- If the evidence cannot support 3 concrete bullets, set `pattern_confidence: low` and do not treat the item as a candidate formal pattern.

## Section Featured Research

For feature-section screenshots, especially images from `Section_Featured 产品功能亮点`, also consult [section-featured-patterns.md](section-featured-patterns.md).

The first real-sample pass found these candidate clusters:

- `capability-overview / equal-card-grid`
- `workflow-explainer / multi-panel-workflow-dashboard`
- `single-capability-deep-dive / centered-product-panel`
- `proof-backed-benefit / dashboard-proof-panel`

Use these as working candidates only when the visible screenshot evidence supports them. They should guide consistent naming, but they are not final product taxonomy values.

## Dynamic Learning Loop

Pattern Layer outputs are per-image evidence. Cross-image synthesis belongs in the Pattern Learning System, documented in [pattern-learning-system.md](pattern-learning-system.md).

Use daily reviews and registry entries to decide whether a repeated `message_intent + structure_pattern` should become an observation, candidate, adopted pattern, or deprecated name.

## Standard Output

```md
## UIBook Pattern Layer

### Pattern Profile
- section_type:
- message_intent:
- structure_pattern:
- layout_variant:
- information_sequence:
- content_style:
- interaction_implication:
- design_language_modifier:

### Similarity Signature
`section_type / message_intent / structure_pattern`

### Discovery Note
- match_when:
- avoid_when:

### Evidence
- ...
- ...
- ...

### Confidence
- pattern_confidence:
- reason:
```

## Test Scenarios

- Features grid: multiple equivalent cards should become `capability-overview / equal-card-grid`, not only `icon-led`.
- How it works: visible steps, arrows, process diagrams, or ordered explanations should become `process-explainer / horizontal-step-flow`.
- Screenshot showcase: a large product UI with callouts should become `deep-dive-showcase / annotated-mockup-panel`.
- Logo wall: customer or integration logo arrays should become `trust-building / uniform-logo-grid`.
- Pricing: plan cards and package comparison should become `comparison / three-plan-card-matrix`.
- CTA: short headline plus action button should become `conversion-push / centered-action-band`.
- Similarity: visually different sections with the same structure and intent should be grouped closer than visually similar sections with different intent.
