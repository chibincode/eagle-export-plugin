# Eagle 素材智能分类方案（基于现有文件夹）

> **状态：方案设计阶段** | 仅供参考，未实际执行

---

## 📋 方案概述

**目标**：通过 AI 视觉分析，将未归类素材智能匹配到**现有文件夹**

**分类方式**：基于你现有的文件夹结构（如按域名/产品命名）

**处理范围**：
- 优先处理：4,961 个未归类素材
- 可选：重新整理已归类素材

**技术路线**：
1. 获取你现有的文件夹列表
2. 获取未归类素材元数据（名称、URL、缩略图路径）
3. 读取缩略图图片
4. AI 视觉分析判断素材属于哪个现有文件夹
5. 通过 MCP 将素材归类到匹配的文件夹

---

## 🗂️ 工作原理

### 你的现有文件夹结构（示例）

根据你的描述，你的文件夹可能是这样的：

```
📁 alibaba.com (阿里巴巴系产品)
📁 taobao.com (淘宝)
📁 aliyun.com (阿里云)
📁 tencent.com (腾讯系产品)
📁 baidu.com (百度系产品)
📁 bytedance.com (字节跳动系产品)
📁 google.com (Google 产品)
📁 microsoft.com (微软产品)
📁 apple.com (苹果产品)
... (其他域名/产品文件夹)
```

### AI 匹配逻辑

对于每个未归类素材，AI 会：

1. **读取缩略图** - 看图片内容
2. **分析视觉特征** - 识别品牌元素（Logo、配色、设计风格）
3. **结合元数据** - 素材名称、来源 URL
4. **匹配文件夹** - 找到最合适的现有文件夹
5. **给出置信度** - 0-100% 的匹配可信度

---

## 🔍 AI 视觉分析标准

### 分类决策流程

```
读取缩略图
    ↓
识别品牌特征（Logo、配色、字体）
    ↓
分析元数据（名称、URL）
    ↓
匹配现有文件夹列表
    ↓
给出最佳匹配 + 置信度
```

### 匹配维度

| 维度 | 权重 | 判断方法 | 示例 |
|------|------|---------|------|
| **Logo 识别** | 40% | 视觉识别页面中的品牌Logo | 看到支付宝Logo → `alipay.com` |
| **配色风格** | 25% | 识别主色调（阿里橙、腾讯蓝等） | 橙色主色调 + 电商风格 → `taobao.com` |
| **来源 URL** | 20% | 素材元数据中的 URL 字段 | url: "alibaba.com" → `alibaba.com` |
| **素材名称** | 10% | 文件名包含的关键词 | "阿里云控制台" → `aliyun.com` |
| **设计风格** | 5% | 整体UI风格（Material Design/iOS风格等） | 苹果风格设计 → `apple.com` |

### 典型匹配场景

**场景 1: Logo 清晰可见**
- 缩略图左上角有"阿里云"Logo → **直接匹配** `aliyun.com` (置信度: 95%)

**场景 2: 配色 + 元数据**
- 橙色主色调 + URL 包含 "taobao" → **匹配** `taobao.com` (置信度: 90%)

**场景 3: 无明显特征，依赖文件名**
- 名称 = "微信支付流程图" → **匹配** `tencent.com` 或 `wechat.com` (置信度: 70%)

**场景 4: 多个可能匹配**
- 通用的后台管理界面，无明显品牌特征 → **列出可能选项** (置信度: < 50%，需人工审核)

---

## 🛠️ 实施工作流

### 方式 1: 手动审核模式（推荐初次使用）

```bash
# 1. 获取 10 个未归类素材
# 2. AI 读图分析并建议分类
# 3. 人工审核建议（确认/修改）
# 4. 执行归类操作
# 5. 重复步骤 1-4，直到处理完所有素材
```

**优点**：可控、准确率高、随时调整
**缺点**：需要人工参与，速度较慢

### 方式 2: 自动批量模式（适合大规模处理）

```bash
# 1. 获取所有未归类素材
# 2. AI 批量读图分析（每批 10-20 个）
# 3. 自动执行归类操作
# 4. 生成分类报告，标记不确定的素材
# 5. 人工审核不确定的素材
```

**优点**：速度快、效率高
**缺点**：需要足够的 token 预算、可能有误分类

---

## 💻 技术实现

### Python 自动化脚本（示例）

