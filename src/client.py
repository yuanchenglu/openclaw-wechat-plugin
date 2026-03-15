"""
OpenClaw 微信频道插件 - 用户端客户端

版本: 1.2.0
变更记录:
- 2026-03-14: 实现 Device ID v2.0
  - 格式: {type}_{machine_id}_{system_username}_{timestamp}_{random4}
  - 设备类型: bare/ecs/docker_local/docker_cloud
  - 卸载即新设备（配置文件不存在 = 新设备）
  - 本地存储 + 云端同步架构

功能：
1. 检测设备类型
2. 生成设备指纹 (machine_id)
3. 生成 device_id（新格式）
4. 本地配置持久化
5. 连接到中转服务的 WebSocket
6. 接收来自微信的消息
7. 调用本地 OpenClaw API 处理消息
8. 将响应发回中转服务
9. 支持自动更新检查

关键设计：
- 卸载插件 = 删除本地配置文件
- 配置文件不存在 = 新设备，需要重新扫码
- 类似 Windows 11 的设备管理体验

使用方法：
    # 本地用户
    python client.py --openclaw-url http://localhost:8080

    # 云端实例
    python client.py --openclaw-url http://localhost:8080 --instance-type cloud
"""
import asyncio
import websockets
import httpx
import argparse
import hashlib
import logging
import platform
import subprocess
import os
import sys
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

# 版本信息
CLIENT_VERSION = "1.2.0"
MIN_SERVER_VERSION = "1.0.0"
UPDATE_CHECK_URL = "https://claw.7color.vip/channel-update/version.json"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def compare_versions(v1: str, v2: str) -> int:
    """比较版本号，返回 -1, 0, 1"""
    parts1 = [int(x) for x in v1.split('.')]
    parts2 = [int(x) for x in v2.split('.')]
    for p1, p2 in zip(parts1, parts2):
        if p1 < p2:
            return -1
        if p1 > p2:
            return 1
    return 0


# ==================== 设备类型检测 ====================

def is_docker() -> bool:
    """检测是否在 Docker 容器中运行"""
    # 方法 1：检查 /.dockerenv 文件
    if os.path.exists("/.dockerenv"):
        return True
    
    # 方法 2：检查 /proc/self/cgroup
    try:
        with open("/proc/self/cgroup", "r") as f:
            content = f.read()
            if "docker" in content or "containerd" in content or "kubepods" in content:
                return True
    except:
        pass
    
    return False


def is_cloud_vm() -> bool:
    """检测是否是云服务器（ECS）"""
    try:
        # 方法 1：检查云厂商标识文件
        if os.path.exists("/sys/class/dmi/id/product_name"):
            with open("/sys/class/dmi/id/product_name", "r") as f:
                name = f.read().lower()
                cloud_vendors = ["aliyun", "alibaba", "tencent", "huawei", "amazon", "ec2", "azure", "google", "gce"]
                if any(vendor in name for vendor in cloud_vendors):
                    return True
        
        # 方法 2：检查 systemd 环境变量
        if os.path.exists("/etc/cloud/cloud.cfg"):
            return True
        
        # 方法 3：检查特定云厂商的特征文件
        cloud_indicator_files = [
            "/sys/hypervisor/uuid",  # EC2
            "/etc/aliyun-instance-id",  # 阿里云
            "/etc/tencent-instance-id",  # 腾讯云
        ]
        for f in cloud_indicator_files:
            if os.path.exists(f):
                return True
                
    except:
        pass
    
    return False


def get_device_type() -> str:
    """获取设备类型
    
    返回值:
        - bare: 物理机（真实的 Mac/PC）
        - ecs: 云服务器（阿里云、腾讯云等）
        - docker_local: 本地 Docker
        - docker_cloud: 云端 Docker
    """
    in_docker = is_docker()
    is_cloud = is_cloud_vm()
    
    if in_docker and is_cloud:
        return "docker_cloud"
    elif in_docker and not is_cloud:
        return "docker_local"
    elif not in_docker and is_cloud:
        return "ecs"
    else:
        return "bare"


def get_system_username() -> str:
    """获取系统用户名
    
    用于标识运行 OpenClaw 的系统账户
    """
    try:
        return os.getlogin()
    except:
        try:
            import getpass
            return getpass.getuser()
        except:
            return "unknown"


# ==================== 设备指纹生成 ====================

