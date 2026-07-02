# UIBook Pattern Discovery Matrix: Section_Featured

Date: 2026-06-29  
Source folder: `Section_Featured 产品功能亮点`  
Sample: most recent 30 Eagle items from folder `K60RMBANRMW95`  
Mode: read-only research, no Eagle writeback

## Why This Matrix Exists

This pass is meant to test the Pattern Layer against real screenshots, not to expand the existing classic taxonomy. The useful work is to separate:

- what the section is trying to help the viewer understand (`message_intent`)
- what reusable structural shape it uses (`structure_pattern`)
- how the structure is placed on the page (`layout_variant`)
- what media strategy carries the message (`content_style`)

The working signature stays compact:

```text
section_type / message_intent / structure_pattern
```

For this folder, `section_type` is assumed to be `Features`. Concrete subjects such as dashboards, phones, app screens, diagrams, charts, and avatar cards are treated as evidence, not as clustering fields.

## Promotion Candidates

The sample already shows a few recurring combinations. These should be considered candidate formal patterns only after checking brand diversity, because repeated screenshots from one brand should not over-count the signal.

Promotion is counted by:

```text
message_intent + structure_pattern
```

The other fields stay useful as modifiers, but they should not split the first pass of discovery.

| Candidate cluster key | Count | Ranks | Common modifiers | Read |
|---|---:|---|---|---|
| `capability-overview / equal-card-grid` | 9 | 10, 11, 15, 20, 21, 23, 26, 27, 30 | grid or bento; illustration-led, screenshot-led, text-led, data-led, mixed-media | The most common section shape in this folder: several equal-weight cards communicate a broad capability set. |
| `workflow-explainer / multi-panel-workflow-dashboard` | 5 | 3, 8, 13, 25, 28 | grid or split; mostly screenshot-led | A complex feature is made understandable through multiple panels that imply process, states, or system steps. |
| `single-capability-deep-dive / centered-product-panel` | 4 | 2, 7, 17, 22 | centered, grid, or split; screenshot-led | One important capability is anchored by a large product mockup or product-like panel. |
| `proof-backed-benefit / dashboard-proof-panel` | 3 | 1, 24, 29 | split or grid; data-led | The feature claim is made credible through visible metrics, charts, or financial/product data. |

Working interpretation:

- `content_style` is useful, but it should not lead the pattern name.
- `structure_pattern` is the key clustering field.
- Some items that look visually similar should stay separate when the cognitive task is different.
- Some items that look visually different should cluster when they share the same intent and structural shape.

## Full Matrix

