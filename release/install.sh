#!/bin/bash
# ============================================================================
# OpenClaw 微信频道插件 - 一键安装脚本
# ============================================================================
# 
# 使用方法：
#   curl -fsSL https://raw.githubusercontent.com/yuanchenglu/openclaw-wechat-plugin/main/release/install.sh | sh
#   
# 或指定配置：
#   OPENCLAW_URL=http://127.0.0.1:18789 curl -fsSL ... | sh
#
# 支持系统：macOS, Linux, Windows (WSL)
# ============================================================================

set -e

VERSION="1.2.0"
PLUGIN_DIR="${PLUGIN_DIR:-$HOME/.openclaw/wechat-channel}"
OPENCLAW_URL="${OPENCLAW_URL:-http://127.0.0.1:18789}"
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
    
    # 下载源列表（按优先级排序）
    local sources=(
        "https://gitee.com/yuanchenglu/openclaw-wechat-plugin/raw/main"
        "https://wechat.clawadmin.org"
        "https://raw.githubusercontent.com/yuanchenglu/openclaw-wechat-plugin/main"
        "https://claw-wechat.7color.vip"
    )
    
    mkdir -p "$PLUGIN_DIR"
    
    # 尝试从多个源下载
    for base_url in "${sources[@]}"; do
        if curl -fsSL --connect-timeout 10 --max-time 30 --retry 2 \
               "$base_url/src/client.py" -o "$PLUGIN_DIR/client.py" 2>/dev/null && \
           curl -fsSL --connect-timeout 10 --max-time 30 --retry 2 \
               "$base_url/requirements.txt" -o "$PLUGIN_DIR/requirements.txt" 2>/dev/null; then
            print_success "客户端已下载到: $PLUGIN_DIR (来源: $base_url)"
            return 0
        fi
    done
    
    print_error "所有下载源均失败，请检查网络连接"
    print_error "建议："
    print_error "  1. 检查网络是否正常"
    print_error "  2. 尝试手动下载: https://gitee.com/yuanchenglu/openclaw-wechat-plugin"
    exit 1
}

install_dependencies() {
    print_step "4/4" "安装依赖..."
    
    cd "$PLUGIN_DIR"
    $PIP_CMD install -q -i https://pypi.tuna.tsinghua.edu.cn/simple websockets httpx 2>/dev/null || {
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