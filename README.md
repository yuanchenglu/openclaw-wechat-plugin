# OpenClaw 微信频道插件

> 让你通过微信与自己本地部署的 OpenClaw 无缝对话。

[![Version](https://img.shields.io/badge/version-1.2.0-blue.svg)](http://claw-wechat.clawadmin.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**官网**: http://claw-wechat.clawadmin.org

---

## 功能特点

- **本地运行** - OpenClaw 运行在你自己的电脑上，数据完全本地存储
- **微信对话** - 通过微信服务号与自己的 OpenClaw 对话
- **NAT 穿透** - WebSocket 长连接自动穿透内网
- **一键安装** - 运行一条命令即可完成安装

---

## 快速开始

### 系统要求

- Python 3.8 或更高版本
- OpenClaw 已部署并运行

### 安装

```bash
curl -fsSL http://claw-wechat.clawadmin.org/install.sh | sh
```

### 启动

```bash
# 默认配置
~/.openclaw/wechat-channel/start.sh

# 指定 OpenClaw 地址
OPENCLAW_URL=http://localhost:3000 ~/.openclaw/wechat-channel/start.sh

# 指定中转服务地址
RELAY_URL=wss://your-server.com/ws-channel ~/.openclaw/wechat-channel/start.sh
```

### 授权

首次运行会显示二维码：

1. 使用微信扫描二维码
2. 关注服务号完成授权
3. 授权成功后即可在微信中对话

---

## 配置选项

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `OPENCLAW_URL` | `http://localhost:8080` | OpenClaw 服务地址 |
| `RELAY_URL` | `wss://claw.7color.vip/ws-channel` | 中转服务地址 |
| `INSTANCE_TYPE` | `bare` | 实例类型 |

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

## 隐私安全

- OpenClaw 运行在你的本地电脑上
- 所有对话数据都在本地处理和存储
- 中转服务仅负责消息转发，不存储内容

---

## 自建服务

如果你想自建中转服务：

1. 你需要一台公网服务器
2. 部署 WebSocket 中转服务
3. 配置微信服务号回调
4. 修改 `RELAY_URL` 指向你的服务器

服务器端代码暂不开源，如需商业合作请联系：services@7color.vip

---

## 项目结构

```
openclaw-wechat-plugin/
├── plugin/
│   ├── src/client.py      # 客户端主程序
│   └── requirements.txt   # Python 依赖
├── release/
│   ├── install.sh         # 安装脚本
│   └── version.json       # 版本信息
├── landing-page/
│   └── index.html         # 官网落地页
└── README.md
```

---

## 支持

- **官网**: http://claw-wechat.clawadmin.org
- **GitHub**: https://github.com/yuanchenglu/openclaw-wechat-plugin
- **问题反馈**: https://github.com/yuanchenglu/openclaw-wechat-plugin/issues
- **邮箱**: services@7color.vip

---

## 许可证

MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.