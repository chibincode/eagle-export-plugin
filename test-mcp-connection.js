#!/usr/bin/env node

/**
 * Eagle MCP 服务连接测试脚本
 *
 * 用途：测试 Eagle MCP Server 的连接和基本功能
 * 运行：node test-mcp-connection.js
 */

const MCP_BASE_URL = 'http://localhost:41596';
const MCP_SSE_ENDPOINT = `${MCP_BASE_URL}/sse`;
const REQUEST_TIMEOUT_MS = 5000;

// 颜色输出
const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m'
};

function log(message, color = 'reset') {
  console.log(`${colors[color]}${message}${colors.reset}`);
}

function logSuccess(message) {
  log(`✅ ${message}`, 'green');
}

function logError(message) {
  log(`❌ ${message}`, 'red');
}

function logInfo(message) {
  log(`ℹ️  ${message}`, 'blue');
}

function logWarning(message) {
  log(`⚠️  ${message}`, 'yellow');
}

function logStep(message) {
  log(`\n${'='.repeat(60)}`, 'cyan');
  log(`  ${message}`, 'cyan');
  log(`${'='.repeat(60)}`, 'cyan');
}

function prettyPrintJson(value) {
  console.log(JSON.stringify(value, null, 2));
}

function parseTextContent(text) {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

class EagleMCPClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
    this.sseUrl = `${baseUrl}/sse`;
    this.abortController = null;
    this.readLoopPromise = null;
    this.connectPromise = null;
    this.messageEndpoint = null;
    this.pending = new Map();
    this.buffer = '';
    this.nextId = 0;
    this.endpointReady = null;
    this.resolveEndpointReady = null;
  }

  async ensureConnected() {
    if (this.messageEndpoint) {
      return;
    }

    if (!this.connectPromise) {
      this.connectPromise = this.connect();
    }

    await this.connectPromise;
  }

  async connect() {
    this.abortController = new AbortController();
    this.endpointReady = new Promise(resolve => {
      this.resolveEndpointReady = resolve;
    });

    const response = await fetch(this.sseUrl, {
      method: 'GET',
      headers: {
        Accept: 'text/event-stream',
      },
      signal: this.abortController.signal,
    });

    if (!response.ok) {
      throw new Error(`SSE 连接失败: HTTP ${response.status} ${response.statusText}`);
    }

    if (!response.body) {
      throw new Error('SSE 连接失败: 响应体为空');
    }

    this.readLoopPromise = this.readEvents(response.body.getReader());
    await Promise.race([
      this.endpointReady,
      new Promise((_, reject) => setTimeout(() => reject(new Error('等待 session endpoint 超时')), REQUEST_TIMEOUT_MS)),
    ]);
  }

  async readEvents(reader) {
    const decoder = new TextDecoder();

    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }

        this.buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
        this.processBufferedEvents();
      }
    } catch (error) {
      if (!this.abortController?.signal.aborted) {
        this.rejectAllPending(error);
      }
    }
  }

  processBufferedEvents() {
    let separatorIndex = this.buffer.indexOf('\n\n');

    while (separatorIndex !== -1) {
      const rawEvent = this.buffer.slice(0, separatorIndex);
      this.buffer = this.buffer.slice(separatorIndex + 2);
      this.handleEvent(rawEvent);
      separatorIndex = this.buffer.indexOf('\n\n');
    }
  }

  handleEvent(rawEvent) {
    if (!rawEvent.trim()) {
      return;
    }

    let eventType = 'message';
    const dataLines = [];

    for (const line of rawEvent.split('\n')) {
      if (line.startsWith('event:')) {
        eventType = line.slice('event:'.length).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice('data:'.length).trimStart());
      }
    }

    const data = dataLines.join('\n');
    if (!data) {
      return;
    }

    if (eventType === 'endpoint') {
      this.messageEndpoint = new URL(data, this.baseUrl).toString();
      if (this.resolveEndpointReady) {
        this.resolveEndpointReady();
      }
      return;
    }

    if (eventType === 'message') {
      let message;
      try {
        message = JSON.parse(data);
      } catch (error) {
        logWarning(`收到无法解析的 SSE 消息: ${error.message}`);
        return;
      }

      if (message.id != null && this.pending.has(message.id)) {
        const entry = this.pending.get(message.id);
        clearTimeout(entry.timeout);
        this.pending.delete(message.id);
        entry.resolve(message);
      }
    }
  }

  async sendNotification(method, params = {}) {
    await this.ensureConnected();

    const payload = {
      jsonrpc: '2.0',
      method,
      params,
    };

    const response = await fetch(this.messageEndpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`通知发送失败: HTTP ${response.status} ${response.statusText}`);
    }
  }

  async sendRequest(method, params = {}) {
    await this.ensureConnected();

    const id = ++this.nextId;
    const payload = {
      jsonrpc: '2.0',
      id,
      method,
      params,
    };

    const responsePromise = new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`等待响应超时 (id=${id})`));
      }, REQUEST_TIMEOUT_MS);

      this.pending.set(id, { resolve, reject, timeout });
    });

    try {
      const response = await fetch(this.messageEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
    } catch (error) {
      const pending = this.pending.get(id);
      if (pending) {
        clearTimeout(pending.timeout);
        this.pending.delete(id);
        pending.reject(new Error(`请求失败: ${error.message}`));
      }
    }

    return responsePromise;
  }

  rejectAllPending(error) {
    for (const [id, entry] of this.pending.entries()) {
      clearTimeout(entry.timeout);
      entry.reject(new Error(`SSE 连接中断 (id=${id}): ${error.message}`));
    }
    this.pending.clear();
  }

  async close() {
    this.abortController?.abort();
    this.rejectAllPending(new Error('客户端已关闭'));

    try {
      await this.readLoopPromise;
    } catch {
      // Ignore shutdown errors.
    }
  }
}

