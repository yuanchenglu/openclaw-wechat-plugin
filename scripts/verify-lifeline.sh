#!/bin/bash
# ============================================================================
# OpenClaw 微信频道插件 - 生命线验证脚本
# ============================================================================
# 
# 用法: ./scripts/verify-lifeline.sh
#
# 此脚本验证从安装到使用的完整链路是否通畅
# 核心原则：从 README.md 提取最新安装提示词，模拟用户实际操作流程
# ============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ERRORS=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
README_PATH="$PROJECT_DIR/README.md"

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       OpenClaw 微信频道插件 - 生命线验证                       ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================================
# 从 README 提取中转服务地址（排除示例占位符和多余字符）
# ============================================================================
get_relay_url() {
    # 从配置表格中提取实际地址
    # 格式: `wss://xxx/ws-channel` | 说明
    local url=$(grep "RELAY_URL" "$README_PATH" | grep -v "你的服务器" | grep -oE 'wss://[a-zA-Z0-9./-]+' | head -1)
    
    if [ -z "$url" ]; then
        echo "wss://claw.7color.vip/ws-channel"
    else
        echo "$url"
    fi
}

# ============================================================================
# 检查点 1: 安装脚本可访问性（使用 README 中的 URL）
# ============================================================================
check_install_script() {
    echo -e "${BLUE}[1/7] 验证安装脚本可访问性（使用 README 最新提示词）...${NC}"
    
    # 从 README 提取所有安装脚本 URL
    local sources=$(grep -oE 'https://[a-zA-Z0-9./_-]+install\.sh' "$README_PATH" | sort -u)
    
    if [ -z "$sources" ]; then
        echo -e "  ${RED}❌ 无法从 README 提取安装脚本 URL${NC}"
        ERRORS=$((ERRORS + 1))
        return 1
    fi
    
    local install_ok=false
    local first_ok_source=""
    local count=0
    
    while IFS= read -r src; do
        count=$((count + 1))
        local http_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 30 "$src" 2>/dev/null || echo "000")
        if [ "$http_code" = "200" ]; then
            if [ "$install_ok" = false ]; then
                first_ok_source="$src"
            fi
            install_ok=true
            echo -e "  ${GREEN}✅ [$count] 可访问:${NC} $src"
        else
            echo -e "  ${YELLOW}⚠️ [$count] 不可访问 (HTTP $http_code):${NC} $src"
        fi
    done <<< "$sources"
    
    if [ "$install_ok" = false ]; then
        echo -e "  ${RED}❌ 所有安装脚本源均不可访问${NC}"
        ERRORS=$((ERRORS + 1))
        return 1
    fi
    
    echo ""
    echo -e "  ${GREEN}首选源: $first_ok_source${NC}"
}

# ============================================================================
# 检查点 2: 客户端代码可下载
# ============================================================================
check_client_code() {
    echo -e "${BLUE}[2/7] 检查客户端代码可下载...${NC}"
    
    # 从安装脚本 URL 推断客户端代码 URL
    local sources=$(grep -oE 'https://[a-zA-Z0-9./_-]+/release/install\.sh' "$README_PATH" | \
                    sed 's|/release/install\.sh|/src/client.py|g' | sort -u)
    
    local client_ok=false
    while IFS= read -r src; do
        local http_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 30 "$src" 2>/dev/null || echo "000")
        if [ "$http_code" = "200" ]; then
            client_ok=true
            echo -e "  ${GREEN}✅ 可下载:${NC} $src"
            break
        fi
    done <<< "$sources"
    
    if [ "$client_ok" = false ]; then
        echo -e "  ${RED}❌ 所有客户端代码源均不可下载${NC}"
        ERRORS=$((ERRORS + 1))
    fi
}

# ============================================================================
# 检查点 3: 本地 OpenClaw 服务
# ============================================================================
check_openclaw() {
    echo -e "${BLUE}[3/7] 检查本地 OpenClaw 服务...${NC}"
    
    local code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 "http://127.0.0.1:18789/" 2>/dev/null || echo "000")
    if [ "$code" = "200" ]; then
        echo -e "  ${GREEN}✅ 本地 OpenClaw 服务正常${NC}"
    else
        echo -e "  ${YELLOW}⚠️ 本地 OpenClaw 服务未运行 (非阻塞)${NC}"
    fi
}

# ============================================================================
# 检查点 4: 中转服务健康状态
# ============================================================================
check_relay_health() {
    echo -e "${BLUE}[4/7] 检查中转服务健康状态...${NC}"
    
    local relay_url=$(get_relay_url)
    local relay_host=$(echo "$relay_url" | sed 's|wss://||' | sed 's|/.*||')
    local health_url="https://$relay_host/api/health"
    
    echo -e "  中转服务: $relay_host"
    
    local health=$(curl -s --connect-timeout 10 --max-time 30 "$health_url" 2>/dev/null || echo '{"health_status":{"redis":"unknown"}}')
    
    local redis_status=$(echo "$health" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('health_status', {}).get('redis', 'unknown'))
except:
    print('unknown')
" 2>/dev/null || echo "unknown")
    
    local wechat_status=$(echo "$health" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('health_status', {}).get('wechat_api', 'unknown'))
except:
    print('unknown')
" 2>/dev/null || echo "unknown")
    
    if [ "$redis_status" = "healthy" ]; then
        echo -e "  ${GREEN}✅ Redis 正常${NC}"
    else
        echo -e "  ${RED}❌ Redis 异常: $redis_status${NC}"
        echo -e "  ${YELLOW}   🔧 需要登录 ECS 服务器修复 Redis${NC}"
        ERRORS=$((ERRORS + 1))
    fi
    
    if [ "$wechat_status" = "healthy" ]; then
        echo -e "  ${GREEN}✅ 微信 API 正常${NC}"
    else
        echo -e "  ${YELLOW}⚠️ 微信 API 状态: $wechat_status${NC}"
    fi
}

