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

# 看门狗和更新模块
try:
    from .watchdog import WatchdogMonitor
    from .updater import Updater
    from .wechat_types import CHECK_INTERVAL, RESTART_DELAY, RESTART_HOUR
    from .update_state import UpdateState, save_state, load_state, clear_state
except ImportError:
    # 当作为脚本直接运行时
    from watchdog import WatchdogMonitor
    from updater import Updater
    # 避免与内置 types 模块冲突，使用 importlib 显式加载本地模块
    import importlib.util
    _types_path = Path(__file__).parent / "wechat_types.py"
    _types_spec = importlib.util.spec_from_file_location("wechat_types", _types_path)
    _local_types = importlib.util.module_from_spec(_types_spec)
    _types_spec.loader.exec_module(_local_types)
    CHECK_INTERVAL = _local_types.CHECK_INTERVAL
    RESTART_DELAY = _local_types.RESTART_DELAY
    RESTART_HOUR = _local_types.RESTART_HOUR
    from update_state import UpdateState, save_state, load_state, clear_state


def load_version() -> str:
    """从 version.json 读取版本号"""
    # 尝试从多个位置查找 version.json
    possible_paths = [
        # 1. 安装目录的 release 目录 (开发和生产环境)
        Path(__file__).parent.parent / "release" / "version.json",
        # 2. 安装目录根目录 (打包后)
        Path(__file__).parent.parent / "version.json",
        # 3. 用户配置目录
        Path.home() / ".openclaw" / "wechat-channel" / "version.json",
    ]
    
    for path in possible_paths:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("version", "0.0.0")
            except Exception:
                pass
    
    return "0.0.0"  # 默认版本

# 版本信息
CLIENT_VERSION = load_version()
MIN_SERVER_VERSION = "1.0.0"
UPDATE_CHECK_URL = "https://claw.7color.vip/channel-update/version.json"
# 重连参数
INITIAL_RETRY_DELAY = 1  # 初始重连延迟（秒）
MAX_RETRY_DELAY = 30     # 最大重连延迟（秒）

# 日志配置
LOG_DIR = Path.home() / ".openclaw" / "wechat-channel" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"client_{datetime.now().strftime('%Y%m%d')}.log"

# 配置日志（同时输出到终端和文件）
def setup_logging():
    """配置日志系统"""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # 格式
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 终端输出
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件输出
    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.info(f"日志文件: {LOG_FILE}")
    except Exception as e:
        logger.warning(f"无法创建日志文件: {e}")
    
    return logger

