# Pattern Learning System

This reference defines the dynamic research loop for turning repeated Eagle screenshot analysis into durable UIBook pattern knowledge.

Use this reference when the user asks for daily learning, pattern research, recurring synthesis, category-level pattern summaries, or any workflow where screenshot analysis should accumulate beyond per-image Eagle notes.

## Goal

The goal is to let daily Eagle analysis produce reusable design intelligence:

```text
per-image evidence -> daily pattern review -> pattern registry -> HTML review surface -> future Smart Discovery
```

Do not treat this as another flat filter taxonomy. It is a research loop for discovering reusable intent + structure patterns from real screenshots.

## Storage Locations

Use these repository paths:

```text
docs/pattern-research/
  README.md
  pattern-learning-system.html
  daily/
    YYYY-MM-DD.md
  templates/
    daily-pattern-review.md
  registry/
    section-featured.md
    section-hero.md
    section-pricing.md
```

Per-image analysis remains in Eagle annotations. Cross-image synthesis belongs in the repository research files, not inside Eagle item notes.

## Layers

### Image Evidence Layer

Written to Eagle annotation.

Contains:

- bilingual visual analysis
- concrete visible evidence
- section-level `UIBook Pattern Layer` when applicable

This layer must not promote official patterns by itself.

### Daily Discovery Layer

Written to `docs/pattern-research/daily/YYYY-MM-DD.md`.

Contains:

- category mix
- repeated `message_intent + structure_pattern` signals
- new observations
- suggested registry updates
- naming questions
- manual review items

Daily reviews are append-only research records.

### Pattern Registry Layer

Written under `docs/pattern-research/registry/`.

A registry entry can move through:

```text
observation -> candidate -> adopted -> deprecated
```

Promotion should be conservative. The default promotion key is:

```text
section_type + message_intent + structure_pattern
```

First-pass discovery can cluster by:

```text
message_intent + structure_pattern
```

### HTML Review Surface

Use HTML when the user needs to read and discuss the system.

Current entry point:

```text
docs/pattern-research/pattern-learning-system.html
```

Focused studies, such as `docs/pattern-layer-section-featured-discovery.html`, are evidence boards that support the registry.

## Daily Review Procedure

After a meaningful batch of Eagle screenshots has been analyzed:

1. Review the per-image Pattern Layer outputs.
2. Group rows by `section_type + message_intent + structure_pattern`.
3. Count repeated combinations.
4. Separate stable patterns from weak one-off observations.
5. Compare against existing registry entries.
6. Write a daily review from `templates/daily-pattern-review.md`.
7. Suggest registry updates, but do not auto-promote low-confidence findings.

## Registry Update Rules

Add or update a registry entry only when:

- the visible screenshot evidence is specific
- the pattern repeats across samples
- the name describes reusable structure, not style or product content
- ambiguity and merge/rename questions are documented
- the entry would help future Smart Discovery

Do not promote patterns only because they share:

- dark mode
- screenshot-led material
- a similar product category
- one brand's repeated design system
- a concrete subject such as phone mockups or dashboards

Those details belong in modifiers, evidence, or visual memory cues.

## Relationship To Eagle Notes

Eagle annotations answer:

```text
What is visible in this screenshot?
```

Daily reviews answer:

```text
What did today's screenshots teach us across examples?
```

The registry answers:

```text
Which reusable patterns are stable enough to remember and search later?
```

Keep these layers separate.