# ============================================================================
# 检查点 5: WebSocket 端点
# ============================================================================
check_websocket() {
    echo -e "${BLUE}[5/7] 检查 WebSocket 端点...${NC}"
    
    local ws_url=$(get_relay_url)
    echo -e "  测试端点: $ws_url"
    
    local ws_check=$(python3 -c "
import asyncio
import websockets
import json
import sys

async def check():
    try:
        async with websockets.connect(
            '$ws_url',
            ping_interval=30,
            ping_timeout=10,
            close_timeout=5
        ) as ws:
            await ws.send(json.dumps({'type': 'ping'}))
            response = await asyncio.wait_for(ws.recv(), timeout=5)
            print('OK')
            sys.exit(0)
    except Exception as e:
        print(f'FAIL: {type(e).__name__}: {str(e)[:50]}')
        sys.exit(1)

try:
    asyncio.run(check())
except SystemExit as e:
    sys.exit(e.code)
" 2>&1)
    
    local ws_exit=$?
    if [ $ws_exit -eq 0 ] && echo "$ws_check" | grep -q "OK"; then
        echo -e "  ${GREEN}✅ WebSocket 端点可连接${NC}"
    else
        echo -e "  ${RED}❌ WebSocket 端点异常: $ws_check${NC}"
        ERRORS=$((ERRORS + 1))
    fi
}

# ============================================================================
# 检查点 6: 单元测试
# ============================================================================
check_unit_tests() {
    echo -e "${BLUE}[6/7] 运行单元测试...${NC}"
    
    if [ -d "$PROJECT_DIR/tests" ]; then
        cd "$PROJECT_DIR"
        if python3 -m pytest tests/ -v --tb=short -q 2>&1 | tail -5 | grep -qE "(passed|PASSED)"; then
            echo -e "  ${GREEN}✅ 单元测试通过${NC}"
        else
            echo -e "  ${YELLOW}⚠️ 单元测试未完全通过 (非阻塞)${NC}"
        fi
    else
        echo -e "  ${YELLOW}⚠️ 未找到测试目录${NC}"
    fi
}

# ============================================================================
# 检查点 7: 客户端注册流程测试
# ============================================================================
check_client_registration() {
    echo -e "${BLUE}[7/7] 测试客户端注册流程...${NC}"
    
    local ws_url=$(get_relay_url)
    
    local reg_check=$(python3 -c "
import asyncio
import websockets
import json
import sys
import random

async def test_register():
    try:
        async with websockets.connect(
            '$ws_url',
            ping_interval=30,
            ping_timeout=10,
            close_timeout=5
        ) as ws:
            # 发送注册消息
            await ws.send(json.dumps({
                'type': 'register',
                'instance_type': 'local',
                'device_id': 'lifeline_test_' + str(random.randint(1000, 9999)),
                'device_type': 'bare',
                'machine_id': 'test_machine',
                'system_username': 'lifeline_test',
                'client_version': '1.4.0',
                'min_server_version': '1.0.0',
                'is_new_device': True
            }))
            
            # 等待响应
            response = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(response)
            
            if data.get('type') == 'registered':
                print('OK: Registration successful')
                sys.exit(0)
            elif data.get('type') == 'error':
                print(f'FAIL: {data.get(\"message\")}')
                sys.exit(1)
            else:
                print(f'FAIL: Unexpected response: {data}')
                sys.exit(1)
    except Exception as e:
        print(f'FAIL: {type(e).__name__}: {str(e)[:80]}')
        sys.exit(1)

try:
    asyncio.run(test_register())
except SystemExit as e:
    sys.exit(e.code)
" 2>&1)
    
    local reg_exit=$?
    if [ $reg_exit -eq 0 ]; then
        echo -e "  ${GREEN}✅ 客户端注册流程正常${NC}"
    else
        echo -e "  ${RED}❌ 客户端注册流程失败: $reg_check${NC}"
        ERRORS=$((ERRORS + 1))
    fi
}

# ============================================================================
# 主流程
# ============================================================================
main() {
    # 检查 README 存在
    if [ ! -f "$README_PATH" ]; then
        echo -e "${RED}❌ README.md 不存在: $README_PATH${NC}"
        exit 1
    fi
    
    echo -e "${BLUE}项目目录: $PROJECT_DIR${NC}"
    echo -e "${BLUE}README: $README_PATH${NC}"
    echo ""
    
    # 执行所有检查
    check_install_script
    check_client_code
    check_openclaw
    check_relay_health
    check_websocket
    check_unit_tests
    check_client_registration
    
    # 总结
    echo ""
    echo "============================================================"
    if [ $ERRORS -eq 0 ]; then
        echo -e "${GREEN}✅ 生命线验证通过！${NC}"
        echo ""
        echo "所有关键服务正常运行，可以安全 push。"
        exit 0
    else
        echo -e "${RED}❌ 生命线验证失败！发现 $ERRORS 个错误${NC}"
        echo ""
        echo "请修复上述错误后再 push。"
        echo ""
        echo "常见修复方法："
        echo "  - Redis 异常: SSH 到 ECS 重启 Redis 服务"
        echo "  - WebSocket 异常: 检查服务端 WebSocket 服务状态"
        echo "  - 注册失败: 检查服务端日志和 Redis 连接"
        exit 1
    fi
}

main "$@"
