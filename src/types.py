"""
OpenClaw 微信频道插件 - 类型定义

版本: 1.0.0
变更记录:
- 2026-03-17: 创建文件，添加 UpgradeStatus 枚举和升级相关常量
"""
from enum import Enum


class UpgradeStatus(str, Enum):
    """客户端升级状态枚举
    
    状态流转:
    IDLE → CHECKING → DOWNLOADING → DOWNLOADED → INSTALLED → RESTART_PENDING → (重启后回到 IDLE)
    
    状态说明:
    - IDLE: 空闲，无升级任务
    - CHECKING: 正在检查是否有新版本
    - DOWNLOADING: 正在下载新版本
    - DOWNLOADED: 已下载完成，等待安装
    - INSTALLED: 已安装完成，等待重启
    - RESTART_PENDING: 重启待定（延迟到指定时间）
    - FAILED: 升级过程失败
    """
    IDLE = "idle"                      # 空闲，无升级
    CHECKING = "checking"              # 检查中
    DOWNLOADING = "downloading"        # 下载中
    DOWNLOADED = "downloaded"          # 已下载，待安装
    INSTALLED = "installed"            # 已安装，待重启
    RESTART_PENDING = "restart_pending"  # 重启待定
    FAILED = "failed"                  # 升级失败


# ============ 升级相关常量 ============

# 检查更新间隔（秒）
CHECK_INTERVAL = 5 * 3600  # 5 小时

# 重启延迟时间（秒）
RESTART_DELAY = 24 * 3600  # 24 小时

# 重启时间点（小时，24 小时制）
RESTART_HOUR = 4  # 次日 4:00 重启

# 下载超时（秒）
DOWNLOAD_TIMEOUT = 300  # 5 分钟

# 下载重试次数
DOWNLOAD_RETRY_COUNT = 3

# 下载重试间隔（秒）
DOWNLOAD_RETRY_INTERVAL = 60  # 1 分钟