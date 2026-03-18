# 修复计划

## 问题背景

用户反馈安装脚本在多个步骤全部失败，无法正常安装插件。经深度分析发现三个阻塞性Bug：

| Bug | 现象 | 根因 |
|-----|------|------|
| sh/bash 兼容性 | `Syntax error: "(" unexpected` | 脚本使用bash数组语法，但文档让用户用sh执行 |
| requirements.txt 路径错误 | 所有下载源失败 | 脚本从src/requirements.txt下载，但文件在根目录 |
| types.py 命名冲突 | `ImportError: cannot import name 'Enum'` | types.py与Python标准库同名 |

## 修复目标

1. 用户使用 `sh` 执行时给出明确错误提示
2. 正确区分 src 目录和根目录的文件下载路径
3. 避免模块名与 Python 标准库冲突

## 技术方案

### 方案1: sh/bash 兼容性

在脚本开头添加检测：

```bash
if [ -z "$BASH_VERSION" ]; then
    echo "错误: 请使用 bash 执行此脚本，而不是 sh"
    exit 1
fi
```

### 方案2: 下载路径分离

```bash
# src 目录下的 Python 模块
local src_modules=("client.py" "watchdog.py" "updater.py" "wechat_types.py" "update_state.py")

# 根目录下的配置文件
local root_modules=("requirements.txt")

# 分别下载
for module in "${src_modules[@]}"; do
    curl "$base_url/src/$module" -o "$PLUGIN_DIR/$module"
done

for module in "${root_modules[@]}"; do
    curl "$base_url/$module" -o "$PLUGIN_DIR/$module"
done
```

### 方案3: 重命名 types.py

```
src/types.py → src/wechat_types.py
```

更新所有引用：
- `from .types import` → `from .wechat_types import`
- 动态加载路径同步更新

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 已安装用户兼容性 | 低 | 旧版types.py仍可工作，新版向下兼容 |
| 文档更新延迟 | 中 | 同时更新README.md和安装脚本注释 |

## 验证标准

1. `sh install.sh` → 输出错误提示，非语法错误
2. `bash install.sh` → 正常下载所有文件
3. 启动客户端 → 无模块冲突错误