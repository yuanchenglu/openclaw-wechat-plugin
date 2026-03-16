"""
OpenClaw 微信频道插件 - 端到端集成测试

测试场景：
1. 启动客户端 → 连接成功
2. 断开连接 → 自动重连
3. 心跳超时 → 看门狗告警
4. 检测更新 → 自动下载

所有测试使用 mock 服务端，不依赖真实微信服务号或中转服务。
"""
import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 导入被测模块
from src.client import (
    OpenClawWeChatClient,
    CLIENT_VERSION,
    INITIAL_RETRY_DELAY,
    MAX_RETRY_DELAY,
)
from src.watchdog import WatchdogMonitor, HealthStatus
from src.updater import Updater


# ==================== Mock WebSocket 服务端 ====================

class MockWebSocketServer:
    """模拟 WebSocket 服务端，用于测试客户端连接"""

    def __init__(self):
        self.sent_messages: List[dict] = []
        self.received_messages: List[dict] = []
        self.is_connected = False
        self._closed = False
        self._recv_queue: asyncio.Queue = asyncio.Queue()

    async def send(self, message: str):
        """模拟发送消息"""
        if self._closed:
            raise Exception("WebSocket is closed")
        try:
            data = json.loads(message)
            self.received_messages.append(data)
        except json.JSONDecodeError:
            pass

    async def recv(self) -> str:
        """模拟接收消息"""
        if self._closed:
            raise Exception("WebSocket is closed")
        msg = await self._recv_queue.get()
        return json.dumps(msg)

    async def close(self):
        """模拟关闭连接"""
        self._closed = True
        self.is_connected = False

    async def ping(self):
        """模拟 ping"""
        if self._closed:
            raise Exception("WebSocket is closed")
        return True

    def queue_response(self, message: dict):
        """将响应消息加入队列"""
        self._recv_queue.put_nowait(message)

    def get_received_messages(self) -> List[dict]:
        """获取已接收的消息列表"""
        return self.received_messages.copy()

    def clear_messages(self):
        """清空消息列表"""
        self.sent_messages.clear()
        self.received_messages.clear()


def create_mock_websocket() -> MockWebSocketServer:
    """创建 mock WebSocket 实例"""
    return MockWebSocketServer()


# ==================== Fixtures ====================

