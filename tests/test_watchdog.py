"""
OpenClaw 微信频道插件 - 看门狗模块测试

测试内容：
1. 看门狗模块可导入
2. 心跳检测逻辑
3. 超时告警触发
4. 健康状态查询
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from watchdog import (
    WatchdogMonitor,
    HealthStatus,
    create_watchdog
)


class TestWatchdogImport:
    """测试模块导入"""

    def test_import_watchdog_module(self):
        """测试看门狗模块可导入"""
        from src.watchdog import WatchdogMonitor
        assert WatchdogMonitor is not None

    def test_import_health_status(self):
        """测试健康状态枚举可导入"""
        from src.watchdog import HealthStatus
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.WARNING.value == "warning"
        assert HealthStatus.CRITICAL.value == "critical"
        assert HealthStatus.UNKNOWN.value == "unknown"

    def test_import_create_watchdog(self):
        """测试便捷函数可导入"""
        from src.watchdog import create_watchdog
        assert create_watchdog is not None


class TestWatchdogMonitor:
    """测试 WatchdogMonitor 类"""

    def test_init_default_params(self):
        """测试默认参数初始化"""
        monitor = WatchdogMonitor(relay_url="wss://test.com/ws")

        assert monitor.relay_url == "wss://test.com/ws"
        assert monitor.openid is None
        assert monitor.send_callback is None
        assert monitor.timeout_seconds == 60
        assert monitor.warning_threshold == 0.8
        assert monitor.alert_cooldown == 300
        assert monitor.check_interval == 10
        assert not monitor.is_running

    def test_init_custom_params(self):
        """测试自定义参数初始化"""
        def dummy_callback(msg):
            pass

        monitor = WatchdogMonitor(
            relay_url="wss://custom.com/ws",
            openid="test_openid_123",
            send_callback=dummy_callback,
            timeout_seconds=120,
            warning_threshold=0.9,
            alert_cooldown=600,
            check_interval=5
        )

        assert monitor.relay_url == "wss://custom.com/ws"
        assert monitor.openid == "test_openid_123"
        assert monitor.send_callback == dummy_callback
        assert monitor.timeout_seconds == 120
        assert monitor.warning_threshold == 0.9
        assert monitor.alert_cooldown == 600
        assert monitor.check_interval == 5

    def test_feed_heartbeat(self):
        """测试喂狗（记录心跳）"""
        monitor = WatchdogMonitor(relay_url="wss://test.com/ws")

        assert monitor.last_heartbeat is None

        monitor.feed()

        assert monitor.last_heartbeat is not None
        assert isinstance(monitor.last_heartbeat, datetime)

    def test_update_openid(self):
        """测试更新 OpenID"""
        monitor = WatchdogMonitor(relay_url="wss://test.com/ws")

        assert monitor.openid is None

        monitor.update_openid("new_openid_456")

        assert monitor.openid == "new_openid_456"

    def test_update_send_callback(self):
        """测试更新发送回调"""
        monitor = WatchdogMonitor(relay_url="wss://test.com/ws")

        assert monitor.send_callback is None

        def new_callback(msg):
            pass

        monitor.update_send_callback(new_callback)

        assert monitor.send_callback == new_callback

    def test_get_health_status_no_heartbeat(self):
        """测试无心跳时的健康状态"""
        monitor = WatchdogMonitor(relay_url="wss://test.com/ws")

        status = monitor.get_health_status()

        assert status["status"] == HealthStatus.UNKNOWN.value
        assert status["last_heartbeat"] is None
        assert status["elapsed_seconds"] is None
        assert status["is_running"] is False

    def test_get_health_status_healthy(self):
        """测试健康状态"""
        monitor = WatchdogMonitor(relay_url="wss://test.com/ws")
        monitor.feed()

        status = monitor.get_health_status()

        assert status["status"] == HealthStatus.HEALTHY.value
        assert status["last_heartbeat"] is not None
        assert status["elapsed_seconds"] < 10  # 刚刚喂狗

    def test_get_health_status_properties(self):
        """测试健康状态属性"""
        monitor = WatchdogMonitor(relay_url="wss://test.com/ws")

        assert monitor.is_running is False
        assert monitor.last_heartbeat is None
        assert monitor.alert_count == 0


class TestWatchdogMonitorAsync:
    """测试 WatchdogMonitor 异步功能"""

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        """测试启动和停止监控"""
        monitor = WatchdogMonitor(relay_url="wss://test.com/ws")

        assert not monitor.is_running

        await monitor.start()

        assert monitor.is_running

        await monitor.stop()

        assert not monitor.is_running

    @pytest.mark.asyncio
    async def test_double_start(self):
        """测试重复启动"""
        monitor = WatchdogMonitor(relay_url="wss://test.com/ws")

        await monitor.start()
        await monitor.start()  # 应该被忽略

        assert monitor.is_running

        await monitor.stop()

    @pytest.mark.asyncio
    async def test_double_stop(self):
        """测试重复停止"""
        monitor = WatchdogMonitor(relay_url="wss://test.com/ws")

        await monitor.start()
        await monitor.stop()
        await monitor.stop()  # 应该安全

        assert not monitor.is_running

    @pytest.mark.asyncio
    async def test_heartbeat_timeout_triggers_alert(self):
        """测试心跳超时触发告警"""
        # 使用较短的超时时间和检查间隔进行测试
        alert_messages = []

        def capture_alert(msg):
            alert_messages.append(msg)

        monitor = WatchdogMonitor(
            relay_url="wss://test.com/ws",
            openid="test_openid",
            send_callback=capture_alert,
            timeout_seconds=2,  # 2秒超时
            alert_cooldown=0,  # 禁用冷却
            check_interval=1  # 1秒检查一次
        )

        # 模拟心跳
        monitor.feed()

        # 启动监控
        await monitor.start()

        # 等待检查周期（检查间隔 + 超时时间 + 一些缓冲）
        await asyncio.sleep(3.5)

        # 检查告警是否发送
        assert len(alert_messages) > 0
        assert alert_messages[0]["type"] == "watchdog_alert"
        assert alert_messages[0]["openid"] == "test_openid"
        assert alert_messages[0]["data"]["alert_type"] == "heartbeat_timeout"

        await monitor.stop()

    @pytest.mark.asyncio
    async def test_heartbeat_resets_timer(self):
        """测试心跳重置计时器"""
        alert_messages = []

        def capture_alert(msg):
            alert_messages.append(msg)

        monitor = WatchdogMonitor(
            relay_url="wss://test.com/ws",
            openid="test_openid",
            send_callback=capture_alert,
            timeout_seconds=2,
            alert_cooldown=0,
            check_interval=1
        )

        await monitor.start()

        # 持续喂狗，不应触发告警
        for _ in range(5):
            monitor.feed()
            await asyncio.sleep(1)

        assert len(alert_messages) == 0

        await monitor.stop()

    @pytest.mark.asyncio
    async def test_alert_cooldown(self):
        """测试告警冷却"""
        alert_messages = []

        def capture_alert(msg):
            alert_messages.append(msg)

        monitor = WatchdogMonitor(
            relay_url="wss://test.com/ws",
            openid="test_openid",
            send_callback=capture_alert,
            timeout_seconds=1,
            alert_cooldown=10,  # 10秒冷却
            check_interval=0.5  # 0.5秒检查一次
        )

        monitor.feed()
        await monitor.start()

        # 等待第一次超时（需要等待检查周期）
        await asyncio.sleep(2)

        # 应该只发送一次告警
        assert len(alert_messages) == 1

        # 再等待一段时间（在冷却期内）
        await asyncio.sleep(2)

        # 仍然只有一次告警
        assert len(alert_messages) == 1

        await monitor.stop()

    @pytest.mark.asyncio
    async def test_no_alert_without_openid(self):
        """测试无 OpenID 时不发送告警"""
        alert_messages = []

        def capture_alert(msg):
            alert_messages.append(msg)

        monitor = WatchdogMonitor(
            relay_url="wss://test.com/ws",
            openid=None,  # 无 OpenID
            send_callback=capture_alert,
            timeout_seconds=1,
            alert_cooldown=0,
            check_interval=0.5
        )

        monitor.feed()
        await monitor.start()

        await asyncio.sleep(2)

        # 不应发送告警
        assert len(alert_messages) == 0

        await monitor.stop()

    @pytest.mark.asyncio
    async def test_no_alert_without_callback(self):
        """测试无回调时不发送告警"""
        monitor = WatchdogMonitor(
            relay_url="wss://test.com/ws",
            openid="test_openid",
            send_callback=None,  # 无回调
            timeout_seconds=1,
            alert_cooldown=0,
            check_interval=0.5
        )

        monitor.feed()
        await monitor.start()

        await asyncio.sleep(2)

        # 不应崩溃
        assert monitor.alert_count == 0

        await monitor.stop()


class TestCreateWatchdog:
    """测试便捷函数"""

    def test_create_watchdog_default(self):
        """测试默认参数创建"""
        monitor = create_watchdog(relay_url="wss://test.com/ws")

        assert isinstance(monitor, WatchdogMonitor)
        assert monitor.relay_url == "wss://test.com/ws"
        assert monitor.timeout_seconds == 60
        assert monitor.check_interval == 10

    def test_create_watchdog_custom(self):
        """测试自定义参数创建"""
        def callback(msg):
            pass

        monitor = create_watchdog(
            relay_url="wss://custom.com/ws",
            openid="test_openid",
            send_callback=callback,
            timeout_seconds=120,
            check_interval=5
        )

        assert monitor.relay_url == "wss://custom.com/ws"
        assert monitor.openid == "test_openid"
        assert monitor.send_callback == callback
        assert monitor.timeout_seconds == 120
        assert monitor.check_interval == 5


class TestHealthStatusCalculation:
    """测试健康状态计算"""

    def test_status_healthy(self):
        """测试健康状态计算 - 健康"""
        monitor = WatchdogMonitor(
            relay_url="wss://test.com/ws",
            timeout_seconds=60
        )

        # 模拟刚刚喂狗
        monitor._last_heartbeat = datetime.utcnow()

        status = monitor.get_health_status()

        assert status["status"] == HealthStatus.HEALTHY.value
        assert status["elapsed_seconds"] < 48  # 80% 阈值内

    def test_status_warning(self):
        """测试健康状态计算 - 预警"""
        monitor = WatchdogMonitor(
            relay_url="wss://test.com/ws",
            timeout_seconds=60
        )

        # 模拟 50 秒前喂狗（超过 80% 阈值）
        monitor._last_heartbeat = datetime.utcnow() - timedelta(seconds=50)

        status = monitor.get_health_status()

        assert status["status"] == HealthStatus.WARNING.value
        assert 48 <= status["elapsed_seconds"] < 60

    def test_status_critical(self):
        """测试健康状态计算 - 严重"""
        monitor = WatchdogMonitor(
            relay_url="wss://test.com/ws",
            timeout_seconds=60
        )

        # 模拟 70 秒前喂狗（超过超时阈值）
        monitor._last_heartbeat = datetime.utcnow() - timedelta(seconds=70)

        status = monitor.get_health_status()

        assert status["status"] == HealthStatus.CRITICAL.value
        assert status["elapsed_seconds"] >= 60


# 运行测试
if __name__ == "__main__":
    pytest.main([__file__, "-v"])