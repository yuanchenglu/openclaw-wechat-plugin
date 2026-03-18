#!/bin/bash
# ============================================================================
# OpenClaw 微信频道插件 - 一键安装脚本
# ============================================================================
# 
# 使用方法：
#   curl -fsSL https://raw.githubusercontent.com/yuanchenglu/openclaw-wechat-plugin/main/release/install.sh | bash
#   
#   注意：必须使用 bash 执行，不能使用 sh
#
# 或指定配置：
#   OPENCLAW_URL=http://127.0.0.1:18789 curl -fsSL ... | bash
#
# 支持系统：macOS, Linux, Windows (WSL)
# ============================================================================

# 检测是否使用 bash 执行
if [ -z "$BASH_VERSION" ]; then
    echo "错误: 请使用 bash 执行此脚本，而不是 sh"
    echo "正确用法: curl -fsSL ... | bash"
    exit 1
fi

set -e

VERSION="1.4.0"
PLUGIN_DIR="${PLUGIN_DIR:-$HOME/.openclaw/wechat-channel}"
OPENCLAW_URL="${OPENCLAW_URL:-http://127.0.0.1:18789}"
RELAY_URL="${RELAY_URL:-wss://claw.7color.vip/ws-channel}"
INSTANCE_TYPE="${INSTANCE_TYPE:-local}"


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
    
    # 需要下载的模块列表（区分 src 目录和根目录）
    # src 目录下的 Python 模块
    local src_modules=("client.py" "watchdog.py" "updater.py" "wechat_types.py" "update_state.py")
    # 根目录下的配置文件
    local root_modules=("requirements.txt")
    
    # 尝试从多个源下载
    for base_url in "${sources[@]}"; do
        local success=true
        
        # 下载 src 目录下的模块
        for module in "${src_modules[@]}"; do
            if ! curl -fsSL --connect-timeout 10 --max-time 30 --retry 2 \
                   "$base_url/src/$module" -o "$PLUGIN_DIR/$module" 2>/dev/null; then
                success=false
                break
            fi
        done
        
        # 如果 src 模块下载成功，继续下载根目录文件
        if $success; then
            for module in "${root_modules[@]}"; do
                if ! curl -fsSL --connect-timeout 10 --max-time 30 --retry 2 \
                       "$base_url/$module" -o "$PLUGIN_DIR/$module" 2>/dev/null; then
                    success=false
                    break
                fi
            done
        fi
        
        if $success; then
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
    
    # 创建虚拟环境（解决 Ubuntu 24.04 externally-managed-environment 问题）
    if [ ! -d "$PLUGIN_DIR/venv" ]; then
        $PYTHON_CMD -m venv "$PLUGIN_DIR/venv" || {
            print_error "虚拟环境创建失败"
            exit 1
        }
        print_success "虚拟环境已创建"
    fi
    
    # 激活虚拟环境
    source "$PLUGIN_DIR/venv/bin/activate" || {
        print_error "虚拟环境激活失败"
        exit 1
    }
    
    # 安装依赖
    pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple websockets httpx 2>/dev/null || {
        print_error "依赖安装失败"
        exit 1
    }
    
    print_success "依赖已安装"
}

create_launcher() {
    cat > "$PLUGIN_DIR/start.sh" << LAUNCHER_EOF
#!/bin/bash
cd "\$(dirname "\$0")"
OPENCLAW_URL="${OPENCLAW_URL:-$OPENCLAW_URL}"
RELAY_URL="${RELAY_URL:-$RELAY_URL}"
INSTANCE_TYPE="${INSTANCE_TYPE:-$INSTANCE_TYPE}"

# 激活虚拟环境
if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "OpenClaw 微信频道客户端 v${VERSION}"
echo "OpenClaw: $OPENCLAW_URL"
echo "中转服务: $RELAY_URL"
exec python3 client.py --openclaw-url "$OPENCLAW_URL" --relay-url "$RELAY_URL" --instance-type "$INSTANCE_TYPE" "\$@"
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

# 可选：安装系统服务
if [ "$1" = "--install-service" ]; then
    echo ""
    print_step "服务" "安装系统服务..."
    if [ -f "$PLUGIN_DIR/scripts/install-service.sh" ]; then
        bash "$PLUGIN_DIR/scripts/install-service.sh"
    else
        print_error "服务安装脚本不存在"
    fi
fi

main "$@"