| Rank | Item ID | Visible summary | message_intent | structure_pattern | layout_variant | content_style | evidence | Confidence | Naming note |
|---:|---|---|---|---|---|---|---|---|---|
| 1 | `MQROJRH9ICY25` | Factory feature claim about buying fewer tokens, supported by a large analytics dashboard. | `proof-backed-benefit` | `dashboard-proof-panel` | `split` | `data-led` | Headline makes a concrete savings claim; right side is a dark dashboard card; bar chart and KPI row act as proof object. | High | Strong candidate for `dashboard-proof-panel`; do not name it after "tokens" because that is product-specific. |
| 2 | `MQROJJ59IXJNK` | Factory presents one product across multiple work surfaces with desktop and mobile mockups. | `single-capability-deep-dive` | `centered-product-panel` | `centered` | `screenshot-led` | Centered headline; surface selector row; desktop-plus-phone mockup carries the cross-surface promise. | High | This should cluster by product stage structure, not by the device pair itself. |
| 3 | `MQROJ8CW5FY7X` | Factory defines "Software Factory" through three technical capability panels. | `workflow-explainer` | `multi-panel-workflow-dashboard` | `grid` | `screenshot-led` | Three equal technical panels; radar chart, deployment list, and node map; section explains parts of a system concept. | High | Could also read as capability overview, but the phrase "Defining" and system panels make `workflow-explainer` stronger. |
| 4 | `MQQ8X495WZIHB` | Vercel Apps section explains app/integration capability with a large embedded product UI. | `ecosystem-capability` | `app-ecosystem-grid` | `split` | `screenshot-led` | Large "Apps" title; Zapier proof copy; embedded app UI and integration-oriented screenshot. | High | Keep as observation until more ecosystem examples appear. |
| 5 | `MQQ2U1D8NQU6R` | CoTrain shows several intelligent tools through a soft card grid of product previews. | `ecosystem-capability` | `app-ecosystem-grid` | `grid` | `mixed-media` | Headline says "Coupled with Intelligent tools"; multiple cards show AI response, interview, matching, earnings, team invite. | High | Same intent as rank 4 but more card-based; may later split into `connected-tools-card-grid`. |
| 6 | `MQHFERHNEVEQY` | Framer announcement area shows several visual announcement cards. | `use-case-gallery` | `visual-example-grid` | `grid` | `screenshot-led` | "Read more about the announcements"; multiple visual tiles; each tile previews a different update or scenario. | Medium | Looks like feature content, but available evidence is more gallery/editorial than capability explanation. |
| 7 | `MQHFAFA3C5PCF` | Framer proves "full platform" through a dark multi-surface product UI. | `single-capability-deep-dive` | `centered-product-panel` | `grid` | `screenshot-led` | Large product UI dominates; supporting panels include performance, CMS, collaboration, uptime; platform claim is product-screen anchored. | High | Although multiple panels exist, the central promise is one deep product surface. |
| 8 | `MQHFA29YIV8YP` | Framer explains AI agents working alongside the user through content cards and a chat/sidebar panel. | `workflow-explainer` | `multi-panel-workflow-dashboard` | `split` | `screenshot-led` | Headline states "Agents that work alongside you"; left content cards and right prompt/chat panel imply a workflow. | High | Useful example of workflow implication without numbered steps. |
| 9 | `MQHF9FV2Z32G8` | Framer shows a concrete website/project example with dark product UI panels. | `use-case-gallery` | `visual-example-grid` | `split` | `screenshot-led` | Branded "Haus" example; multiple project previews; right sidebar looks like a contextual work panel. | Medium | Could become deep-dive if the surrounding page confirms a single feature, but the visible evidence reads as example gallery. |
| 10 | `MQF3GV46WBK8E` | YouMind shows three creation states from spark to exploration to reality. | `capability-overview` | `equal-card-grid` | `grid` | `illustration-led` | Three equal cards; each card has a title and image; the set explains a broad creation capability. | High | Strong example that equal-card-grid can be illustration-led, not only screenshot-led. |
| 11 | `MQ20AW5MRNRF0` | Dynadot presents domain-building capabilities through four tall cards. | `capability-overview` | `equal-card-grid` | `grid` | `mixed-media` | "Build on Your Domain Names"; multiple tall cards; cards show website builder, custom email, logo, and mobile management. | High | Good evidence that card equality matters more than specific card count. |
| 12 | `MQ209TO3YTK1L` | Dynadot compares two primary domain actions: buy and transfer. | `comparison-support` | `two-card-comparison-panel` | `grid` | `screenshot-led` | Two equal large cards; one for buying a domain and one for transferring a domain; CTA sits below. | High | Do not merge into overview yet; the dominant task is helping choose between two actions. |
| 13 | `MPXTOD1PUQAB4` | Endra AI breaks a heavy MEP design workflow into three dark feature panels. | `workflow-explainer` | `multi-panel-workflow-dashboard` | `grid` | `screenshot-led` | Three panels under one claim; panels show integration, collaboration, and documentation UI; each has its own caption. | High | Similar enough to rank 3 and 28 to keep in the same workflow cluster. |
| 14 | `MPWSDBDKSS1UA` | Delphi explains insight/focus with central process-like UI and supporting cards. | `workflow-explainer` | `process-diagram-panel` | `split` | `data-led` | Central light UI diagram; visible connectors/steps; surrounding content frames "insight" and "opportunity." | Medium | One-off structure in this sample; keep as observation, not formal pattern. |
| 15 | `MPUMQXM65OHT4` | Column presents building blocks for financial products in a modular grid. | `capability-overview` | `equal-card-grid` | `grid` | `text-led` | Headline says building blocks; repeated module rows and labels such as ACH, Checks, Wires; broad capability set. | High | The right-side UI is abstracted; classify by modular capability grid, not screenshot subject. |
| 16 | `MPUMQJI9EIDW2` | Column explains customer segments with text left and a technical graphic right. | `single-capability-deep-dive` | `split-copy-product-panel` | `split` | `illustration-led` | Left column lists user types; right side is a large bank/architecture-like graphic; one idea gets a focused explanation. | Medium | Could later merge with architecture-specific examples if more appear. |
| 17 | `MPUMQ2ADAL8BD` | Column deep-dives flexible USD building blocks with a dark product-like stage. | `single-capability-deep-dive` | `centered-product-panel` | `split` | `screenshot-led` | Dark section; one feature headline; UI/product panel and technical object anchor the explanation. | High | Same structural family as ranks 2, 7, and 22 despite different visual tone. |
| 18 | `MPUM7QRHZHF3B` | Unsupported mp4 item in the recent sample. | `needs-manual-review` | `unsupported-video` | `unknown` | `unknown` | Contact sheet only shows video placeholder; no reliable frame-level evidence available in this pass. | Low | Exclude from pattern promotion until a representative frame is inspected. |
| 19 | `MPRTI1E3Q3QWI` | Webflow explains marketing teams using Webflow with copy and a product UI preview. | `single-capability-deep-dive` | `split-copy-product-panel` | `split` | `screenshot-led` | Left copy/accordion; right product UI screenshot; one audience-specific capability is the focus. | High | Similar to rank 16 at the structural level, but screenshot-led instead of illustration-led. |
| 20 | `MPRTHS4N4NAWS` | Webflow shows AI knowledge base capabilities with one mockup and three feature cards. | `capability-overview` | `equal-card-grid` | `grid` | `screenshot-led` | Large product image at top; three cards labeled Build, Manage, Optimize; cards carry a capability set. | High | The overview pattern is stronger than the central mockup because the bottom card row defines the section. |
| 21 | `MPQMUUQI04PVY` | Bevel presents health coaching features through three mobile app cards. | `capability-overview` | `equal-card-grid` | `grid` | `screenshot-led` | Three equal cards labeled Strain, Sleep, Recovery; each has a phone screenshot and metric overlay. | High | Could be `mobile-screen-trio`, but for discovery it should stay in the broader equal-card-grid cluster. |
| 22 | `MPQMU840ENRMJ` | Bevel shows an "And that's not all" feature list with a phone mockup. | `single-capability-deep-dive` | `centered-product-panel` | `split` | `screenshot-led` | Feature list on the left; phone mockup on the right; section is about additional capabilities inside one product context. | High | Good example of centered/split product-panel without dark cinematic styling. |
| 23 | `MPOVR7355V0O2` | Sierra presents customer-experience capabilities and trust/reliability underneath. | `capability-overview` | `equal-card-grid` | `grid` | `screenshot-led` | Multiple feature cards; central product-like panel; secondary "Trust and reliability" proof row. | Medium-high | Keep as overview because the upper grid explains capabilities; trust content is secondary. |
| 24 | `MPOVR3WZ0LZ2U` | Sierra supports "Use AI to improve your AI" with metrics and cards. | `proof-backed-benefit` | `dashboard-proof-panel` | `grid` | `data-led` | Metric/chart card is visible; surrounding cards explain monitor/evaluate/optimize loop; benefit is backed by measurable UI. | High | Could be workflow, but the visible data proof is the strongest retrieval value. |
| 25 | `MPOVR0OY6XHX5` | Sierra explains an agent-building agent through two product panels. | `workflow-explainer` | `multi-panel-workflow-dashboard` | `split` | `screenshot-led` | Two large panels show builder and optimization states; headline describes an agent-building process. | High | Strong candidate for process/workflow without explicit step numbers. |
| 26 | `MPOVQGUXKKNFX` | Sierra shows multiple outcome/use-case cards with avatars, icons, and rating proof. | `capability-overview` | `equal-card-grid` | `bento` | `mixed-media` | Colored cards are equal-weight; cards show team support, workflow, job completion, and review/rating proof. | High | Could also be use-case-gallery; classify as overview because each card expresses a customer-facing capability. |
| 27 | `MPNUXPJMITDRM` | Liveblocks lists collaborative features users expect inside a dark card layout. | `capability-overview` | `equal-card-grid` | `grid` | `text-led` | Main feature list; multiple smaller capability blocks; headline frames a broad feature set. | High | Despite dark style, it should cluster with overview grids, not with dark deep dives. |
| 28 | `MPMHT7PRQUCSX` | Giza explains intelligent optimization through three side-by-side product/story panels. | `workflow-explainer` | `multi-panel-workflow-dashboard` | `grid` | `screenshot-led` | Three equal panels; each panel combines scenery/screenshot overlays and captions; flow from action to optimization is implied. | High | Same workflow family as ranks 3, 8, 13, and 25. |
| 29 | `MPMHT2MHBXV50` | Giza shows agents as interface through one large transaction/dashboard panel. | `proof-backed-benefit` | `dashboard-proof-panel` | `split` | `data-led` | Huge dollar amount in dashboard; table-like transaction UI; section claim is made concrete through financial data. | High | Good proof-panel example even though it visually uses a product screenshot. |
| 30 | `MPKL8E1ZAVCBY` | Hostinger shows power/control and flexible growth with stats and feature bands. | `capability-overview` | `equal-card-grid` | `grid` | `data-led` | Two feature columns; expandable rows; four prominent metric cards at the bottom. | High | Data-led overview should still cluster with equal-card-grid because the repeated blocks define the shape. |

