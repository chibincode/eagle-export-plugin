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
```

### 核心 API

- `eagle.item.get()` - 获取所有素材
- `eagle.item.getSelected()` - 获取选中的素材
- `eagle.library.getInfo()` - 获取资料库信息

## License

MIT

## 作者

Created with ❤️ for Eagle users
