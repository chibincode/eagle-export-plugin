---
name: eagle-uibook-vision-notes
description: Find recent Eagle image items and recent UIBook-synced screenshots within a selected recent time window, hand them off to the current Codex conversation for image understanding, and safely write a structured AI analysis block back to Eagle annotation. Use when Codex should rely on the live chat model's vision ability instead of an API key, while still using local scripts to scan recent image additions from today, yesterday, the last 3 days, or the last 7 days and update Eagle notes without disturbing manual notes or sync logs.
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

1. Confirm Eagle is running, the local MCP service on `127.0.0.1:41596` is reachable, and the Eagle folder HTTP API on `127.0.0.1:41595` is reachable.
2. Use the runtime `uibook-sync` config under `~/Library/Application Support/Eagle/plugins/uibook-sync/config.json` to read the current success tag.
3. Read successful sync records for the selected window from local `state.json`.
4. Read Eagle library items that were recently added in the selected window by checking the local image file timestamp in the library.
5. Fetch tagged Eagle items through local MCP, then take the union of:
   - items that were synced in that window
   - items whose original local image file was added in that window
6. Ask for the scan window if the user did not already specify it.
7. Use the scan command to get candidate item IDs and local image paths.
8. Let the current Codex conversation inspect the chosen screenshot and draft the analysis block.
9. Use the apply command to replace only the prior AI block and append the updated block at the bottom of `annotation`.
10. After scan, automatically evaluate the semantically best existing folder path for each candidate as part of the normal flow, but treat existing folders as locked by default.
11. Write or refresh the AI analysis block for every processed candidate, including items that already have folders.
12. If an item is unfiled, assign the suggested folder automatically only when the suggestion is strong enough.
13. If an item already has any folder, do not auto-change, auto-reassign, or auto-remove that folder in the default flow.
14. Folder correction for already-filed items is an explicit separate workflow, not part of normal scan/analyze processing.

## Default Processing Order

Once the user picks a time window, treat the end-to-end flow as:

1. `scan`
2. inspect the image in this conversation
3. draft the AI analysis block from observed screenshot evidence only
4. run the quality gate before writing
5. `apply` the annotation only if the block passes the quality gate
6. evaluate the semantically best existing folder path
7. for unfiled items, inspect the image visually before assigning any folder
8. if `folderAction=review_unfiled`, choose the folder from visual evidence and then run `assign-folder`
9. if `folderAction=keep_locked`, keep the existing folder unchanged, but still complete annotation writing for that item
10. only enter correction mode for already-filed items when the user explicitly asks for folder correction

Do not treat folder assignment as a separate follow-up task. It is part of the default completion criteria for each processed candidate.

## AI Notes Quality Gate

This skill is only useful if the annotation contains real visual understanding. A formally valid block is not enough.

Hard rules before writing any AI block:
- Do not use template, fallback, or boilerplate analysis to fill unknown details.
- Do not write an AI block from file name, URL, folder name, dimensions, or scan metadata alone.
- Do not write generic claims such as "clean SaaS palette", "visual proof", or "multiple stacked sections" unless tied to specific observed content in the screenshot.
- If a contact sheet or thumbnail is not detailed enough, open the original image before drafting.
- If the original image is too large or too hard to inspect in one pass, inspect key regions or skip the item and report it as `needs_manual_review`.
- If you cannot name at least 3 concrete visible details from the screenshot, do not write the block.
- If the screenshot is a long page, include page-specific section evidence, not only "long scroll page" structure.
- Never prioritize completion count over note quality. It is better to process fewer images than to write unreliable notes.

Each finished block must include screenshot-specific evidence:
- `Overview`: the actual page purpose and the concrete product/page type visible in the image.
- `Visible Text`: real visible text, not a placeholder saying that navigation, CTA, body copy, or footer links are present.
- `Layout`: page-specific structure, including actual major regions visible in this screenshot.
- `Components`: concrete components visible in this screenshot.
- `Color Palette`: concrete colors and where they are used.
- `Visual Memory Cues`: concrete visual anchors, such as portraits, clothing, photos, product mockups, diagrams, decorative motifs, textures, or specific image treatments.
- `Visual Notes`: what makes this specific screenshot useful as a UI/design reference.

Forbidden template phrases:
- `It captures the page as a design reference`
- `Key visible text includes the page title/name`
- `Additional visible text includes navigation labels`
- `A long scroll capture with multiple stacked sections`
- `A single-screen desktop section with a top navigation or framed module`
- `Mostly clean SaaS palettes`
- `The strongest visual cue is the dominant page-specific subject`
- `These non-text anchors make the screenshot recognizable beyond its copy`
- `The screenshot is useful as a UI reference`
- `它适合作为层级、信息表达、视觉证明和转化结构的设计参考`
- `主要可见文字包括页面标题/名称`
- `截图中还可见导航标签`
- `整体是干净的 SaaS 配色`
- `最强视觉记忆点来自页面特定主体`

