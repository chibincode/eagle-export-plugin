#!/bin/bash

# Eagle MCP 服务连接测试脚本（Shell 版本）
# 用途：快速测试 Eagle MCP Server 的连接和基本功能
# 运行：bash test-mcp-connection.sh

MCP_BASE_URL="http://localhost:41596"
MCP_SSE_ENDPOINT="${MCP_BASE_URL}/sse"
MCP_MESSAGE_ENDPOINT=""
SSE_FILE=""
SSE_PID=""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 日志函数
log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_step() {
    local divider
    divider=$(printf '=%.0s' {1..60})
    echo -e "\n${CYAN}${divider}${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}${divider}${NC}"
}

# 检查依赖
check_dependencies() {
    if ! command -v curl &> /dev/null; then
        log_error "curl 未安装，请先安装 curl"
        exit 1
    fi

    if ! command -v jq &> /dev/null; then
        log_warning "jq 未安装，输出将不会格式化（建议安装: brew install jq）"
    fi
}

# 格式化 JSON 输出
format_json() {
    if command -v jq &> /dev/null; then
        echo "$1" | jq '.'
    else
        echo "$1"
    fi
}

cleanup() {
    if [ -n "$SSE_PID" ]; then
        kill "$SSE_PID" >/dev/null 2>&1 || true
        wait "$SSE_PID" 2>/dev/null || true
    fi

    if [ -n "$SSE_FILE" ] && [ -f "$SSE_FILE" ]; then
        rm -f "$SSE_FILE"
    fi
}

start_session() {
    log_step "测试 2: 初始化 MCP 会话"

    SSE_FILE=$(mktemp)
    curl -sN "${MCP_SSE_ENDPOINT}" > "${SSE_FILE}" &
    SSE_PID=$!

    local endpoint=""
    local attempt
    for attempt in {1..50}; do
        endpoint=$(sed -n 's/^data: //p' "${SSE_FILE}" | head -n 1)
        if [ -n "$endpoint" ]; then
            break
        fi
        sleep 0.1
    done

    if [ -z "$endpoint" ]; then
        log_error "未能从 SSE 连接中获取 session endpoint"
        return 1
    fi

    MCP_MESSAGE_ENDPOINT="${MCP_BASE_URL}${endpoint}"
    log_success "MCP 会话已建立"
    log_info "消息端点: ${MCP_MESSAGE_ENDPOINT}"
    return 0
}

wait_for_response() {
    local id="$1"
    local attempt
    local response=""

    for attempt in {1..100}; do
        response=$(grep "\"id\":${id}" "${SSE_FILE}" | tail -n 1 | sed 's/^data: //')
        if [ -n "$response" ]; then
            echo "$response"
            return 0
        fi
        sleep 0.1
    done

    return 1
}

send_request() {
    local id="$1"
    local payload="$2"

    local status
    status=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${MCP_MESSAGE_ENDPOINT}" \
        -H "Content-Type: application/json" \
        -d "${payload}")

    if [ "$status" != "200" ] && [ "$status" != "202" ]; then
        log_error "请求发送失败: HTTP ${status}"
        return 1
    fi

    wait_for_response "$id"
}

test_initialize() {
    local response=""

    if ! response=$(send_request 1 '{
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "eagle-plugin-test",
                "version": "2.0.0"
            }
        }
    }'); then
        log_error "初始化失败"
        return 1
    fi

    if echo "$response" | grep -q '"error"'; then
        log_error "初始化失败"
        format_json "$response"
        return 1
    fi

    curl -s -o /dev/null -w "%{http_code}" -X POST "${MCP_MESSAGE_ENDPOINT}" \
        -H "Content-Type: application/json" \
        -d '{
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }' >/dev/null

    log_success "MCP 连接初始化成功"
    log_info "响应内容:"
    format_json "$response"
    return 0
}

# 测试 1: 检查端口连接
test_port_connection() {
    log_step "测试 1: 检查 MCP 服务端口连接"

    if curl -s --connect-timeout 5 "${MCP_BASE_URL}" > /dev/null 2>&1; then
        log_success "MCP 服务在 ${MCP_BASE_URL} 上运行"
        return 0
    else
        log_error "无法连接到 MCP 服务"
        log_warning "请确保 Eagle 应用正在运行"
        return 1
    fi
}

# 测试 2: 列出可用工具
test_list_tools() {
    log_step "测试 3: 获取可用工具列表"

    local response=""
    if ! response=$(send_request 2 '{
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }'); then
        log_error "未收到响应"
        return 1
    fi

    # 检查是否有错误
    if echo "$response" | grep -q '"error"'; then
        log_error "获取工具列表失败"
        echo "$response"
        return 1
    fi

    log_success "成功获取工具列表"
    log_info "响应内容:"
    format_json "$response"
    return 0
}

# 测试 4: 获取应用信息
test_get_app_info() {
    log_step "测试 4: 调用工具 - 获取应用信息"

    local response=""
    if ! response=$(send_request 3 '{
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "get_app_info",
                "arguments": {}
            }
        }'); then
        log_error "未收到响应"
        return 1
    fi

    if echo "$response" | grep -q '"error"'; then
        log_error "调用失败"
        echo "$response"
        return 1
    fi

    log_success "成功获取应用信息"
    log_info "响应内容:"
    format_json "$response"
    return 0
}

# 测试 5: 获取素材列表
test_get_items() {
    log_step "测试 5: 调用工具 - 获取素材列表（前 5 个）"

    local response=""
    if ! response=$(send_request 4 '{
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "item_get",
                "arguments": {
                    "limit": 5
                }
            }
        }'); then
        log_error "未收到响应"
        return 1
    fi

    if echo "$response" | grep -q '"error"'; then
        log_error "调用失败"
        echo "$response"
        return 1
    fi

    log_success "成功获取素材列表"
    log_info "响应内容:"
    format_json "$response"
    return 0
}

# 主测试流程
main() {
    echo -e "\n${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║          Eagle MCP 服务连接测试 (Shell 版本)              ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"

    trap cleanup EXIT

    # 检查依赖
    check_dependencies

    total_tests=6
    passed=0
    failed=0

    # 运行测试
    if test_port_connection; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
    fi

    if [ $failed -eq 1 ]; then
        log_error "\n无法连接到 MCP 服务，测试终止"
        log_warning "请确保:"
        log_warning "1. Eagle 应用正在运行"
        log_warning "2. MCP 服务已启用"
        log_warning "3. 端口 41596 未被占用"
        exit 1
    fi

    if start_session; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
    fi

    if [ $failed -gt 1 ]; then
        log_error "\n会话初始化失败，测试终止"
        exit 1
    fi

    if test_initialize; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
    fi

    if test_list_tools; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
    fi

    if test_get_app_info; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
    fi

    if test_get_items; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
    fi

    # 测试总结
    log_step "测试总结"
    echo -e "${CYAN}总测试数: ${total_tests}${NC}"
    log_success "通过: ${passed}"
    [ $failed -gt 0 ] && log_error "失败: ${failed}"

    percentage=$((passed * 100 / total_tests))
    echo -e "\n${CYAN}成功率: ${percentage}%${NC}"

    if [ $percentage -eq 100 ]; then
        echo -e "\n${GREEN}🎉 所有测试通过！Eagle MCP 服务工作正常。${NC}\n"
    else
        echo -e "\n${YELLOW}⚠️  部分测试失败，请查看上方错误信息。${NC}\n"
    fi
}

# 运行主函数
main
