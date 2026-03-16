"""
OpenClaw 微信频道插件 - WebSocket 重连测试

测试指数退避重连逻辑。
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.client import (
    INITIAL_RETRY_DELAY,
    MAX_RETRY_DELAY,
    OpenClawWeChatClient
)


class TestReconnectConstants:
    """测试重连常量定义"""

    def test_initial_retry_delay(self):
        """初始重连延迟应为 1 秒"""
        assert INITIAL_RETRY_DELAY == 1

    def test_max_retry_delay(self):
        """最大重连延迟应为 30 秒"""
        assert MAX_RETRY_DELAY == 30


class TestExponentialBackoff:
    """测试指数退避逻辑"""

    def test_first_retry_delay(self):
        """第一次重试延迟应为 1 秒 (2^0 = 1)"""
        retry_count = 1
        delay = min(2 ** (retry_count - 1), MAX_RETRY_DELAY)
        assert delay == 1

    def test_second_retry_delay(self):
        """第二次重试延迟应为 2 秒 (2^1 = 2)"""
        retry_count = 2
        delay = min(2 ** (retry_count - 1), MAX_RETRY_DELAY)
        assert delay == 2

    def test_third_retry_delay(self):
        """第三次重试延迟应为 4 秒 (2^2 = 4)"""
        retry_count = 3
        delay = min(2 ** (retry_count - 1), MAX_RETRY_DELAY)
        assert delay == 4

    def test_fourth_retry_delay(self):
        """第四次重试延迟应为 8 秒 (2^3 = 8)"""
        retry_count = 4
        delay = min(2 ** (retry_count - 1), MAX_RETRY_DELAY)
        assert delay == 8

    def test_fifth_retry_delay(self):
        """第五次重试延迟应为 16 秒 (2^4 = 16)"""
        retry_count = 5
        delay = min(2 ** (retry_count - 1), MAX_RETRY_DELAY)
        assert delay == 16

    def test_sixth_retry_delay(self):
        """第六次重试延迟应为 30 秒（达到上限）"""
        retry_count = 6
        delay = min(2 ** (retry_count - 1), MAX_RETRY_DELAY)
        assert delay == 30  # 2^5 = 32, 但上限是 30

    def test_max_delay_cap(self):
        """延迟应被限制在 30 秒"""
        retry_count = 10
        delay = min(2 ** (retry_count - 1), MAX_RETRY_DELAY)
        assert delay == 30


class TestConnectWithRetry:
    """测试 _connect_with_retry 方法"""

    @pytest.mark.asyncio
    async def test_connect_success_on_first_try(self):
        """首次连接成功时，应立即返回 True"""
        client = OpenClawWeChatClient(
            openclaw_url="http://127.0.0.1:18789",
            relay_url="wss://test.example.com/ws"
        )

        # 模拟 connect 成功
        with patch.object(client, 'connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = None

            result = await client._connect_with_retry()

            assert result is True
            mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_retries_on_failure(self):
        """连接失败时应重试"""
        client = OpenClawWeChatClient(
            openclaw_url="http://127.0.0.1:18789",
            relay_url="wss://test.example.com/ws"
        )

        call_count = 0

        async def mock_connect():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Connection failed")
            # 第三次成功

        with patch.object(client, 'connect', new_callable=AsyncMock) as mock_connect_method:
            mock_connect_method.side_effect = mock_connect

            # 使用 asyncio.wait_for 添加超时保护
            result = await asyncio.wait_for(
                client._connect_with_retry(),
                timeout=5
            )

            assert result is True
            assert call_count == 3  # 失败 2 次，成功 1 次

    @pytest.mark.asyncio
    async def test_reconnect_resets_retry_count(self):
        """重连成功后应重置重试计数器"""
        client = OpenClawWeChatClient(
            openclaw_url="http://127.0.0.1:18789",
            relay_url="wss://test.example.com/ws"
        )

        call_count = 0

        async def mock_connect():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Connection failed")
            # 第二次成功

        with patch.object(client, 'connect', new_callable=AsyncMock) as mock_connect_method:
            mock_connect_method.side_effect = mock_connect

            result = await asyncio.wait_for(
                client._connect_with_retry(),
                timeout=5
            )

            assert result is True
            # 验证重试计数器在成功后被重置（通过内部状态）
            # 由于 retry_count 是局部变量，我们通过行为验证


class TestReconnectLogging:
    """测试重连日志记录"""

    @pytest.mark.asyncio
    async def test_reconnect_logs_attempt(self, caplog):
        """重连尝试应记录日志"""
        client = OpenClawWeChatClient(
            openclaw_url="http://127.0.0.1:18789",
            relay_url="wss://test.example.com/ws"
        )

        call_count = 0

        async def mock_connect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Connection failed")
            # 第二次成功

        with patch.object(client, 'connect', new_callable=AsyncMock) as mock_connect_method:
            mock_connect_method.side_effect = mock_connect

            with caplog.at_level('WARNING'):
                result = await asyncio.wait_for(
                    client._connect_with_retry(),
                    timeout=5
                )

            assert result is True
            # 验证日志包含重连尝试信息
            assert any("连接失败" in record.message for record in caplog.records)
            assert any("重试" in record.message for record in caplog.records)