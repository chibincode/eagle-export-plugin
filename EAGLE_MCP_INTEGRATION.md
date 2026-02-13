# Eagle MCP 服务对接测试文档

本文档记录 Eagle Plugin 与 Eagle MCP Server 的集成测试过程和接口调用情况。

## 📋 目录

- [快速开始](#快速开始)
- [概述](#概述)
- [MCP 服务说明](#mcp-服务说明)
- [测试环境配置](#测试环境配置)
- [MCP 连接测试](#mcp-连接测试)
- [Eagle Plugin API 测试](#eagle-plugin-api-测试)
- [测试记录](#测试记录)
- [问题与解决方案](#问题与解决方案)

---

## 快速开始

### 1. 检查 Eagle MCP 服务

确保 Eagle 应用正在运行，然后测试 MCP 服务：

```bash
# 测试 SSE 连接
curl -N http://localhost:41596/sse

# 检查端口是否监听
lsof -i :41596
# 或使用 netstat
netstat -an | grep 41596
```

### 2. 发送测试请求

```bash
# 列出可用工具
curl -X POST http://localhost:41596/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list"
  }'
```

### 3. 调用工具获取数据

```bash
# 获取资料库信息
curl -X POST http://localhost:41596/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "get_library_info",
      "arguments": {}
    }
  }'
```

如果以上命令都能正常返回数据，说明 MCP 服务工作正常。

### 4. 使用测试脚本（推荐）

项目提供了两个自动化测试脚本：

**Node.js 版本（推荐，输出更详细）：**
```bash
node test-mcp-connection.js
```

**Shell 版本（无需 Node.js）：**
```bash
chmod +x test-mcp-connection.sh
./test-mcp-connection.sh
```

测试脚本会自动执行以下检查：
- ✅ 端口连接测试
- ✅ 初始化 MCP 连接
- ✅ 获取可用工具列表
- ✅ 调用工具获取资料库信息
- ✅ 调用工具获取素材列表

---

## 概述

Eagle MCP (Model Context Protocol) Server 是用于与 Eagle 应用进行程序化交互的服务接口。通过 MCP 服务，我们可以：

- 读取 Eagle 资料库中的素材数据
- 管理素材的标签、注释等元信息
- 进行素材搜索和过滤
- 与其他系统进行数据同步

本文档记录插件与 MCP 服务对接的测试过程。

---

## MCP 服务说明

### 服务端点

- **SSE 端点**: `http://localhost:41596/sse`
- **基础 URL**: `http://localhost:41596`
- **协议**: Server-Sent Events (SSE) + JSON-RPC 2.0

### 认证方式

- 本地 Socket 通信（无需额外认证）
- 仅监听本地回环地址 (127.0.0.1)

### 支持的协议版本

- MCP Protocol Version: `2024-11-05`

### 连接测试

使用 curl 测试 SSE 连接：
```bash
curl -N http://localhost:41596/sse
```

预期响应（SSE 格式）：
```
event: endpoint
data: /message

event: message
data: {"jsonrpc":"2.0","id":1,"result":{"capabilities":{...}}}
```

---

## 测试环境配置

### 前置条件

- [ ] Eagle 应用已安装并运行
- [ ] Eagle 资料库已创建
- [ ] MCP 服务已启用
- [ ] 测试用素材已准备

### 环境变量

```bash
# Eagle 安装路径
EAGLE_PATH=/Applications/Eagle.app

# MCP 服务端口
MCP_PORT=41596

# MCP SSE 端点
MCP_SSE_ENDPOINT=http://localhost:41596/sse
```

---

## MCP 连接测试

### 建立 SSE 连接

**测试时间**: `YYYY-MM-DD HH:mm:ss`

**方法 1: 使用 curl 测试连接**
```bash
curl -N http://localhost:41596/sse
```

**方法 2: 使用 JavaScript EventSource**
```javascript
const eventSource = new EventSource('http://localhost:41596/sse');

eventSource.onmessage = (event) => {
  console.log('收到消息:', event.data);
  const data = JSON.parse(event.data);
  console.log('解析后的数据:', data);
};

eventSource.onerror = (error) => {
  console.error('连接错误:', error);
};
```

**方法 3: 使用 MCP SDK**
```javascript
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { SSEClientTransport } from '@modelcontextprotocol/sdk/client/sse.js';

const transport = new SSEClientTransport(
  new URL('http://localhost:41596/sse')
);

const client = new Client({
  name: 'eagle-plugin-client',
  version: '1.0.0'
}, {
  capabilities: {}
});

await client.connect(transport);
```

**测试结果**:
- [ ] SSE 连接成功
- [ ] 收到 endpoint 事件
- [ ] 收到 capabilities 信息
- [ ] 连接稳定

**收到的初始消息**:
```
event: endpoint
data: /message

event: message
data: {"jsonrpc":"2.0","method":"notifications/initialized"}
```

**备注**:

---

### 发送 JSON-RPC 请求

**测试时间**: `YYYY-MM-DD HH:mm:ss`

MCP 使用 JSON-RPC 2.0 协议，需要向 `/message` 端点发送 POST 请求。

**初始化请求示例**:
```bash
curl -X POST http://localhost:41596/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {
        "name": "eagle-plugin-test",
        "version": "1.0.0"
      }
    }
  }'
```

**列出可用工具**:
```bash
curl -X POST http://localhost:41596/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list"
  }'
```

**测试结果**:
- [x] 初始化成功 (2026-02-11)
- [x] 获取到工具列表
- [x] 响应格式正确

**服务端信息**:
- 服务名: Eagle MCP Server (Beta) v0.0.1
- 协议版本: 2024-11-05
- 能力: tools (listChanged: true)

**可用工具列表 (25 个):**

| 分类 | 工具名 | 说明 |
|------|--------|------|
| 应用 | `get_app_info` | 获取 Eagle 应用信息（版本、构建号等） |
| 文件夹 | `folder_create` | 批量创建文件夹（支持嵌套结构） |
| 文件夹 | `folder_get` | 获取文件夹（支持 ID、选中、层级查询） |
| 文件夹 | `folder_update` | 批量更新文件夹属性 |
| 素材 | `item_query` | 智能文本搜索（支持 AND/OR/NOT） |
| 素材 | `item_get` | 属性过滤获取素材（ID/标签/文件夹/扩展名/评分等） |
| 素材 | `item_get_selected` | 获取当前选中的素材 |
| 素材 | `item_update` | 批量更新素材属性 |
| 素材 | `item_count` | 高性能素材计数 |
| 素材 | `item_add` | 添加素材（URL/Base64/路径/书签） |
| 素材 | `item_move_to_trash` | 批量移入回收站 |
| 标签 | `item_add_tags` | 增量添加标签到素材 |
| 标签 | `item_remove_tags` | 从素材移除标签 |
| 文件夹 | `item_add_to_folders` | 增量添加素材到文件夹 |
| 文件夹 | `item_remove_from_folders` | 从文件夹移除素材 |
| 标签组 | `tag_group_create` | 创建标签组 |
| 标签组 | `tag_group_get` | 获取标签组 |
| 标签组 | `tag_group_update` | 更新标签组 |
| 标签组 | `tag_group_delete` | 删除标签组 |
| 标签组 | `tag_group_add_tags` | 向标签组添加/移动标签 |
| 标签组 | `tag_group_remove_tags` | 从标签组移除标签 |
| 标签 | `tag_get` | 查询标签（支持名称、用量过滤） |
| 标签 | `tag_count` | 标签计数 |
| 标签 | `tag_update` | 批量重命名标签 |
| 标签 | `tag_merge` | 合并标签 |

**备注**: 工具功能非常完整，覆盖了素材管理、文件夹管理、标签管理的全部核心操作。

---

### 调用 MCP 工具

**测试时间**: `YYYY-MM-DD HH:mm:ss`

**调用示例 - 获取资料库信息**:
```bash
curl -X POST http://localhost:41596/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "get_library_info",
      "arguments": {}
    }
  }'
```

**预期响应**:
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\n  \"library\": {\n    \"path\": \"/path/to/library\",\n    \"name\": \"我的素材库\"\n  }\n}"
      }
    ]
  }
}
```

**调用示例 - 获取素材列表**:
```bash
curl -X POST http://localhost:41596/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "get_items",
      "arguments": {
        "limit": 10
      }
    }
  }'
```

**使用 JavaScript 调用**:
```javascript
async function callMCPTool(toolName, args = {}) {
  const response = await fetch('http://localhost:41596/message', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: Date.now(),
      method: 'tools/call',
      params: {
        name: toolName,
        arguments: args
      }
    })
  });

  return await response.json();
}

