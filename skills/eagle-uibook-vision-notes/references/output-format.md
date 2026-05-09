# Output Format

This skill writes a single replaceable AI analysis block to the bottom of Eagle `annotation`.

## Block Markers

Always wrap the generated notes with these exact markers:

```md
<!-- UIBOOK_AI_ANALYSIS_START -->
...
<!-- UIBOOK_AI_ANALYSIS_END -->
```

If a previous block already exists, replace only the content inside these markers and keep all other notes unchanged.

Important:
- Eagle may strip HTML comment markers after write-back.
- Treat the heading `## AI Screen Analysis` or `## AI 页面分析` as the durable block boundary when markers are missing.

## Markdown Layout

Default output is bilingual and non-interleaved:
- English analysis first
- Chinese analysis second
- Do not alternate languages section by section

Recommended block layout:

```md
<!-- UIBOOK_AI_ANALYSIS_START -->
## AI Screen Analysis

### Overview
...

### Visible Text
- ...

### Layout
- ...

### Components
- ...

### Color Palette
- ...

### Visual Memory Cues
- ...

### Visual Notes
- ...

### Metadata
- analyzedAt: 2026-04-16T13:05:00+08:00
- source: Eagle local image
- model: gpt-4.1-mini

## AI 页面分析

### 页面概述
...

### 可见文字
- ...

### 布局结构
- ...

### 组件拆分
- ...

### 配色信息
- ...

### 视觉记忆点
- ...

### 视觉备注
- ...

### 元数据
- analyzedAt: 2026-04-16T13:05:00+08:00
- source: Eagle local image
- model: gpt-4.1-mini
<!-- UIBOOK_AI_ANALYSIS_END -->
```

## Drafting Rules

- Always write the English version first.
- Always append a full Chinese version after the English version.
- Do not mix English and Chinese within the same section.
- Keep all sync lines and manual notes outside this block.
- Replace only the block between the markers.
- `Visible Text` or `可见文字` should preserve reading order as much as possible.
- Keep all bullet lists concise, UI-focused, and non-redundant.
- Always include `Visual Memory Cues` or `视觉记忆点` between the color and visual-notes sections.
- Use that section for observable, memorable visual anchors only: photography vs illustration vs product screenshot, key subjects, clothing, pose, props, crop, scene, lighting, texture, and distinctive background treatment.
- Do not infer non-observable attributes such as age, ethnicity, nationality, seniority, profession, or personality.
- If a real-photo subject is prominent, describe visible clothing, posture/action, nearby objects, and setting/light.
- If there are no people, describe the strongest non-text visual anchor instead, such as charts, device frames, 3D objects, illustrations, gradients, patterns, or decorative motifs.
- Keep `Color Palette` / `配色信息` focused on color usage only; do not hide subject or photography details there.
- The Chinese version should be a faithful translation/adaptation of the English version, not a second different analysis.

## Quality Gate

Before writing to Eagle, the block must pass this specificity check:

- The analysis must be based on actual visual inspection of the local image, not only file name, URL, folder name, dimensions, or scan metadata.
- `Visible Text` must list real text observed in the screenshot. Do not use placeholders such as "navigation labels, CTA labels, headings, body copy, and footer links".
- `Layout` must describe this screenshot's specific regions. Do not use generic "multiple stacked sections" language without naming what those sections are.
- `Components` must name visible components, such as portrait cards, pricing tables, article cards, code blocks, product mockups, video players, logo walls, footer columns, compliance badges, or specific form fields.
- `Color Palette` must connect colors to visible usage, such as black footer, pale mint hero background, purple gradient stats card, red CTA, or gray document sidebar.
- `Visual Memory Cues` must include concrete visual anchors that would help the user remember the asset later.
- If the draft could apply to multiple screenshots from the same brand, it is too generic and must be rewritten.
- If the image cannot be inspected with enough detail, do not write the AI block. Report the item as needing manual review instead.

Forbidden boilerplate phrases:

```txt
It captures the page as a design reference
Key visible text includes the page title/name
Additional visible text includes navigation labels
A long scroll capture with multiple stacked sections
A single-screen desktop section with a top navigation or framed module
Mostly clean SaaS palettes
The strongest visual cue is the dominant page-specific subject
These non-text anchors make the screenshot recognizable beyond its copy
The screenshot is useful as a UI reference
它适合作为层级、信息表达、视觉证明和转化结构的设计参考
主要可见文字包括页面标题/名称
截图中还可见导航标签
整体是干净的 SaaS 配色
最强视觉记忆点来自页面特定主体
```

## Example

Example English-first then Chinese `Visual Memory Cues` for a growth-stage card with embedded photography:

English:

```md
### Visual Memory Cues
- High-quality lifestyle photography is embedded in the center card. A bald man in a dark button-up shirt and round glasses is smiling while holding a sheet of paper beside a laptop.
- A second person in a light top appears cropped on the right, leaning into the meeting. Soft daylight and pale curtain backdrops give the scene a calm, premium, collaborative tone.
```

Chinese:

```md
### 视觉记忆点
- 中间卡片嵌入了一张高品质真实摄影图。画面主体是一位穿深色衬衫、戴圆框眼镜的光头男士，面带笑容，手里拿着纸张，面前有笔记本电脑。
- 右侧还有一位穿浅色上衣的人物半身入镜，身体向会议桌一侧倾斜。整体是柔和自然光和浅色窗帘背景，传达出专业、轻松、协作中的商务氛围。
```
