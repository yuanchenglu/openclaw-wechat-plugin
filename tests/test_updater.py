"""
OpenClaw 微信频道插件 - 更新模块测试
"""

import asyncio
import json
import os
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# 添加 src 到路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from updater import Updater, check_for_updates, perform_update


class TestUpdaterVersionCompare:
    """版本比较测试"""
    
    def test_compare_equal_versions(self):
        """测试相等版本"""
        updater = Updater()
        assert updater.compare_versions("1.0.0", "1.0.0") == 0
        assert updater.compare_versions("2.3.4", "2.3.4") == 0
    
    def test_compare_older_versions(self):
        """测试旧版本"""
        updater = Updater()
        assert updater.compare_versions("1.0.0", "2.0.0") == -1
        assert updater.compare_versions("1.0.0", "1.1.0") == -1
        assert updater.compare_versions("1.0.0", "1.0.1") == -1
    
    def test_compare_newer_versions(self):
        """测试新版本"""
        updater = Updater()
        assert updater.compare_versions("2.0.0", "1.0.0") == 1
        assert updater.compare_versions("1.1.0", "1.0.0") == 1
        assert updater.compare_versions("1.0.1", "1.0.0") == 1
    
    def test_compare_invalid_versions(self):
        """测试无效版本"""
        updater = Updater()
        # 无效版本应返回 0（相等）
        assert updater.compare_versions("invalid", "1.0.0") == 0
        assert updater.compare_versions("1.0.0", None) == 0


class TestUpdaterCheckUpdate:
    """更新检查测试"""
    
    @pytest.mark.asyncio
    async def test_no_update_available(self):
        """测试无更新"""
        with tempfile.TemporaryDirectory() as tmpdir:
            updater = Updater(
                config_dir=Path(tmpdir),
                current_version="99.0.0"  # 模拟已经是最新版本
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
                
                result = await updater.check_update()
                assert result is None  # 无更新
    
    @pytest.mark.asyncio
    async def test_update_available(self):
        """测试有更新"""
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
                    "download_url": "https://example.com/update.tar.gz",
                    "changelog": ["新功能1", "新功能2"]
                }
                
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )
                
                result = await updater.check_update()
                assert result is not None
                assert result["has_update"] is True
                assert result["latest_version"] == "1.3.0"
                assert result["current_version"] == "1.0.0"
    
    @pytest.mark.asyncio
    async def test_update_check_network_error(self):
        """测试网络错误"""
        with tempfile.TemporaryDirectory() as tmpdir:
            updater = Updater(
                config_dir=Path(tmpdir),
                current_version="1.0.0"
            )
            
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    side_effect=Exception("Network error")
                )
                
                result = await updater.check_update()
                assert result is None  # 网络错误返回 None


class TestUpdaterDownload:
    """下载测试"""
    
    @pytest.mark.asyncio
    async def test_download_without_check(self):
        """测试未检查直接下载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            updater = Updater(
                config_dir=Path(tmpdir),
                current_version="1.0.0"
            )
            
            result = await updater.download_update()
            assert result is None  # 未检查更新，无法下载


class TestUpdaterInstall:
    """安装测试"""
    
    def test_backup_protected_files(self):
        """测试备份保护文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir()
            
            # 创建测试配置文件
            config_file = config_dir / "config.json"
            config_file.write_text('{"test": "value"}')
            
            updater = Updater(config_dir=config_dir)
            backup_dir = Path(tmpdir) / "backup"
            
            backed_up = updater._backup_protected_files(backup_dir)
            
            assert "config.json" in backed_up
            assert (backup_dir / "config.json").exists()
    
    def test_restore_protected_files(self):
        """测试恢复配置文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir()
            backup_dir = Path(tmpdir) / "backup"
            backup_dir.mkdir()
            
            # 创建备份文件
            backup_file = backup_dir / "config.json"
            backup_file.write_text('{"restored": true}')
            
            updater = Updater(config_dir=config_dir)
            updater._restore_protected_files(
                backup_dir,
                {"config.json": str(backup_file)}
            )
            
            restored_file = config_dir / "config.json"
            assert restored_file.exists()
            assert json.loads(restored_file.read_text()) == {"restored": True}
    
    def test_protected_files_not_overwritten(self):
        """测试保护文件不被覆盖"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir()
            
            # 创建原始配置
            config_file = config_dir / "config.json"
            original_content = '{"original": true}'
            config_file.write_text(original_content)
            
            # 创建更新包
            update_dir = Path(tmpdir) / "update"
            update_dir.mkdir()
            (update_dir / "client.py").write_text("# new client")
            (update_dir / "config.json").write_text('{"new": true}')  # 应该被忽略
            
            # 创建 tar.gz
            archive_path = Path(tmpdir) / "update.tar.gz"
            with tarfile.open(archive_path, "w:gz") as tar:
                for item in update_dir.iterdir():
                    tar.add(item, arcname=item.name)
            
            updater = Updater(config_dir=config_dir)
            
            # 运行 asyncio 安装
            async def run_install():
                return await updater.install_update(archive_path)
            
            success = asyncio.run(run_install())
            
            # 配置文件应保持原样
            assert config_file.read_text() == original_content
            # 新文件应被安装
            assert (config_dir / "client.py").exists()


