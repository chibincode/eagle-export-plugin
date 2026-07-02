# UIBook Pattern Learning System

This folder turns repeated Eagle screenshot analysis into a durable Pattern Learning System.

The goal is not to create more flat filters. The goal is to let daily visual analysis accumulate into reusable design knowledge that helps designers find similar inspiration by intent and structure.

## System Layers

```text
Eagle screenshot analysis
-> per-image Pattern Layer
-> daily pattern review
-> pattern registry update
-> HTML review surface
-> future Smart Discovery
```

## What Each Layer Does

### 1. Image Evidence Layer

Stored in Eagle annotations.

Each image analysis should stay grounded in visible screenshot evidence:

- visible text
- layout
- components
- color usage
- visual memory cues
- section-level Pattern Layer when applicable

This layer should not promote official patterns by itself.

### 2. Daily Discovery Layer

Stored under `docs/pattern-research/daily/`.

After a batch of Eagle images is analyzed, create one daily review that summarizes:

- which page or section categories appeared
- which `message_intent + structure_pattern` combinations repeated
- which names look stable
- which names should be merged or split
- which observations are too weak to promote

### 3. Pattern Registry Layer

Stored under `docs/pattern-research/registry/`.

The registry is the long-lived source of pattern candidates. A registry entry can move through:

```text
observation -> candidate -> adopted -> deprecated
```

Promotion should be conservative. A pattern should only become a candidate when it repeats across enough screenshots and brands to feel structurally reusable.

### 4. Review Surface

Use HTML for reading and discussion.

- `pattern-learning-system.html` gives the top-level system view.
- Existing focused studies, such as `pattern-layer-section-featured-discovery.html`, remain as evidence boards.

## Promotion Rules

Default promotion key:

```text
section_type + message_intent + structure_pattern
```

First-pass clustering may use:

```text
message_intent + structure_pattern
```

Use modifiers such as `layout_skeleton`, `content_style`, `design_language_modifier`, and concrete visual subjects as supporting evidence. Do not let them split a pattern too early.

## Daily Review Rule

Every daily review should separate:

- confirmed evidence
- new observations
- candidate promotions
- naming questions
- items that need manual review

Do not update the registry automatically when confidence is low.