```python
#!/usr/bin/env python3
"""
Eagle 素材智能分类脚本
通过 AI 视觉分析自动将素材归类到文件夹
"""

import anthropic
import json
import time
from typing import List, Dict

# 1. 连接 Eagle MCP 服务
def connect_eagle_mcp():
    """建立 SSE 连接并返回 sessionId"""
    # ... SSE 连接代码 ...
    pass

# 2. 获取未归类素材
def get_unfiled_items(session_id: str, limit: int = 10) -> List[Dict]:
    """
    获取未归类的素材

    Args:
        session_id: MCP 会话 ID
        limit: 每批获取数量

    Returns:
        素材列表，包含 id、name、url、thumbnailPath 等
    """
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "item_get",
            "arguments": {
                "isUnfiled": True,
                "limit": limit
            }
        }
    }
    # ... 发送请求并获取响应 ...
    return items

# 3. AI 视觉分析 - 基于现有文件夹匹配
def classify_by_vision(items: List[Dict], existing_folders: List[Dict]) -> List[Dict]:
    """
    使用 Claude 视觉分析将素材匹配到现有文件夹

    Args:
        items: 素材列表
        existing_folders: 现有文件夹列表

    Returns:
        分类结果，格式: [{"id": "xxx", "folder_id": "yyy", "folder_name": "alibaba.com", "confidence": 0.95}]
    """
    client = anthropic.Anthropic()

    # 读取缩略图
    images = []
    for item in items:
        thumbnail_path = item['thumbnailPath']
        with open(thumbnail_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
            images.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": f"image/{item['ext']}",
                    "data": image_data
                }
            })

    # 构建文件夹列表
    folder_list = "\n".join([f"- {f['name']} (ID: {f['id']})" for f in existing_folders])

    # 构建 prompt
    prompt = f"""
请分析这些截图，判断它们应该归类到哪个现有文件夹。

🗂️ **现有文件夹列表**：
{folder_list}

📋 **素材信息**：
{json.dumps([{"id": item['id'], "name": item['name'], "url": item.get('url', '')} for item in items], ensure_ascii=False, indent=2)}

🔍 **匹配标准**：
1. **Logo 识别** (最高优先级) - 截图中是否有明显的品牌 Logo
2. **配色风格** - 主色调是否与某个品牌匹配（如阿里橙、腾讯蓝）
3. **来源 URL** - 素材的 URL 字段
4. **文件名** - 名称中的关键词
5. **设计风格** - 整体UI设计风格

📤 **返回格式**（JSON）：
[
  {{
    "id": "素材ID",
    "folder_id": "文件夹ID",
    "folder_name": "文件夹名称",
    "confidence": 0.95,
    "reason": "匹配依据（如：截图左上角有阿里云Logo）"
  }}
]

⚠️ **注意**：
- 如果置信度 < 50%，将 folder_id 设为 null，并在 reason 中说明无法匹配的原因
- 只返回 JSON，不要其他文字
"""

    # 调用 Claude API
    message = client.messages.create(
        model="claude-sonnet-4-5-20250514",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": images + [{"type": "text", "text": prompt}]
        }]
    )

    # 解析响应
    result = json.loads(message.content[0].text)
    return result

# 4. 创建文件夹
def create_folders(session_id: str, folder_names: List[str]):
    """批量创建文件夹"""
    request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "folder_create",
            "arguments": {
                "folders": [{"name": name} for name in folder_names]
            }
        }
    }
    # ... 发送请求 ...
    pass

# 5. 将素材添加到文件夹
def add_items_to_folders(session_id: str, classifications: List[Dict]):
    """将素材批量添加到对应文件夹"""
    # 按文件夹分组
    folder_groups = {}
    for item in classifications:
        folder = item['folder']
        if folder not in folder_groups:
            folder_groups[folder] = []
        folder_groups[folder].append(item['id'])

    # 批量添加
    for folder_name, item_ids in folder_groups.items():
        request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "item_add_to_folders",
                "arguments": {
                    "ids": item_ids,
                    "folders": [folder_name]  # 实际应使用 folder_id
                }
            }
        }
        # ... 发送请求 ...

# 主流程
def main():
    print("🚀 Eagle 素材智能分类开始")

    # 1. 连接 MCP
    session_id = connect_eagle_mcp()
    print(f"✅ 已连接 MCP (sessionId: {session_id})")

    # 2. 获取现有文件夹
    existing_folders = get_existing_folders(session_id)
    print(f"✅ 找到 {len(existing_folders)} 个现有文件夹")
    print("现有文件夹列表:")
    for folder in existing_folders[:10]:  # 显示前10个
        print(f"  📁 {folder['name']} ({folder['imagesCount']} 素材)")

    # 3. 批量处理素材
    batch_size = 10
    processed = 0

    while True:
        # 获取未归类素材
        items = get_unfiled_items(session_id, batch_size)
        if not items:
            print("✅ 所有素材已处理完成")
            break

        print(f"\n📦 处理第 {processed + 1}-{processed + len(items)} 个素材...")

        # AI 分析
        classifications = classify_by_vision(items)

        # 显示结果供审核
        print("\n分类结果：")
        for cls in classifications:
            print(f"  - {cls['id']}: {cls['folder']} (置信度: {cls['confidence']:.0%})")
            print(f"    理由: {cls['reason']}")

        # 询问是否执行
        confirm = input("\n是否执行归类？(y/n): ")
        if confirm.lower() == 'y':
            add_items_to_folders(session_id, classifications)
            print(f"✅ 已归类 {len(items)} 个素材")
            processed += len(items)
        else:
            print("❌ 已跳过本批")

        time.sleep(1)  # 避免 API 限流

    print(f"\n🎉 完成！共处理 {processed} 个素材")

if __name__ == "__main__":
    main()
```

