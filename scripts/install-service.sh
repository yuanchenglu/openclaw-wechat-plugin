#!/bin/bash
# ============================================================================
# OpenClaw WeChat Channel - 服务安装脚本
# ============================================================================
#
# 用法：
#   ./install-service.sh        # 安装服务
#   ./install-service.sh --uninstall  # 卸载服务
#
# ============================================================================

set -e

PLUGIN_DIR="$HOME/.openclaw/wechat-channel"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ -f /etc/os-release ]] || [[ -f /usr/lib/os-release ]]; then
        echo "linux"
    else
        echo "unknown"
    fi
}

install_systemd_service() {
    local service_dir="$HOME/.config/systemd/user"
    local service_file="$service_dir/openclaw-wechat.service"
    
    print_info "安装 systemd 用户服务..."
    
    mkdir -p "$service_dir"
    
    # 创建服务文件，替换 %h 为实际路径
    sed "s|%h|$HOME|g" "$SCRIPT_DIR/openclaw-wechat.service" > "$service_file"
    
    systemctl --user daemon-reload
    systemctl --user enable openclaw-wechat
    systemctl --user start openclaw-wechat
    
    print_success "systemd 服务已安装并启动"
    echo ""
    echo "管理命令："
    echo "  查看状态: systemctl --user status openclaw-wechat"
    echo "  查看日志: journalctl --user -u openclaw-wechat -f"
    echo "  停止服务: systemctl --user stop openclaw-wechat"
    echo "  重启服务: systemctl --user restart openclaw-wechat"
}

install_launchd_service() {
    local plist_dir="$HOME/Library/LaunchAgents"
    local plist_file="$plist_dir/com.openclaw.wechat.plist"
    
    print_info "安装 launchd 服务..."
    
    mkdir -p "$plist_dir"
    
    # 创建 plist 文件，替换 {{HOME}} 为实际路径
    sed "s|{{HOME}}|$HOME|g" "$SCRIPT_DIR/com.openclaw.wechat.plist" > "$plist_file"
    
    launchctl load "$plist_file"
    
    print_success "launchd 服务已安装并启动"
    echo ""
    echo "管理命令："
    echo "  查看状态: launchctl list | grep openclaw"
    echo "  查看日志: tail -f $PLUGIN_DIR/openclaw-wechat.log"
    echo "  停止服务: launchctl unload $plist_file"
    echo "  重启服务: launchctl unload $plist_file && launchctl load $plist_file"
}

uninstall_systemd_service() {
    print_info "卸载 systemd 服务..."
    
    systemctl --user stop openclaw-wechat 2>/dev/null || true
    systemctl --user disable openclaw-wechat 2>/dev/null || true
    rm -f "$HOME/.config/systemd/user/openclaw-wechat.service"
    systemctl --user daemon-reload
    
    print_success "systemd 服务已卸载"
}

uninstall_launchd_service() {
    local plist_file="$HOME/Library/LaunchAgents/com.openclaw.wechat.plist"
    
    print_info "卸载 launchd 服务..."
    
    launchctl unload "$plist_file" 2>/dev/null || true
    rm -f "$plist_file"
    
    print_success "launchd 服务已卸载"
}

main() {
    local os=$(detect_os)
    
    if [[ "$1" == "--uninstall" ]] || [[ "$1" == "-u" ]]; then
        case "$os" in
            linux)
                uninstall_systemd_service
                ;;
            macos)
                uninstall_launchd_service
                ;;
            *)
                print_error "不支持的操作系统: $os"
                exit 1
                ;;
        esac
        exit 0
    fi
    
    # 检查安装目录是否存在
    if [[ ! -d "$PLUGIN_DIR" ]]; then
        print_error "插件未安装，请先运行安装脚本"
        echo "安装命令: curl -fsSL https://wechat.clawadmin.org/release/install.sh | sh"
        exit 1
    fi
    
    # 检查启动脚本是否存在
    if [[ ! -f "$PLUGIN_DIR/start.sh" ]]; then
        print_error "启动脚本不存在: $PLUGIN_DIR/start.sh"
        exit 1
    fi
    
    case "$os" in
        linux)
            install_systemd_service
            ;;
        macos)
            install_launchd_service
            ;;
        *)
            print_error "不支持的操作系统: $os"
            echo "支持的系统: Linux (systemd), macOS (launchd)"
            exit 1
            ;;
    esac
}

main "$@"