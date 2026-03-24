# 变更记录：版本号自适应修复

> CID: FIX-20260324-版本号自适应
> 日期：2026-03-24
> 版本：v1.4.0
> 作者：OpenCode (Sisyphus)

---

## 一、变更概述

### 1.1 Context（背景）

用户反馈安装插件后出现三个问题：
1. 版本号显示为 `0.0.0`
2. 自动更新时所有下载源均失败
3. 版本号不自适应，`download_url` 写死导致版本不一致

### 1.2 Decision（决策）

- **移除 `download_url` 字段**：让 `updater.py` 完全根据 `version` 字段动态构建下载 URL
- **统一文件名格式**：所有下载源使用 `v{version}.tar.gz` 格式
- **完善发布流程**：确保 Gitee 同步和 R2/ECS 上传自动化

### 1.3 Manifest（变更清单）

| Commit | 描述 |
|--------|------|
| `fe06196` | fix: 版本号完全自适应，不再依赖 version.json 中的 download_url |
| `13dd7d3` | fix: 统一所有下载源的文件名格式为 v{version}.tar.gz |
| `92609f5` | fix: 修复版本号显示和下载源问题 |

---

## 二、详细变更

### 2.1 release/version.json

**变更前：**
```json
{
  "version": "1.4.0",
  "release_date": "2026-03-17",
  "min_server_version": "1.0.0",
  "download_url": "https://github.com/yuanchenglu/openclaw-wechat-plugin/archive/refs/tags/v1.4.0.tar.gz",
  "changelog": [...]
}
```

**变更后：**
```json
{
  "version": "1.4.0",
  "release_date": "2026-03-17",
  "min_server_version": "1.0.0",
  "changelog": [...]
}
```

**原因：** `download_url` 写死了版本号，如果只更新 `version` 字段，用户会下载到错误版本。移除后，`updater.py` 会根据 `version` 字段动态构建 URL。

---

### 2.2 src/updater.py

**变更前：**
```python
# 构建 download_url
download_url = data.get("download_url")
if not download_url and source.get("tag_archive_url"):
    # 使用 tag_archive_url 模板构建
    download_url = source["tag_archive_url"].format(version=latest_version)
```

**变更后：**
```python
# 始终根据 latest_version 动态构建 download_url
# 不依赖 version.json 中的 download_url（避免版本号不一致）
download_url = None
if source.get("tag_archive_url"):
    download_url = source["tag_archive_url"].format(version=latest_version)
```

**原因：** 确保下载 URL 始终与 `version` 字段一致，避免版本不匹配。

---

### 2.3 .github/workflows/release.yml

**变更前：**
```yaml
# 更新 download_url
UPDATED_JSON=$(echo "$VERSION_JSON" | jq --arg v "$VERSION" \
  '.download_url = "https://github.com/yuanchenglu/openclaw-wechat-plugin/archive/refs/tags/v\($v).tar.gz"')
```

**变更后：**
```yaml
# 直接使用 version.json（updater.py 会根据 version 字段动态构建下载 URL）
UPDATED_JSON="$VERSION_JSON"
```

**原因：** 不再需要生成 `download_url`，简化发布流程。

---

### 2.4 tests/test_silent_upgrade_integration.py

**变更前：**
```python
assert "openclaw-wechat-channel-v1.3.0.tar.gz" in result["download_url"]
```

**变更后：**
```python
# 验证 URL 被正确构建（文件名格式为 v{version}.tar.gz）
assert "v1.3.0.tar.gz" in result["download_url"]
```

**原因：** 文件名格式统一为 `v{version}.tar.gz`。

---

## 三、下载源验证

### 3.1 验证结果

| 源 | v1.4.0 tar.gz | version.json | 状态 |
|---|---------------|--------------|------|
| GitHub | HTTP 302 | ✅ | 正常 |
| Gitee | HTTP 302 | ✅ 无 download_url | 正常 |
| R2 CDN | HTTP 200 | ✅ 无 download_url | 正常 |
| ECS | HTTP 200 | ✅ 无 download_url | 正常 |

### 3.2 下载 URL 格式

| 源 | URL |
|---|-----|
| Gitee | `https://gitee.com/yuanchenglu/openclaw-wechat-plugin/repository/archive/v1.4.0.tar.gz` |
| GitHub | `https://github.com/yuanchenglu/openclaw-wechat-plugin/archive/refs/tags/v1.4.0.tar.gz` |
| R2 CDN | `https://wechat.clawadmin.org/release/v1.4.0.tar.gz` |
| ECS | `https://claw-wechat.7color.vip/release/v1.4.0.tar.gz` |

---

## 四、影响分析

### 4.1 兼容性

| 场景 | 影响 |
|------|------|
| 新安装用户 | 无影响，使用最新版本 |
| 现有用户更新 | 无影响，动态构建 URL |
| 旧版本客户端 | 不支持自动更新，需手动升级到 v1.4.0+ |

### 4.2 回滚方案

如需回滚：
1. 重新添加 `download_url` 字段到 `version.json`
2. 更新 `updater.py` 优先使用 `download_url`
3. 重新上传 `version.json` 到各下载源

---

## 五、后续任务

1. **后端 API 版本号**：`openclaw-wechat-channel` 的 `/channel-update/version.json` 端点版本号硬编码，需要改为动态读取
2. **监控告警**：添加下载源可用性监控
3. **文档更新**：更新用户文档中的版本号说明

---

## 六、关联资源

- GitHub Release: https://github.com/yuanchenglu/openclaw-wechat-plugin/releases/tag/v1.4.0
- Actions Run: https://github.com/yuanchenglu/openclaw-wechat-plugin/actions/runs/23480066187
- Gitee 仓库: https://gitee.com/yuanchenglu/openclaw-wechat-plugin