/**
 * 测试 1: 检查端口连接
 */
async function testPortConnection() {
  logStep('测试 1: 检查 MCP 服务端口连接');

  try {
    const response = await fetch(MCP_BASE_URL, {
      method: 'GET',
      signal: AbortSignal.timeout(5000)
    });

    logSuccess(`MCP 服务在 ${MCP_BASE_URL} 上运行`);
    return true;
  } catch (error) {
    logError(`无法连接到 MCP 服务: ${error.message}`);
    logWarning('请确保 Eagle 应用正在运行');
    return false;
  }
}

/**
 * 测试 2: 初始化连接
 */
async function testInitialize() {
  logStep('测试 2: 初始化 MCP 连接');

  try {
    const client = new EagleMCPClient(MCP_BASE_URL);
    const result = await client.sendRequest('initialize', {
      protocolVersion: '2024-11-05',
      capabilities: {},
      clientInfo: {
        name: 'eagle-plugin-test',
        version: '2.0.0'
      }
    });

    if (result.error) {
      logError(`初始化失败: ${result.error.message}`);
      await client.close();
      return null;
    }

    await client.sendNotification('notifications/initialized');
    logSuccess('MCP 连接初始化成功');
    logInfo(`协议版本: ${result.result?.protocolVersion || 'N/A'}`);
    logInfo(`服务端: ${result.result?.serverInfo?.name || 'N/A'} v${result.result?.serverInfo?.version || 'N/A'}`);
    logInfo(`消息端点: ${client.messageEndpoint || 'N/A'}`);

    if (result.result?.capabilities) {
      logInfo('服务端能力:');
      prettyPrintJson(result.result.capabilities);
    }

    return client;
  } catch (error) {
    logError(error.message);
    return null;
  }
}

/**
 * 测试 3: 列出可用工具
 */
async function testListTools(client) {
  logStep('测试 3: 获取可用工具列表');

  try {
    const result = await client.sendRequest('tools/list', {});

    if (result.error) {
      logError(`获取工具列表失败: ${result.error.message}`);
      return false;
    }

    const tools = result.result?.tools || [];
    logSuccess(`找到 ${tools.length} 个可用工具`);

    if (tools.length > 0) {
      logInfo('可用工具:');
      tools.forEach((tool, index) => {
        console.log(`  ${index + 1}. ${tool.name}`);
        if (tool.description) {
          console.log(`     描述: ${tool.description}`);
        }
      });
    } else {
      logWarning('未找到任何工具');
    }

    return tools;
  } catch (error) {
    logError(error.message);
    return false;
  }
}

/**
 * 测试 4: 调用工具 - 获取应用信息
 */
