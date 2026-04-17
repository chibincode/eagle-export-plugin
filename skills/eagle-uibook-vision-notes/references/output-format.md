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

For English-first pages:

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

### Visual Notes
- ...

### Metadata
- analyzedAt: 2026-04-16T13:05:00+08:00
- source: Eagle local image
- model: gpt-4.1-mini
<!-- UIBOOK_AI_ANALYSIS_END -->
```

For Chinese-first pages:

```md
<!-- UIBOOK_AI_ANALYSIS_START -->
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

### 视觉备注
- ...

### 元数据
- analyzedAt: 2026-04-16T13:05:00+08:00
- source: Eagle local image
- model: gpt-4.1-mini
<!-- UIBOOK_AI_ANALYSIS_END -->
```

## Drafting Rules

- Use English headings for English-first pages.
- Use Chinese headings for Chinese-first pages.
- Keep all sync lines and manual notes outside this block.
- Replace only the block between the markers.
- `Visible Text` or `可见文字` should preserve reading order as much as possible.
- Keep all bullet lists concise, UI-focused, and non-redundant.
