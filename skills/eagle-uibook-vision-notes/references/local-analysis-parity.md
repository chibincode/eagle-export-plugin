# Local UIBook Analysis Parity

Use this profile only for the Eagle-local analysis mode. It does not replace,
modify, or disable the existing Eagle to Lovable cloud-analysis sync path.

The local mode uses the current Codex conversation for image understanding. It
aims for semantic and contract parity with UIBook's OCR-first enrichment flow,
not byte-for-byte parity with the model used by Lovable.

## Required order

Analyze each image in two deliberate stages. Finish Stage 1 before choosing any
UIBook classification values.

### Stage 1: Search corpus

Produce these fields from the screenshot itself:

1. `uiContext`
2. `contentMap`
3. `contentCoverage`
4. the complete visible text used by the human-readable `Visible Text` sections

#### UI Context

Write one English paragraph and one Chinese paragraph containing the same
visible facts.

- Identify whether the artifact is a website/page or a standalone section, its
  likely UI purpose, and its actual spatial structure.
- Describe confidently visible regions in reading order. For tall screenshots,
  mention top, middle, and bottom only when those regions were actually
  inspected at readable detail.
- Name concrete components and what they contain: forms, cards, tables, charts,
  product screenshots, diagrams, flows, people, illustrations, icons, CTAs,
  navigation, and other visible subjects.
- Preserve searchable subject-to-position relationships, such as a workflow
  diagram below a headline or customer portraits in a testimonial grid.
- Include visual design traits only when they help identify or retrieve this
  specific screen.
- State positive visible evidence only. Do not infer hidden interactions,
  unsupported product claims, or negative facts about absent content.

The target is usually 100-220 English words plus a faithful Chinese paragraph.
Use fewer words only when the screenshot genuinely contains less inspectable
evidence. This is an information-dense visual-search corpus, not marketing copy
and not a prose version of the taxonomy tags.

#### Content Map

- Keep only major, confidently distinguishable regions in top-to-bottom order.
- Use at most 8 entries for a website/page and 4 for a section.
- Each entry needs `region`, `position`, `summaryEn`, and `summaryZh`.
- Keep subjects and their spatial relationships in the same entry.
- Use only `top`, `upper-middle`, `middle`, `lower-middle`, or `bottom` for
  `position`.
- Do not invent unreadable regions or add entries to fill the limit.

Use `overview_only` for a tall/full-page or dense screenshot whose small
regions cannot be read confidently from the inspected image. Use
`single_screen` only for a normal viewport or standalone section that was
reviewed as one frame.

#### Visible Text

Capture all readable text in general reading order. Include headings, body
copy, navigation, buttons, badges, form labels, testimonials, pricing, and
footer text. Never reconstruct unreadable copy.

## Stage 2: UIBook classification

Classify only after Stage 1 is complete.

- Run `analysis-context` for the candidate's entity type and use its live public
  taxonomy values, descriptions, style dimensions, and blocklists.
- Treat UI Context as strong supplementary evidence for page/section type and
  concrete patterns such as testimonial cards, pricing tables, FAQ accordions,
  and signup forms.
- Use the URL as a strong page-type signal for website/page records. A non-root
  URL must not silently fall back to `Homepage`.
- For section records, visible content is primary. URL and filename remain weak
  hints.
- Every selected taxonomy value needs screenshot-specific evidence and a
  confidence value.
- Distinctive style values precede generic fallbacks. Preserve style dimensions
  from the live taxonomy.

The local public-key context cannot read UIBook's private `prompt_templates`,
`tag_rules`, or `tag_corrections`. Never claim exact cloud parity when those
inputs are unavailable. The existing Lovable cloud-analysis mode remains the
control path for parallel comparison.

## Final gate

Before Apply, confirm that UI Context, Content Map, the human-readable analysis,
and Mirror classification describe the same screenshot without contradictions.
Run the pure Mirror validator against the same taxonomy snapshot. Do not write
when validation contains an error.
