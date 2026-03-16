"""
OpenClaw 微信频道插件 - pytest 配置和 fixtures

提供测试所需的基础设施，保持简单，避免复杂依赖。
"""
import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环，用于异步测试"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_websocket():
    """模拟 WebSocket 连接"""
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock()
    ws.close = AsyncMock()
    ws.ping = AsyncMock()
    return ws


@pytest.fixture
def mock_openclaw_response():
    """模拟 OpenClaw API 响应"""
    return {
        "success": True,
        "message": "测试响应",
        "conversation_id": "test-conv-123"
    }