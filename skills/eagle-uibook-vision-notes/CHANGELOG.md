# Changelog

This changelog records user-visible releases of `eagle-uibook-vision-notes`.
It is separate from the Mirror and Review schema versions: schemas describe
stored data; a Skill release describes the complete behavior installed on a
device.

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
