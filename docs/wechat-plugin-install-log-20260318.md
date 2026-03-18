# 微信频道插件安装日志

> 记录时间: 2026-03-18
> 操作系统: Linux (Ubuntu 24.04)
> Python 版本: 3.12.3

---

## 一、环境检测

### 1.1 系统信息

```bash
$ uname -a
Linux bluth-ThinkPad-E450c 6.17.0-19-generic #19~24.04.2-Ubuntu SMP PREEMPT_DYNAMIC Fri Mar 6 23:08:49 UTC 2 x86_64 x86_64 x86_64 GNU/Linux

$ python3 --version
Python 3.12.3
```

**结论**: ✅ 满足 Python 3.8+ 要求

---

## 二、安装尝试

### 2.1 尝试 Gitee 源（方式一）

```bash
$ curl -fsSL https://gitee.com/yuanchenglu/openclaw-wechat-plugin/raw/main/release/install.sh | sh
sh: 87: Syntax error: "(" unexpected (expecting "}")
```

**问题分析**: 脚本使用 bash 数组语法，但 Ubuntu 默认 `sh` 是 dash，不支持这些语法。

### 2.2 尝试 Cloudflare CDN（方式二）

```bash
$ curl -fsSL https://wechat.clawadmin.org/release/install.sh | sh
sh: 87: Syntax error: "(" unexpected (expecting "}")
```

**同样问题**。

### 2.3 使用 bash 执行

```bash
$ curl -fsSL https://wechat.clawadmin.org/release/install.sh | bash

╔════════════════════════════════════════════════════════════════╗
║       OpenClaw 微信频道客户端 v1.4.0                       ║
║       让你的 AI，就在微信里                                    ║
╚════════════════════════════════════════════════════════════════╝

[1/4] 检查 Python 环境...
✅ Python3 已安装
[2/4] 检查 pip...
✅ pip 已安装
[3/4] 下载客户端...
❌ 所有下载源均失败，请检查网络连接
❌ 建议：
❌   1. 检查网络是否正常
❌   2. 尝试手动下载: https://gitee.com/yuanchenglu/openclaw-wechat-plugin
```

### 2.4 尝试 GitHub 源（方式三）

```bash
$ curl -fsSL https://raw.githubusercontent.com/yuanchenglu/openclaw-wechat-plugin/main/release/install.sh | bash
# 同样失败：所有下载源均失败
```

### 2.5 尝试国内备用源（方式四）

```bash
$ curl -fsSL https://claw-wechat.7color.vip/release/install.sh | bash
# 同样失败：所有下载源均失败
```

---

## 三、问题诊断

### 3.1 网络连通性测试

```bash
$ curl -v --connect-timeout 10 https://gitee.com/yuanchenglu/openclaw-wechat-plugin/raw/main/src/client.py 2>&1 | head -30

* Host gitee.com:443 was resolved.
* IPv4: 180.76.199.13, 180.76.198.225, 180.76.198.77
*   Trying 180.76.199.13:443...
* Connected to gitee.com (180.76.199.13) port 443
* TLSv1.3 (OUT), TLS handshake, Client hello (1)
* TLSv1.3 (IN), TLS handshake, Server hello (2)
# ... TLS 握手成功
```

**结论**: 网络连接正常

### 3.2 单独文件下载测试

```bash
$ curl -fsSL --connect-timeout 10 --max-time 30 \
  "https://gitee.com/yuanchenglu/openclaw-wechat-plugin/raw/main/src/client.py" \
  -o /tmp/test_client.py && echo "下载成功"
下载成功
-rw-r--r-- 1 bluth bluth 42462 3月 18 16:18 /tmp/test_client.py
```

**结论**: 单独下载成功，问题在脚本逻辑

### 3.3 定位脚本 Bug

```bash
# 测试根目录的 requirements.txt
$ curl -fsSL "https://gitee.com/yuanchenglu/openclaw-wechat-plugin/raw/main/requirements.txt" -o /tmp/test_req.txt
下载成功

# 测试 src 目录下的 requirements.txt
$ curl -fsSL "https://gitee.com/yuanchenglu/openclaw-wechat-plugin/raw/main/src/requirements.txt"
curl: (22) The requested URL returned error: 404
```

**发现 Bug**: 安装脚本从 `src/requirements.txt` 下载，但文件实际在根目录

