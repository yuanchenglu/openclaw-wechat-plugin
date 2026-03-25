# OpenClaw 微信频道插件 - 项目规则

> 版本: v1.4.0
> 更新时间: 2026-03-24

---

## 🔴 规则一：生命线验证（最高优先级）

> **定义**：生命线是指从用户安装插件到正常使用微信与 AI 对话的完整链路。任何代码 push 前后都必须验证此链路通畅。

### 1.1 生命线定义

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              生 命 线 流 程                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [1] 安装阶段                                                               │
│      ├─ Python 环境检查 (3.8+)                                              │
│      ├─ pip 检查                                                            │
│      ├─ 客户端代码下载 (Gitee/GitHub/CDN)                                   │
│      └─ 依赖安装 (websockets, httpx)                                        │
│                              ↓                                              │
│  [2] 运行阶段                                                               │
│      ├─ 本地 OpenClaw 服务 (http://127.0.0.1:18789)                        │
│      ├─ 客户端启动 (~/.openclaw/wechat-channel/start.sh)                   │
│      └─ WebSocket 连接 (wss://claw.7color.vip/ws-channel)                  │
│                              ↓                                              │
│  [3] 授权阶段                                                               │
│      ├─ 服务端返回授权链接                                                  │
│      ├─ 用户微信扫码                                                        │
│      └─ 绑定成功                                                            │
│                              ↓                                              │
│  [4] 使用阶段                                                               │
│      ├─ 微信发送消息                                                        │
│      ├─ 中转服务转发                                                        │
│      ├─ 本地 AI 处理                                                        │
│      └─ 微信收到回复                                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 验证检查点

| 检查点 | 验证命令 | 期望结果 |
|--------|----------|----------|
| Python 环境 | `python3 --version` | 3.8+ |
| 安装脚本可访问 | `curl -sI https://gitee.com/.../install.sh` | HTTP 200 |
| 客户端代码可下载 | `curl -sI https://gitee.com/.../src/client.py` | HTTP 200 |
| 本地 OpenClaw | `curl -s http://127.0.0.1:18789/` | 返回 HTML |
| 中转服务健康 | `curl -s https://claw.7color.vip/api/health` | redis: healthy |
| WebSocket 端点 | WebSocket 连接测试 | 可建立连接 |

### 1.3 验证脚本说明

> **核心原则**：验证脚本从 `README.md` 提取最新安装提示词，模拟用户实际操作流程。
> 这样确保验证流程与用户实际操作一致，当 README 更新时验证脚本自动适配。

**验证脚本功能：**
- 从 README 提取所有安装脚本 URL 并验证可访问性
- 从 README 提取中转服务地址并验证健康状态
- 测试 WebSocket 连接和客户端注册流程
- 运行单元测试

**执行验证：**
```bash
# 手动执行
./scripts/verify-lifeline.sh

# 通过 pre-commit hook 自动执行（推荐）
# 配置见 .git/hooks/pre-commit
```

### 1.4 Push 前验证流程

**强制要求：** 每次 `git push` 前必须执行验证脚本。

### 1.5 Push 后验证流程

**强制要求：** 每次 `git push` 后必须验证：

1. **GitHub Actions 检查**：确认 CI 通过
2. **Gitee 同步检查**：确认代码已同步到 Gitee
3. **安装测试**：在干净环境执行安装命令测试
4. **功能测试**：启动客户端，验证扫码授权流程

---

## 🔴 规则二：服务端部署架构

> **约束**：wechat-channel 服务端**只能**部署在 ECS (claw.7color.vip)，禁止在本地设备部署服务端。

### 2.1 服务端组件

| 组件 | 端口 | 状态检查命令 |
|------|------|-------------|
| Redis | 6379 | `docker ps \| grep redis` |
| WebSocket 服务 | 8765 | `curl -s https://claw.7color.vip/api/health` |
| Nginx | 80/443 | `curl -sI https://claw.7color.vip/` |

### 2.2 服务端健康检查

```bash
# 检查 Redis 状态
curl -s https://claw.7color.vip/api/health | jq '.health_status.redis'

# 期望输出: "healthy"
```

### 2.3 服务端故障恢复

如果 Redis 显示 unhealthy：

```bash
# SSH 到 ECS（使用私钥）
ssh -i ~/.ssh/ecs_claw.pem root@121.40.150.39

# 或者直接使用域名
ssh -i ~/.ssh/ecs_claw.pem root@claw.7color.vip

# 检查 Redis 容器
docker ps | grep redis

# 重启 Redis
docker restart <redis-container-name>

# 检查 Redis 连接
docker exec -it <redis-container-name> redis-cli ping

# 重启 WebSocket 服务
docker restart <websocket-container-name>
```

### 2.4 ECS SSH 登录信息

| 项目 | 值 |
|------|-----|
| IP 地址 | `121.40.150.39` |
| 域名 | `claw.7color.vip` |
| 用户名 | `root` |
| 认证方式 | RSA 私钥 |
| 私钥存储 | `~/.ssh/ecs_claw.pem` |

**SSH 连接命令：**
```bash
ssh -i ~/.ssh/ecs_claw.pem root@121.40.150.39
```

---

## 🔴 规则三：客户端安装路径

### 3.1 标准安装路径

| 环境 | 安装路径 |
|------|----------|
| 本地裸机 (Linux/macOS) | `~/.openclaw/wechat-channel/` |
| 本地裸机 (Windows) | `%USERPROFILE%\.openclaw\wechat-channel\` |
| Docker 容器 | `/opt/openclaw/plugins/wechat-channel/` |

### 3.2 安装后文件结构

```
~/.openclaw/wechat-channel/
├── client.py          # 主客户端
├── watchdog.py        # 看门狗
├── updater.py         # 自动更新
├── wechat_types.py    # 类型定义
├── update_state.py    # 更新状态
├── requirements.txt   # 依赖
├── venv/              # 虚拟环境
├── start.sh           # 启动脚本
├── stop.sh            # 停止脚本
├── uninstall.sh       # 卸载脚本
├── config.json        # 设备配置
└── logs/              # 日志目录
```

---

## 🔴 规则四：下载源优先级

| 优先级 | 源 | URL 前缀 | 适用场景 |
|--------|-----|----------|---------|
| 1 | Gitee | `https://gitee.com/yuanchenglu/openclaw-wechat-plugin/raw/main` | 国内首选 |
| 2 | Cloudflare CDN | `https://wechat.clawadmin.org` | 全球加速 |
| 3 | GitHub | `https://raw.githubusercontent.com/yuanchenglu/openclaw-wechat-plugin/main` | 备用 |
| 4 | 国内备用 | `https://claw-wechat.7color.vip` | 最后备选 |

---

## 🔴 规则五：版本兼容性

### 5.1 版本号格式

遵循语义化版本：`MAJOR.MINOR.PATCH`

- **MAJOR**: 不兼容的 API 变更
- **MINOR**: 向后兼容的功能新增
- **PATCH**: 向后兼容的问题修复

### 5.2 客户端-服务端版本检查

客户端在注册时会发送 `min_server_version`，服务端必须满足最低版本要求。

---

## 六、故障排查清单

### 客户端无法连接中转服务

1. 检查网络连接：`ping claw.7color.vip`
2. 检查中转服务健康：`curl -s https://claw.7color.vip/api/health`
3. 检查 Redis 状态：查看 health 响应中的 `redis` 字段
4. 检查 WebSocket 端点：使用 Python 测试 WebSocket 连接

### 扫码授权失败

1. 确认客户端已成功连接中转服务
2. 检查服务端日志
3. 确认微信服务号配置正确

### 消息收发异常

1. 检查本地 OpenClaw 服务是否运行
2. 检查客户端日志：`~/.openclaw/wechat-channel/logs/`
3. 检查 OpenClaw API 是否可访问

---

## 七、联系方式

| 项目 | 值 |
|------|-----|
| 用户 | 小路 |
| 手机号 | 15527321668 |
| 邮箱 | ycl_pj@163.com |
| 客服微信 | ycl1552732 |

---

## 🔴 规则六：端到端测试协作

> **定义**：端到端测试是指从微信发送消息到收到 AI 回复的完整用户流程验证。此测试需要用户配合完成。

### 6.1 用户测试信息

| 项目 | 值 |
|------|-----|
| 用户 | 小路 |
| 微信 OpenID | `oFb8866iAh903OZht3CukuNwEcXc` |
| 用途 | 消息收发测试、设备绑定验证 |

### 6.2 完整生命线测试流程

> **测试环境**：使用本机 OpenClaw 进行测试，模拟真实用户安装流程

```
┌─────────────────────────────────────────────────────────────┐
│  完整生命线测试流程（Push 前后各执行一次）                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [AI] 1. 卸载本地 wechat-channel 插件                       │
│            ~/.openclaw/wechat-channel/uninstall.sh          │
│                              ↓                               │
│  [AI] 2. 执行重装流程（模拟用户安装）                        │
│            使用 README 中的最新安装命令                      │
│                              ↓                               │
│  [AI] 3. 启动客户端，生成授权链接                            │
│            ~/.openclaw/wechat-channel/start.sh              │
│                              ↓                               │
│  [AI] 4. 把授权链接发给用户                                  │n│            「请用微信扫码授权」                              │
│                              ↓                               │
│  [用户] 5. 微信扫码，关注服务号                              │
│                              ↓                               │
│  [AI] 6. 确认授权成功，告诉用户：                            │
│            「准备好了，请发消息测试」                        │
│                              ↓                               │
│  [用户] 7. 在微信服务号发送消息（如「你好」）                │
│                              ↓                               │
│  [AI] 8. 验证消息收发                                        │
│            - 中转服务是否收到消息                            │
│            - 本地 OpenClaw 是否处理                          │
│            - 微信是否收到回复                                │
│                              ↓                               │
│  [AI] 9. 告诉用户结果                                        │
│            「测试通过 ✅」或「有问题 ❌」                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 测试命令速查

```bash
# 卸载插件
~/.openclaw/wechat-channel/uninstall.sh

# 安装插件（从 README 获取最新命令）
# macOS/Linux:
curl -fsSL https://gitee.com/yuanchenglu/openclaw-wechat-plugin/raw/main/release/install.sh | bash

# 启动客户端
~/.openclaw/wechat-channel/start.sh

# 查看客户端日志（获取授权链接）
tail -f ~/.openclaw/wechat-channel/logs/client.log

# 检查客户端是否运行
ps aux | grep client.py

# 停止客户端
~/.openclaw/wechat-channel/stop.sh
```

### 6.4 测试前提条件

| 条件 | 验证方式 |
|------|----------|
| 中转服务正常 | `curl -s https://claw.7color.vip/api/health` |
| 本地 OpenClaw 运行 | `curl -s http://127.0.0.1:18789/` |
| 客户端运行 | `ps aux \| grep client.py` |
| 微信已绑定服务号 | 用户确认 |

### 6.5 测试场景

| 场景 | 操作 | 验证点 |
|------|------|--------|
| 完整安装流程 | 卸载 → 重装 → 扫码 → 发消息 | 全链路通畅 |
| 消息收发 | 用户发消息，AI 回复 | 消息往返正常 |
| 解绑重绑 | 用户取消关注，重新关注 | 授权流程正常 |
| 多轮对话 | 连续发送多条消息 | 上下文保持 |

---

## 🔴 规则七：测试规范

> **定义**：测试分层和触发时机，确保代码质量。

### 7.1 测试分层

| 层级 | 测试类型 | 触发时机 | 工具 |
|------|----------|----------|------|
| L1 | 单元测试 | 每次提交 | pytest |
| L2 | 集成测试 | 每次 PR | pytest-asyncio |
| L3 | E2E 测试 | 发布前 | 自定义脚本 |
| L4 | 生产验证 | 发布后 | 真实用户测试 |

### 7.2 测试命令

```bash
# 单元测试
pytest tests/ -v

# 覆盖率报告
pytest tests/ -v --cov=src --cov-report=term-missing

# E2E 测试
python scripts/e2e_test.py --openid oFb8866iAh903OZht3CukuNwEcXc

# 压力测试
locust -f scripts/locustfile.py --headless -u 100 -r 10 -t 1m
```

### 7.3 测试账号

| 项目 | 值 |
|------|-----|
| 测试用户 | 小路 |
| 微信 OpenID | `oFb8866iAh903OZht3CukuNwEcXc` |
| 用途 | 消息收发测试、设备绑定验证 |

---

## 九、变更历史

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-03-18 | v1.0.0 | 初始版本，定义生命线验证规则 |
| 2026-03-18 | v1.1.0 | 添加 ECS SSH 登录信息，更新验证脚本从 README 提取命令 |
| 2026-03-18 | v1.2.0 | 添加端到端测试协作流程和用户 OpenID |
| 2026-03-18 | v1.3.0 | 完善生命线测试流程，包含卸载重装完整步骤 |
| 2026-03-24 | v1.4.0 | 添加测试规则章节 |
|------|------|---------|
| 2026-03-18 | v1.0.0 | 初始版本，定义生命线验证规则 |
| 2026-03-18 | v1.1.0 | 添加 ECS SSH 登录信息，更新验证脚本从 README 提取命令 |
| 2026-03-18 | v1.2.0 | 添加端到端测试协作流程和用户 OpenID |
