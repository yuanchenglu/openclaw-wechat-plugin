"""
OpenClaw 微信频道插件 - 自动更新模块

功能：
1. 版本检查：从服务器获取最新版本信息
2. 下载更新：三级容错下载（R2 CDN → GitHub → ECS）
3. 安装更新：解压覆盖，保留用户配置
4. 自动重启：通过 systemd/launchd 重启服务

使用方法：
    from updater import Updater
    
    updater = Updater()
    if await updater.check_update():
        await updater.download_and_install()
"""

import asyncio
import hashlib
import httpx
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime

# 配置日志
logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_CONFIG_DIR = Path.home() / ".openclaw" / "wechat-channel"
DEFAULT_UPDATE_DIR = DEFAULT_CONFIG_DIR / "updates"
DEFAULT_VERSION_URL = "https://claw.7color.vip/channel-update/version.json"

# 下载源列表（按优先级排序）
DOWNLOAD_SOURCES = [
    {
        "name": "R2 CDN",
        "base_url": "https://wechat.clawadmin.org/release",
        "version_url": "https://wechat.clawadmin.org/release/version.json"
    },
    {
        "name": "GitHub",
        "base_url": "https://github.com/yuanchenglu/openclaw-wechat-plugin/releases/download",
        "version_url": "https://raw.githubusercontent.com/yuanchenglu/openclaw-wechat-plugin/main/release/version.json"
    },
    {
        "name": "ECS",
        "base_url": "https://claw-wechat.7color.vip/release",
        "version_url": "https://claw-wechat.7color.vip/release/version.json"
    }
]

# 需要保留的用户配置文件
PROTECTED_FILES = [
    "config.json",
    "device_id.json",
    ".env",
]