---

## 四、手动安装

### 4.1 下载所有客户端文件

```bash
PLUGIN_DIR="$HOME/.openclaw/wechat-channel"
mkdir -p "$PLUGIN_DIR"

# 下载源
BASE_URL="https://gitee.com/yuanchenglu/openclaw-wechat-plugin/raw/main"

# 下载 Python 模块（在 src 目录下）
for module in client.py watchdog.py updater.py types.py update_state.py; do
    curl -fsSL "$BASE_URL/src/$module" -o "$PLUGIN_DIR/$module"
done

# 下载 requirements.txt（在根目录下）
curl -fsSL "$BASE_URL/requirements.txt" -o "$PLUGIN_DIR/requirements.txt"
```

**输出**:
```
✅ client.py
✅ watchdog.py
✅ updater.py
✅ types.py
✅ update_state.py
✅ requirements.txt
```

### 4.2 创建虚拟环境并安装依赖

```bash
PLUGIN_DIR="$HOME/.openclaw/wechat-channel"
cd "$PLUGIN_DIR"

# 创建虚拟环境
python3 -m venv "$PLUGIN_DIR/venv"

# 激活并安装依赖
source "$PLUGIN_DIR/venv/bin/activate"
pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple websockets httpx
```

**输出**:
```
✅ 虚拟环境已创建
✅ 依赖已安装
```

### 4.3 创建启动/停止/卸载脚本

```bash
PLUGIN_DIR="$HOME/.openclaw/wechat-channel"
OPENCLAW_URL="http://127.0.0.1:18789"
RELAY_URL="wss://claw.7color.vip/ws-channel"
VERSION="1.4.0"

# 创建 start.sh
cat > "$PLUGIN_DIR/start.sh" << 'LAUNCHER_EOF'
#!/bin/bash
PLUGIN_DIR="$HOME/.openclaw/wechat-channel"
cd "$PLUGIN_DIR"
OPENCLAW_URL="${OPENCLAW_URL:-http://127.0.0.1:18789}"
RELAY_URL="${RELAY_URL:-wss://claw.7color.vip/ws-channel}"
INSTANCE_TYPE="${INSTANCE_TYPE:-local}"

if [ -d "$PLUGIN_DIR/venv" ]; then
    source "$PLUGIN_DIR/venv/bin/activate"
fi

echo "OpenClaw 微信频道客户端 v1.4.0"
echo "OpenClaw: $OPENCLAW_URL"
echo "中转服务: $RELAY_URL"
exec python3 "$PLUGIN_DIR/client.py" --openclaw-url "$OPENCLAW_URL" --relay-url "$RELAY_URL" --instance-type "$INSTANCE_TYPE" "$@"
LAUNCHER_EOF
chmod +x "$PLUGIN_DIR/start.sh"

# 创建 stop.sh
cat > "$PLUGIN_DIR/stop.sh" << 'STOP_EOF'
#!/bin/bash
pkill -f "python.*client.py.*wechat" 2>/dev/null || true
echo "客户端已停止"
STOP_EOF
chmod +x "$PLUGIN_DIR/stop.sh"

# 创建 uninstall.sh
cat > "$PLUGIN_DIR/uninstall.sh" << 'UNINSTALL_EOF'
#!/bin/bash
rm -rf "$HOME/.openclaw/wechat-channel"
echo "已卸载"
UNINSTALL_EOF
chmod +x "$PLUGIN_DIR/uninstall.sh"
```

---

## 五、启动测试与问题修复

### 5.1 首次启动

```bash
$ ~/.openclaw/wechat-channel/start.sh

OpenClaw 微信频道客户端 v1.4.0
OpenClaw: http://127.0.0.1:18789
中转服务: wss://claw.7color.vip/ws-channel
python3: can't open file '/home/bluth/Code/openclaw-wechat-plugin/client.py': [Errno 2] No such file or directory
```

**问题**: 启动脚本路径引用错误

### 5.2 修复启动脚本

修改 `start.sh` 使用绝对路径

### 5.3 第二次启动