def get_machine_id() -> str:
    """获取设备硬件指纹（不变标识）

    实现：
    - macOS: IOPlatformUUID
    - Windows: 主板 UUID
    - Linux: /etc/machine-id

    Returns:
        16 位十六进制字符串
    """
    system = platform.system()

    try:
        if system == "Darwin":  # macOS
            result = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split("\n"):
                if "IOPlatformUUID" in line:
                    uuid_str = line.split('"')[-2]
                    return hashlib.sha256(uuid_str.encode()).hexdigest()[:16]

        elif system == "Windows":
            result = subprocess.run(
                ["wmic", "csproduct", "get", "UUID"],
                capture_output=True, text=True, timeout=5
            )
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                uuid_str = lines[1].strip()
                if uuid_str:
                    return hashlib.sha256(uuid_str.encode()).hexdigest()[:16]

        else:  # Linux
            machine_id_path = "/etc/machine-id"
            if os.path.exists(machine_id_path):
                with open(machine_id_path, "r") as f:
                    content = f.read().strip()
                    return hashlib.sha256(content.encode()).hexdigest()[:16]

    except Exception as e:
        logger.warning(f"Failed to get machine ID via primary method: {e}")

    # 备用方案：使用 hostname + 用户名的 hash
    # 注意：这不如硬件指纹稳定
    fallback = f"{platform.node()}-{os.getlogin()}"
    return hashlib.sha256(fallback.encode()).hexdigest()[:16]


def generate_device_id() -> str:
    """生成 device_id（新格式）

    格式: {type}_{machine_id}_{system_username}_{timestamp}_{random4}
    
    设计原则:
    - 卸载插件 = 删除本地配置文件
    - 配置文件不存在 = 新设备
    - 每次安装生成唯一的 device_id

    Returns:
        device_id 字符串
    """
    import uuid
    
    device_type = get_device_type()
    machine_id = get_machine_id()
    system_username = get_system_username()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_suffix = uuid.uuid4().hex[:4]
    
    return f"{device_type}_{machine_id}_{system_username}_{timestamp}_{random_suffix}"


# ==================== 本地配置管理 ====================