If any forbidden phrase appears in the draft, rewrite the block before applying it.

## Visual Folder Decision Protocol

Use this protocol before assigning folders to unfiled items. Every unfiled image requires visual inspection before folder assignment.

1. First classify the screenshot shape:
   - long scroll page: page-level candidate
   - 16:9 single-screen desktop capture, including Retina sizes such as `1920x1080`, `2560x1440`, and `3840x2160`: section-level candidate
2. For page-level candidates, URL and file name can be strong hints when they match the full page type, such as `/about`, `/pricing`, `/login`, or documentation pages, but still inspect the screenshot before assigning.
3. For section-level candidates, URL and file name are only weak pre-visual hints.
4. For every unfiled candidate, inspect the image before assigning any folder.
5. Decide the folder topic from visible content first:
   - visible section label, such as `BLOG`, `TEAM`, `INVESTORS`, `FAQ`, `PRICING`, `CUSTOMERS`
   - main headline
   - dominant component type, such as pricing cards, testimonial cards, logo wall, article grid, sign-up form, dashboard, or hero
   - dominant visual subject, such as portrait grid, photography strip, product mockup, prompt input, or abstract hero artwork
6. Only after visual inspection, choose the most accurate existing folder path.
7. If no accurate existing folder exists, keep `review_unfiled`; do not force a weak generic folder.

Hard rule: never assign a folder to an unfiled image from URL, file name, dimensions, or script suggestion alone. Visual content is the source of truth.

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
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py scan --repo "$PWD" --window today --only-unfiled
```

Show counts for the ask step:

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py windows --repo "$PWD"
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py windows --repo "$PWD" --only-unfiled
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

List current Eagle folders for classification:

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py folders
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py folders --json
```

Get a folder suggestion before writing, or use the suggestion fields already returned by `scan --json`:

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py suggest-folder --item-id ITEM_ID
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py suggest-folder --item-id ITEM_ID --json
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py suggest-folder --item-id ITEM_ID --allow-filed --json
```

Add an unfiled item to the chosen existing folder:

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py assign-folder --item-id ITEM_ID --folder-name "Section_Selected Works"
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py assign-folder --item-id ITEM_ID --folder-id FOLDER_ID
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py assign-folder --item-id ITEM_ID --folder-name "Page_Gerneral/Page_About"
```

Explicit correction flow for an item that already has folders:

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py suggest-folder --item-id ITEM_ID --allow-filed --json
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py assign-folder --item-id ITEM_ID --folder-name "Page_Gerneral/Page_About" --replace-parent-folders
```

## Requirements

- Eagle must be open locally so the MCP endpoint can serve `item_get` and `item_update`.
- Eagle folder tree is read from `http://127.0.0.1:41595/api/folder/list`.
- Supported windows for scan are `today`, `yesterday`, `last3d`, and `last7d`.
- The candidate item must satisfy at least one of:
  - include the current UIBook success tag and appear in the selected window's local sync logs, or contain a matching sync marker in `annotation`
  - point to a supported local image file whose local add timestamp falls inside the selected window

Supported image formats for conversation analysis:
- `jpg`
- `jpeg`
- `png`
- `webp`
- `gif`
- `avif`
- Folder classification only writes to existing Eagle folders. It does not auto-create new folders.

## Notes Policy

- Keep the existing `- 同步于 ...` lines untouched.
- Keep all manual notes untouched.
- Always move the AI analysis block to the bottom.
- If an older AI block exists, replace only that block.
- Eagle may strip HTML comment markers from annotation. The script therefore treats either the marker-wrapped block or a block starting with `## AI Screen Analysis` / `## AI 页面分析` as replaceable AI content.

The block format is documented in [references/output-format.md](references/output-format.md).

## Conversation Rules

- Use the scan output to identify the exact item ID and image path.
- Treat folder choice as part of the default processing flow only for unfiled items.
- Treat annotation writing as part of the default processing flow for every processed candidate, regardless of whether it already has folders.
- Use `scan --only-unfiled` when the task is to classify newly added images that currently have no folder.
- Ask the user for the time window first unless it is already explicit in the request.
- If possible, ask with live counts, for example: `today (22), yesterday (1), last3d (23), last7d (23)`.
- Treat recent local image additions as valid candidates even if they have never been synced to UIBook.
- Ask the user to confirm the target image or paste the full local image path if needed for inspection.
- Use the current conversation's vision ability to inspect the screenshot.
- Never draft notes from a reusable brand/page-type template. Every section must be grounded in visible screenshot evidence.
- Do not let a contact sheet be the only evidence for detailed notes unless all required details are clearly readable there.
- For long screenshots, inspect enough of the original image to identify actual top, middle, and bottom content before writing.
- Before applying, check that the block names concrete visible text, concrete layout regions, concrete components, concrete colors, and concrete visual memory cues.
- If the draft could plausibly apply to several different screenshots from the same brand, it is too generic and must be rewritten.
- If a candidate cannot be analyzed with sufficient specificity in the current run, skip writing for that item and report it instead of writing a generic block.
- Separate each analysis into three layers before drafting: visible text, UI structure, and visual subject cues.
- Draft the block as two full passes:
  - English version first
  - Chinese version second