```bash
$ ~/.openclaw/wechat-channel/start.sh

OpenClaw 微信频道客户端 v1.4.0
OpenClaw: http://127.0.0.1:18789
中转服务: wss://claw.7color.vip/ws-channel
Traceback (most recent call last):
  File "/home/bluth/.openclaw/wechat-channel/client.py", line 35, in <module>
    import asyncio
  ...
  File "/home/bluth/.openclaw/wechat-channel/types.py", line 8, in <module>
    from enum import Enum
ImportError: cannot import name 'Enum' from partially initialized module 'enum' 
(most likely due to a circular import) (/usr/lib/python3.12/enum.py)
```

**问题**: `types.py` 与 Python 标准库模块名冲突

### 5.4 修复模块名冲突

```bash
PLUGIN_DIR="$HOME/.openclaw/wechat-channel"
cd "$PLUGIN_DIR"

# 重命名文件
mv types.py wechat_types.py

# 修改 client.py 中的引用
sed -i 's/"types.py"/"wechat_types.py"/g' client.py
```

### 5.5 第三次启动（成功）

```bash
$ ~/.openclaw/wechat-channel/start.sh

OpenClaw 微信频道客户端 v1.4.0
OpenClaw: http://127.0.0.1:18789
中转服务: wss://claw.7color.vip/ws-channel
2026-03-18 16:22:05 [INFO] 日志文件: /home/bluth/.openclaw/wechat-channel/logs/client_20260318.log
2026-03-18 16:22:05 [INFO] ============================================================
2026-03-18 16:22:05 [INFO] OpenClaw 微信频道客户端
2026-03-18 16:22:05 [INFO] 版本: 0.0.0
2026-03-18 16:22:05 [INFO] 实例类型: local
2026-03-18 16:22:05 [INFO] OpenClaw URL: http://127.0.0.1:18789
2026-03-18 16:22:05 [INFO] Relay URL: wss://claw.7color.vip/ws-channel
2026-03-18 16:22:05 [INFO] ============================================================
2026-03-18 16:22:06 [INFO] 
🔔 发现新版本: 1.4.0
2026-03-18 16:22:06 [INFO]    当前版本: 0.0.0
2026-03-18 16:22:06 [INFO]    下载地址: https://github.com/yuanchenglu/...

2026-03-18 16:22:06 [INFO] 🆕 新设备: bare_82fe9c38f255a124_bluth_20260318162206_63c8
2026-03-18 16:22:06 [INFO] Config saved to /home/bluth/.openclaw/wechat-channel/config.json
2026-03-18 16:22:06 [INFO] Connecting to wss://claw.7color.vip/ws-channel...
2026-03-18 16:22:06 [ERROR] Connection failed: server rejected WebSocket connection: HTTP 502
```

---

## 六、服务端问题诊断

### 6.1 健康检查

```bash
$ curl -s "https://claw.7color.vip/health"
{"status":"healthy","timestamp":"2026-03-18T08:22:54.888384","version":"1.0.0","redis_connected":true}
```

### 6.2 WebSocket 连接测试

```bash
$ source ~/.openclaw/wechat-channel/venv/bin/activate && python3 -c "
import asyncio
import websockets

async def test():
    try:
        async with websockets.connect('wss://claw.7color.vip/ws-channel', close_timeout=5) as ws:
            print('连接成功!')
    except Exception as e:
        print(f'错误: {type(e).__name__}: {e}')

asyncio.run(test())
"

错误: InvalidStatus: server rejected WebSocket connection: HTTP 502
```

**结论**: 中转服务的 WebSocket 端点返回 HTTP 502，需要检查服务端状态

---

## 七、发现的问题总结

### 问题 1: 安装脚本 sh/bash 兼容性

- **现象**: `sh: 87: Syntax error: "(" unexpected`
- **原因**: 脚本使用 bash 数组语法，但 `sh` 在 Ubuntu 上是 dash
- **建议**: 安装命令应使用 `bash` 而非 `sh`

### 问题 2: 安装脚本下载路径错误

- **现象**: 所有下载源失败
- **原因**: 脚本从 `src/requirements.txt` 下载，但文件在根目录
- **位置**: `install.sh` 第 87 行左右
- **建议**: 修正下载路径或移动文件位置

### 问题 3: types.py 模块名冲突

- **现象**: `ImportError: cannot import name 'Enum' from partially initialized module 'enum'`
- **原因**: `types.py` 与 Python 标准库模块名冲突
- **建议**: 重命名为 `wechat_types.py` 或其他不冲突的名称

### 问题 4: 服务端 WebSocket 502

