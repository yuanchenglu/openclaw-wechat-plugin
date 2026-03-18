# 变更记录

## 概要

| 项目 | 内容 |
|------|------|
| **类型** | FIX (Bug修复) |
| **日期** | 2026-03-18 |
| **版本** | v1.4.0 → v1.4.1 |
| **影响范围** | 安装流程 |

---

## 业务需求

用户按照官方文档执行安装命令时，连续遇到三个阻塞性Bug，导致安装失败：

1. **sh/bash 兼容性问题**：用户执行 `curl ... | sh` 时报语法错误
2. **下载源全部失败**：脚本无法正确下载 requirements.txt
3. **模块名冲突**：启动时报 `ImportError`

**用户价值**：修复后用户可顺利完成一键安装，体验流畅。

---

## 技术方式

### 1. sh/bash 兼容性修复

**文件**: `release/install.sh`

**修改内容**:
```bash
# 在脚本开头添加 bash 环境检测
if [ -z "$BASH_VERSION" ]; then
    echo "错误: 请使用 bash 执行此脚本，而不是 sh"
    echo "正确用法: curl -fsSL ... | bash"
    exit 1
fi
```

**原理**: 
- Ubuntu/Debian 的 `sh` 是 `dash`，不支持 bash 数组语法
- 检测 `$BASH_VERSION` 环境变量判断是否在 bash 中执行
- 给出明确的错误提示而非语法错误

### 2. 下载路径修复

**文件**: `release/install.sh`

**修改内容**:
```bash
# 原来：所有文件都从 src/ 下载
local modules=("client.py" "requirements.txt" ...)

# 修复后：区分路径
local src_modules=("client.py" "watchdog.py" "updater.py" "wechat_types.py" "update_state.py")
local root_modules=("requirements.txt")

# 分别下载
for module in "${src_modules[@]}"; do
    curl "$base_url/src/$module" ...
done

for module in "${root_modules[@]}"; do
    curl "$base_url/$module" ...  # 注意：没有 /src/ 前缀
done
```

**原理**:
- 项目文件分布在两个位置：
  - Python 模块在 `src/` 目录
  - `requirements.txt` 在根目录
- 原脚本统一从 `src/` 下载，导致 `requirements.txt` 404

### 3. 模块名冲突修复

**文件变更**:
```
src/types.py → src/wechat_types.py (重命名)
src/client.py (更新导入)
```

**修改内容**:
```python
# 原来
from .types import CHECK_INTERVAL, RESTART_DELAY, RESTART_HOUR
_types_path = Path(__file__).parent / "types.py"

# 修复后
from .wechat_types import CHECK_INTERVAL, RESTART_DELAY, RESTART_HOUR
_types_path = Path(__file__).parent / "wechat_types.py"
```

**原理**:
- Python 标准库有 `types` 模块
- 当项目有同名 `types.py` 时，`from enum import Enum` 会触发循环导入
- 重命名为 `wechat_types.py` 避免冲突

---

## 核心变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/types.py` | 删除 | 重命名为 wechat_types.py |
| `src/wechat_types.py` | 新增 | 原 types.py 重命名 |
| `src/client.py` | 修改 | 更新导入 wechat_types |
| `release/install.sh` | 修改 | 修复兼容性和下载路径 |
| `README.md` | 修改 | 所有 `| sh` 改为 `| bash` |
| `docs/10_Design/微信频道插件需求文档.md` | 新增 | 需求文档 |
| `docs/30_Changelogs/FIX-20260318-安装脚本修复/` | 新增 | 变更记录 |

---

## 数据流转

```
安装流程（修复后）：

用户执行命令
    │
    ▼
curl 下载 install.sh
    │
    ▼
bash 执行脚本 ◀── 检测 $BASH_VERSION
    │
    ▼
检查 Python/pip 环境
    │
    ▼
下载客户端文件 ─────────────────────────┐
    │                                   │
    │  src_modules → $base_url/src/     │
    │  root_modules → $base_url/        │
    │                                   │
    ▼                                   │
创建虚拟环境                            │
    │                                   │
    ▼                                   │
安装依赖 (websockets, httpx)            │
    │                                   │
    ▼                                   │
创建启动脚本                            │
    │                                   │
    ▼                                   │
启动客户端 ─── 导入 wechat_types ── 成功 │
    │                                   │
    ▼                                   │
连接中转服务                            │
```

---

## Manifest

| Commit | 说明 |
|--------|------|
| [1975680](https://github.com/yuanchenglu/openclaw-wechat-plugin/commit/1975680) | FIX: 修复安装脚本三个阻塞性Bug |
|--------|------|
| (待提交) | FIX: 修复安装脚本三个阻塞性Bug |

---

## 相关文档

- [需求文档](../10_Design/微信频道插件需求文档.md)
- [安装脚本问题深度分析报告](../install-script-analysis-20260318.md)
- [安装脚本问题深度分析报告](../../../.sisyphus/install-script-analysis-20260318.md)