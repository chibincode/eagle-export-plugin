# Changelog

This changelog records user-visible releases of `eagle-uibook-vision-notes`.
It is separate from the Mirror and Review schema versions: schemas describe
stored data; a Skill release describes the complete behavior installed on a
device.

## [0.5.0] - 2026-08-28

### Added

- A versioned `uibook-local-parity` profile that follows UIBook's OCR-first
  order: UI Context and Content Map before taxonomy classification.
- A read-only `analysis-context` command that loads the live public UIBook
  taxonomy, style dimensions, descriptions, and blocklists before local
  conversation analysis.
- Deterministic audit warnings for thin bilingual UI Context and stale local
  analysis policy versions.

### Changed

- UI Context is now an information-dense bilingual visual-search corpus with a
  usual target of 100-220 English words plus a faithful Chinese paragraph.
- The local analysis policy is now `2026-08-28.1`.

### Compatibility

- Mirror Data schema: v3
- Human Review schema: v1
- Policy: `2026-08-28.1`

### Boundary

- The existing Eagle to Lovable cloud-analysis sync remains unchanged and can
  continue as the control mode for parallel testing.
- Lovable's private `prompt_templates`, `tag_rules`, and `tag_corrections` stay
  cloud-only when the local mode has only a public Supabase key. This release
  claims parity for OCR/context rules and the public taxonomy, not exact private
  cloud-prompt parity.

## [0.4.0] - 2026-08-26

### Added

- A machine-readable `skill-manifest.json` with the Skill release, supported
  contracts, and integrity checksums for the executable files.
- `scripts/release.py version` for a concise local release report.
- `scripts/release.py doctor` to verify an installed package and compare it
  with a local source copy before updating another Mac.

### Compatibility

- Mirror Data schema: v3
- Human Review schema: v1
- Policy: `2026-08-17.1`

### Upgrade

After copying the package into `~/.codex/skills/eagle-uibook-vision-notes`, run
`python3 scripts/release.py doctor --source /path/to/source/skill` from the
installed Skill directory. Do not treat a matching Mirror schema alone as
proof that the full Skill is current.
