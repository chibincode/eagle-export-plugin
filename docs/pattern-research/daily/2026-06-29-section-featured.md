# Daily Pattern Review: 2026-06-29

Source window:

- Eagle window: recent 30 from `Section_Featured 产品功能亮点`
- Candidate count: 30
- Processed count: 30
- Skipped count: 1 unsupported video placeholder
- Main folders seen: `Section_Featured 产品功能亮点`

## Summary

- `Section_Featured` is not one pattern; it is a broad container for several feature-section intentions.
- The strongest repeated structure is `capability-overview / equal-card-grid`, appearing 9 times across different visual materials.
- `content_style` should stay a modifier. The same structure appears as illustration-led, screenshot-led, text-led, data-led, and mixed-media.
- Product screenshots are not automatically the pattern. A screenshot can support overview, workflow explanation, deep dive, or proof.
- Long pages should not get a forced Pattern Layer signature in v1.

## Category Mix

| Category | Count | Notes |
|---|---:|---|
| Section_Featured | 30 | 29 image screenshots and 1 unsupported video placeholder |

## Repeated Pattern Signals

| section_type | message_intent | structure_pattern | count | example ranks | confidence |
|---|---|---|---:|---|---|
| Features | capability-overview | equal-card-grid | 9 | 10, 11, 15, 20, 21, 23, 26, 27, 30 | high |
| Features | workflow-explainer | multi-panel-workflow-dashboard | 5 | 3, 8, 13, 25, 28 | high |
| Features | single-capability-deep-dive | centered-product-panel | 4 | 2, 7, 17, 22 | high |
| Features | proof-backed-benefit | dashboard-proof-panel | 3 | 1, 24, 29 | high |

## New Observations

- Observation: ecosystem-oriented feature sections may need a separate pattern.
  - evidence: ranks 4 and 5 both explain apps, tools, or connected systems.
  - candidate name: `ecosystem-capability / app-ecosystem-grid`
  - why it is not promoted yet: only 2 examples in this sample.

- Observation: two-card action comparison exists inside feature sections.
  - evidence: rank 12 compares buying and transferring a domain.
  - candidate name: `comparison-support / two-card-comparison-panel`
  - why it is not promoted yet: only 1 example.

- Observation: split copy plus product/architecture panel may become a deep-dive structure.
  - evidence: ranks 16 and 19 use a split layout for one focused capability.
  - candidate name: `single-capability-deep-dive / split-copy-product-panel`
  - why it is not promoted yet: only 2 examples.

## Registry Updates Suggested

| action | pattern_id | reason | examples |
|---|---|---|---|
| promote-candidate | `features.capability-overview.equal-card-grid` | 9 examples, different material strategies | 10, 11, 15, 20, 21, 23, 26, 27, 30 |
| promote-candidate | `features.workflow-explainer.multi-panel-workflow-dashboard` | 5 examples of complex feature/system explanation | 3, 8, 13, 25, 28 |
| promote-candidate | `features.single-capability-deep-dive.centered-product-panel` | 4 examples of one capability anchored by product panel | 2, 7, 17, 22 |
| promote-candidate | `features.proof-backed-benefit.dashboard-proof-panel` | 3 examples where visible data acts as proof | 1, 24, 29 |
| add-observation | `features.ecosystem-capability.app-ecosystem-grid` | promising but under threshold | 4, 5 |
| add-observation | `features.comparison-support.two-card-comparison-panel` | one clear example | 12 |
| add-observation | `features.single-capability-deep-dive.split-copy-product-panel` | promising but under threshold | 16, 19 |

## Naming Questions

- Should `single-capability-deep-dive` and `deep-dive-showcase` merge?
- Should `dashboard-proof-panel` stay under Features only, or should it also apply to Stats sections?
- Should `app-ecosystem-grid` belong under Features, Integrations, or both?
- Should mobile app feature trios remain inside `equal-card-grid`, or become a modifier such as `mobile-screen-trio`?

## Manual Review Needed

| item_id | reason |
|---|---|
| `MPUM7QRHZHF3B` | unsupported mp4 placeholder; needs representative frame before Pattern Layer analysis |