class LocalConfig:
    """本地配置管理

    配置文件路径: ~/.openclaw/wechat-channel/config.json
    """

    def __init__(self, config_dir: Optional[str] = None):
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            self.config_dir = Path.home() / ".openclaw" / "wechat-channel"

        self.config_file = self.config_dir / "config.json"
        self._ensure_dir()

    def _ensure_dir(self):
        """确保配置目录存在"""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> Optional[dict]:
        """加载配置"""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load config: {e}")
        return None

    def save(self, config: dict):
        """保存配置"""
        try:
            with open(self.config_file, "w") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            logger.info(f"Config saved to {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def clear(self):
        """清除配置"""
        if self.config_file.exists():
            self.config_file.unlink()
            logger.info("Config cleared")


# ==================== 更新检查 ====================

async def check_update() -> Optional[dict]:
    """检查是否有更新"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(UPDATE_CHECK_URL)
            if resp.status_code == 200:
                data = resp.json()
                latest = data.get("client_version", "0.0.0")
                if compare_versions(latest, CLIENT_VERSION) > 0:
                    return {
                        "has_update": True,
                        "latest_version": latest,
                        "download_url": data.get("download_url"),
                        "changelog": data.get("changelog", "")
                    }
    except Exception as e:
        logger.debug(f"Update check failed: {e}")
    return None


# ==================== 主客户端类 ====================

class OpenClawWeChatClient:
    """OpenClaw 微信频道客户端"""

    def __init__(
        self,
        openclaw_url: str,
        relay_url: str,
        instance_type: str = "local",
        api_key: Optional[str] = None,
        config_dir: Optional[str] = None
    ):
        self.openclaw_url = openclaw_url.rstrip("/")
        self.relay_url = relay_url
        self.instance_type = instance_type
        self.api_key = api_key

        # 本地配置
        self.config = LocalConfig(config_dir)

        # 设备信息（延迟初始化）
        self.device_id: Optional[str] = None
        self.device_type: Optional[str] = None
        self.machine_id: Optional[str] = None
        self.system_username: Optional[str] = None

        # 连接状态
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self.authorized = False
        self.openid: Optional[str] = None
        self.server_version: Optional[str] = None

        # 是否是新设备
        self.is_new_device = False

    def _init_device_info(self):
        """初始化设备信息
        
        逻辑：
        1. 检查本地配置文件是否存在
        2. 存在 → 读取 device_id（恢复设备）
        3. 不存在 → 生成新 device_id（新设备）
        """
        # 尝试从本地配置加载
        saved_config = self.config.load()
        
        if saved_config and saved_config.get("device_id"):
            # 恢复设备
            self.device_id = saved_config["device_id"]
            self.device_type = saved_config.get("device_type", "unknown")
            self.machine_id = saved_config.get("machine_id")
            self.system_username = saved_config.get("system_username")
            self.openid = saved_config.get("openid")
            self.is_new_device = False
            logger.info(f"🔄 恢复设备: {self.device_id}")
        else:
            # 新设备
            self.device_type = get_device_type()
            self.machine_id = get_machine_id()
            self.system_username = get_system_username()
            self.device_id = generate_device_id()
            self.is_new_device = True
            logger.info(f"🆕 新设备: {self.device_id}")

    async def connect(self):
        """连接到中转服务"""
        # 初始化设备信息
        self._init_device_info()
        
        logger.info(f"Connecting to {self.relay_url}...")
        logger.info(f"Client version: {CLIENT_VERSION}")
        logger.info(f"Device ID: {self.device_id}")
        logger.info(f"Device Type: {self.device_type}")
        logger.info(f"Machine ID: {self.machine_id}")
        logger.info(f"System User: {self.system_username}")

        try:
            self.websocket = await websockets.connect(
                self.relay_url,
                ping_interval=30,
                ping_timeout=10
            )

            # 发送注册消息（包含完整设备信息）
            await self.websocket.send(json.dumps({
                "type": "register",
                "instance_type": self.instance_type,
                "device_id": self.device_id,
                "device_type": self.device_type,
                "machine_id": self.machine_id,
                "system_username": self.system_username,
                "client_version": CLIENT_VERSION,
                "min_server_version": MIN_SERVER_VERSION,
                "is_new_device": self.is_new_device
            }))

            # 等待注册响应
            response = await asyncio.wait_for(
                self.websocket.recv(),
                timeout=10
            )
            data = json.loads(response)

            if data.get("type") == "registered":
                self.server_version = data.get("server_version")
                self.connected = True

                # 检查是否是恢复连接（云端有该 device_id 的绑定记录）
                is_recovery = data.get("is_recovery", False)
                if is_recovery:
                    self.openid = data.get("recovered_openid")
                    self.authorized = True
                    logger.info(f"🔄 设备绑定已恢复! OpenID: {self.openid}")

                logger.info(f"Connected! Server version: {self.server_version}")

                # 检查版本兼容性
                if data.get("version_compatible") == False:
                    logger.warning("⚠️ Server version may not be fully compatible!")
                    logger.warning(f"Server recommends client version: {data.get('recommended_client_version')}")

                # 显示授权链接
                auth_url = data.get("auth_url", "")
                if self.authorized:
                    logger.info(f"\n{'='*60}")
                    logger.info("✅ 设备已绑定，可以开始对话！")
                    logger.info(f"{'='*60}\n")
                else:
                    logger.info(f"\n{'='*60}")
                    logger.info("请扫码完成授权：")
                    logger.info(f"{auth_url}")
                    logger.info(f"{'='*60}\n")

                    # 如果是桌面环境，尝试自动打开浏览器
                    if self.instance_type == "local":
                        try:
                            import webbrowser
                            webbrowser.open(auth_url)
                            logger.info("已自动打开浏览器")
                        except:
                            pass

            elif data.get("type") == "error":
                logger.error(f"Registration failed: {data.get('message')}")
                if data.get("update_required"):
                    logger.error(f"Please update to version: {data.get('required_version')}")
                raise Exception("Registration failed")
            else:
                logger.error(f"Unexpected response: {data}")
                raise Exception("Registration failed")

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise

    async def disconnect(self):
        """断开连接"""
        if self.websocket:
            await self.websocket.close()
            self.connected = False
            logger.info("Disconnected")

    async def send_message(self, message: dict):
        """发送消息"""
        if self.websocket:
            await self.websocket.send(json.dumps(message))

    async def receive_messages(self):
        """接收消息循环"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    await self.handle_message(data)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON: {message}")
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Connection closed by server")
            self.connected = False
        except Exception as e:
            logger.error(f"Error receiving message: {e}")
            self.connected = False

    async def handle_message(self, data: dict):
        """处理收到的消息"""
        msg_type = data.get("type", "")

        if msg_type == "ping":
            await self.send_message({"type": "pong"})

        elif msg_type == "chat_request":
            openid = data.get("openid", "")
            content = data.get("content", "")
            msg_type_in = data.get("msg_type", "text")

            logger.info(f"Received from WeChat: {content[:50]}...")

            response = await self.call_openclaw(content, msg_type_in)

            if response:
                await self.send_message({
                    "type": "chat_response",
                    "openid": openid,
                    "content": response,
                    "client_version": CLIENT_VERSION
                })
                logger.info("Response sent to WeChat")

        elif msg_type == "status_response":
            is_authorized = data.get("is_authorized", False)
            self.openid = data.get("openid")
            self.authorized = is_authorized

            if is_authorized:
                logger.info(f"✅ Authorized! OpenID: {self.openid}")

                # 保存配置
                self._save_local_config()
            else:
                logger.info("❌ Not authorized. Please scan QR code.")

        elif msg_type == "update_required":
            logger.warning("⚠️ Update required!")
            logger.warning(f"Required version: {data.get('required_version')}")
            logger.warning(f"Download: {data.get('download_url')}")

    def _save_local_config(self):
        """保存本地配置"""
        config = {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "machine_id": self.machine_id,
            "system_username": self.system_username,
            "openid": self.openid,
            "relay_url": self.relay_url,
            "instance_type": self.instance_type,
            "created_at": datetime.utcnow().isoformat(),
            "version": CLIENT_VERSION
        }
        self.config.save(config)

    async def call_openclaw(self, message: str, msg_type: str = "text") -> Optional[str]:
        """调用 OpenClaw API"""
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            url = f"{self.openclaw_url}/v1/chat/completions"

            payload = {
                "model": "default",
                "messages": [
                    {"role": "user", "content": message}
                ],
                "stream": False
            }

            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return content
                else:
                    logger.error(f"OpenClaw API error: {response.status_code}")
                    return f"Error: OpenClaw returned {response.status_code}"

        except Exception as e:
            logger.error(f"Failed to call OpenClaw: {e}")
            return f"Error: {str(e)}"

    async def check_status(self):
        """检查连接状态"""
        await self.send_message({"type": "status"})

    async def run(self):
        """主循环"""
        # 检查更新
        update_info = await check_update()
        if update_info:
            logger.info(f"\n🔔 New version available: {update_info['latest_version']}")
            logger.info(f"Download: {update_info['download_url']}\n")

        await self.connect()

        receive_task = asyncio.create_task(self.receive_messages())

        while self.connected:
            await asyncio.sleep(30)
            await self.check_status()

        receive_task.cancel()
        try:
            await receive_task
        except asyncio.CancelledError:
            pass