// 使用示例
const libraryInfo = await callMCPTool('get_library_info');
const items = await callMCPTool('get_items', { limit: 10 });
```

**测试结果**:
- [ ] 工具调用成功
- [ ] 返回数据格式正确
- [ ] 数据内容准确

**备注**:

---

## Eagle Plugin API 测试

以下测试使用 Eagle Plugin 内置的 JavaScript API（非 MCP 协议）。

### 1. 获取资料库信息

**接口**: `eagle.library.getInfo()`

**测试时间**: `YYYY-MM-DD HH:mm:ss`

**请求示例**:
```javascript
const libraryInfo = await eagle.library.getInfo();
```

**响应示例**:
```json
{
  "id": "library_id",
  "name": "我的素材库",
  "path": "/path/to/library",
  "itemCount": 150
}
```

**测试结果**:
- [ ] 通过
- [ ] 失败

**备注**:

---

### 2. 获取所有素材

**接口**: `eagle.item.get()`

**测试时间**: `YYYY-MM-DD HH:mm:ss`

**请求参数**:
```javascript
const items = await eagle.item.get();
```

**响应数据结构**:
```json
[
  {
    "id": "item_id",
    "name": "素材名称.png",
    "size": 524288,
    "ext": "png",
    "tags": ["设计", "UI"],
    "folders": ["文件夹1"],
    "isDeleted": false,
    "url": "https://...",
    "annotation": "",
    "modificationTime": 1704067200000,
    "width": 1920,
    "height": 1080,
    "palettes": [
      {"color": "#FF5733", "ratio": 0.45}
    ]
  }
]
```

**测试结果**:
- [ ] 通过
- [ ] 失败

**性能数据**:
- 素材数量:
- 响应时间:
- 数据大小:

**备注**:

---

### 3. 获取选中的素材

**接口**: `eagle.item.getSelected()`

**测试时间**: `YYYY-MM-DD HH:mm:ss`

**请求示例**:
```javascript
const selectedItems = await eagle.item.getSelected();
```

**测试场景**:
- [ ] 未选中任何素材 (预期返回空数组)
- [ ] 选中单个素材
- [ ] 选中多个素材
- [ ] 选中跨文件夹素材

**测试结果**:
- [ ] 通过
- [ ] 失败

**备注**:

---

### 4. 图片数据获取

**接口**: `eagle.item.getImageData()`

**测试时间**: `YYYY-MM-DD HH:mm:ss`

**请求示例**:
```javascript
const imageData = await eagle.item.getImageData(itemId);
```

**测试场景**:
- [ ] PNG 格式
- [ ] JPEG 格式
- [ ] GIF 格式
- [ ] WebP 格式
- [ ] 大文件 (>10MB)

**Base64 编码测试**:
- 原始大小:
- Base64 大小:
- 编码耗时:

**测试结果**:
- [ ] 通过
- [ ] 失败

**备注**:

---

## 测试记录

### 测试批次 #1 - MCP 实际连接测试

**日期**: 2026-02-11

**测试目标**: 验证 Eagle MCP Server 连接、工具列表获取、素材数据读取

**测试环境**:
- Eagle MCP Server (Beta) v0.0.1
- 操作系统: macOS (Darwin 25.1.0)
- 连接方式: SSE + JSON-RPC 2.0

**测试步骤**:
1. curl 连接 `http://localhost:41596/sse`
2. 获取 sessionId
3. POST 初始化请求
4. 获取工具列表
5. 调用 `item_count` 统计素材
6. 调用 `item_get` 获取素材数据