logger = setup_logging()

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
        
        # 方法 2：移除 cloud.cfg 检查（物理机也可能安装 cloud-init）
        # 不再单独依赖 cloud.cfg，而是依赖方法 1 和方法 3
        
        
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
                latest = data.get("version", "0.0.0")
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
        
        # 看门狗监控器（延迟初始化，需要 openid）
        self.watchdog: Optional[WatchdogMonitor] = None
        
        # 自动更新器
        self.updater: Optional[Updater] = None
        
        # 更新信息缓存
        self._pending_update: Optional[dict] = None
        
        # 静默升级相关
        self._update_check_task: Optional[asyncio.Task] = None
        self._restart_timer: Optional[asyncio.TimerHandle] = None
        self._upgrade_state: Optional[UpdateState] = None
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
            # 新设备生成 device_id 后立即保存，防止重启后丢失
            self._save_local_config()

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
                
                # 初始化看门狗监控（需要 openid）
                if not self.watchdog or not self.watchdog.is_running:
                    await self._init_watchdog()
            else:
                logger.info("❌ Not authorized. Please scan QR code.")
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
        logger.info(f"[API] 调用 OpenClaw: url={self.openclaw_url}/v1/chat/completions")
        
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
                
                logger.info(f"[API] 响应状态码: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    logger.info(f"[API] 成功: 响应长度={len(content)} 字符")
                    return content
                
                elif response.status_code == 404:
                    # Chat Completions API 未启用
                    logger.error(f"[API] 404 错误: Chat Completions API 未启用")
                    logger.error(f"[API] 解决方法: 在 gateway.http.endpoints.chatCompletions.enabled 设置为 true")
                    return self._build_self_healing_message("chat_api_disabled")
                
                elif response.status_code == 401:
                    # 认证错误
                    logger.error(f"[API] 401 错误: 认证失败")
                    logger.error(f"[API] 响应内容: {response.text[:200]}")
                    return self._build_self_healing_message("auth_failed")
                
                else:
                    logger.error(f"[API] 错误 {response.status_code}: {response.text[:200]}")
                    return f"⚠️ OpenClaw 服务异常 ({response.status_code})\n\n请稍后重试，或发送 /status 查看状态。"

        except httpx.ConnectError:
            logger.error(f"[API] 连接失败: 无法连接到 {self.openclaw_url}")
            logger.error(f"[API] 请检查: 1) OpenClaw 是否运行 2) 端口是否正确 3) 防火墙设置")
            return self._build_self_healing_message("connection_failed")
        
        except httpx.TimeoutException:
            logger.error(f"[API] 请求超时 (120秒)")
            return "⚠️ OpenClaw 响应超时\n\n请稍后重试。"
        
        except Exception as e:
            logger.error(f"[API] 未知错误: {type(e).__name__}: {e}")
            return f"⚠️ 连接异常\n\n错误信息: {str(e)}\n\n请发送 /status 查看状态。"

    def _build_self_healing_message(self, error_type: str) -> str:
        """构建自愈指引消息
        
        返回包含三部分的消息：
        1. 问题描述（通俗语言）
        2. 解决方法（用户复制粘贴给 OpenClaw 即可触发自愈）
        3. 原因分析（供 AI 理解，非用户阅读）
        """
        if error_type == "chat_api_disabled":
            return """⚠️ 需要启用 API 接口

【问题描述】
OpenClaw 的微信对话接口未启用，导致消息无法正常处理。

【解决方法】
请复制以下内容，发送给 OpenClaw 对话框（打开浏览器访问 http://127.0.0.1:18789/）：

```
请帮我启用 Gateway 的 Chat Completions API：
在 gateway 配置中添加：
"http": {"endpoints": {"chatCompletions": {"enabled": true}}}
```

发送后，OpenClaw 会自动完成配置更新，微信对话即可恢复正常。

【原因分析】
技术细节：Gateway 的 /v1/chat/completions 端点默认禁用。OpenClaw 升级或配置重置后可能恢复默认设置。启用该端点后，微信频道插件才能正常调用 AI 对话能力。"""
        
        elif error_type == "auth_failed":
            return """⚠️ 认证配置需要更新

【问题描述】
OpenClaw Gateway 的认证配置不正确，导致请求被拒绝。

【解决方法】
请复制以下内容，发送给 OpenClaw 对话框：

```
请检查 gateway.auth 配置，确保 token 配置正确，或暂时将 auth.mode 设置为 "none" 进行测试。
```

【原因分析】
技术细节：Gateway auth token 不匹配或过期。需要检查 gateway.auth.token 配置。"""
        
        elif error_type == "connection_failed":
            return f"""⚠️ 无法连接到 OpenClaw

【问题描述】
无法连接到 OpenClaw 服务（{self.openclaw_url}），请确认 OpenClaw 是否正在运行。

【解决方法】
1. 确保 OpenClaw 已启动（终端运行 `openclaw gateway` 或打开 OpenClaw 应用）
2. 检查端口 {self.openclaw_url.split(':')[-1] if ':' in self.openclaw_url else '18789'} 是否正确

【原因分析】
技术细节：HTTP 连接失败，可能是 OpenClaw 未启动、端口不匹配或防火墙阻止。"""
        
        else:
            return """⚠️ 未知错误

请发送 /status 查看连接状态，或联系技术支持。"""

    async def check_status(self):
        """检查连接状态"""
        await self.send_message({"type": "status"})

    async def _connect_with_retry(self) -> bool:
        """带指数退避的重连逻辑
        
        Returns:
            bool: 连接成功返回 True
        """
        retry_count = 0
        
        while True:
            try:
                await self.connect()
                retry_count = 0  # 连接成功，重置计数器
                return True
            except Exception as e:
                retry_count += 1
                # 计算指数退避延迟
                delay = min(2 ** (retry_count - 1), MAX_RETRY_DELAY)
                
                logger.warning(f"🔄 连接失败 (第 {retry_count} 次重试): {e}")
                logger.info(f"⏳ {delay} 秒后重连...")
                
                await asyncio.sleep(delay)

    async def run(self):
        """主循环，支持自动重连、看门狗监控和静默升级"""
        
        # ==================== 初始化更新器 ====================
        self.updater = Updater(
            config_dir=self.config.config_dir,
            current_version=CLIENT_VERSION
        )
        
        # ==================== 检查是否需要重启（T7）====================
        self._upgrade_state = load_state()
        if self._upgrade_state and self._upgrade_state.is_restart_due():
            logger.info("🔄 检测到待重启的更新，正在执行重启...")
            await self._execute_restart()
            return  # 重启后不会执行到这里
        
        # ==================== 启动时检查更新（首次启动，非静默）====================
        update_info = await self.updater.check_update(silent=False)
        if update_info:
            logger.info(f"\n🔔 发现新版本: {update_info['latest_version']}")
            logger.info(f"   当前版本: {update_info['current_version']}")
            logger.info(f"   下载地址: {update_info['download_url']}\n")
            
            # 后台下载更新（不阻塞主循环）
            asyncio.create_task(self._download_update_background(update_info, silent=False))
        
        # ==================== 启动定时检查任务（T5）====================
        self._update_check_task = asyncio.create_task(self._periodic_update_check())
        
        # ==================== 主循环 ====================
        # 主循环：连接 -> 接收消息 -> 断开后重连
        while True:
            try:
                # 带重连的连接
                await self._connect_with_retry()
                
                # 初始化看门狗（需要 openid，在授权成功后）
                if self.authorized and self.openid:
                    await self._init_watchdog()

                # 接收消息
                receive_task = asyncio.create_task(self.receive_messages())

                # 心跳循环
                while self.connected:
                    await asyncio.sleep(30)
                    await self.check_status()
                    
                    # 心跳成功，重置看门狗计时器
                    if self.watchdog and self.watchdog.is_running:
                        self.watchdog.feed()

                # 连接断开，取消接收任务
                receive_task.cancel()
                try:
                    await receive_task
                except asyncio.CancelledError:
                    pass

                # 停止看门狗监控
                if self.watchdog and self.watchdog.is_running:
                    await self.watchdog.stop()

                logger.warning("🔄 连接已断开，准备重连...")
                # 循环会自动进入下一次 _connect_with_retry

            except asyncio.CancelledError:
                # 被外部取消，退出循环
                logger.info("客户端正在关闭...")
                
                # 停止定时检查任务
                if self._update_check_task:
                    self._update_check_task.cancel()
                    try:
                        await self._update_check_task
                    except asyncio.CancelledError:
                        pass
                
                # 停止看门狗监控
                if self.watchdog and self.watchdog.is_running:
                    await self.watchdog.stop()
                break
    
    async def _periodic_update_check(self):
        """定时检查更新任务（每 5 小时）
        
        使用静默模式，不打印通知日志。
        """
        while True:
            try:
                # 等待检查间隔
                await asyncio.sleep(CHECK_INTERVAL)
                
                logger.debug("[Updater] 执行定时更新检查...")
                
                # 静默检查更新
                update_info = await self.updater.check_update(silent=True)
                if update_info:
                    logger.info(f"[Updater] 定时检查发现新版本: {update_info['latest_version']}")
                    
                    # 静默下载安装
                    await self._download_update_background(update_info, silent=True)
                
            except asyncio.CancelledError:
                logger.debug("[Updater] 定时检查任务已取消")
                break
            except Exception as e:
                logger.error(f"[Updater] 定时检查出错: {e}")
                # 继续下一次检查
    
    async def _execute_restart(self):
        """执行重启
        
        延迟重启策略：
        - 如果已超过 24 小时 → 立即重启
        - 如果未到 24 小时 → 调度到次日 4:00
        """
        if not self._upgrade_state:
            return
        
        # 清除升级状态
        clear_state()
        
        # 获取重启命令并执行
        restart_cmd = self.updater.get_restart_command()
        logger.info(f"🔄 执行重启命令: {restart_cmd}")
        
        # 这里使用 os.execvp 或 subprocess 来重启
        # 实际重启前记录日志
        logger.info("客户端即将重启...")
        
        # 通过停止当前进程让 systemd/launchd 自动重启
        # 或者执行重启脚本
        import sys
        sys.exit(0)  # 退出让外部服务重启
    
    async def _schedule_delayed_restart(self):
        """调度延迟重启
        
        计算到次日 4:00 的延迟时间，设置定时器。
        """
        if not self._upgrade_state:
            return
        
        delay_seconds = self._upgrade_state.get_restart_delay()
        
        if delay_seconds <= 0:
            # 已超过重启时间，立即重启
            logger.info("[Updater] 已超过重启窗口，立即重启")
            await self._execute_restart()
            return
        
        logger.info(f"[Updater] 计划在 {delay_seconds // 3600} 小时后重启")
        
        # 使用 asyncio.sleep 实现延迟
        async def delayed_restart():
            await asyncio.sleep(delay_seconds)
            await self._execute_restart()
        
        asyncio.create_task(delayed_restart())
        
    
    async def _init_watchdog(self):
        """初始化看门狗监控器
        
        需要在授权成功后调用，因为需要 openid。
        """
        if self.watchdog and self.watchdog.is_running:
            logger.debug("[Watchdog] 监控已在运行中")
            return
        
        # 创建看门狗监控器
        self.watchdog = WatchdogMonitor(
            relay_url=self.relay_url,
            openid=self.openid,
            send_callback=self._watchdog_send_callback,
            timeout_seconds=60,  # 心跳超时阈值
            check_interval=10   # 检查间隔
        )
        
        # 启动监控
        await self.watchdog.start()
        logger.info("[Watchdog] 监控已启动")
    
    def _watchdog_send_callback(self, message: dict):
        """看门狗告警发送回调
        
        将告警消息发送到中转服务，由中转服务转发给用户微信。
        
        Args:
            message: 告警消息字典
        """
        # 使用 asyncio.create_task 在后台发送，避免阻塞
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._send_watchdog_alert(message))
            else:
                loop.run_until_complete(self._send_watchdog_alert(message))
        except Exception as e:
            logger.error(f"[Watchdog] 发送告警回调失败: {e}")
    
    async def _send_watchdog_alert(self, message: dict):
        """发送看门狗告警到中转服务
        
        Args:
            message: 告警消息字典
        """
        try:
            if self.websocket and self.connected:
                await self.websocket.send(json.dumps(message))
                logger.info(f"[Watchdog] 告警已发送到中转服务")
            else:
                logger.warning("[Watchdog] 连接已断开，无法发送告警")
        except Exception as e:
            logger.error(f"[Watchdog] 发送告警失败: {e}")
    
    async def _download_update_background(self, update_info: dict, silent: bool = False):
        """后台下载更新
        
        不阻塞主循环，下载完成后等待合适时机重启。
        
        Args:
            update_info: 更新信息字典
            silent: 静默模式，不打印通知日志
        """
        try:
            if not silent:
                logger.info("[Updater] 开始后台下载更新...")
            
            # 下载更新包（静默模式）
            filepath = await self.updater.download_update(silent=silent)
            if not filepath:
                if not silent:
                    logger.error("[Updater] 下载更新失败")
                return
            
            if not silent:
                logger.info(f"[Updater] 更新已下载: {filepath}")
            
            # 安装更新（静默模式）
            success = await self.updater.install_update(filepath, silent=silent)
            if success:
                self._pending_update = update_info
                
                # 保存升级状态（用于延迟重启）
                self._upgrade_state = UpdateState(
                    pending_update=True,
                    download_progress=100,
                    install_time=datetime.now().isoformat(),
                    target_version=update_info['latest_version'],
                    current_version=update_info['current_version']
                )
                save_state(self._upgrade_state)
                
                if not silent:
                    # 非静默模式：显示重启提示
                    logger.info("[Updater] 更新已安装，将在下次空闲时重启")
                    logger.info("\n" + "="*60)
                    logger.info("✨ 新版本已安装，重启客户端生效")
                    logger.info(f"   {update_info['current_version']} → {update_info['latest_version']}")
                    logger.info(f"   重启命令: {self.updater.get_restart_command()}")
                    logger.info("="*60 + "\n")
                else:
                    # 静默模式：仅记录日志，调度延迟重启
                    logger.info(f"[Updater] 静默升级完成: {update_info['current_version']} → {update_info['latest_version']}")
                    logger.info("[Updater] 将在 24 小时后或次日 4:00 自动重启")
                    
                    # 调度延迟重启
                    await self._schedule_delayed_restart()
            else:
                if not silent:
                    logger.error("[Updater] 安装更新失败")
        except Exception as e:
            logger.error(f"[Updater] 后台更新失败: {e}")
    




async def main():
    parser = argparse.ArgumentParser(description="OpenClaw 微信频道客户端")
    parser.add_argument(
        "--openclaw-url",
        default=os.getenv("OPENCLAW_URL", "http://127.0.0.1:18789"),
        help="OpenClaw 服务地址（默认 18789，即 OpenClaw Gateway）"
    )
    parser.add_argument(
        "--relay-url",
        default=os.getenv("RELAY_URL", "wss://claw.7color.vip/ws-channel"),
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