class Updater:
    """自动更新管理器"""
    
    def __init__(
        self,
        config_dir: Optional[Path] = None,
        update_dir: Optional[Path] = None,
        current_version: str = "0.0.0"
    ):
        """
        初始化更新器
        
        Args:
            config_dir: 配置目录，默认 ~/.openclaw/wechat-channel/
            update_dir: 更新下载目录，默认 ~/.openclaw/wechat-channel/updates/
            current_version: 当前版本号
        """
        self.config_dir = config_dir or DEFAULT_CONFIG_DIR
        self.update_dir = update_dir or DEFAULT_UPDATE_DIR
        self.current_version = current_version
        
        # 确保目录存在
        self.update_dir.mkdir(parents=True, exist_ok=True)
        
        # 更新信息缓存
        self._update_info: Optional[dict] = None
        self._downloaded_file: Optional[Path] = None
    
    def compare_versions(self, v1: str, v2: str) -> int:
        """
        比较版本号
        
        Args:
            v1: 版本1
            v2: 版本2
            
        Returns:
            -1: v1 < v2
            0: v1 == v2
            1: v1 > v2
        """
        try:
            parts1 = [int(x) for x in v1.split('.')]
            parts2 = [int(x) for x in v2.split('.')]
            for p1, p2 in zip(parts1, parts2):
                if p1 < p2:
                    return -1
                if p1 > p2:
                    return 1
            return 0
        except (ValueError, AttributeError):
            return 0
    
    async def check_update(self, force: bool = False) -> Optional[dict]:
        """
        检查是否有更新
        
        Args:
            force: 强制重新检查，忽略缓存
            
        Returns:
            如果有更新，返回更新信息字典；否则返回 None
        """
        if self._update_info and not force:
            return self._update_info
        
        # 依次尝试各个下载源
        for source in DOWNLOAD_SOURCES:
            try:
                logger.info(f"正在从 {source['name']} 检查更新...")
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(source["version_url"])
                    if resp.status_code == 200:
                        data = resp.json()
                        latest_version = data.get("version", "0.0.0")
                        
                        if self.compare_versions(latest_version, self.current_version) > 0:
                            # 构建 download_url
                            download_url = data.get("download_url")
                            if not download_url:
                                # 从 base_url 构建
                                download_url = f"{source['base_url']}/openclaw-wechat-channel-v{latest_version}.tar.gz"
                            
                            self._update_info = {
                                "has_update": True,
                                "current_version": self.current_version,
                                "latest_version": latest_version,
                                "download_url": download_url,
                                "fallback_url": data.get("fallback_url"),
                                "checksum": data.get("checksum", {}).get("sha256"),
                                "changelog": data.get("changelog", []),
                                "source": source["name"]
                            }
                            return self._update_info
                        else:
                            logger.info(f"已是最新版本: {self.current_version}")
                            return None
            except Exception as e:
                logger.debug(f"从 {source['name']} 检查更新失败: {e}")
                continue
        
        logger.warning("所有更新源均无法访问")
        return None
    
    async def download_update(
        self,
        progress_callback: Optional[callable] = None
    ) -> Optional[Path]:
        """
        下载更新包
        
        Args:
            progress_callback: 进度回调函数，参数为 (downloaded_bytes, total_bytes)
            
        Returns:
            下载成功返回文件路径，失败返回 None
        """
        if not self._update_info:
            logger.error("请先调用 check_update() 检查更新")
            return None
        
        # 构建下载 URL 列表
        urls = []
        if self._update_info.get("download_url"):
            urls.append(self._update_info["download_url"])
        if self._update_info.get("fallback_url"):
            urls.append(self._update_info["fallback_url"])
        
        # 为每个下载源构建 URL
        for source in DOWNLOAD_SOURCES:
            url = f"{source['base_url']}/openclaw-wechat-channel-v{self._update_info['latest_version']}.tar.gz"
            if url not in urls:
                urls.append(url)
        
        for url in urls:
            try:
                logger.info(f"正在下载: {url}")
                
                async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                    # 先获取文件大小
                    head_resp = await client.head(url)
                    total_size = int(head_resp.headers.get("content-length", 0))
                    
                    # 下载文件
                    downloaded = 0
                    filename = f"openclaw-wechat-channel-v{self._update_info['latest_version']}.tar.gz"
                    filepath = self.update_dir / filename
                    
                    async with client.stream("GET", url) as response:
                        if response.status_code != 200:
                            continue
                        
                        with open(filepath, "wb") as f:
                            async for chunk in response.aiter_bytes(chunk_size=8192):
                                f.write(chunk)
                                downloaded += len(chunk)
                                if progress_callback:
                                    await progress_callback(downloaded, total_size)
                    
                    # 验证下载
                    if filepath.exists() and filepath.stat().st_size > 0:
                        # 验证校验和（如果有）
                        if self._update_info.get("checksum"):
                            if not self._verify_checksum(filepath, self._update_info["checksum"]):
                                logger.warning(f"校验和验证失败，删除文件: {filepath}")
                                filepath.unlink()
                                continue
                        
                        logger.info(f"下载完成: {filepath}")
                        self._downloaded_file = filepath
                        return filepath
                        
            except Exception as e:
                logger.debug(f"下载失败 ({url}): {e}")
                continue
        
        logger.error("所有下载源均失败")
        return None
    
    def _verify_checksum(self, filepath: Path, expected_sha256: str) -> bool:
        """
        验证文件校验和
        
        Args:
            filepath: 文件路径
            expected_sha256: 预期的 SHA256 值
            
        Returns:
            校验通过返回 True，否则返回 False
        """
        if not expected_sha256 or expected_sha256 == "待发布时计算":
            return True  # 跳过未计算的校验和
        
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        
        actual = sha256_hash.hexdigest()
        if actual.lower() != expected_sha256.lower():
            logger.warning(f"校验和不匹配: 期望 {expected_sha256}, 实际 {actual}")
            return False
        
        return True
    
    def _backup_protected_files(self, backup_dir: Path) -> dict:
        """
        备份需要保留的配置文件
        
        Args:
            backup_dir: 备份目录
            
        Returns:
            备份的文件列表
        """
        backup_dir.mkdir(parents=True, exist_ok=True)
        backed_up = {}
        
        for filename in PROTECTED_FILES:
            src = self.config_dir / filename
            if src.exists():
                dst = backup_dir / filename
                shutil.copy2(src, dst)
                backed_up[filename] = str(dst)
                logger.debug(f"已备份: {filename}")
        
        return backed_up
    
    def _restore_protected_files(self, backup_dir: Path, backed_up: dict):
        """
        恢复配置文件
        
        Args:
            backup_dir: 备份目录
            backed_up: 备份的文件列表
        """
        for filename, backup_path in backed_up.items():
            src = Path(backup_path)
            dst = self.config_dir / filename
            if src.exists():
                shutil.copy2(src, dst)
                logger.debug(f"已恢复: {filename}")
    
    async def install_update(self, archive_path: Optional[Path] = None) -> bool:
        """
        安装更新
        
        Args:
            archive_path: 更新包路径，如果为 None 则使用已下载的文件
            
        Returns:
            安装成功返回 True，失败返回 False
        """
        filepath = archive_path or self._downloaded_file
        if not filepath or not filepath.exists():
            logger.error("更新包不存在，请先下载")
            return False
        
        # 创建备份目录
        backup_dir = self.update_dir / "backup"
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # 1. 备份配置文件
            logger.info("正在备份配置文件...")
            backed_up = self._backup_protected_files(backup_dir)
            
            # 2. 解压更新包到临时目录
            logger.info("正在解压更新包...")
            extract_dir = self.update_dir / "extracted"
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            extract_dir.mkdir(parents=True, exist_ok=True)
            
            with tarfile.open(filepath, "r:gz") as tar:
                tar.extractall(extract_dir)
            
            # 3. 找到解压后的目录（可能有子目录）
            extracted_items = list(extract_dir.iterdir())
            if len(extracted_items) == 1 and extracted_items[0].is_dir():
                source_dir = extracted_items[0]
            else:
                source_dir = extract_dir
            
            # 4. 复制文件到配置目录（跳过受保护的文件）
            logger.info("正在安装更新...")
            for item in source_dir.iterdir():
                if item.name in PROTECTED_FILES:
                    logger.debug(f"跳过受保护文件: {item.name}")
                    continue
                
                dst = self.config_dir / item.name
                if dst.exists():
                    if dst.is_dir():
                        shutil.rmtree(dst)
                    else:
                        dst.unlink()
                
                if item.is_dir():
                    shutil.copytree(item, dst)
                else:
                    shutil.copy2(item, dst)
            
            # 5. 恢复配置文件
            logger.info("正在恢复配置文件...")
            self._restore_protected_files(backup_dir, backed_up)
            
            # 6. 更新启动脚本
            self._update_launcher_scripts()
            
            # 7. 清理临时文件
            shutil.rmtree(extract_dir)
            
            logger.info("更新安装完成！")
            return True
            
        except Exception as e:
            logger.error(f"安装更新失败: {e}")
            # 尝试恢复备份
            if backed_up:
                self._restore_protected_files(backup_dir, backed_up)
            return False
    
    def _update_launcher_scripts(self):
        """更新启动脚本"""
        # 创建 start.sh
        start_sh = self.config_dir / "start.sh"
        start_sh.write_text(f'''#!/bin/bash
cd "$(dirname "$0")"
OPENCLAW_URL="${{OPENCLAW_URL:-http://127.0.0.1:18789}}"
RELAY_URL="${{RELAY_URL:-wss://claw.7color.vip/ws-channel}}"
INSTANCE_TYPE="${{INSTANCE_TYPE:-bare}}"
echo "OpenClaw 微信频道客户端"
echo "OpenClaw: $OPENCLAW_URL"
echo "中转服务: $RELAY_URL"
exec python3 client.py --openclaw-url "$OPENCLAW_URL" --relay-url "$RELAY_URL" --instance-type "$INSTANCE_TYPE" "$@"
''')
        start_sh.chmod(0o755)
        
        # 创建 stop.sh
        stop_sh = self.config_dir / "stop.sh"
        stop_sh.write_text('''#!/bin/bash
pkill -f "python.*client.py.*wechat" 2>/dev/null || true
echo "客户端已停止"
''')
        stop_sh.chmod(0o755)
        
        # 创建 uninstall.sh
        uninstall_sh = self.config_dir / "uninstall.sh"
        uninstall_sh.write_text(f'''#!/bin/bash
read -p "确定要卸载 OpenClaw 微信频道插件吗？[y/N] " confirm
if [[ $confirm =~ ^[Yy]$ ]]; then
    pkill -f "python.*client.py.*wechat" 2>/dev/null || true
    rm -rf "{self.config_dir}"
    echo "已卸载"
else
    echo "已取消"
fi
''')
        uninstall_sh.chmod(0o755)
    
    async def download_and_install(self) -> bool:
        """
        下载并安装更新（一站式接口）
        
        Returns:
            成功返回 True，失败返回 False
        """
        # 下载
        filepath = await self.download_update()
        if not filepath:
            return False
        
        # 安装
        return await self.install_update(filepath)
    
    def needs_restart(self) -> bool:
        """
        检查是否需要重启服务
        
        Returns:
            需要重启返回 True
        """
        return self._downloaded_file is not None or self._update_info is not None
    
    def get_restart_command(self) -> Optional[str]:
        """
        获取重启命令
        
        Returns:
            重启命令字符串
        """
        system = platform.system()
        
        if system == "Linux":
            # 检查是否使用 systemd
            if self._is_systemd_service():
                return "systemctl --user restart openclaw-wechat"
            else:
                return f"{self.config_dir}/stop.sh && {self.config_dir}/start.sh"
        
        elif system == "Darwin":
            # macOS: 检查是否使用 launchd
            if self._is_launchd_service():
                return "launchctl restart com.openclaw.wechat"
            else:
                return f"{self.config_dir}/stop.sh && {self.config_dir}/start.sh"
        
        else:
            # Windows 或其他系统
            return f"{self.config_dir}/stop.sh && {self.config_dir}/start.sh"
    
    def _is_systemd_service(self) -> bool:
        """检查是否作为 systemd 服务运行"""
        try:
            # 检查用户级 systemd 服务
            service_path = Path.home() / ".config" / "systemd" / "user" / "openclaw-wechat.service"
            return service_path.exists()
        except Exception:
            return False
    
    def _is_launchd_service(self) -> bool:
        """检查是否作为 launchd 服务运行"""
        try:
            plist_path = Path.home() / "Library" / "LaunchAgents" / "com.openclaw.wechat.plist"
            return plist_path.exists()
        except Exception:
            return False
    
    def cleanup(self):
        """清理下载的临时文件"""
        if self._downloaded_file and self._downloaded_file.exists():
            self._downloaded_file.unlink()
            logger.debug(f"已清理: {self._downloaded_file}")
        
        # 清理解压目录
        extract_dir = self.update_dir / "extracted"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        
        self._downloaded_file = None
    
    def cleanup_old_updates(self, keep_latest: int = 3):
        """
        清理旧的更新包
        
        Args:
            keep_latest: 保留最近几个更新包
        """
        archives = sorted(
            self.update_dir.glob("openclaw-wechat-channel-*.tar.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        for archive in archives[keep_latest:]:
            archive.unlink()
            logger.debug(f"已清理旧更新包: {archive}")


# 便捷函数
async def check_for_updates(current_version: str) -> Optional[dict]:
    """
    检查更新的便捷函数
    
    Args:
        current_version: 当前版本号
        
    Returns:
        如果有更新，返回更新信息；否则返回 None
    """
    updater = Updater(current_version=current_version)
    return await updater.check_update()


async def perform_update(current_version: str) -> bool:
    """
    执行更新的便捷函数
    
    Args:
        current_version: 当前版本号
        
    Returns:
        成功返回 True，失败返回 False
    """
    updater = Updater(current_version=current_version)
    
    # 检查更新
    update_info = await updater.check_update()
    if not update_info:
        logger.info("没有可用更新")
        return False
    
    # 下载并安装
    success = await updater.download_and_install()
    
    if success:
        logger.info(f"更新成功: {update_info['current_version']} → {update_info['latest_version']}")
        logger.info(f"请运行以下命令重启服务: {updater.get_restart_command()}")
    
    return success


# 命令行入口
async def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="OpenClaw 微信频道更新器")
    parser.add_argument("--check", action="store_true", help="仅检查更新")
    parser.add_argument("--install", action="store_true", help="下载并安装更新")
    parser.add_argument("--cleanup", action="store_true", help="清理旧的更新包")
    parser.add_argument("--version", default="0.0.0", help="当前版本号")
    
    args = parser.parse_args()
    
    updater = Updater(current_version=args.version)
    
    if args.check:
        update_info = await updater.check_update()
        if update_info:
            print(f"\n🔔 发现新版本: {update_info['latest_version']}")
            print(f"   当前版本: {update_info['current_version']}")
            print(f"   下载地址: {update_info['download_url']}")
            print(f"   更新来源: {update_info['source']}")
            if update_info.get("changelog"):
                print("\n📝 更新日志:")
                for item in update_info["changelog"]:
                    print(f"   - {item}")
        else:
            print("✅ 已是最新版本")
    
    elif args.install:
        success = await updater.download_and_install()
        if success:
            print("\n✅ 更新安装成功！")
            print(f"   重启命令: {updater.get_restart_command()}")
        else:
            print("\n❌ 更新安装失败")
    
    elif args.cleanup:
        updater.cleanup_old_updates()
        print("✅ 已清理旧的更新包")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())