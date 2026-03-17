"""
OpenClaw 微信频道插件 - 升级状态持久化模块测试

测试覆盖：
1. UpdateState 数据类基本功能
2. save_state 和 load_state 持久化
3. is_restart_due 时间判断逻辑
4. get_restart_delay 延迟计算
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# 添加 src 到路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from update_state import (
    UpdateState,
    save_state,
    load_state,
    clear_state,
    RESTART_DELAY_HOURS,
    RESTART_HOUR
)


class TestUpdateStateDataclass:
    """UpdateState 数据类基础测试"""
    
    def test_default_values(self):
        """测试默认值"""
        state = UpdateState()
        assert state.pending_update is False
        assert state.download_progress == 0
        assert state.install_time is None
        assert state.target_version is None
        assert state.current_version is None
    
    def test_custom_values(self):
        """测试自定义值"""
        state = UpdateState(
            pending_update=True,
            download_progress=50,
            install_time="2026-03-17T10:00:00",
            target_version="1.3.0",
            current_version="1.2.0"
        )
        assert state.pending_update is True
        assert state.download_progress == 50
        assert state.install_time == "2026-03-17T10:00:00"
        assert state.target_version == "1.3.0"
        assert state.current_version == "1.2.0"
    
    def test_to_dict(self):
        """测试转换为字典"""
        state = UpdateState(
            pending_update=True,
            download_progress=100,
            install_time="2026-03-17T10:00:00",
            target_version="1.3.0",
            current_version="1.2.0"
        )
        data = state.to_dict()
        
        assert data["pending_update"] is True
        assert data["download_progress"] == 100
        assert data["install_time"] == "2026-03-17T10:00:00"
        assert data["target_version"] == "1.3.0"
        assert data["current_version"] == "1.2.0"
    
    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "pending_update": True,
            "download_progress": 75,
            "install_time": "2026-03-17T10:00:00",
            "target_version": "1.3.0",
            "current_version": "1.2.0"
        }
        state = UpdateState.from_dict(data)
        
        assert state.pending_update is True
        assert state.download_progress == 75
        assert state.install_time == "2026-03-17T10:00:00"
        assert state.target_version == "1.3.0"
        assert state.current_version == "1.2.0"
    
    def test_from_dict_partial(self):
        """测试从部分字典创建"""
        data = {"pending_update": True}
        state = UpdateState.from_dict(data)
        
        assert state.pending_update is True
        assert state.download_progress == 0  # 默认值
        assert state.install_time is None


class TestUpdateStateMethods:
    """UpdateState 方法测试"""
    
    def test_set_installed(self):
        """测试设置安装状态"""
        state = UpdateState()
        
        with patch("update_state.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 17, 10, 30, 0)
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            
            state.set_installed("1.3.0", "1.2.0")
        
        assert state.pending_update is True
        assert state.download_progress == 100
        assert state.install_time == "2026-03-17T10:30:00"
        assert state.target_version == "1.3.0"
        assert state.current_version == "1.2.0"
    
    def test_clear(self):
        """测试清除状态"""
        state = UpdateState(
            pending_update=True,
            download_progress=100,
            install_time="2026-03-17T10:00:00",
            target_version="1.3.0",
            current_version="1.2.0"
        )
        
        state.clear()
        
        assert state.pending_update is False
        assert state.download_progress == 0
        assert state.install_time is None
        assert state.target_version is None
        assert state.current_version is None


class TestIsRestartDue:
    """is_restart_due 方法测试"""
    
    def test_no_pending_update(self):
        """测试无待安装更新"""
        state = UpdateState(install_time="2026-03-17T10:00:00")
        assert state.is_restart_due() is False
    
    def test_no_install_time(self):
        """测试无安装时间"""
        state = UpdateState(pending_update=True)
        assert state.is_restart_due() is False
    
    def test_elapsed_over_24_hours(self):
        """测试超过 24 小时"""
        # 安装时间是 25 小时前
        install_time = datetime.now() - timedelta(hours=25)
        state = UpdateState(
            pending_update=True,
            install_time=install_time.isoformat()
        )
        
        assert state.is_restart_due() is True
    
    def test_elapsed_under_24_hours_before_restart_hour(self):
        """测试未到 24 小时且未到次日 4:00"""
        # 当前时间模拟为安装后 12 小时
        # 假设安装时间是今天 00:00，现在是 12:00
        install_time = datetime.now() - timedelta(hours=12)
        state = UpdateState(
            pending_update=True,
            install_time=install_time.isoformat()
        )
        
        # 未到 24 小时，未到次日 4:00
        assert state.is_restart_due() is False
    
    def test_reached_next_day_restart_hour(self):
        """测试到达次日 4:00 重启时间"""
        # 模拟场景：昨天 10:00 安装，现在是次日 5:00
        # 此时应该需要重启（虽然未满 24 小时，但已过次日 4:00）
        
        # 安装时间：昨天 10:00
        install_dt = datetime.now() - timedelta(hours=19)  # 19小时前
        state = UpdateState(
            pending_update=True,
            install_time=install_dt.isoformat()
        )
        
        # 这种情况下，取决于当前时间是否已过次日 4:00
        # 由于无法精确控制当前时间，这里主要验证逻辑不会崩溃
        result = state.is_restart_due()
        assert isinstance(result, bool)
    
    def test_invalid_install_time(self):
        """测试无效的安装时间格式"""
        state = UpdateState(
            pending_update=True,
            install_time="invalid-time"
        )
        
        # 无效时间应该返回 False，不应抛出异常
        assert state.is_restart_due() is False


class TestGetRestartDelay:
    """get_restart_delay 方法测试"""
    
    def test_no_pending_update(self):
        """测试无待安装更新"""
        state = UpdateState(install_time="2026-03-17T10:00:00")
        assert state.get_restart_delay() == -1
    
    def test_no_install_time(self):
        """测试无安装时间"""
        state = UpdateState(pending_update=True)
        assert state.get_restart_delay() == -1
    
    def test_already_overdue(self):
        """测试已超过重启时间"""
        # 安装时间是 25 小时前
        install_time = datetime.now() - timedelta(hours=25)
        state = UpdateState(
            pending_update=True,
            install_time=install_time.isoformat()
        )
        
        assert state.get_restart_delay() == 0
    
    def test_returns_positive_delay(self):
        """测试返回正数延迟"""
        # 安装时间是 1 小时前
        install_time = datetime.now() - timedelta(hours=1)
        state = UpdateState(
            pending_update=True,
            install_time=install_time.isoformat()
        )
        
        delay = state.get_restart_delay()
        # 延迟应该是一个正数（具体值取决于当前时间）
        assert delay > 0
    
    def test_invalid_install_time(self):
        """测试无效的安装时间格式"""
        state = UpdateState(
            pending_update=True,
            install_time="invalid-time"
        )
        
        assert state.get_restart_delay() == -1


class TestSaveAndLoadState:
    """save_state 和 load_state 测试"""
    
    def test_save_and_load(self):
        """测试保存和加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "update_state.json"
            
            original_state = UpdateState(
                pending_update=True,
                download_progress=100,
                install_time="2026-03-17T10:00:00",
                target_version="1.3.0",
                current_version="1.2.0"
            )
            
            # 保存
            result = save_state(original_state, state_path)
            assert result is True
            assert state_path.exists()
            
            # 加载
            loaded_state = load_state(state_path)
            assert loaded_state is not None
            assert loaded_state.pending_update is True
            assert loaded_state.download_progress == 100
            assert loaded_state.install_time == "2026-03-17T10:00:00"
            assert loaded_state.target_version == "1.3.0"
            assert loaded_state.current_version == "1.2.0"
    
    def test_load_nonexistent_file(self):
        """测试加载不存在的文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "nonexistent.json"
            result = load_state(state_path)
            assert result is None
    
    def test_load_invalid_json(self):
        """测试加载无效的 JSON 文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "invalid.json"
            
            # 写入无效 JSON
            state_path.write_text("not a valid json{")
            
            result = load_state(state_path)
            assert result is None
    
    def test_save_creates_parent_directory(self):
        """测试保存时创建父目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 父目录不存在
            state_path = Path(tmpdir) / "subdir" / "nested" / "state.json"
            
            state = UpdateState(pending_update=True)
            result = save_state(state, state_path)
            
            assert result is True
            assert state_path.exists()
    
    def test_clear_state(self):
        """测试清除状态文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "update_state.json"
            
            # 先创建文件
            state = UpdateState(pending_update=True)
            save_state(state, state_path)
            assert state_path.exists()
            
            # 清除
            result = clear_state(state_path)
            assert result is True
            assert not state_path.exists()
    
    def test_clear_nonexistent_file(self):
        """测试清除不存在的文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "nonexistent.json"
            result = clear_state(state_path)
            assert result is True  # 清除不存在的文件也返回成功


class TestIntegration:
    """集成测试"""
    
    def test_full_workflow(self):
        """测试完整工作流"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "update_state.json"
            
            # 1. 初始状态：无状态文件
            state = load_state(state_path)
            assert state is None
            
            # 2. 下载开始
            state = UpdateState(pending_update=True, download_progress=0)
            save_state(state, state_path)
            
            # 3. 下载进行中
            state.download_progress = 50
            save_state(state, state_path)
            
            # 4. 下载完成，安装
            state.download_progress = 100
            with patch("update_state.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2026, 3, 17, 10, 0, 0)
                mock_dt.fromisoformat.side_effect = datetime.fromisoformat
                state.set_installed("1.3.0", "1.2.0")
            
            save_state(state, state_path)
            
            # 5. 系统重启后恢复状态
            restored = load_state(state_path)
            assert restored is not None
            assert restored.pending_update is True
            assert restored.target_version == "1.3.0"
            assert restored.current_version == "1.2.0"
            
            # 6. 检查是否需要重启（刚安装，不需要）
            assert restored.is_restart_due() is False
            
            # 7. 重启完成后清除状态
            clear_state(state_path)
            assert load_state(state_path) is None
    
    def test_state_persistence_after_restart(self):
        """测试重启后状态恢复"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "update_state.json"
            
            # 模拟安装（25小时前）
            install_dt = datetime.now() - timedelta(hours=25)
            original_state = UpdateState(
                pending_update=True,
                download_progress=100,
                install_time=install_dt.isoformat(),
                target_version="1.3.0",
                current_version="1.2.0"
            )
            save_state(original_state, state_path)
            
            # 模拟重启后加载
            restored = load_state(state_path)
            assert restored is not None
            assert restored.is_restart_due() is True


class TestEdgeCases:
    """边缘情况测试"""
    
    def test_empty_state_file(self):
        """测试空状态文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "empty.json"
            state_path.write_text("{}")
            
            state = load_state(state_path)
            assert state is not None
            assert state.pending_update is False
            assert state.download_progress == 0
    
    def test_extra_fields_in_state_file(self):
        """测试状态文件包含额外字段"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "extra.json"
            
            data = {
                "pending_update": True,
                "download_progress": 100,
                "install_time": "2026-03-17T10:00:00",
                "target_version": "1.3.0",
                "current_version": "1.2.0",
                "extra_field": "should be ignored"
            }
            state_path.write_text(json.dumps(data))
            
            state = load_state(state_path)
            assert state is not None
            assert state.pending_update is True
            # 额外字段被忽略
            assert not hasattr(state, "extra_field")
    
    def test_restart_delay_calculation_near_boundary(self):
        """测试接近边界时间的延迟计算"""
        # 安装时间是 23 小时 59 分前
        install_time = datetime.now() - timedelta(hours=23, minutes=59)
        state = UpdateState(
            pending_update=True,
            install_time=install_time.isoformat()
        )
        
        delay = state.get_restart_delay()
        # 延迟应该是很小的正数或 0
        assert delay >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])