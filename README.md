# OpenClaw 微信频道插件

> 让你通过微信与自己本地部署的 OpenClaw 无缝对话。

[![Version](https://img.shields.io/badge/version-1.2.0-blue.svg)](https://wechat.clawadmin.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**官网**: [wechat.clawadmin.org](https://wechat.clawadmin.org)

---

## 安装方法

### 对话安装（推荐）

打开 OpenClaw 对话框 http://127.0.0.1:18789
复制以下内容粘贴发送：

```
请帮我安装微信频道插件。

安装要求：
- Python 3.8 或更高版本（请先确认已安装）

安装步骤：
1. 检测当前操作系统（macOS/Linux/Windows）
2. 执行安装命令（按顺序尝试，成功即停止）：

   macOS/Linux:
   # 方式一（Gitee，国内推荐）
   curl -fsSL https://gitee.com/yuanchenglu/openclaw-wechat-plugin/raw/main/release/install.sh | sh
   # 方式二（Cloudflare CDN，全球加速）
   curl -fsSL https://wechat.clawadmin.org/release/install.sh | sh
   # 方式三（GitHub 备用）
   curl -fsSL https://raw.githubusercontent.com/yuanchenglu/openclaw-wechat-plugin/main/release/install.sh | sh
   # 方式四（国内备用）
   curl -fsSL https://claw-wechat.7color.vip/release/install.sh | sh
    
   Windows PowerShell:
   # 方式一（Gitee，国内推荐）
   irm https://gitee.com/yuanchenglu/openclaw-wechat-plugin/raw/main/release/install.ps1 | iex
   # 方式二（Cloudflare CDN，全球加速）
   irm https://wechat.clawadmin.org/release/install.ps1 | iex
   # 方式三（GitHub 备用）
   irm https://raw.githubusercontent.com/yuanchenglu/openclaw-wechat-plugin/main/release/install.ps1 | iex
   # 方式四（国内备用）
   irm https://claw-wechat.7color.vip/release/install.ps1 | iex

3. 安装完成后，启动客户端：
   macOS/Linux: ~/.openclaw/wechat-channel/start.sh
   Windows: ~/.openclaw/wechat-channel/start.ps1

4. 启动后会显示授权链接。请将授权链接发送给用户，提示用户：
   "请点击此链接并用微信扫码，关注「七彩科技AI」服务号即可完成绑定。"

如果遇到问题，请自行解决，除非必须要用户操作，用户只要结果。
```

等待 OpenClaw 执行安装，然后按提示扫码授权即可。

> ⚠️ **重要提示**：OpenClaw 执行安装命令时会弹出授权确认框，请点击「允许」。这是安全机制，需要用户授权才能执行安装。建议在电脑前操作，方便及时确认。

---

### 命令行安装

如果熟悉终端，可直接运行：

**macOS / Linux：**
```bash
# 推荐（Gitee，国内用户首选）
curl -fsSL https://gitee.com/yuanchenglu/openclaw-wechat-plugin/raw/main/release/install.sh | sh

# 备用（Cloudflare CDN，全球加速）
curl -fsSL https://wechat.clawadmin.org/release/install.sh | sh

# 备用（GitHub）
curl -fsSL https://raw.githubusercontent.com/yuanchenglu/openclaw-wechat-plugin/main/release/install.sh | sh

# 备用（国内）
curl -fsSL https://claw-wechat.7color.vip/release/install.sh | sh
```

**Windows PowerShell：**
```powershell
# 推荐（Gitee，国内用户首选）
irm https://gitee.com/yuanchenglu/openclaw-wechat-plugin/raw/main/release/install.ps1 | iex

# 备用（Cloudflare CDN，全球加速）
irm https://wechat.clawadmin.org/release/install.ps1 | iex

# 备用（GitHub）
irm https://raw.githubusercontent.com/yuanchenglu/openclaw-wechat-plugin/main/release/install.ps1 | iex

# 备用（国内）
irm https://claw-wechat.7color.vip/release/install.ps1 | iex
```

---

## 启动与授权

安装完成后，运行：

```bash
~/.openclaw/wechat-channel/start.sh
```

首次运行会显示授权链接，用微信扫码关注「七彩科技AI」服务号即可完成绑定。

---

## 常用命令

```bash
# 启动客户端
~/.openclaw/wechat-channel/start.sh

# 停止客户端
~/.openclaw/wechat-channel/stop.sh

# 卸载
~/.openclaw/wechat-channel/uninstall.sh
```

---

## 常见问题

### OpenClaw 的默认地址是什么？

OpenClaw 默认运行在 `http://127.0.0.1:18789/`

### 如何指定 OpenClaw 地址？

如果你的 OpenClaw 运行在其他地址：

```bash
OPENCLAW_URL=http://localhost:你的端口 ~/.openclaw/wechat-channel/start.sh
```

### 如何指定中转服务地址？

```bash
RELAY_URL=wss://你的服务器/ws-channel ~/.openclaw/wechat-channel/start.sh
```

### 配置选项有哪些？

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `OPENCLAW_URL` | `http://127.0.0.1:18789` | OpenClaw 服务地址 |
| `RELAY_URL` | `wss://claw.7color.vip/ws-channel` | 中转服务地址 |
| `INSTANCE_TYPE` | `bare` | 实例类型 |

### 对话安装时弹出授权确认怎么办？

OpenClaw 执行安装命令时会弹出授权确认框，请点击「允许」。这是安全机制，需要用户授权才能执行安装。建议在电脑前操作，方便及时确认。

---

## 隐私安全

- OpenClaw 运行在你的本地电脑上
- 所有对话数据都在本地处理和存储
- 中转服务仅负责消息转发，不存储内容

---

## 支持

- **官网**: [wechat.clawadmin.org](https://wechat.clawadmin.org)
- **GitHub**: https://github.com/yuanchenglu/openclaw-wechat-plugin
- **邮箱**: services@7color.vip

---

## 许可证

MIT License

Copyright (c) 2026 七彩科技