- Do not interleave English and Chinese section by section.
- Keep `Visible Text` in reading order as completely as possible.
- Keep layout, component, and color notes UI-focused rather than marketing-heavy.
- Always include a `Visual Memory Cues` / `视觉记忆点` section between color and visual notes.
- Use that section for observable visual anchors only: real photography vs illustration vs product screenshot, key subjects, clothing, pose, props, crop, scene, lighting, texture, and the most memorable non-text element.
- If a real photo with people is prominent, describe visible clothing, posture/action, objects in hand or nearby, and the surrounding setting without inferring identity, age, ethnicity, seniority, or personality.
- If there are no people, use `Visual Memory Cues` to describe the strongest non-text anchor instead, such as illustration subjects, 3D objects, device frames, charts, gradients, decorative motifs, or background treatment.
- Keep `Color Palette` focused on colors only; do not use it to carry photography or subject descriptions.
- If the image area is a dominant part of the card or page, write at least two sentences in `Visual Memory Cues`; if it is a small supporting image, one sentence is enough as long as it explains the role it plays.
- The Chinese pass should mirror the English pass faithfully, not introduce a second different interpretation.
- When an item has no Eagle folder, fetch the current full folder tree first and classify against existing folders only.
- If an item already has any folder, treat that folder state as locked and user-owned in the default flow, but do not treat the item as fully processed until the AI analysis block is written or refreshed.
- Prefer the semantically most accurate existing folder path based on visual content first, then page type, URL, file name, and folder naming.
- Do not prefer a deeper folder just because it is deeper. First-level and deeper folders are equally valid if their names are the best match.
- If a parent path and a child path both match, choose the one whose folder name and path semantics are more accurate. Use depth only as a tie-breaker, not as the primary rule.
- Long pages, full-page scroll screenshots, or screenshots with navigation plus multiple sections should default to `Page_*`.
- Detect single-screen screenshots by aspect ratio first, not exact pixels. Treat `1920x1080`, `2560x1440`, `3840x2160`, and similar 16:9 Retina captures as the same kind of single-screen candidate.
- If the image is close to a single-screen 16:9 desktop screenshot, prioritize matching `Section_*` folders first.
- For all screenshots, the script's URL/name suggestion is only a pre-visual hint. Do not assign the folder until you inspect the image.
- For all screenshots, visual content wins over URL or file name. Use the visible section label, headline, main component, page structure, and visual subject to determine the folder topic.
- For those single-screen screenshots, use this folder-kind order after visual inspection: `Section_{visualTopic}` first, then `Page_{visualTopic}` only if no semantically accurate section folder exists.
- If the URL/file name says `about` but the screenshot visibly shows `BLOG`, `TEAM`, `INVESTORS`, testimonials, pricing cards, logos, or another specific module, choose the visually indicated section folder, not `Section_About`.
- Do not assign to a weak generic section folder just because the image is 16:9; if only generic evidence exists, keep `review_unfiled`.
- Use URL as a hint, not a write permission: `/about` may suggest `Page_About`, `/pricing` may suggest `Page_Pricing`, `/login` may suggest `Page_Login`, but the screenshot must still be visually inspected before folder assignment.
- Treat the `scan --json` suggestion fields as the default folder decision input:
  - `suggestedFolderPath`
  - `folderAction`
  - `folderActionNeeded`
- Use full folder path or exact folder id when assigning if a simple folder name is ambiguous.
- After drafting the block, use the `apply` command to write it back.
- After scan, do not auto-assign unfiled items from script suggestions alone.
- After scan, if `folderAction` is `review_unfiled`, inspect the image, choose the folder from visual content, then use `assign-folder` only after that visual decision.
- After scan, if `folderAction` is `keep_locked`, do not modify folders, but still write or refresh the AI analysis block for that item.
- Use `suggest-folder --allow-filed` only when the user explicitly wants a correction suggestion for an item that already has folders.
- A candidate is not fully processed until annotation writing is done, and folder handling is also done when the item is unfiled or the user explicitly requested folder correction.

## Failure Handling

- Skip unsupported or missing local image files during scan review.
- If `127.0.0.1:41595/api/folder/list` is unavailable, stop and report the blocker instead of falling back to a partial MCP folder tree.
- Use `apply --dry-run` to preview the merged annotation before writing back.
- If `apply` fails, do not regenerate the block; fix the write path and retry with the same block.
