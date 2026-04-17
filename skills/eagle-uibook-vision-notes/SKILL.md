---
name: eagle-uibook-vision-notes
description: Find Eagle screenshots that were synced to UIBook within a selected recent time window, hand them off to the current Codex conversation for image understanding, and safely write a structured AI analysis block back to Eagle annotation. Use when Codex should rely on the live chat model's vision ability instead of an API key, while still using local scripts to scan synced items from today, yesterday, the last 3 days, or the last 7 days and update Eagle notes without disturbing manual notes or sync logs.
---

# Eagle UIBook Vision Notes

Use this skill when analysis must come from the current conversation, not from a separate API-driven script.

## First Question

Before running `scan`, first get the current counts for each time window, then ask which time window to use unless the user already specified one.

Use:

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py windows --repo "$PWD"
```

Ask with these exact choices:
- `today`
- `yesterday`
- `last3d`
- `last7d`

Default conversation behavior:
- If the user says only "use the skill" or asks to scan/analyze without a window, ask for the window first.
- If the user already says "today", "yesterday", "last 3 days", or "last 7 days", do not ask again.
- When asking, include the live candidate counts if the `windows` command succeeded.
- After the window is clear, run `scan` with the matching `--window` value.

## Workflow

1. Confirm Eagle is running and the local MCP service on `127.0.0.1:41596` is reachable.
2. Use the runtime `uibook-sync` config under `~/Library/Application Support/Eagle/plugins/uibook-sync/config.json` to read the current success tag.
3. Read successful sync records for the selected window from local `state.json`.
4. Fetch tagged Eagle items through local MCP, then keep only items that were synced in that window.
5. Ask for the scan window if the user did not already specify it.
6. Use the scan command to get candidate item IDs and local image paths.
7. Let the current Codex conversation inspect the chosen screenshot and draft the analysis block.
8. Use the apply command to replace only the prior AI block and append the updated block at the bottom of `annotation`.

## Command

Scan candidates in the default `today` window:

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py scan --repo "$PWD"
```

Useful scan flags:

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py scan --repo "$PWD" --window yesterday
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py scan --repo "$PWD" --window last3d --limit 10
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py scan --repo "$PWD" --window last7d --json
```

Show counts for the ask step:

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py windows --repo "$PWD"
```

Write a prepared AI block back to Eagle:

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py apply --repo "$PWD" --item-id ITEM_ID --analysis-file /absolute/path/to/block.md
```

Or pipe the block through stdin:

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py apply --repo "$PWD" --item-id ITEM_ID <<'EOF'
<!-- UIBOOK_AI_ANALYSIS_START -->
...
<!-- UIBOOK_AI_ANALYSIS_END -->
EOF
```

## Requirements

- Eagle must be open locally so the MCP endpoint can serve `item_get` and `item_update`.
- Supported windows for scan are `today`, `yesterday`, `last3d`, and `last7d`.
- The candidate item must:
  - include the current UIBook success tag
  - appear in the selected window's local sync logs, or contain a matching sync marker in `annotation`
  - point to a supported local image file

Supported image formats for conversation analysis:
- `jpg`
- `jpeg`
- `png`
- `webp`
- `gif`
- `avif`

## Notes Policy

- Keep the existing `- 同步于 ...` lines untouched.
- Keep all manual notes untouched.
- Always move the AI analysis block to the bottom.
- If an older AI block exists, replace only that block.
- Eagle may strip HTML comment markers from annotation. The script therefore treats either the marker-wrapped block or a block starting with `## AI Screen Analysis` / `## AI 页面分析` as replaceable AI content.

The block format is documented in [references/output-format.md](references/output-format.md).

## Conversation Rules

- Use the scan output to identify the exact item ID and image path.
- Ask the user for the time window first unless it is already explicit in the request.
- If possible, ask with live counts, for example: `today (22), yesterday (1), last3d (23), last7d (23)`.
- Ask the user to confirm the target image or paste the full local image path if needed for inspection.
- Use the current conversation's vision ability to inspect the screenshot.
- Draft the block in the page's primary language.
- Keep `Visible Text` in reading order as completely as possible.
- Keep layout, component, and color notes UI-focused rather than marketing-heavy.
- After drafting the block, use the `apply` command to write it back.

## Failure Handling

- Skip unsupported or missing local image files during scan review.
- Use `apply --dry-run` to preview the merged annotation before writing back.
- If `apply` fails, do not regenerate the block; fix the write path and retry with the same block.
