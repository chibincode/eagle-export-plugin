#!/usr/bin/env node

/**
 * Eagle MCP 服务连接测试脚本
 *
 * 用途：测试 Eagle MCP Server 的连接和基本功能
 * 运行：node test-mcp-connection.js
 */

const MCP_BASE_URL = 'http://localhost:41596';
const MCP_MESSAGE_ENDPOINT = `${MCP_BASE_URL}/message`;

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

/**
 * 发送 JSON-RPC 请求
 */
async function sendRequest(method, params = {}) {
  const payload = {
    jsonrpc: '2.0',
    id: Date.now(),
    method,
    params
  };

  try {
    const response = await fetch(MCP_MESSAGE_ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    throw new Error(`请求失败: ${error.message}`);
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
    const result = await sendRequest('initialize', {
      protocolVersion: '2024-11-05',
      capabilities: {},
      clientInfo: {
        name: 'eagle-plugin-test',
        version: '1.0.0'
      }
    });

    if (result.error) {
      logError(`初始化失败: ${result.error.message}`);
      return false;
    }

    logSuccess('MCP 连接初始化成功');
    logInfo(`协议版本: ${result.result?.protocolVersion || 'N/A'}`);
    logInfo(`服务端: ${result.result?.serverInfo?.name || 'N/A'} v${result.result?.serverInfo?.version || 'N/A'}`);

    if (result.result?.capabilities) {
      logInfo('服务端能力:');
      console.log(JSON.stringify(result.result.capabilities, null, 2));
    }

    return true;
  } catch (error) {
    logError(error.message);
    return false;
  }
}

/**
 * 测试 3: 列出可用工具
 */
async function testListTools() {
  logStep('测试 3: 获取可用工具列表');

  try {
    const result = await sendRequest('tools/list');

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
 * 测试 4: 调用工具 - 获取资料库信息
 */
async function testGetLibraryInfo() {
  logStep('测试 4: 调用工具 - 获取资料库信息');

  try {
    const result = await sendRequest('tools/call', {
      name: 'get_library_info',
      arguments: {}
    });

    if (result.error) {
      logError(`调用失败: ${result.error.message}`);
      return false;
    }

    logSuccess('成功获取资料库信息');

    if (result.result?.content) {
      logInfo('返回内容:');
      result.result.content.forEach(item => {
        if (item.type === 'text') {
          try {
            const data = JSON.parse(item.text);
            console.log(JSON.stringify(data, null, 2));
          } catch {
            console.log(item.text);
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
async function testGetItems() {
  logStep('测试 5: 调用工具 - 获取素材列表（前 5 个）');

  try {
    const result = await sendRequest('tools/call', {
      name: 'get_items',
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
          try {
            const data = JSON.parse(item.text);
            if (Array.isArray(data)) {
              logInfo(`共 ${data.length} 个素材`);
              data.forEach((asset, index) => {
                console.log(`\n  素材 ${index + 1}:`);
                console.log(`    ID: ${asset.id}`);
                console.log(`    名称: ${asset.name}`);
                console.log(`    扩展名: ${asset.ext}`);
                if (asset.tags) console.log(`    标签: ${asset.tags.join(', ')}`);
              });
            } else {
              console.log(JSON.stringify(data, null, 2));
            }
          } catch {
            console.log(item.text);
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

  // 测试 2: 初始化
  if (await testInitialize()) {
    results.passed++;
  } else {
    results.failed++;
  }

  // 测试 3: 列出工具
  const tools = await testListTools();
  if (tools) {
    results.passed++;
  } else {
    results.failed++;
  }

  // 测试 4: 获取资料库信息
  if (await testGetLibraryInfo()) {
    results.passed++;
  } else {
    results.failed++;
  }

  // 测试 5: 获取素材列表
  if (await testGetItems()) {
    results.passed++;
  } else {
    results.failed++;
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
