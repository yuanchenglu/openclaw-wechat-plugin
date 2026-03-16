"""
OpenClaw 微信频道插件 - 看门狗监控模块

功能：
1. 心跳超时检测（阈值 60 秒，服务端 WS_TIMEOUT=30s 的两倍）
2. 通过中转服务发送微信告警
3. 健康状态查询

使用方法：
    watchdog = WatchdogMonitor(relay_url, openid, send_callback)
    watchdog.start()

    # 心跳正常时调用
    watchdog.feed()

    # 查询健康状态
    status = watchdog.get_health_status()

    # 停止监控
    watchdog.stop()
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, Any
from enum import Enum

# 日志配置
logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """健康状态枚举"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class WatchdogMonitor:
    """
    看门狗监控器

    监控心跳状态，超时后发送告警。
    告警通过中转服务发送微信消息给用户。

    Attributes:
        timeout_seconds: 心跳超时阈值（秒），默认 60 秒
        warning_threshold: 预警阈值比例（默认 0.8，即 48 秒时开始预警）
        alert_cooldown: 告警冷却时间（秒），防止频繁告警，默认 300 秒
        check_interval: 监控检查间隔（秒），默认 10 秒
    """

    # 默认配置
    DEFAULT_TIMEOUT = 60  # 心跳超时阈值（秒）
    DEFAULT_WARNING_THRESHOLD = 0.8  # 预警阈值（80% 超时时间）
    DEFAULT_ALERT_COOLDOWN = 300  # 告警冷却时间（秒）
    DEFAULT_CHECK_INTERVAL = 10  # 监控检查间隔（秒）

    def __init__(
        self,
        relay_url: str,
        openid: Optional[str] = None,
        send_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        timeout_seconds: int = DEFAULT_TIMEOUT,
        warning_threshold: float = DEFAULT_WARNING_THRESHOLD,
        alert_cooldown: int = DEFAULT_ALERT_COOLDOWN,
        check_interval: int = DEFAULT_CHECK_INTERVAL
    ):
        """
        初始化看门狗监控器

        Args:
            relay_url: 中转服务地址
            openid: 用户 OpenID（用于发送告警）
            send_callback: 发送消息的回调函数，用于发送告警消息
            timeout_seconds: 心跳超时阈值（秒）
            warning_threshold: 预警阈值比例
            alert_cooldown: 告警冷却时间（秒）
            check_interval: 监控检查间隔（秒）
        """
        self.relay_url = relay_url
        self.openid = openid
        self.send_callback = send_callback
        self.timeout_seconds = timeout_seconds
        self.warning_threshold = warning_threshold
        self.alert_cooldown = alert_cooldown
        self.check_interval = check_interval

        # 内部状态
        self._last_heartbeat: Optional[datetime] = None
        self._last_alert_time: Optional[datetime] = None
        self._alert_count: int = 0
        self._running: bool = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    def feed(self):
        """
        喂狗（记录心跳）

        在心跳正常时调用此方法，重置心跳计时器。
        """
        self._last_heartbeat = datetime.utcnow()
        logger.debug(f"[Watchdog] 心跳记录: {self._last_heartbeat.isoformat()}")

    def update_openid(self, openid: str):
        """
        更新用户 OpenID

        Args:
            openid: 新的用户 OpenID
        """
        self.openid = openid
        logger.debug(f"[Watchdog] OpenID 更新: {openid}")

    def update_send_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """
        更新发送回调函数

        Args:
            callback: 新的发送回调函数
        """
        self.send_callback = callback
        logger.debug("[Watchdog] 发送回调已更新")

    async def start(self):
        """
        启动看门狗监控

        创建后台任务，定期检查心跳状态。
        """
        if self._running:
            logger.warning("[Watchdog] 监控已在运行中")
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info(f"[Watchdog] 监控已启动 (超时阈值: {self.timeout_seconds}秒)")

    async def stop(self):
        """
        停止看门狗监控

        取消后台监控任务。
        """
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        logger.info("[Watchdog] 监控已停止")

    async def _monitor_loop(self):
        """
        监控循环

        定期检查心跳状态。
        """
        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                await self._check_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Watchdog] 监控循环异常: {e}")

    async def _check_health(self):
        """
        检查健康状态

        如果心跳超时，发送告警。
        """
        async with self._lock:
            now = datetime.utcnow()

            # 如果还没有心跳记录，跳过检查
            if self._last_heartbeat is None:
                logger.debug("[Watchdog] 等待首次心跳...")
                return

            # 计算距离上次心跳的时间
            elapsed = (now - self._last_heartbeat).total_seconds()

            # 检查是否超时
            if elapsed >= self.timeout_seconds:
                await self._handle_timeout(elapsed)
            elif elapsed >= self.timeout_seconds * self.warning_threshold:
                logger.warning(
                    f"[Watchdog] 心跳预警: {elapsed:.1f}秒 "
                    f"(阈值: {self.timeout_seconds * self.warning_threshold:.1f}秒)"
                )

    async def _handle_timeout(self, elapsed: float):
        """
        处理心跳超时

        Args:
            elapsed: 距离上次心跳的秒数
        """
        now = datetime.utcnow()

        # 检查是否在冷却期内
        if self._last_alert_time:
            cooldown_remaining = self.alert_cooldown - (now - self._last_alert_time).total_seconds()
            if cooldown_remaining > 0:
                logger.debug(
                    f"[Watchdog] 告警冷却中，剩余 {cooldown_remaining:.0f} 秒"
                )
                return

        logger.error(
            f"[Watchdog] ⚠️ 心跳超时! 距上次心跳 {elapsed:.1f} 秒 "
            f"(阈值: {self.timeout_seconds} 秒)"
        )

        # 发送告警
        sent = await self._send_alert(elapsed)

        # 只有发送成功才更新告警时间和计数
        if sent:
            self._last_alert_time = now
            self._alert_count += 1

    async def _send_alert(self, elapsed: float) -> bool:
        """
        发送告警消息

        通过中转服务发送微信消息给用户。

        Args:
            elapsed: 距离上次心跳的秒数

        Returns:
            bool: 是否成功发送
        """
        if not self.send_callback:
            logger.warning("[Watchdog] 无发送回调，无法发送告警")
            return False

        if not self.openid:
            logger.warning("[Watchdog] 无 OpenID，无法发送告警")
            return False

        # 构建告警消息
        alert_message = {
            "type": "watchdog_alert",
            "openid": self.openid,
            "data": {
                "alert_type": "heartbeat_timeout",
                "elapsed_seconds": elapsed,
                "threshold_seconds": self.timeout_seconds,
                "timestamp": datetime.utcnow().isoformat(),
                "alert_count": self._alert_count + 1
            }
        }

        try:
            # 通过回调发送消息到中转服务
            self.send_callback(alert_message)
            logger.info(f"[Watchdog] 告警已发送 (第 {self._alert_count + 1} 次)")
            return True
        except Exception as e:
            logger.error(f"[Watchdog] 发送告警失败: {e}")
            return False

    def get_health_status(self) -> Dict[str, Any]:
        """
        获取健康状态

        Returns:
            包含健康状态的字典：
            - status: 健康状态枚举值
            - last_heartbeat: 上次心跳时间
            - elapsed_seconds: 距离上次心跳的秒数
            - alert_count: 告警次数
            - is_running: 监控是否运行中
        """
        now = datetime.utcnow()

        # 计算健康状态
        if self._last_heartbeat is None:
            status = HealthStatus.UNKNOWN
            elapsed = None
        else:
            elapsed = (now - self._last_heartbeat).total_seconds()

            if elapsed < self.timeout_seconds * self.warning_threshold:
                status = HealthStatus.HEALTHY
            elif elapsed < self.timeout_seconds:
                status = HealthStatus.WARNING
            else:
                status = HealthStatus.CRITICAL

        return {
            "status": status.value,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            "elapsed_seconds": elapsed,
            "threshold_seconds": self.timeout_seconds,
            "warning_threshold_seconds": self.timeout_seconds * self.warning_threshold,
            "alert_count": self._alert_count,
            "is_running": self._running,
            "openid": self.openid
        }

    @property
    def is_running(self) -> bool:
        """监控是否运行中"""
        return self._running

    @property
    def last_heartbeat(self) -> Optional[datetime]:
        """上次心跳时间"""
        return self._last_heartbeat

    @property
    def alert_count(self) -> int:
        """告警次数"""
        return self._alert_count


# 便捷函数
def create_watchdog(
    relay_url: str,
    openid: Optional[str] = None,
    send_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    timeout_seconds: int = WatchdogMonitor.DEFAULT_TIMEOUT,
    check_interval: int = WatchdogMonitor.DEFAULT_CHECK_INTERVAL
) -> WatchdogMonitor:
    """
    创建看门狗监控器

    Args:
        relay_url: 中转服务地址
        openid: 用户 OpenID
        send_callback: 发送消息的回调函数
        timeout_seconds: 心跳超时阈值（秒）
        check_interval: 监控检查间隔（秒）

    Returns:
        WatchdogMonitor 实例
    """
    return WatchdogMonitor(
        relay_url=relay_url,
        openid=openid,
        send_callback=send_callback,
        timeout_seconds=timeout_seconds,
        check_interval=check_interval
    )