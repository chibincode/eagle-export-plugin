# Eagle Data Exporter Plugin

一个专业的 Eagle 素材数据导出插件，支持将素材信息导出为 JSON 或 CSV 格式，方便后端程序分析使用。

## 功能特性

✨ **灵活的字段选择**
- 名称 (Name)
- URL
- 标签 (Tags)
- 注释 (Annotation)
- 文件大小 (Size)
- 扩展名 (Extension)
- 文件夹 (Folders)
- 修改时间 (Modified Time)
- 文件路径 (File Path)
- 宽度/高度 (Width/Height)
- 色板 (Color Palette)

📦 **多种导出格式**
- JSON - 适合程序解析，结构化数据
- CSV - 适合 Excel 打开，数据分析

🖼️ **图片处理模式（JSON 格式专属）**
- 不包含图片 - 仅导出元数据
- Base64 编码 - 图片转为 Base64 嵌入 JSON（小文件适用）
- 完整数据包 - 导出 ZIP 包，包含图片文件 + JSON 元数据（推荐）

🎯 **灵活的导出来源**
- 导出选中的素材
- 导出全部素材

🎨 **现代化的用户界面**
- 清晰直观的操作流程
- 实时素材数量显示
- 友好的交互反馈

## 📚 文档导航

- [基础使用指南](#使用方法)（本文档）
- [UIBook Sync 插件](#uibook-sync-插件) - 直接将 Eagle 素材同步到 UIBook 云端
- [UIBook Vision Skill](#uibook-vision-skill) - 用当前对话的视觉能力为今天已同步素材补充结构化分析备注
- [后端集成指南](./BACKEND_INTEGRATION.md) - 详细的后端处理示例
- [Eagle MCP 集成测试](./EAGLE_MCP_INTEGRATION.md) - MCP 服务对接测试文档

## 使用方法

### 安装插件

1. 下载或克隆此仓库
2. 打开 Eagle 应用
3. 进入 `插件中心` > `开发者` > `加载插件`
4. 选择 `exportitem` 文件夹

### 使用插件

1. 在 Eagle 中选择要导出的素材（可选）
2. 打开 Eagle Data Exporter 插件
3. 选择需要导出的字段（支持全选/取消全选）
4. 选择导出来源（选中的素材 或 全部素材）
5. 选择导出格式（JSON 或 CSV）
6. **[JSON 格式] 选择图片处理方式：**
   - 🚫 不包含图片 - 仅导出元数据
   - 📷 Base64 编码 - 图片嵌入 JSON（适合小文件）
   - 📦 完整数据包 - 导出 ZIP（推荐，包含图片+元数据）
7. 点击"开始导出"按钮
8. 文件会自动下载到默认下载位置

## UIBook Sync 插件

`uibook-sync/` 是一个独立的 Eagle 服务插件，用于把素材直接同步到 Lovable Cloud / Supabase 的 `eagle-sync` edge function。

### 使用方式

1. 在 Eagle 中进入 `插件中心` > `开发者` > `加载插件`
2. 选择 `uibook-sync` 文件夹
3. 填写云端 `Endpoint` 和 `Sync Secret`
4. 配置 `website / section` 的标签或文件夹规则
5. 点击“保存设置”
6. 手动使用“同步选中项”，或在主设备上打开自动同步开关

### 自动同步默认策略

- 默认关闭
- 仅建议在一台常开主设备上开启
- 其他通过 iCloud 同步 Eagle 的设备保留手动同步即可

## UIBook Vision Skill

`skills/eagle-uibook-vision-notes/` 是一个配套 skill，用于扫描最近时间窗口内的 Eagle 图片素材。候选范围既包括已经同步到 UIBook 的素材，也包括最近直接添加到 Eagle 的本地图片素材。候选截图会交给当前对话做视觉理解，再把结构化分析写回素材 `annotation`。

### 适用场景

- 你没有单独的视觉 API key
- 你希望直接用当前对话能力识别截图内容
- 你希望最近添加到 Eagle 的图片也能直接纳入分析
- 你希望把 OCR、布局、组件、配色、视觉记忆点等分析结果回写到 Eagle 备注里
- 你希望对“还没有任何文件夹分类”的新图片，直接让 AI 帮你匹配到 Eagle 里现有的合适文件夹

分析块默认包含这些核心部分：
- `Overview`
- `Visible Text`
- `Layout`
- `Components`
- `Color Palette`
- `Visual Memory Cues`
- `Visual Notes`

其中 `Visual Memory Cues` 专门记录可被记住的非文字视觉线索，例如真实摄影、人物穿着、姿态、道具、场景、光线，或无人物页面中的插画主体、3D 物体、图表、设备框、渐变背景等。

现在 notes 默认采用双段式输出：
- 先完整英文版
- 再完整中文版
- 不做中英穿插

另外，这个 skill 现在也支持“无文件夹素材分类”工作流：
- 先扫描最近新增图片，必要时只看 `--only-unfiled`
- 通过 Eagle 本地 HTTP API `http://127.0.0.1:41595/api/folder/list` 读取完整 folder tree 和完整 path
- 由当前对话结合图片内容、页面类型、URL 和现有 folder 名称自动判断最合适的分类
- 最后把素材直接添加到现有 Eagle 文件夹中

现在 folder 选择已经是默认流程的一部分，但默认只对无 folder 素材生效：
- `scan --json` 会直接返回 `suggestedFolderPath`
- 也会返回 `folderAction`，例如 `keep_locked`、`assign`、`review_unfiled`
- 只要素材已经有任何 folder，默认就锁定，不会自动改动
- 处理图片时会默认一起处理无 folder 项的分类，但必须先看截图视觉内容，再写入 folder
- 脚本给出的 `suggestedFolderPath` 只是预判，不是自动写入依据
- 无 folder 项默认进入视觉复核，不会只靠 URL、文件名、尺寸或脚本建议自动 assign
- 已有 folder 的修正必须显式进入 correction workflow

默认处理顺序现在是：
- 先扫描候选
- 再做截图理解并写回 annotation
- 然后处理无 folder 项的 folder
- 无 folder 项必须先由当前对话看图判断视觉内容
- 视觉判断完成后才运行 `assign-folder`
- 已有 folder 的素材默认保持不动

文件夹分类现在是 full-path-aware 的：
- 会读取完整层级路径，例如 `Page_Gerneral/Page_About`
- 一级和更深层级都可以是准确目标，关键看 folder 名称和 path 语义是否最匹配
- 不会因为 folder 更深就默认更优先，层级深浅只在语义同样准确时才作为次级参考
- 长页面、整页滚动图、含导航和多个 section 的页面默认优先归 `Page_*`
- 单屏桌面截图按比例判断，不按固定像素判断；`1920x1080`、`2560x1440`、`3840x2160` 这类 16:9 Retina 截图都视为同类
- 接近 16:9 的单屏桌面截图会优先查找语义匹配的 `Section_*` folder
- 对这类单屏截图，脚本里的 URL / 文件名建议只作为预判，必须结合截图视觉内容后才能真正写入 folder
- 如果文件名或 URL 是 `about`，但画面里实际是 `BLOG`、`TEAM`、`INVESTORS`、客户评价、价格卡片、logo 墙等具体模块，以画面内容为准，不归到 `Section_About`
- 对这类单屏截图，视觉确认后的顺序是先找 `Section_{visualTopic}`，实在没有准确 section 时再退到 `Page_{visualTopic}`
- 不会因为只有弱泛化证据就盲目归入 `Section_Gerneral`；弱 fallback 仍会进入人工 review
- URL 会作为强信号，例如 `/about` 优先命中 `Page_About`
- 如果素材此前误归到较宽泛的父级 folder，可以在写入更准确的 path 时同步移除旧父级

单屏 section 的判断流程现在固定为：
- 先看截图比例，16:9 Retina 图会进入视觉复核状态
- 再看画面里的 section label、主标题、核心组件和视觉主体
- 画面内容与 URL / 文件名冲突时，以画面内容为准
- 没有准确 folder 时保持 `review_unfiled`，不强行塞进泛化 folder

更高优先级规则：
- 所有无 folder 图片都必须通过视觉内容判断后才能选择 folder
- URL、文件名、尺寸和脚本建议都只能作为辅助线索
- 画面内容是最终分类依据

### 常用命令

在对话里使用这个 skill 时，默认应先问时间窗口：
- `today`
- `yesterday`
- `last3d`
- `last7d`

如果用户已经明确说了窗口，再直接执行对应扫描。

也可以先看每个窗口的当前候选数量：

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py windows --repo "$PWD"
```

扫描今天的候选素材：

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py scan --repo "$PWD"
```

扫描其他时间窗口：

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py scan --repo "$PWD" --window yesterday
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py scan --repo "$PWD" --window last3d
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py scan --repo "$PWD" --window last7d
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py scan --repo "$PWD" --window today --only-unfiled
```

查看 Eagle 当前已有文件夹：

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py folders
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py folders --json
```

先只读获取 AI 的 folder 建议：

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py suggest-folder --item-id ITEM_ID
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py suggest-folder --item-id ITEM_ID --json
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py suggest-folder --item-id ITEM_ID --allow-filed --json
```

把某张无文件夹素材添加到已有 folder：

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py assign-folder --item-id ITEM_ID --folder-name "Section_Selected Works"
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py assign-folder --item-id ITEM_ID --folder-name "Page_Gerneral/Page_About"
```

如果你明确要修正一个已经有 folder 的素材，再显式进入 correction workflow：

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py suggest-folder --item-id ITEM_ID --allow-filed --json
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py assign-folder --item-id ITEM_ID --folder-name "Page_Gerneral/Page_About" --replace-parent-folders --dry-run
```

把已经写好的分析块回写到 Eagle：

```bash
python3 skills/eagle-uibook-vision-notes/scripts/analyze_synced_items.py apply --repo "$PWD" --item-id ITEM_ID --analysis-file /absolute/path/to/block.md
```

### 后端如何使用导出的数据？

详见 **[后端集成指南](./BACKEND_INTEGRATION.md)**，包含：
- Node.js / Python 完整代码示例
- 三种导出模式的处理方法
- AWS S3 / 阿里云 OSS 上传示例
- 最佳实践建议

## 导出数据示例

### 模式 1: 仅元数据（JSON/CSV）

```json
[
  {
    "id": "abc123",
    "name": "产品设计.png",
    "url": "https://example.com/image.png",
    "tags": ["设计", "产品", "UI"],
    "annotation": "这是一个产品设计图",
    "size": 524288,
    "ext": "png",
    "filePath": "/path/to/file.png"
  }
]
```

### 模式 2: Base64 编码（JSON）

```json
[
  {
    "id": "abc123",
    "name": "产品设计.png",
    "url": "https://example.com/image.png",
    "tags": ["设计", "产品"],
    "imageBase64": "data:image/png;base64,iVBORw0KGgoAAAANS..."
  }
]
```

### 模式 3: 完整数据包（ZIP）⭐ 推荐

导出文件结构：
```
eagle_export_2026-01-11.zip
├── metadata.json          # 所有素材的元数据
└── images/
    ├── abc123.png        # 图片文件（以 ID 命名）
    ├── def456.jpg
    └── ghi789.png
```

**metadata.json 内容：**
```json
[
  {
    "id": "abc123",
    "name": "产品设计.png",
    "url": "https://example.com/image.png",
    "tags": ["设计", "产品"],
    "imageFile": "abc123.png"  // 对应的图片文件名
  }
]
```

## 技术栈

- 原生 JavaScript
- Eagle Plugin API
- HTML5 + CSS3

## 开发说明

### 项目结构

```
exportitem/
├── index.html          # 主界面
├── js/
│   └── plugin.js      # 核心逻辑
├── manifest.json      # 插件配置
└── logo.png          # 插件图标

uibook-sync/
├── index.html          # 同步配置、状态摘要、活动日志
├── js/
│   └── plugin.js      # 手动/自动同步逻辑
├── manifest.json      # 插件配置
└── logo.png          # 插件图标

skills/
└── eagle-uibook-vision-notes/
    ├── SKILL.md
    ├── scripts/
    │   └── analyze_synced_items.py
    ├── references/
    │   └── output-format.md
    └── agents/
        └── openai.yaml
```

### 核心 API

- `eagle.item.get()` - 获取所有素材
- `eagle.item.getSelected()` - 获取选中的素材
- `eagle.library.getInfo()` - 获取资料库信息

## License

MIT

## 作者

Created with ❤️ for Eagle users