**测试结果**:
- ✅ SSE 连接成功，返回 sessionId
- ✅ 初始化成功，获取到 serverInfo
- ✅ 工具列表获取成功（25 个工具）
- ✅ 素材计数成功
- ✅ 素材数据读取成功

**资料库统计数据**:

| 指标 | 数值 |
|------|------|
| 总素材数 | **45,129** |
| 未标签素材 | **33,283** (73.7%) |
| 未归类素材 | **4,961** (11%) |
| 标签总数 | **1,985** |

**未标签素材示例**:

| ID | 名称 | 格式 | 来源 URL |
|----|------|------|----------|
| MLHEAQKA645PQ | Gather Pricing Virtual Workspace | jpg | gather.town/pricing |
| M9QEOYK2TZBJR | Trucker Path Technology Built for Trucking | mp4 | truckerpath.com |
| MLG78LVN9S81F | 即梦AI - 一站式AI创作平台 | jpg | jimeng.jianying.com |

**关键发现**:
1. SSE 连接必须保持打开状态，POST 请求才能发送成功
2. 响应通过 SSE 事件流异步返回，不是 POST 的直接响应
3. POST 请求返回 `Accepted` 表示已接收
4. 73.7% 的素材没有标签 —— 这是 AI 归类的最大价值点

**备注**:
所有核心接口工作正常。MCP Server 处于 Beta 阶段但已经非常稳定。

