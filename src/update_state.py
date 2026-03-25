"""
OpenClaw 微信频道插件 - 升级状态持久化模块

功能：
1. 持久化升级状态到本地 JSON 文件
2. 记录安装时间，判断是否需要重启
3. 支持延迟重启策略（24小时后次日4:00）

状态文件路径: ~/.openclaw/update_state.json

使用方法：
    from update_state import UpdateState, save_state, load_state
    
    # 保存状态
    state = UpdateState(
        pending_update=True,
        target_version="1.3.0",
        current_version="1.2.0"
    )
    save_state(state)
    
    # 加载状态
    state = load_state()
    if state and state.is_restart_due():
        # 执行重启
        pass
"""

import json
import logging
import datetime as datetime_module  # 导入整个模块以便测试 mock
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

# 注意：直接使用 datetime_module.datetime 和 datetime_module.timedelta 以便测试 mock
# 配置日志
logger = logging.getLogger(__name__)

# 状态文件路径
STATE_FILE_PATH = Path.home() / ".openclaw" / "update_state.json"

# 重启策略配置
RESTART_DELAY_HOURS = 24  # 安装后延迟重启的小时数
RESTART_HOUR = 4  # 重启时间点（次日4:00）


@dataclass
class UpdateState:
    """
    升级状态数据类
    
    Attributes:
        pending_update: 是否有待安装的更新
        download_progress: 下载进度（0-100）
        install_time: 安装完成时间（ISO 格式字符串）
        target_version: 目标版本号
        current_version: 当前版本号（安装前）
    """
    pending_update: bool = False
    download_progress: int = 0
    install_time: Optional[str] = None
    target_version: Optional[str] = None
    current_version: Optional[str] = None
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "UpdateState":
        """
        从字典创建 UpdateState 实例
        
        Args:
            data: 包含状态数据的字典
            
        Returns:
            UpdateState 实例
        """
        return cls(
            pending_update=data.get("pending_update", False),
            download_progress=data.get("download_progress", 0),
            install_time=data.get("install_time"),
            target_version=data.get("target_version"),
            current_version=data.get("current_version")
        )
    
    def is_restart_due(self) -> bool:
        """
        判断是否需要重启
        
        重启条件：
        1. 存在待安装的更新
        2. 安装时间存在
        3. 距离安装时间已超过 24 小时，或已到达次日 4:00
        
        Returns:
            True 表示需要重启，False 表示不需要
        """
        if not self.pending_update or not self.install_time:
            return False
        
        try:
            install_dt = datetime_module.datetime.fromisoformat(self.install_time)
            now = datetime_module.datetime.now()
            
            # 计算距离安装的时间
            elapsed = now - install_dt
            
            # 超过 24 小时，需要重启
            if elapsed >= datetime_module.timedelta(hours=RESTART_DELAY_HOURS):
                return True
            
            # 未到 24 小时，检查是否到达次日 4:00
            # 计算次日 4:00 的时间点
            next_restart_time = self._calculate_next_restart_time(install_dt)
            
            return now >= next_restart_time
            
        except (ValueError, TypeError) as e:
            logger.error(f"解析安装时间失败: {e}")
            return False
    
    def _calculate_next_restart_time(self, install_dt: datetime_module.datetime) -> datetime_module.datetime:
        """
        计算下一次重启时间（次日4:00或更后）
        
        Args:
            install_dt: 安装时间
            
        Returns:
            下一次重启时间
        """
        # 安装时间的次日
        next_day = install_dt + datetime_module.timedelta(days=1)
        
        # 次日 4:00
        restart_time = next_day.replace(
            hour=RESTART_HOUR, 
            minute=0, 
            second=0, 
            microsecond=0
        )
        
        # 如果安装时间已经是 4:00 之后，则重启时间是次日 4:00
        # 如果安装时间在 4:00 之前，则重启时间是当天次日 4:00
        return restart_time
    
    def get_restart_delay(self) -> int:
        """
        计算距离重启还有多少秒
        
        Returns:
            距离重启的秒数，如果已经需要重启则返回 0，
            如果没有待安装更新则返回 -1
        """
        if not self.pending_update or not self.install_time:
            return -1
        
        try:
            install_dt = datetime_module.datetime.fromisoformat(self.install_time)
            now = datetime_module.datetime.now()
            
            # 已经超过 24 小时
            elapsed = now - install_dt
            if elapsed >= datetime_module.timedelta(hours=RESTART_DELAY_HOURS):
                return 0
            
            # 计算到重启时间的剩余秒数
            restart_time = self._calculate_next_restart_time(install_dt)
            
            if now >= restart_time:
                return 0
            
            remaining = restart_time - now
            return int(remaining.total_seconds())
            
        except (ValueError, TypeError) as e:
            logger.error(f"解析安装时间失败: {e}")
            return -1
    
    def set_installed(self, target_version: str, current_version: str) -> None:
        """
        设置更新已安装状态
        
        Args:
            target_version: 目标版本号
            current_version: 当前版本号
        """
        self.pending_update = True
        self.install_time = datetime_module.datetime.now().isoformat()
        self.target_version = target_version
        self.current_version = current_version
        self.download_progress = 100
    def clear(self) -> None:
        """清除更新状态（重启完成后调用）"""
        self.pending_update = False
        self.download_progress = 0
        self.install_time = None
        self.target_version = None
        self.current_version = None


def save_state(state: UpdateState, state_path: Optional[Path] = None) -> bool:
    """
    保存升级状态到文件
    
    Args:
        state: 要保存的状态对象
        state_path: 状态文件路径，默认为 ~/.openclaw/update_state.json
        
    Returns:
        保存成功返回 True，失败返回 False
    """
    path = state_path or STATE_FILE_PATH
    
    try:
        # 确保目录存在
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入文件
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
        
        logger.debug(f"升级状态已保存到: {path}")
        return True
        
    except Exception as e:
        logger.error(f"保存升级状态失败: {e}")
        return False


def load_state(state_path: Optional[Path] = None) -> Optional[UpdateState]:
    """
    从文件加载升级状态
    
    Args:
        state_path: 状态文件路径，默认为 ~/.openclaw/update_state.json
        
    Returns:
        加载成功返回 UpdateState 实例，失败或文件不存在返回 None
    """
    path = state_path or STATE_FILE_PATH
    
    try:
        if not path.exists():
            logger.debug(f"状态文件不存在: {path}")
            return None
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        state = UpdateState.from_dict(data)
        logger.debug(f"升级状态已加载: {path}")
        return state
        
    except json.JSONDecodeError as e:
        logger.error(f"解析状态文件失败: {e}")
        return None
    except Exception as e:
        logger.error(f"加载升级状态失败: {e}")
        return None


def clear_state(state_path: Optional[Path] = None) -> bool:
    """
    清除状态文件
    
    Args:
        state_path: 状态文件路径，默认为 ~/.openclaw/update_state.json
        
    Returns:
        清除成功返回 True，失败返回 False
    """
    path = state_path or STATE_FILE_PATH
    
    try:
        if path.exists():
            path.unlink()
            logger.debug(f"状态文件已删除: {path}")
        return True
        
    except Exception as e:
        logger.error(f"清除状态文件失败: {e}")
        return False