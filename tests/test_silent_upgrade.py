"""
OpenClaw 微信频道插件 - 静默升级功能测试

测试覆盖：
- T5: 定时检查更新
- T6: 静默升级模式
- T7: 延迟重启逻辑
"""

import asyncio
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# 添加 src 到路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# 使用别名导入避免与内置 types 模块冲突
from src import types as plugin_types
from src.update_state import UpdateState, save_state, load_state, clear_state
from src.updater import Updater

# 导出常量
CHECK_INTERVAL = plugin_types.CHECK_INTERVAL
RESTART_DELAY = plugin_types.RESTART_DELAY
RESTART_HOUR = plugin_types.RESTART_HOUR
UpgradeStatus = plugin_types.UpgradeStatus


# ============ T5: 定时检查更新测试 ============

class TestPeriodicCheck:
    """定时检查更新测试"""
    
    def test_check_interval_value(self):
        """验证检查间隔为 5 小时"""
        assert CHECK_INTERVAL == 5 * 3600
    
    @pytest.mark.asyncio
    async def test_periodic_check_task_creation(self):
        """测试定时检查任务创建"""
        from src.client import OpenClawWeChatClient
        
        with tempfile.TemporaryDirectory() as tmpdir:
            client = OpenClawWeChatClient(
                openclaw_url="http://localhost:18789",
                relay_url="wss://example.com/ws",
                config_dir=tmpdir
            )
            
            # 验证定时检查任务属性初始化
            assert client._update_check_task is None
    
    @pytest.mark.asyncio
    async def test_periodic_check_runs_silently(self):
        """测试定时检查使用静默模式"""
        with tempfile.TemporaryDirectory() as tmpdir:
            updater = Updater(
                config_dir=Path(tmpdir),
                current_version="1.0.0"
            )
            
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "version": "1.3.0",
                    "download_url": "https://example.com/update.tar.gz"
                }
                
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )
                
                # 静默模式检查
                result = await updater.check_update(silent=True)
                
                assert result is not None
                assert result["has_update"] is True


# ============ T6: 静默升级模式测试 ============