---

## AI 辅助归类 - 实际用法

### 核心思路

你的素材库有 **45,129** 个素材，其中 **33,283 个 (73.7%)** 没有标签。
通过 MCP 服务 + AI (如 Claude) 可以实现自动智能归类：

```
Eagle 素材库 → MCP 获取素材元数据 → AI 分析 → MCP 写回标签/文件夹
```

### 方式 1: 直接在 Claude Code / Cursor 中使用

将 Eagle MCP 配置为 Claude Code 或 Cursor 的 MCP Server，AI 就能直接操作你的素材库：

**Claude Code 配置** (`~/.claude/mcp_servers.json`):
```json
{
  "eagle": {
    "type": "sse",
    "url": "http://localhost:41596/sse"
  }
}
```

**Cursor MCP 配置** (`.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "eagle": {
      "url": "http://localhost:41596/sse"
    }
  }
}
```

配置后，你可以直接对 AI 说：

> "帮我看看未标签的素材，根据名称和 URL 自动分类打标签"

AI 会自动调用 `item_get` 获取素材，分析后用 `item_add_tags` 批量打标签。

### 方式 2: 自动化脚本 (Node.js + Claude API)

```javascript
import Anthropic from '@anthropic-ai/sdk';

const anthropic = new Anthropic();

// 1. 通过 MCP 获取未标签素材
const untaggedItems = await mcpCall('item_get', {
  isUntagged: true,
  limit: 50
});

// 2. 让 AI 分析素材并建议标签
const response = await anthropic.messages.create({
  model: 'claude-sonnet-4-5-20250514',
  max_tokens: 4096,
  messages: [{
    role: 'user',
    content: `请分析以下 Eagle 素材，根据名称和 URL 为每个素材建议合适的标签。
返回 JSON 格式：[{"id": "素材ID", "tags": ["标签1", "标签2"]}]

素材列表：
${JSON.stringify(untaggedItems.map(item => ({
  id: item.id,
  name: item.name,
  ext: item.ext,
  url: item.url
})), null, 2)}`
  }]
});

// 3. 解析 AI 建议并通过 MCP 写回
const suggestions = JSON.parse(response.content[0].text);
for (const item of suggestions) {
  await mcpCall('item_add_tags', {
    ids: [item.id],
    tags: item.tags
  });
}
```

### 方式 3: AI 归类实际示例

基于测试获取的 3 个未标签素材，AI 分析结果：

| 素材 | 分析依据 | 建议标签 |
|------|---------|---------|
| Gather Pricing (jpg) | 名称含 "Pricing"、URL 为 gather.town | `定价页`, `SaaS`, `远程协作`, `网页截图` |
| Trucker Path (mp4) | 名称含 "Technology"、URL 为 truckerpath.com | `物流`, `科技`, `视频`, `官网` |
| 即梦AI (jpg) | 名称含 "AI创作平台"、URL 为 jimeng.jianying.com | `AI工具`, `创作平台`, `字节跳动`, `网页截图` |

**批量打标签命令**:
```bash
# 通过 MCP tools/call 发送
{
  "method": "tools/call",
  "params": {
    "name": "item_add_tags",
    "arguments": {
      "ids": ["MLHEAQKA645PQ"],
      "tags": ["定价页", "SaaS", "远程协作", "网页截图"]
    }
  }
}
```

### 进阶: 自动创建文件夹归类

```javascript
// 1. AI 分析素材后建议文件夹分类
const categories = {
  "SaaS产品": ["MLHEAQKA645PQ"],
  "AI工具": ["MLG78LVN9S81F"],
  "物流科技": ["M9QEOYK2TZBJR"]
};

// 2. 创建文件夹
const folders = await mcpCall('folder_create', {
  folders: Object.keys(categories).map(name => ({
    name,
    iconColor: 'blue'
  }))
});

// 3. 将素材添加到对应文件夹
for (const [folderName, itemIds] of Object.entries(categories)) {
  const folderId = folders.find(f => f.name === folderName).id;
  await mcpCall('item_add_to_folders', {
    ids: itemIds,
    folders: [folderId]
  });
}
```

### 推荐工作流

1. **小批量试跑** — 先用 `item_get(isUntagged: true, limit: 20)` 取少量素材
2. **AI 分析** — 让 Claude 根据 name + url + ext 建议标签
3. **人工审核** — 确认标签合理后再批量应用
4. **批量执行** — 使用 `item_add_tags` 增量添加（不会覆盖已有标签）
5. **逐步扩大** — 确认效果后加大 limit，循环处理

---

## 问题与解决方案

### 问题 1: MCP 服务连接超时

**现象**:
调用 API 时出现超时错误

**错误信息**:
```
Error: Request timeout after 5000ms
```

**分析**:
- Eagle 应用未启动
- MCP 服务端口被占用
- 防火墙阻止连接

**解决方案**:
1. 确认 Eagle 应用正常运行
2. 检查端口是否被占用: `lsof -i :41596`
3. 调整防火墙规则

**状态**:
- [ ] 已解决
- [ ] 待解决

---

### 问题 2:

**现象**:


**错误信息**:
```

```

**分析**:


**解决方案**:
1.

**状态**:
- [ ] 已解决
- [ ] 待解决

---

## 性能测试

### 大量素材加载测试

| 素材数量 | 加载时间 | 内存占用 | CPU 占用 |
|---------|---------|---------|---------|
| 100     |         |         |         |
| 500     |         |         |         |
| 1000    |         |         |         |
| 5000    |         |         |         |

### 导出性能测试

| 导出模式 | 素材数量 | 处理时间 | 文件大小 |
|---------|---------|---------|---------|
| 仅元数据 |         |         |         |
| Base64  |         |         |         |
| ZIP 包  |         |         |         |

---

## 兼容性测试

### Eagle 版本兼容性

- [ ] Eagle 3.0.x
- [ ] Eagle 3.1.x
- [ ] Eagle 4.0.x

### 操作系统兼容性

- [ ] macOS 13+
- [ ] macOS 12
- [ ] Windows 10
- [ ] Windows 11

---

## 待办事项

- [ ] 完成基础接口测试
- [ ] 性能测试与优化
- [ ] 错误处理机制完善
- [ ] 编写自动化测试脚本
- [ ] 文档更新与完善

---

## 参考资料

- [Eagle API 文档](https://eagle.cool/help/developer-api)
- [MCP 协议规范](https://modelcontextprotocol.io/)
- [插件开发指南](./README.md)
- [后端集成指南](./BACKEND_INTEGRATION.md)

---

## 更新日志

### 2024-XX-XX
- 初始化文档结构
- 添加基础测试用例

---

**维护人员**:
**最后更新**: 2024-XX-XX