---

## 💸 Token 成本估算

### 单个素材处理成本

假设使用 **Claude Sonnet 4.5**：

| 操作 | Token 消耗 | 成本（USD） |
|------|-----------|-----------|
| 读取缩略图（200KB） | ~400-600 tokens | $0.0012 |
| 分类 Prompt + 响应 | ~200 tokens | $0.0006 |
| **单素材总计** | ~600-800 tokens | **$0.0018** |

### 批量处理成本

| 处理数量 | 总 Token | 总成本（USD） | 时间估算 |
|---------|---------|--------------|---------|
| 10 个素材 | ~6,000-8,000 | $0.018 | 1 分钟 |
| 100 个素材 | ~60,000-80,000 | $0.18 | 10 分钟 |
| 1,000 个素材 | ~600,000-800,000 | $1.80 | 100 分钟 |
| **4,961 个（全部未归类）** | ~3,000,000 | **$9.00** | 8 小时 |
| **45,129 个（全部素材）** | ~27,000,000 | **$81.00** | 3 天 |

**优化建议**：
1. 优先处理未归类素材（4,961 个）
2. 使用 **Claude Haiku** 处理简单素材（成本降低 80%）
3. 元数据足够明确时跳过视觉分析（如文件名是 "login-page.png"）

---

## 📊 分类演示示例

### 示例 1: 基于元数据快速匹配

基于之前获取的素材：

| 素材 ID | 名称 | URL | 判断依据 | 匹配文件夹 | 置信度 |
|---------|------|-----|---------|-----------|--------|
| MLHEAQKA645PQ | Gather Pricing Virtual Workspace | gather.town/pricing | URL 包含 "gather.town" | **gather.town** | 90% |
| M9QEOYK2TZBJR | Trucker Path Technology Built for Trucking | truckerpath.com | URL 包含 "truckerpath.com" | **truckerpath.com** | 90% |
| MLG78LVN9S81F | 即梦AI - 一站式AI创作平台 | jimeng.jianying.com | URL 包含 "jianying"，字节系产品 | **bytedance.com** | 85% |

### 示例 2: 基于视觉分析匹配

假设你有以下现有文件夹：
- `alibaba.com` - 阿里巴巴
- `aliyun.com` - 阿里云
- `taobao.com` - 淘宝
- `tencent.com` - 腾讯
- `wechat.com` - 微信
- `apple.com` - 苹果

读取缩略图后的 AI 分析结果：

```json
[
  {
    "id": "ABC123",
    "name": "控制台截图.png",
    "url": "",
    "folder_id": "aliyun_folder_id",
    "folder_name": "aliyun.com",
    "confidence": 0.95,
    "reason": "截图左上角有明显的"阿里云"Logo和橙色导航栏，典型的阿里云控制台界面"
  },
  {
    "id": "DEF456",
    "name": "支付流程.jpg",
    "url": "https://pay.taobao.com/...",
    "folder_id": "taobao_folder_id",
    "folder_name": "taobao.com",
    "confidence": 0.92,
    "reason": "URL 包含 taobao.com，界面采用橙色主色调，有淘宝支付特征"
  },
  {
    "id": "GHI789",
    "name": "iOS设置界面.png",
    "url": "",
    "folder_id": "apple_folder_id",
    "folder_name": "apple.com",
    "confidence": 0.88,
    "reason": "典型的iOS风格设置界面，使用SF Pro字体，圆角列表设计，浅灰色背景"
  },
  {
    "id": "JKL012",
    "name": "未知后台.png",
    "url": "",
    "folder_id": null,
    "folder_name": null,
    "confidence": 0.30,
    "reason": "通用的后台管理界面，无明显品牌特征，建议人工审核"
  }
]
```