async function testGetAppInfo(client) {
  logStep('测试 4: 调用工具 - 获取应用信息');

  try {
    const result = await client.sendRequest('tools/call', {
      name: 'get_app_info',
      arguments: {}
    });

    if (result.error) {
      logError(`调用失败: ${result.error.message}`);
      return false;
    }

    logSuccess('成功获取应用信息');

    if (result.result?.content) {
      logInfo('返回内容:');
      result.result.content.forEach(item => {
        if (item.type === 'text') {
          const data = parseTextContent(item.text);
          if (typeof data === 'string') {
            console.log(data);
          } else {
            prettyPrintJson(data);
          }
        }
      });
    }

    return true;
  } catch (error) {
    logError(error.message);
    return false;
  }
}

/**
 * 测试 5: 调用工具 - 获取素材列表
 */
async function testGetItems(client) {
  logStep('测试 5: 调用工具 - 获取素材列表（前 5 个）');

  try {
    const result = await client.sendRequest('tools/call', {
      name: 'item_get',
      arguments: {
        limit: 5
      }
    });

    if (result.error) {
      logError(`调用失败: ${result.error.message}`);
      return false;
    }

    logSuccess('成功获取素材列表');

    if (result.result?.content) {
      logInfo('返回内容:');
      result.result.content.forEach(item => {
        if (item.type === 'text') {
          const data = parseTextContent(item.text);
          if (typeof data === 'string') {
            console.log(item.text);
            return;
          }

          const items = Array.isArray(data?.data) ? data.data : [];
          logInfo(`共 ${items.length} 个素材，服务端总数 ${data?.totalCount ?? 'N/A'}`);

          items.forEach((asset, index) => {
            console.log(`\n  素材 ${index + 1}:`);
            console.log(`    ID: ${asset.id}`);
            console.log(`    名称: ${asset.name}`);
            console.log(`    扩展名: ${asset.ext}`);
            if (asset.tags?.length) console.log(`    标签: ${asset.tags.join(', ')}`);
            if (asset.filePath) console.log(`    路径: ${asset.filePath}`);
          });
        }
      });
    }

    return true;
  } catch (error) {
    logError(error.message);
    return false;
  }
}

/**
 * 主测试流程
 */
async function runTests() {
  log('\n╔════════════════════════════════════════════════════════════╗', 'cyan');
  log('║          Eagle MCP 服务连接测试                            ║', 'cyan');
  log('╚════════════════════════════════════════════════════════════╝', 'cyan');

  const results = {
    total: 5,
    passed: 0,
    failed: 0
  };

  // 测试 1: 端口连接
  const portConnected = await testPortConnection();
  if (!portConnected) {
    logError('\n无法连接到 MCP 服务，测试终止');
    logWarning('请确保:');
    logWarning('1. Eagle 应用正在运行');
    logWarning('2. MCP 服务已启用');
    logWarning('3. 端口 41596 未被占用');
    process.exit(1);
  }
  results.passed++;

  const client = await testInitialize();
  if (client) {
    results.passed++;
  } else {
    results.failed++;
  }

  if (client) {
    // 测试 3: 列出工具
    const tools = await testListTools(client);
    if (tools) {
      results.passed++;
    } else {
      results.failed++;
    }

    // 测试 4: 获取应用信息
    if (await testGetAppInfo(client)) {
      results.passed++;
    } else {
      results.failed++;
    }

    // 测试 5: 获取素材列表
    if (await testGetItems(client)) {
      results.passed++;
    } else {
      results.failed++;
    }

    await client.close();
  }

  // 输出测试总结
  logStep('测试总结');
  log(`总测试数: ${results.total}`, 'cyan');
  logSuccess(`通过: ${results.passed}`);
  if (results.failed > 0) {
    logError(`失败: ${results.failed}`);
  }

  const percentage = Math.round((results.passed / results.total) * 100);
  log(`\n成功率: ${percentage}%`, percentage === 100 ? 'green' : 'yellow');

  if (percentage === 100) {
    log('\n🎉 所有测试通过！Eagle MCP 服务工作正常。\n', 'green');
  } else {
    log('\n⚠️  部分测试失败，请查看上方错误信息。\n', 'yellow');
  }
}

// 运行测试
runTests().catch(error => {
  logError(`测试脚本出错: ${error.message}`);
  process.exit(1);
});