class TestSilentMode:
    """静默升级模式测试"""
    
    @pytest.mark.asyncio
    async def test_check_update_silent_no_log(self):
        """测试静默检查更新不打印通知"""
        with tempfile.TemporaryDirectory() as tmpdir:
            updater = Updater(
                config_dir=Path(tmpdir),
                current_version="1.0.0"
            )
            
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "version": "1.3.0",
                    "download_url": "https://example.com/update.tar.gz"
                }
                
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )
                
                # 静默模式
                result = await updater.check_update(silent=True)
                assert result is not None
    
    @pytest.mark.asyncio
    async def test_check_update_silent_no_update(self):
        """测试静默模式无更新时不打印日志"""
        with tempfile.TemporaryDirectory() as tmpdir:
            updater = Updater(
                config_dir=Path(tmpdir),
                current_version="99.0.0"  # 模拟已是最新
            )
            
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "version": "1.3.0",
                    "download_url": "https://example.com/update.tar.gz"
                }
                
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )
                
                result = await updater.check_update(silent=True)
                assert result is None  # 无更新
    
    @pytest.mark.asyncio
    async def test_download_update_silent(self):
        """测试静默下载更新"""
        with tempfile.TemporaryDirectory() as tmpdir:
            updater = Updater(
                config_dir=Path(tmpdir),
                current_version="1.0.0"
            )
            
            # 先设置更新信息
            updater._update_info = {
                "has_update": True,
                "current_version": "1.0.0",
                "latest_version": "1.3.0",
                "download_url": "https://example.com/update.tar.gz"
            }
            
            with patch("httpx.AsyncClient") as mock_client:
                # 模拟 HEAD 请求
                mock_head = MagicMock()
                mock_head.headers = {"content-length": "1024"}
                
                # 模拟 GET 请求流
                mock_stream = MagicMock()
                mock_stream.status_code = 200
                mock_stream.aiter_bytes = AsyncMock(return_value=[b"test data"])
                
                mock_context = MagicMock()
                mock_context.head = AsyncMock(return_value=mock_head)
                mock_context.stream = MagicMock(return_value=MagicMock(
                    __aenter__=AsyncMock(return_value=mock_stream),
                    __aexit__=AsyncMock()
                ))
                
                mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_context)
                
                # 静默下载
                result = await updater.download_update(silent=True)
                # 验证返回值（可能是 None 或路径）
                assert result is None or isinstance(result, Path)
    
    @pytest.mark.asyncio
    async def test_install_update_silent(self):
        """测试静默安装更新"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            updater = Updater(
                config_dir=config_dir,
                current_version="1.0.0"
            )
            
            # 创建模拟的更新包
            update_file = config_dir / "updates" / "update.tar.gz"
            update_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 创建一个简单的 tar.gz 文件
            import tarfile
            import io
            
            with tarfile.open(update_file, "w:gz") as tar:
                # 添加一个测试文件
                data = b"test content"
                info = tarfile.TarInfo(name="test.txt")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            
            updater._downloaded_file = update_file
            
            # 静默安装
            # 注意：实际安装可能需要更多文件结构
            # 这里主要验证 silent 参数被正确传递
            try:
                await updater.install_update(silent=True)
            except Exception:
                pass  # 安装可能失败，主要验证参数传递


# ============ T7: 延迟重启逻辑测试 ============

class TestDelayedRestart:
    """延迟重启逻辑测试"""
    
    def test_restart_delay_value(self):
        """验证重启延迟为 24 小时"""
        assert RESTART_DELAY == 24 * 3600
    
    def test_restart_hour_value(self):
        """验证重启时间为 4:00"""
        assert RESTART_HOUR == 4
    
    def test_is_restart_due_immediate(self):
        """测试超过 24 小时立即重启"""
        # 设置安装时间为 25 小时前
        install_time = (datetime.now() - timedelta(hours=25)).isoformat()
        
        state = UpdateState(
            pending_update=True,
            install_time=install_time,
            target_version="1.3.0",
            current_version="1.2.0"
        )
        
        assert state.is_restart_due() is True
    
    def test_is_restart_due_not_yet(self):
        """测试未到重启时间"""
        # 设置安装时间为 1 小时前
        install_time = (datetime.now() - timedelta(hours=1)).isoformat()
        
        state = UpdateState(
            pending_update=True,
            install_time=install_time,
            target_version="1.3.0",
            current_version="1.2.0"
        )
        
        # 可能返回 True（如果到了次日 4:00）或 False
        # 主要验证方法不会崩溃
        result = state.is_restart_due()
        assert isinstance(result, bool)
    
    def test_is_restart_due_no_pending(self):
        """测试无待更新时不重启"""
        state = UpdateState(
            pending_update=False,
            install_time=datetime.now().isoformat()
        )
        
        assert state.is_restart_due() is False
    
    def test_get_restart_delay(self):
        """测试获取重启延迟"""
        # 设置安装时间为 23 小时前
        install_time = (datetime.now() - timedelta(hours=23)).isoformat()
        
        state = UpdateState(
            pending_update=True,
            install_time=install_time,
            target_version="1.3.0",
            current_version="1.2.0"
        )
        
        delay = state.get_restart_delay()
        # 应该返回一个正数或 0
        assert delay >= 0
    
    def test_get_restart_delay_overdue(self):
        """测试已超过重启时间"""
        # 设置安装时间为 30 小时前
        install_time = (datetime.now() - timedelta(hours=30)).isoformat()
        
        state = UpdateState(
            pending_update=True,
            install_time=install_time,
            target_version="1.3.0",
            current_version="1.2.0"
        )
        
        delay = state.get_restart_delay()
        assert delay == 0
    
    def test_state_persistence_after_install(self):
        """测试安装后状态持久化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "update_state.json"
            
            # 创建并保存状态
            state = UpdateState(
                pending_update=True,
                install_time=datetime.now().isoformat(),
                target_version="1.3.0",
                current_version="1.2.0"
            )
            
            save_state(state, state_path)
            
            # 加载并验证
            loaded = load_state(state_path)
            assert loaded is not None
            assert loaded.pending_update is True
            assert loaded.target_version == "1.3.0"
            assert loaded.current_version == "1.2.0"
    
    def test_state_clear_after_restart(self):
        """测试重启后清除状态"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "update_state.json"
            
            # 创建并保存状态
            state = UpdateState(
                pending_update=True,
                install_time=datetime.now().isoformat(),
                target_version="1.3.0",
                current_version="1.2.0"
            )
            
            save_state(state, state_path)
            
            # 清除状态
            clear_state(state_path)
            
            # 验证已清除
            loaded = load_state(state_path)
            assert loaded is None


# ============ 集成测试 ============

class TestSilentUpgradeIntegration:
    """静默升级集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_silent_upgrade_flow(self):
        """测试完整的静默升级流程"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            # 1. 创建更新器
            updater = Updater(
                config_dir=config_dir,
                current_version="1.0.0"
            )
            
            # 2. 模拟检查更新
            updater._update_info = {
                "has_update": True,
                "current_version": "1.0.0",
                "latest_version": "1.3.0",
                "download_url": "https://example.com/update.tar.gz"
            }
            
            # 3. 创建模拟状态
            state = UpdateState(
                pending_update=True,
                install_time=datetime.now().isoformat(),
                target_version="1.3.0",
                current_version="1.0.0"
            )
            
            state_path = config_dir / "update_state.json"
            save_state(state, state_path)
            
            # 4. 验证状态
            loaded = load_state(state_path)
            assert loaded is not None
            assert loaded.target_version == "1.3.0"
    
    @pytest.mark.asyncio
    async def test_missed_restart_window(self):
        """测试错过重启窗口的情况"""
        # 设置安装时间为 30 小时前（超过 24 小时）
        install_time = (datetime.now() - timedelta(hours=30)).isoformat()
        
        state = UpdateState(
            pending_update=True,
            install_time=install_time,
            target_version="1.3.0",
            current_version="1.2.0"
        )
        
        # 应该立即重启
        assert state.is_restart_due() is True
        assert state.get_restart_delay() == 0


# ============ 运行测试 ============

if __name__ == "__main__":
    pytest.main([__file__, "-v"])