## Cluster Review

### Candidate Formal Patterns

`equal-card-grid`

This appears across YouMind, Dynadot, Column, Webflow, Bevel, Sierra, Liveblocks, and Hostinger. It is the clearest reusable pattern in this sample. The material varies widely: illustration, screenshot, text, avatar/review, and metric cards. That makes it a strong proof that `content_style` should remain a modifier, not the pattern.

`multi-panel-workflow-dashboard`

This appears across Factory, Framer, Endra, Sierra, and Giza. It is useful for explaining complex systems without a literal numbered "How it works" section. It should likely be searchable by intent such as "explain how a complex feature works."

`centered-product-panel`

This appears across Factory, Framer, Column, and Bevel. It is a good candidate for product-screenshot-heavy feature sections where one product surface carries the explanation.

`dashboard-proof-panel`

This appears across Factory, Sierra, and Giza. It is distinct from generic screenshot-led because the screenshot behaves as evidence: metrics, charts, dollar values, or measurable outcomes make the claim more concrete.

### Hold As Observations

`app-ecosystem-grid`

Ranks 4 and 5 suggest a real pattern for connected apps, integrations, and built-in tools, but this sample only gives two examples.

`two-card-comparison-panel`

Rank 12 is clear, but one example is not enough to promote.

`process-diagram-panel`

Rank 14 is useful but not common in this sample.

`split-copy-product-panel`

Ranks 16 and 19 suggest a recurring split layout for one capability, but two examples are not enough yet.

## Framework Implications

For Eagle analysis, the Pattern Layer should use this order:

```text
visible evidence -> message_intent -> structure_pattern -> layout_variant -> content_style -> confidence
```

Do not start from `content_style`. In this sample, the same structural pattern appears as screenshot-led, illustration-led, data-led, text-led, and mixed-media. Starting from material would split apart examples that are actually useful to retrieve together.

For long pages, do not force a single Pattern Layer signature for the whole page. Either skip Pattern Layer or split the page into visible section-level observations first.