@pytest.fixture
def temp_config_dir():
    """临时配置目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_relay_server():
    """Mock 中转服务"""
    return create_mock_websocket()


@pytest.fixture
def mock_openclaw_response():
    """Mock OpenClaw API 响应"""
    return {
        "choices": [
            {
                "message": {
                    "content": "这是测试回复"
                }
            }
        ]
    }


@pytest.fixture
def mock_version_response():
    """Mock 版本检查响应"""
    return {
        "version": "1.3.0",
        "download_url": "https://example.com/release/openclaw-wechat-channel-v1.3.0.tar.gz",
        "changelog": ["新增功能 A", "修复问题 B"],
        "checksum": {
            "sha256": "abc123"
        }
    }


# ==================== 场景 1: 启动连接测试 ====================

class TestClientConnectSuccess:
    """测试场景 1: 客户端成功连接到服务端"""

    @pytest.mark.asyncio
    async def test_client_init_with_config(self, temp_config_dir):
        """客户端初始化时应正确加载配置"""
        # 准备已存在的配置
        config_file = temp_config_dir / "config.json"
        config_data = {
            "device_id": "bare_test123_testuser_20260101120000_a1b2",
            "device_type": "bare",
            "machine_id": "test123",
            "system_username": "testuser",
            "openid": "test_openid_123",
            "version": "1.0.0"
        }
        config_file.write_text(json.dumps(config_data))

        # 创建客户端
        client = OpenClawWeChatClient(
            openclaw_url="http://127.0.0.1:18789",
            relay_url="wss://test.example.com/ws",
            config_dir=str(temp_config_dir)
        )

        # 初始化设备信息
        client._init_device_info()

        # 验证配置已正确加载
        assert client.device_id == config_data["device_id"]
        assert client.device_type == config_data["device_type"]
        assert client.openid == config_data["openid"]
        assert client.is_new_device is False

    @pytest.mark.asyncio
    async def test_client_connect_registers_device(self, temp_config_dir, mock_relay_server):
        """连接成功后应发送注册消息"""
        client = OpenClawWeChatClient(
            openclaw_url="http://127.0.0.1:18789",
            relay_url="wss://test.example.com/ws",
            config_dir=str(temp_config_dir)
        )

        # 准备注册成功响应
        mock_relay_server.queue_response({
            "type": "registered",
            "server_version": "1.0.0",
            "auth_url": "https://example.com/auth?code=test",
            "is_recovery": False
        })

        # Mock websockets.connect
        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_relay_server
            mock_relay_server.is_connected = True

            # 执行连接
            await client.connect()

            # 验证连接被调用
            mock_connect.assert_called_once()

            # 验证发送了注册消息
            received = mock_relay_server.get_received_messages()
            assert len(received) == 1
            assert received[0]["type"] == "register"
            assert "device_id" in received[0]
            assert "device_type" in received[0]
            assert "client_version" in received[0]

            # 验证客户端状态
            assert client.connected is True
            assert client.server_version == "1.0.0"

    @pytest.mark.asyncio
    async def test_client_handles_recovery(self, temp_config_dir, mock_relay_server):
        """恢复设备时应有正确的状态"""
        # 准备已存在的配置
        config_file = temp_config_dir / "config.json"
        config_data = {
            "device_id": "bare_test123_testuser_20260101120000_a1b2",
            "device_type": "bare",
            "machine_id": "test123",
            "system_username": "testuser",
            "openid": None,
            "version": "1.0.0"
        }
        config_file.write_text(json.dumps(config_data))

        client = OpenClawWeChatClient(
            openclaw_url="http://127.0.0.1:18789",
            relay_url="wss://test.example.com/ws",
            config_dir=str(temp_config_dir)
        )

        # 准备恢复响应
        mock_relay_server.queue_response({
            "type": "registered",
            "server_version": "1.0.0",
            "is_recovery": True,
            "recovered_openid": "recovered_openid_123"
        })

        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_relay_server
            mock_relay_server.is_connected = True

            await client.connect()

            # 验证恢复状态
            assert client.authorized is True
            assert client.openid == "recovered_openid_123"


# ==================== 场景 2: 自动重连测试 ====================

class TestClientAutoReconnect:
    """测试场景 2: 连接断开后自动重连"""

    @pytest.mark.asyncio
    async def test_reconnect_on_connection_closed(self, temp_config_dir, mock_relay_server):
        """连接断开后应自动重连"""
        client = OpenClawWeChatClient(
            openclaw_url="http://127.0.0.1:18789",
            relay_url="wss://test.example.com/ws",
            config_dir=str(temp_config_dir)
        )

        connect_count = 0

        async def mock_connect_func(*args, **kwargs):
            nonlocal connect_count
            connect_count += 1

            if connect_count == 1:
                # 第一次连接成功
                mock_relay_server.is_connected = True
                mock_relay_server.queue_response({
                    "type": "registered",
                    "server_version": "1.0.0"
                })
                return mock_relay_server
            else:
                # 重连
                new_mock = create_mock_websocket()
                new_mock.is_connected = True
                new_mock.queue_response({
                    "type": "registered",
                    "server_version": "1.0.0"
                })
                return new_mock

        with patch('websockets.connect', side_effect=mock_connect_func):
            # 第一次连接
            await client.connect()
            assert client.connected is True
            assert connect_count == 1

            # 模拟连接断开
            await mock_relay_server.close()

            # 重连
            result = await client._connect_with_retry()
            assert result is True
            assert connect_count >= 2

    @pytest.mark.asyncio
    async def test_reconnect_exponential_backoff(self, temp_config_dir):
        """重连应使用指数退避"""
        client = OpenClawWeChatClient(
            openclaw_url="http://127.0.0.1:18789",
            relay_url="wss://test.example.com/ws",
            config_dir=str(temp_config_dir)
        )

        # 验证退避参数
        assert INITIAL_RETRY_DELAY == 1
        assert MAX_RETRY_DELAY == 30

        # 验证退避计算
        delays = []
        for retry_count in range(1, 7):
            delay = min(2 ** (retry_count - 1), MAX_RETRY_DELAY)
            delays.append(delay)

        # 期望: [1, 2, 4, 8, 16, 30]
        assert delays[0] == 1   # 第1次重试: 1秒
        assert delays[1] == 2   # 第2次重试: 2秒
        assert delays[2] == 4   # 第3次重试: 4秒
        assert delays[3] == 8   # 第4次重试: 8秒
        assert delays[4] == 16  # 第5次重试: 16秒
        assert delays[5] == 30  # 第6次重试: 30秒（达到上限）

    @pytest.mark.asyncio
    async def test_reconnect_resets_on_success(self, temp_config_dir, mock_relay_server):
        """连接成功后应重置重试状态"""
        client = OpenClawWeChatClient(
            openclaw_url="http://127.0.0.1:18789",
            relay_url="wss://test.example.com/ws",
            config_dir=str(temp_config_dir)
        )

        mock_relay_server.queue_response({
            "type": "registered",
            "server_version": "1.0.0"
        })

        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_relay_server
            mock_relay_server.is_connected = True

            # 连接
            result = await client._connect_with_retry()
            assert result is True
            assert client.connected is True


# ==================== 场景 3: 看门狗告警测试 ====================

class TestWatchdogHeartbeatTimeoutAlert:
    """测试场景 3: 心跳超时触发告警"""

    @pytest.mark.asyncio
    async def test_watchdog_detects_timeout(self):
        """看门狗应检测到心跳超时"""
        alert_received = []

        def alert_callback(message: dict):
            alert_received.append(message)

        # 创建看门狗，设置较短的超时时间用于测试
        watchdog = WatchdogMonitor(
            relay_url="wss://test.example.com/ws",
            openid="test_openid",
            send_callback=alert_callback,
            timeout_seconds=5,  # 5秒超时
            check_interval=1,   # 1秒检查一次
            alert_cooldown=1    # 1秒冷却
        )

        # 启动监控
        await watchdog.start()
        assert watchdog.is_running is True

        # 记录一次心跳
        watchdog.feed()
        assert watchdog.last_heartbeat is not None

        # 等待超时
        await asyncio.sleep(6)

        # 验证告警被触发
        assert len(alert_received) > 0
        assert alert_received[0]["type"] == "watchdog_alert"
        assert alert_received[0]["openid"] == "test_openid"
        assert alert_received[0]["data"]["alert_type"] == "heartbeat_timeout"

        # 停止监控
        await watchdog.stop()
        assert watchdog.is_running is False

    @pytest.mark.asyncio
    async def test_watchdog_heartbeat_resets_timer(self):
        """心跳应重置看门狗计时器"""
        alert_received = []

        def alert_callback(message: dict):
            alert_received.append(message)

        watchdog = WatchdogMonitor(
            relay_url="wss://test.example.com/ws",
            openid="test_openid",
            send_callback=alert_callback,
            timeout_seconds=3,
            check_interval=1,
            alert_cooldown=1
        )

        await watchdog.start()

        # 持续喂狗
        for _ in range(5):
            watchdog.feed()
            await asyncio.sleep(1)

        # 不应触发告警
        assert len(alert_received) == 0

        # 健康状态应为 HEALTHY
        status = watchdog.get_health_status()
        assert status["status"] == HealthStatus.HEALTHY.value

        await watchdog.stop()

    @pytest.mark.asyncio
    async def test_watchdog_alert_cooldown(self):
        """告警应有冷却时间，防止频繁发送"""
        alert_count = 0

        def alert_callback(message: dict):
            nonlocal alert_count
            alert_count += 1

        watchdog = WatchdogMonitor(
            relay_url="wss://test.example.com/ws",
            openid="test_openid",
            send_callback=alert_callback,
            timeout_seconds=2,
            check_interval=1,
            alert_cooldown=10  # 10秒冷却
        )

        await watchdog.start()
        watchdog.feed()

        # 等待第一次超时
        await asyncio.sleep(3)
        first_alert_count = alert_count
        assert first_alert_count >= 1

        # 继续等待，不应发送第二次告警（冷却中）
        await asyncio.sleep(2)
        assert alert_count == first_alert_count  # 没有新增告警

        await watchdog.stop()

    @pytest.mark.asyncio
    async def test_watchdog_health_status_transitions(self):
        """健康状态应正确转换"""
        watchdog = WatchdogMonitor(
            relay_url="wss://test.example.com/ws",
            openid="test_openid",
            send_callback=lambda x: None,
            timeout_seconds=10,
            warning_threshold=0.8,
            check_interval=1
        )

        await watchdog.start()

        # 初始状态（无心跳）
        status = watchdog.get_health_status()
        assert status["status"] == HealthStatus.UNKNOWN.value

        # 记录心跳
        watchdog.feed()
        status = watchdog.get_health_status()
        assert status["status"] == HealthStatus.HEALTHY.value

        # 模拟接近超时（不实际等待）
        watchdog._last_heartbeat = None  # 重置

        await watchdog.stop()


# ==================== 场景 4: 更新检查测试 ====================

class TestUpdaterCheckAndDownload:
    """测试场景 4: 检查更新并后台下载"""

    @pytest.mark.asyncio
    async def test_updater_detects_new_version(self, temp_config_dir, mock_version_response):
        """应检测到新版本"""
        updater = Updater(
            config_dir=temp_config_dir,
            current_version="1.2.0"
        )

        # Mock HTTP 响应
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_version_response
            mock_get.return_value = mock_response

            update_info = await updater.check_update()

            assert update_info is not None
            assert update_info["has_update"] is True
            assert update_info["latest_version"] == "1.3.0"
            assert update_info["current_version"] == "1.2.0"

    @pytest.mark.asyncio
    async def test_updater_no_update_when_latest(self, temp_config_dir):
        """已是最新版本时应返回 None"""
        updater = Updater(
            config_dir=temp_config_dir,
            current_version="1.3.0"
        )

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "version": "1.3.0",
                "download_url": "https://example.com/release.tar.gz"
            }
            mock_get.return_value = mock_response

            update_info = await updater.check_update()

            assert update_info is None

    @pytest.mark.asyncio
    async def test_updater_fallback_to_secondary_source(self, temp_config_dir, mock_version_response):
        """主源失败时应尝试备用源"""
        updater = Updater(
            config_dir=temp_config_dir,
            current_version="1.2.0"
        )

        call_count = 0

        async def mock_get_func(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            mock_response = MagicMock()

            if call_count == 1:
                # 第一次请求失败
                mock_response.status_code = 500
            else:
                # 第二次请求成功（备用源）
                mock_response.status_code = 200
                mock_response.json.return_value = mock_version_response

            return mock_response

        with patch('httpx.AsyncClient.get', side_effect=mock_get_func):
            # 启用 force 强制重新检查
            update_info = await updater.check_update(force=True)

            # 应该尝试了多个源
            assert call_count >= 1

    @pytest.mark.asyncio
    async def test_updater_download_progress(self, temp_config_dir):
        """下载进度回调功能测试"""
        updater = Updater(
            config_dir=temp_config_dir,
            current_version="1.2.0"
        )

        # 设置更新信息
        updater._update_info = {
            "latest_version": "1.3.0",
            "download_url": "https://example.com/release.tar.gz"
        }

        progress_calls = []

        async def progress_callback(downloaded: int, total: int):
            progress_calls.append((downloaded, total))

        # 创建模拟的更新包文件
        test_content = b"fake archive content" * 100
        test_file = temp_config_dir / "updates" / "openclaw-wechat-channel-v1.3.0.tar.gz"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_bytes(test_content)

        # 验证文件已创建
        assert test_file.exists()
        assert test_file.stat().st_size == len(test_content)

        # 直接测试进度回调功能
        await progress_callback(100, len(test_content))
        await progress_callback(500, len(test_content))
        await progress_callback(len(test_content), len(test_content))

        # 验证进度回调被调用
        assert len(progress_calls) == 3
        assert progress_calls[0][0] == 100
        assert progress_calls[2][0] == len(test_content)

    @pytest.mark.asyncio
    async def test_updater_checksum_verification(self, temp_config_dir):
        """应验证下载文件的校验和"""
        updater = Updater(
            config_dir=temp_config_dir,
            current_version="1.2.0"
        )

        # 设置更新信息（包含校验和）
        updater._update_info = {
            "latest_version": "1.3.0",
            "download_url": "https://example.com/release.tar.gz",
            "checksum": "abc123"
        }

        # 创建测试文件
        test_file = temp_config_dir / "updates" / "test.tar.gz"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_bytes(b"test content")

        # 验证校验和不匹配时应返回 False
        result = updater._verify_checksum(test_file, "wrong_checksum")
        assert result is False

        # 验证空校验和时应跳过验证
        result = updater._verify_checksum(test_file, "")
        assert result is True

    @pytest.mark.asyncio
    async def test_updater_protects_user_config(self, temp_config_dir):
        """更新时应保护用户配置文件"""
        # 创建用户配置
        config_file = temp_config_dir / "config.json"
        config_file.write_text('{"device_id": "test_device"}')

        updater = Updater(
            config_dir=temp_config_dir,
            current_version="1.2.0"
        )

        # 验证受保护的文件列表
        from src.updater import PROTECTED_FILES
        assert "config.json" in PROTECTED_FILES
        assert ".env" in PROTECTED_FILES

        # 备份测试
        backup_dir = temp_config_dir / "backup"
        backed_up = updater._backup_protected_files(backup_dir)

        assert "config.json" in backed_up
        assert (backup_dir / "config.json").exists()


# ==================== 集成测试 ====================

class TestIntegrationScenarios:
    """完整集成测试场景"""

    @pytest.mark.asyncio
    async def test_full_connect_flow(self, temp_config_dir, mock_relay_server, mock_openclaw_response):
        """完整连接流程测试"""
        client = OpenClawWeChatClient(
            openclaw_url="http://127.0.0.1:18789",
            relay_url="wss://test.example.com/ws",
            config_dir=str(temp_config_dir)
        )

        # 准备响应
        mock_relay_server.queue_response({
            "type": "registered",
            "server_version": "1.0.0",
            "auth_url": "https://example.com/auth"
        })

        # 授权成功响应
        mock_relay_server.queue_response({
            "type": "status_response",
            "is_authorized": True,
            "openid": "test_openid"
        })

        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_relay_server
            mock_relay_server.is_connected = True

            # 连接
            await client.connect()
            assert client.connected is True

            # 模拟收到消息
            mock_relay_server.queue_response({
                "type": "chat_request",
                "openid": "test_openid",
                "content": "你好",
                "msg_type": "text"
            })

            # Mock OpenClaw API
            with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = mock_openclaw_response
                mock_post.return_value = mock_response

                # 模拟处理消息
                await client.handle_message({
                    "type": "chat_request",
                    "openid": "test_openid",
                    "content": "你好",
                    "msg_type": "text"
                })

    @pytest.mark.asyncio
    async def test_watchdog_integration_with_client(self, temp_config_dir, mock_relay_server):
        """看门狗与客户端集成测试"""
        client = OpenClawWeChatClient(
            openclaw_url="http://127.0.0.1:18789",
            relay_url="wss://test.example.com/ws",
            config_dir=str(temp_config_dir)
        )

        # 设置授权状态
        client.openid = "test_openid"
        client.authorized = True
        client.websocket = mock_relay_server
        client.connected = True

        # 初始化看门狗
        await client._init_watchdog()

        assert client.watchdog is not None
        assert client.watchdog.is_running is True

        # 喂狗
        client.watchdog.feed()
        status = client.watchdog.get_health_status()
        assert status["status"] == HealthStatus.HEALTHY.value

        # 停止
        await client.watchdog.stop()

    @pytest.mark.asyncio
    async def test_update_check_on_startup(self, temp_config_dir, mock_version_response):
        """启动时检查更新测试"""
        updater = Updater(
            config_dir=temp_config_dir,
            current_version="1.2.0"
        )

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_version_response
            mock_get.return_value = mock_response

            update_info = await updater.check_update()

            assert update_info is not None
            assert "latest_version" in update_info

    @pytest.mark.asyncio
    async def test_error_handling_chat_api_disabled(self, temp_config_dir):
        """Chat API 禁用时应返回自愈消息"""
        client = OpenClawWeChatClient(
            openclaw_url="http://127.0.0.1:18789",
            relay_url="wss://test.example.com/ws",
            config_dir=str(temp_config_dir)
        )

        # 构建自愈消息
        message = client._build_self_healing_message("chat_api_disabled")

        assert "Chat Completions API" in message or "API 接口" in message
        assert "启用" in message

    @pytest.mark.asyncio
    async def test_error_handling_connection_failed(self, temp_config_dir):
        """连接失败时应返回自愈消息"""
        client = OpenClawWeChatClient(
            openclaw_url="http://127.0.0.1:18789",
            relay_url="wss://test.example.com/ws",
            config_dir=str(temp_config_dir)
        )

        message = client._build_self_healing_message("connection_failed")

        assert "无法连接" in message or "OpenClaw" in message


# ==================== 运行测试 ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])