async def main():
    parser = argparse.ArgumentParser(description="OpenClaw 微信频道客户端")
    parser.add_argument(
        "--openclaw-url",
        default=os.getenv("OPENCLAW_URL", "http://127.0.0.1:18789"),
        help="OpenClaw 服务地址（默认 18789，即 OpenClaw Gateway）"
    )
    parser.add_argument(
        "--relay-url",
        default=os.getenv("RELAY_URL", "wss://claw-wechat.7color.vip/ws-channel"),
        help="中转服务 WebSocket 地址"
    )
    parser.add_argument(
        "--instance-type",
        default=os.getenv("INSTANCE_TYPE", "local"),
        choices=["local", "cloud"],
        help="实例类型：local（用户本地）或 cloud（云端）"
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OPENCLAW_API_KEY"),
        help="OpenClaw API Key（可选）"
    )
    parser.add_argument(
        "--check-update",
        action="store_true",
        help="只检查更新，不启动客户端"
    )
    parser.add_argument(
        "--show-device-id",
        action="store_true",
        help="显示设备 ID 并退出"
    )

    args = parser.parse_args()

    # 只显示设备 ID
    if args.show_device_id:
        print(f"Device ID: {generate_device_id()}")
        print(f"Machine ID: {get_machine_id()}")
        return

    # 只检查更新
    if args.check_update:
        update_info = await check_update()
        if update_info:
            print(f"Update available: {update_info['latest_version']}")
            print(f"Download: {update_info['download_url']}")
            print(f"Changelog: {update_info['changelog']}")
        else:
            print(f"No update available. Current version: {CLIENT_VERSION}")
        return

    logger.info("="*60)
    logger.info("OpenClaw 微信频道客户端")
    logger.info(f"版本: {CLIENT_VERSION}")
    logger.info(f"实例类型: {args.instance_type}")
    logger.info(f"OpenClaw URL: {args.openclaw_url}")
    logger.info(f"Relay URL: {args.relay_url}")
    logger.info("="*60)

    client = OpenClawWeChatClient(
        openclaw_url=args.openclaw_url,
        relay_url=args.relay_url,
        instance_type=args.instance_type,
        api_key=args.api_key
    )

    try:
        await client.run()
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
        await client.disconnect()
    except Exception as e:
        logger.error(f"Error: {e}")
        await client.disconnect()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())