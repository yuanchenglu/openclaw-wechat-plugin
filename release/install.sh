#!/bin/bash
# ============================================================================
# OpenClaw 微信频道插件 - 一键安装脚本
# ============================================================================
# 
# 使用方法：
#   curl -fsSL https://raw.githubusercontent.com/yuanchenglu/openclaw-wechat-client/main/release/install.sh | sh
#   
# 或指定配置：
#   RELAY_URL=wss://your-server.com/ws-channel curl -fsSL ... | sh
#
# 支持系统：macOS, Linux, Windows (WSL)
# ============================================================================

set -e

VERSION="1.2.0"
PLUGIN_DIR="${PLUGIN_DIR:-$HOME/.openclaw/wechat-channel}"
OPENCLAW_URL="${OPENCLAW_URL:-http://localhost:8080}"
RELAY_URL="${RELAY_URL:-wss://claw.7color.vip/ws-channel}"
INSTANCE_TYPE="${INSTANCE_TYPE:-bare}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_banner() {
    echo ""
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║       OpenClaw 微信频道客户端 v${VERSION}                       ║${NC}"
    echo -e "${BLUE}║       让你的 AI，就在微信里                                    ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_step() {
    echo -e "${BLUE}[${1}] ${2}${NC}"
}

print_success() {
    echo -e "${GREEN}✅ ${1}${NC}"
}

print_error() {
    echo -e "${RED}❌ ${1}${NC}"
}

check_python() {
    print_step "1/4" "检查 Python 环境..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
        print_success "Python3 已安装"
        return 0
    fi
    
    if command -v python &> /dev/null; then
        PYTHON_CMD="python"
        print_success "Python 已安装"
        return 0
    fi
    
    print_error "未找到 Python，请先安装 Python 3.8+"
    exit 1
}

check_pip() {
    print_step "2/4" "检查 pip..."
    
    if $PYTHON_CMD -m pip --version &> /dev/null; then
        PIP_CMD="$PYTHON_CMD -m pip"
        print_success "pip 已安装"
        return 0
    fi
    
    print_error "未找到 pip，请先安装 pip"
    exit 1
}

download_client() {
    print_step "3/4" "下载客户端..."
    
    local repo_url="https://raw.githubusercontent.com/yuanchenglu/openclaw-wechat-client/main"
    local temp_dir=$(mktemp -d)
    
    mkdir -p "$PLUGIN_DIR"
    
    curl -fsSL "$repo_url/plugin/src/client.py" -o "$PLUGIN_DIR/client.py"
    curl -fsSL "$repo_url/plugin/requirements.txt" -o "$PLUGIN_DIR/requirements.txt"
    
    print_success "客户端已下载到: $PLUGIN_DIR"
}

install_dependencies() {
    print_step "4/4" "安装依赖..."
    
    cd "$PLUGIN_DIR"
    $PIP_CMD install -q websockets httpx 2>/dev/null || {
        print_error "依赖安装失败"
        exit 1
    }
    
    print_success "依赖已安装"
}

create_launcher() {
    cat > "$PLUGIN_DIR/start.sh" << LAUNCHER_EOF
#!/bin/bash
cd "$(dirname "\$0")"
OPENCLAW_URL="\${OPENCLAW_URL:-$OPENCLAW_URL}"
RELAY_URL="\${RELAY_URL:-$RELAY_URL}"
INSTANCE_TYPE="\${INSTANCE_TYPE:-$INSTANCE_TYPE}"
echo "OpenClaw 微信频道客户端 v${VERSION}"
echo "OpenClaw: \$OPENCLAW_URL"
echo "中转服务: \$RELAY_URL"
exec python3 client.py --openclaw-url "\$OPENCLAW_URL" --relay-url "\$RELAY_URL" --instance-type "\$INSTANCE_TYPE" "\$@"
LAUNCHER_EOF
    chmod +x "$PLUGIN_DIR/start.sh"
    
    cat > "$PLUGIN_DIR/stop.sh" << 'STOP_EOF'
#!/bin/bash
pkill -f "python.*client.py.*wechat" 2>/dev/null || true
echo "客户端已停止"
STOP_EOF
    chmod +x "$PLUGIN_DIR/stop.sh"
    
    cat > "$PLUGIN_DIR/uninstall.sh" << UNINSTALL_EOF
#!/bin/bash
rm -rf "$PLUGIN_DIR"
echo "已卸载"
UNINSTALL_EOF
    chmod +x "$PLUGIN_DIR/uninstall.sh"
}

print_completion() {
    echo ""
    echo -e "${GREEN}✅ 安装完成！${NC}"
    echo ""
    echo "使用方法："
    echo "  $PLUGIN_DIR/start.sh"
    echo ""
    echo "自定义配置："
    echo "  OPENCLAW_URL=http://localhost:3000 $PLUGIN_DIR/start.sh"
    echo "  RELAY_URL=wss://your-server.com/ws-channel $PLUGIN_DIR/start.sh"
    echo ""
}

main() {
    print_banner
    check_python
    check_pip
    download_client
    install_dependencies
    create_launcher
    print_completion
}

main "$@"