class TestUpdaterCleanup:
    """清理测试"""
    
    def test_cleanup_downloaded_file(self):
        """测试清理下载文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir()
            update_dir = Path(tmpdir) / "updates"
            update_dir.mkdir()
            
            # 创建模拟下载文件
            downloaded_file = update_dir / "test.tar.gz"
            downloaded_file.write_text("fake archive")
            
            updater = Updater(config_dir=config_dir, update_dir=update_dir)
            updater._downloaded_file = downloaded_file
            
            updater.cleanup()
            
            assert not downloaded_file.exists()
            assert updater._downloaded_file is None
    
    def test_cleanup_old_updates(self):
        """测试清理旧更新包"""
        with tempfile.TemporaryDirectory() as tmpdir:
            update_dir = Path(tmpdir) / "updates"
            update_dir.mkdir()
            
            # 创建多个模拟更新包
            for i in range(5):
                archive = update_dir / f"openclaw-wechat-channel-v1.{i}.0.tar.gz"
                archive.write_text(f"version 1.{i}.0")
            
            updater = Updater(update_dir=update_dir)
            updater.cleanup_old_updates(keep_latest=2)
            
            archives = list(update_dir.glob("openclaw-wechat-channel-*.tar.gz"))
            assert len(archives) == 2


class TestUpdaterChecksum:
    """校验和测试"""
    
    def test_verify_checksum_valid(self):
        """测试有效校验和"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")
            
            # 计算 SHA256
            import hashlib
            sha256 = hashlib.sha256(b"test content").hexdigest()
            
            updater = Updater()
            result = updater._verify_checksum(test_file, sha256)
            
            assert result is True
    
    def test_verify_checksum_invalid(self):
        """测试无效校验和"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")
            
            updater = Updater()
            result = updater._verify_checksum(test_file, "invalid_checksum")
            
            assert result is False
    
    def test_verify_checksum_skip_placeholder(self):
        """测试跳过占位符校验和"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")
            
            updater = Updater()
            result = updater._verify_checksum(test_file, "待发布时计算")
            
            assert result is True  # 应跳过


class TestUpdaterRestart:
    """重启测试"""
    
    def test_get_restart_command_linux(self):
        """测试 Linux 重启命令"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir()
            
            updater = Updater(config_dir=config_dir)
            
            with patch("platform.system", return_value="Linux"):
                with patch.object(updater, "_is_systemd_service", return_value=False):
                    cmd = updater.get_restart_command()
                    assert "stop.sh" in cmd
                    assert "start.sh" in cmd
    
    def test_get_restart_command_macos(self):
        """测试 macOS 重启命令"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir()
            
            updater = Updater(config_dir=config_dir)
            
            with patch("platform.system", return_value="Darwin"):
                with patch.object(updater, "_is_launchd_service", return_value=False):
                    cmd = updater.get_restart_command()
                    assert "stop.sh" in cmd
                    assert "start.sh" in cmd


class TestConvenienceFunctions:
    """便捷函数测试"""
    
    @pytest.mark.asyncio
    async def test_check_for_updates(self):
        """测试检查更新便捷函数"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "version": "99.0.0",  # 更高版本
                "download_url": "https://example.com/update.tar.gz"
            }
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            result = await check_for_updates("1.0.0")
            assert result is not None
            assert result["has_update"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])