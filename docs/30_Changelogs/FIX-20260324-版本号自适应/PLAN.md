# 实施计划：版本号自适应修复

> CID: FIX-20260324-版本号自适应
> 日期：2026-03-24
> 状态：已完成

---

## 一、业务背景

### 1.1 问题描述

用户在安装插件后发现以下问题：

1. **版本号显示为 0.0.0**：安装脚本 `install.sh` 没有下载 `version.json` 文件
2. **自动更新下载失败**：下载 URL 格式不正确，导致所有下载源均失败
3. **版本号不自适应**：`version.json` 中写死了 `download_url`，如果只更新 `version` 字段，用户会下载到错误版本

### 1.2 影响范围

- 所有通过安装脚本安装的用户
- 触发自动更新的用户（v1.4.0+）
- Gitee/GitHub/R2/ECS 四个下载源

---

## 二、技术方案

### 2.1 核心改动

| 文件 | 改动内容 | 影响 |
|------|----------|------|
| `release/version.json` | 移除 `download_url` 字段 | 版本号源文件 |
| `src/updater.py` | 动态构建下载 URL | 更新模块 |
| `.github/workflows/release.yml` | 不再生成 `download_url` | 发布流程 |
| `tests/test_silent_upgrade_integration.py` | 更新测试断言 | 测试用例 |

### 2.2 数据流转

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           版本号自适应流程                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [发布阶段]                                                                 │
│      开发者更新 version.json (仅 version 字段)                              │
│                     ↓                                                       │
│      GitHub Release 触发 Actions                                            │
│                     ↓                                                       │
│      自动上传到 Gitee / R2 / ECS                                            │
│                     ↓                                                       │
│      version.json 分发到各源（无 download_url）                             │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [更新检查阶段]                                                             │
│      客户端启动 → Updater.check_update()                                    │
│                     ↓                                                       │
│      从下载源获取 version.json                                              │
│                     ↓                                                       │
│      提取 version 字段 → "1.5.0"                                            │
│                     ↓                                                       │
│      动态构建 download_url:                                                  │
│        Gitee:  https://gitee.com/.../archive/v1.5.0.tar.gz                 │
│        GitHub: https://github.com/.../refs/tags/v1.5.0.tar.gz              │
│        R2:     https://wechat.clawadmin.org/release/v1.5.0.tar.gz          │
│        ECS:    https://claw-wechat.7color.vip/release/v1.5.0.tar.gz        │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [下载阶段]                                                                 │
│      按优先级依次尝试下载：                                                   │
│        1. Gitee（国内首选）                                                  │
│        2. GitHub（国际备用）                                                 │
│        3. R2 CDN（全球加速）                                                 │
│        4. ECS（国内备用）                                                    │
│                     ↓                                                       │
│      任一源成功即停止，失败则尝试下一个                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 关键代码逻辑

#### updater.py 核心改动

```python
# 旧逻辑：依赖 version.json 中的 download_url
download_url = data.get("download_url")
if not download_url and source.get("tag_archive_url"):
    download_url = source["tag_archive_url"].format(version=latest_version)

# 新逻辑：始终根据 latest_version 动态构建
# 不依赖 version.json 中的 download_url（避免版本号不一致）
download_url = None
if source.get("tag_archive_url"):
    download_url = source["tag_archive_url"].format(version=latest_version)
```

---

## 三、下载源配置

### 3.1 下载源优先级

| 优先级 | 源 | URL 模板 | 适用场景 |
|--------|-----|----------|---------|
| 1 | Gitee | `https://gitee.com/yuanchenglu/openclaw-wechat-plugin/repository/archive/v{version}.tar.gz` | 国内首选 |
| 2 | GitHub | `https://github.com/yuanchenglu/openclaw-wechat-plugin/archive/refs/tags/v{version}.tar.gz` | 国际备用 |
| 3 | R2 CDN | `https://wechat.clawadmin.org/release/v{version}.tar.gz` | 全球加速 |
| 4 | ECS | `https://claw-wechat.7color.vip/release/v{version}.tar.gz` | 国内备用 |

### 3.2 发布流程配置

| 配置项 | 位置 | 状态 |
|--------|------|------|
| `GITEE_TOKEN` | GitHub Secrets | ✅ 已配置 |
| `CLOUDFLARE_API_TOKEN` | GitHub Secrets | ✅ 已配置 |
| `ECS_SSH_KEY` | GitHub Secrets | ✅ 已配置 |

---

## 四、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 下载源不可用 | 低 | 高 | 四级容错，任一成功即停止 |
| 版本号格式错误 | 低 | 中 | 版本比较函数有异常处理 |
| 缓存问题 | 中 | 低 | 添加 Cache-Control 头 |

---

## 五、验收标准

- [x] GitHub v1.4.0 tag 可下载
- [x] Gitee v1.4.0 tag 可下载
- [x] R2 v1.4.0.tar.gz 可下载
- [x] ECS v1.4.0.tar.gz 可下载
- [x] 所有源 version.json 无 download_url 字段
- [x] 单元测试全部通过（187 passed）

---

## 六、参考文档

- [静默升级设计文档](../10_Design/12_Feat_静默升级.md)
- [生命线验证规则](../../AGENTS.md)