### 示例 3: 置信度阈值处理

| 置信度范围 | 处理方式 | 说明 |
|-----------|---------|------|
| **90-100%** | 自动归类 | Logo清晰、URL匹配，可直接执行 |
| **70-89%** | 自动归类 + 标记 | 配色/风格匹配，建议抽查 |
| **50-69%** | 人工审核 | 特征不明显，需要人工确认 |
| **< 50%** | 跳过 | 无法匹配，保持未归类状态 |

---

## ⚠️ 注意事项

### 匹配准确率

| 匹配特征 | 预期准确率 | 说明 |
|---------|-----------|------|
| Logo 清晰可见 | 95%+ | 直接识别品牌 Logo，准确率最高 |
| URL + 配色匹配 | 90%+ | 元数据 + 视觉双重验证 |
| 配色风格匹配 | 80%+ | 识别品牌主色调（阿里橙、腾讯蓝等） |
| 仅文件名匹配 | 70%+ | 依赖名称关键词 |
| 无明显特征 | < 50% | 需要人工审核 |

### 可能的问题

1. **误分类**：视觉相似的页面可能被分到错误类别
   - **解决**：人工审核模式、降低置信度阈值

2. **多页面合图**：一张截图包含多个页面
   - **解决**：分到"组件元素"或人工处理

3. **非页面截图**：纯Logo、图标、插画等
   - **解决**：分到"组件元素"

4. **语言问题**：非中英文页面识别率可能下降
   - **解决**：主要依赖视觉结构而非文字

---

## 🚀 如何使用

### 方式 1: 通过 Claude Code（推荐）

Eagle MCP 已配置到你的 Claude Code，可以直接对话：

```
你：帮我把未归类的素材通过看图分到现有文件夹里，先处理 10 个我看看效果

Claude:
1. 获取你现有的文件夹列表
2. 获取 10 个未归类素材
3. 读取缩略图并分析
4. 给出分类建议
5. 等待你确认后执行
```

### 方式 2: 自动化脚本

使用上面提供的 Python 脚本：

```bash
# 1. 安装依赖
pip install anthropic

# 2. 配置 API Key
export ANTHROPIC_API_KEY="your_key"

# 3. 运行脚本
python eagle_classify.py

# 4. 按提示操作
#    - 查看分类建议
#    - 确认或调整
#    - 执行归类
```

### 方式 3: 手动逐批处理

如果你想完全掌控：

```bash
1. 我获取 10 个未归类素材 → 展示给你
2. 你选择其中几个 → 告诉我 ID
3. 我读图分析 → 给出建议
4. 你确认 → 我执行归类
5. 重复以上步骤
```

---

## 🎯 下一步行动

### 建议流程

1. **[现在] 审核本方案**
   - ✅ 是基于现有文件夹匹配，而不是创建新的 ✓
   - 这个方案是否符合你的需求？
   - 需要调整什么吗？

2. **[准备就绪后] 小批量测试** - 处理 10 个素材
   - 验证匹配准确率
   - 评估 token 消耗
   - 调整置信度阈值

3. **[测试通过后] 批量执行** - 处理所有未归类素材
   - 每批 10-20 个（因为要读图）
   - 置信度 > 90% 的自动归类
   - 置信度 < 90% 的人工审核

4. **[完成后] 优化维护**
   - 处理无法匹配的素材
   - 记录常见匹配规则
   - 提升准确率

---

## 💡 使用建议

### 优化 Token 成本

1. **先用元数据过滤** - 对于 URL 字段明确的素材（如 url 包含 "alibaba.com"），跳过视觉分析，直接匹配
2. **批量处理** - 每次读 10-20 个素材的缩略图，而不是逐个处理
3. **使用 Haiku** - 对于简单匹配（Logo 清晰），使用 Claude Haiku 降低成本 80%
4. **设置阈值** - 只处理文件大小 < 1MB 的缩略图，跳过视频和大文件

### 提升准确率

1. **人工审核高价值素材** - 对于重要的素材，低置信度时手动确认
2. **建立规则库** - 记录常见的匹配规则（如"橙色 + 电商 → taobao.com"）
3. **反馈学习** - 记录误分类案例，优化 prompt

---

## 📝 你的反馈

请告诉我：

- ✅ 这个方案（基于现有文件夹匹配）是否符合你的需求？
- ✅ 需要调整什么吗？
- ✅ 准备好后，我可以帮你处理第一批 10 个素材看看效果

**重要提醒**：在你明确同意之前，我不会对你的 Eagle 库执行任何实际操作。