- **现象**: `HTTP 502 Bad Gateway`
- **原因**: 中转服务 WebSocket 端点不可用
- **建议**: 检查 ECS 上 wechat-channel 服务端状态

---

## 八、最终安装结果

| 项目 | 状态 |
|------|------|
| 安装目录 | `~/.openclaw/wechat-channel/` |
| Python 模块 | ✅ 已下载 |
| 虚拟环境 | ✅ 已创建 |
| 依赖 | ✅ 已安装 |
| 启动脚本 | ✅ 已创建 |
| 客户端启动 | ✅ 成功 |
| WebSocket 连接 | ❌ HTTP 502 |

---

## 九、待修复项

1. **安装脚本**: 修复 sh/bash 兼容性和下载路径问题
2. **types.py**: 重命名避免与标准库冲突
3. **服务端**: 检查 ECS 上 WebSocket 服务状态

---

## 十、WebSocket 502 问题深度分析

### 10.1 客户端连接流程

基于代码分析，客户端 WebSocket 连接流程如下：

```
1. 连接 URL: wss://claw.7color.vip/ws-channel
2. websockets.connect(relay_url, ping_interval=30, ping_timeout=10)
3. 发送注册消息:
   {
     "type": "register",
     "instance_type": "local",
     "device_id": "bare_xxx_username_timestamp_random",
     "device_type": "bare",
     "machine_id": "硬件指纹",
     "system_username": "用户名",
     "client_version": "版本号",
     "min_server_version": "最低服务端版本",
     "is_new_device": true/false
   }
4. 等待响应（超时 10 秒）:
   成功: {"type": "registered", "server_version": "...", "auth_url": "..."}
   失败: {"type": "error", "message": "..."}
```

**关键发现**: HTTP 502 发生在 WebSocket 握手阶段，此时还未发送注册消息，说明问题在**服务端**。

### 10.2 HTTP 502 常见原因

| 原因 | Nginx 错误日志特征 | 可能性 |
|------|-------------------|--------|
| 后端服务未运行 | `connect() failed (111: Connection refused)` | ⭐⭐⭐ 高 |
| 后端服务崩溃 | `recv() failed (104: Connection reset by peer)` | ⭐⭐ 中 |
| Nginx 配置错误 | 缺少 WebSocket 升级头 | ⭐⭐ 中 |
| 后端网络不可达 | `connect() failed (113: No route to host)` | ⭐ 低 |
| SELinux 阻止 | `connect() failed (13: Permission denied)` | ⭐ 低 |

### 10.3 服务端排查命令

在 ECS (claw.7color.vip) 上执行：

```bash
# 1. 检查服务是否运行
sudo systemctl status wechat-channel
ps aux | grep wechat-channel

# 2. 检查端口监听
sudo ss -tlnp | grep 8765
sudo netstat -tlnp | grep 8765

# 3. 检查 Nginx 配置
cat /etc/nginx/conf.d/*.conf | grep -A 20 "ws-channel"

# 4. 查看 Nginx 错误日志
sudo tail -50 /var/log/nginx/error.log

# 5. 测试本地直连（绕过 Nginx）
wscat -c ws://127.0.0.1:8765
```

### 10.4 预期的 Nginx WebSocket 代理配置

```nginx
# 在 http 块中定义 map
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl;
    server_name claw.7color.vip;

    location /ws-channel {
        proxy_pass http://127.0.0.1:8765;
        
        # 必须设置 HTTP/1.1
        proxy_http_version 1.1;
        
        # WebSocket 握手必需的头
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        
        # 传递客户端信息
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        # 超时设置（WebSocket 长连接）
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

---

## 十一、结论与下一步

### 安装状态
| 项目 | 状态 |
|------|------|
| 客户端安装 | ✅ 完成 |
| 客户端启动 | ✅ 成功 |
| WebSocket 连接 | ❌ 服务端 502 |

### 待处理
1. **服务端**: 在 ECS 上检查 wechat-channel 服务端状态和 Nginx 配置
2. **安装脚本 Bug**: 修复 sh/bash 兼容性和下载路径问题
3. **types.py 冲突**: 重命名为 `wechat_types.py`

### 下一步行动
需要登录 ECS (claw.7color.vip) 检查：
1. wechat-channel 服务端是否运行
2. Nginx WebSocket 代理配置是否正确
3. Nginx 错误日志中的具体错误信息
