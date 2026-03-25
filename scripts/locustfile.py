"""
OpenClaw 微信频道插件 - Locust 压力测试脚本

使用方法:
    # Web UI 模式（默认）
    locust -f scripts/locustfile.py

    # Headless 模式
    locust -f scripts/locustfile.py --headless -u 10 -r 2 -t 60s --host wss://claw.7color.vip

参数说明:
    -u, --users: 用户数
    -r, --spawn-rate: 每秒启动用户数
    -t, --run-time: 运行时间 (如 60s, 5m, 1h)

测试场景:
    1. 快速连接测试: 连接建立 -> 立即断开
    2. 消息吞吐量测试: 连接 -> 发送消息 -> 接收响应
    3. 长连接稳定性测试: 保持连接，定期心跳

注意:
    - 此脚本仅用于测试目的，请勿在生产环境运行
    - 使用虚拟用户数据，不涉及真实用户
"""

import json
import time
import uuid
import random
import argparse
from typing import Optional

from locust import User, task, events, between
from locust.argument_parser import LocustArgumentParser
import websocket


# WebSocket 服务地址
DEFAULT_WS_URL = "wss://claw.7color.vip/ws-channel"

# 测试用户 OpenID（用于特定测试）
TEST_OPENID = "oFb8866iAh903OZht3CukuNwEcXc"


@events.init_command_line_parser.add_listener
def _(parser: LocustArgumentParser):
    """添加自定义命令行参数"""
    parser.add_argument(
        "--ws-url",
        type=str,
        default=DEFAULT_WS_URL,
        help="WebSocket 服务地址 (默认: wss://claw.7color.vip/ws-channel)"
    )
    parser.add_argument(
        "--test-scenario",
        type=str,
        default="mixed",
        choices=["connect", "throughput", "stability", "mixed"],
        help="测试场景: connect(连接测试), throughput(吞吐量), stability(稳定性), mixed(混合)"
    )
    parser.add_argument(
        "--message-interval",
        type=float,
        default=1.0,
        help="消息发送间隔（秒），用于 throughput 和 stability 场景"
    )


class WeChatChannelUser(User):
    """
    微信频道用户模拟器

    模拟真实的 WebSocket 客户端行为：
    1. 建立连接
    2. 发送注册消息
    3. 接收/发送消息
    4. 保持心跳
    5. 断开重连
    """

    # 用户等待时间
    wait_time = between(1, 3)

    def __init__(self, environment):
        super().__init__(environment)
        self.ws: Optional[websocket.WebSocket] = None
        self.device_id: str = ""
        self.connected: bool = False
        self.authorized: bool = False
        self.message_count: int = 0

        # 从环境获取配置
        self.ws_url = environment.parsed_options.ws_url
        self.test_scenario = environment.parsed_options.test_scenario
        self.message_interval = environment.parsed_options.message_interval

    def on_start(self):
        """用户开始时初始化"""
        # 生成唯一的设备 ID
        self.device_id = self._generate_device_id()
        self._connect()

    def on_stop(self):
        """用户结束时清理"""
        self._disconnect()

    def _generate_device_id(self) -> str:
        """生成虚拟设备 ID"""
        device_types = ["bare", "ecs", "docker_local", "docker_cloud"]
        device_type = random.choice(device_types)
        machine_id = uuid.uuid4().hex[:16]
        timestamp = int(time.time())
        random_suffix = uuid.uuid4().hex[:4]
        return f"{device_type}_{machine_id}_testuser_{timestamp}_{random_suffix}"

    def _connect(self):
        """建立 WebSocket 连接"""
        start_time = time.time()

        try:
            # 创建 WebSocket 连接
            self.ws = websocket.create_connection(
                self.ws_url,
                timeout=10
            )

            # 发送注册消息
            register_msg = {
                "type": "register",
                "instance_type": "local",
                "device_id": self.device_id,
                "device_type": self.device_id.split("_")[0],
                "machine_id": self.device_id.split("_")[1],
                "system_username": "locust_test",
                "client_version": "1.2.0",
                "min_server_version": "1.0.0",
                "is_new_device": True
            }
            self.ws.send(json.dumps(register_msg))

            # 等待注册响应
            response = self.ws.recv()
            response_time = (time.time() - start_time) * 1000

            data = json.loads(response)

            if data.get("type") == "registered":
                self.connected = True
                events.request.fire(
                    request_type="ws",
                    name="connect",
                    response_time=response_time,
                    response_length=len(response),
                    exception=None
                )
            elif data.get("type") == "error":
                events.request.fire(
                    request_type="ws",
                    name="connect",
                    response_time=response_time,
                    response_length=0,
                    exception=Exception(data.get("message", "Registration failed"))
                )

        except Exception as e:
            events.request.fire(
                request_type="ws",
                name="connect",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=e
            )

    def _disconnect(self):
        """断开连接"""
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
        self.connected = False
        self.ws = None

    def _send_message(self, msg_type: str, content: str) -> bool:
        """
        发送消息并等待响应

        Args:
            msg_type: 消息类型
            content: 消息内容

        Returns:
            bool: 是否成功
        """
        if not self.connected or not self.ws:
            return False

        start_time = time.time()

        try:
            message = {
                "type": msg_type,
                "openid": f"test_user_{self.message_count}",
                "content": content,
                "client_version": "1.2.0"
            }

            self.ws.send(json.dumps(message))

            # 等待响应（带超时）
            self.ws.settimeout(5)
            response = self.ws.recv()
            response_time = (time.time() - start_time) * 1000

            events.request.fire(
                request_type="ws",
                name="send_message",
                response_time=response_time,
                response_length=len(response),
                exception=None
            )

            self.message_count += 1
            return True

        except websocket.WebSocketTimeoutException:
            events.request.fire(
                request_type="ws",
                name="send_message",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=Exception("Timeout waiting for response")
            )
            return False

        except Exception as e:
            events.request.fire(
                request_type="ws",
                name="send_message",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=e
            )
            return False

    def _send_ping(self) -> bool:
        """发送心跳"""
        if not self.connected or not self.ws:
            return False

        start_time = time.time()

        try:
            self.ws.send(json.dumps({"type": "ping"}))
            self.ws.settimeout(5)
            response = self.ws.recv()

            response_time = (time.time() - start_time) * 1000
            data = json.loads(response)

            if data.get("type") == "pong":
                events.request.fire(
                    request_type="ws",
                    name="ping",
                    response_time=response_time,
                    response_length=len(response),
                    exception=None
                )
                return True

        except Exception as e:
            events.request.fire(
                request_type="ws",
                name="ping",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=e
            )

        return False

    # ==================== 测试任务 ====================

    @task(3)
    class ConnectTest(User):
        """
        场景 1: 快速连接测试

        测试连接建立和断开的性能
        """

        @task
        def connect_disconnect(self):
            """连接 -> 断开"""
            if self.connected:
                self._disconnect()
                time.sleep(0.5)
            self._connect()

    @task(5)
    class ThroughputTest(User):
        """
        场景 2: 消息吞吐量测试

        测试消息收发的吞吐量
        """

        @task
        def send_chat_message(self):
            """发送测试消息"""
            if not self.connected:
                self._connect()

            if self.connected:
                # 生成随机消息内容
                messages = [
                    "你好，这是压力测试消息",
                    "测试消息吞吐量",
                    "Hello, stress test!",
                    "这是一条较长的测试消息，用于测试消息传输的稳定性和性能",
                    "特殊字符测试：!@#$%^&*()_+-=[]{}|;':\",./<>?"
                ]
                content = random.choice(messages)

                self._send_message("chat_request", content)
                time.sleep(self.message_interval)

    @task(2)
    class StabilityTest(User):
        """
        场景 3: 长连接稳定性测试

        保持连接，定期发送心跳
        """

        @task
        def keep_alive(self):
            """保持连接心跳"""
            if not self.connected:
                self._connect()

            if self.connected:
                self._send_ping()
                time.sleep(30)  # 每 30 秒一次心跳


class QuickConnectUser(User):
    """
    快速连接测试专用用户类

    仅测试连接建立和断开
    """

    wait_time = between(0.5, 2)

    def __init__(self, environment):
        super().__init__(environment)
        self.ws_url = environment.parsed_options.ws_url
        self.ws: Optional[websocket.WebSocket] = None

    def on_start(self):
        """开始时连接"""
        pass

    def on_stop(self):
        """结束时断开"""
        self._disconnect()

    @task
    def connect_test(self):
        """快速连接测试"""
        start_time = time.time()
        try:
            self.ws = websocket.create_connection(
                self.ws_url,
                timeout=10
            )
            response_time = (time.time() - start_time) * 1000

            events.request.fire(
                request_type="ws",
                name="quick_connect",
                response_time=response_time,
                response_length=0,
                exception=None
            )

            # 立即关闭
            self.ws.close()
            self.ws = None

        except Exception as e:
            events.request.fire(
                request_type="ws",
                name="quick_connect",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=e
            )

    def _disconnect(self):
        """断开连接"""
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None


class MessageThroughputUser(User):
    """
    消息吞吐量测试专用用户类

    持续发送消息测试吞吐量
    """

    wait_time = between(0.1, 0.5)

    def __init__(self, environment):
        super().__init__(environment)
        self.ws_url = environment.parsed_options.ws_url
        self.ws: Optional[websocket.WebSocket] = None
        self.connected: bool = False
        self.device_id: str = ""

    def on_start(self):
        """开始时连接"""
        self.device_id = f"throughput_{uuid.uuid4().hex[:8]}"
        self._connect()

    def on_stop(self):
        """结束时断开"""
        self._disconnect()

    @task
    def send_message(self):
        """发送消息"""
        if not self.connected:
            self._connect()

        if not self.connected or not self.ws:
            return

        start_time = time.time()
        try:
            message = {
                "type": "chat_request",
                "openid": f"throughput_test_{int(time.time())}",
                "content": f"吞吐量测试消息 #{int(time.time() * 1000)}"
            }

            self.ws.send(json.dumps(message))

            # 非阻塞检查（设置短超时）
            self.ws.settimeout(1)
            try:
                response = self.ws.recv()
                response_time = (time.time() - start_time) * 1000
                events.request.fire(
                    request_type="ws",
                    name="throughput_send",
                    response_time=response_time,
                    response_length=len(response),
                    exception=None
                )
            except websocket.WebSocketTimeoutException:
                # 超时不计入失败，继续发送
                pass

        except Exception as e:
            events.request.fire(
                request_type="ws",
                name="throughput_send",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=e
            )
            # 连接可能已断开
            self.connected = False

    def _connect(self):
        """建立连接"""
        if self.connected:
            return

        try:
            self.ws = websocket.create_connection(
                self.ws_url,
                timeout=10
            )

            # 发送注册
            register_msg = {
                "type": "register",
                "instance_type": "local",
                "device_id": self.device_id,
                "device_type": "bare",
                "machine_id": uuid.uuid4().hex[:16],
                "system_username": "throughput_test",
                "client_version": "1.2.0",
                "min_server_version": "1.0.0",
                "is_new_device": True
            }
            self.ws.send(json.dumps(register_msg))

            # 等待注册响应
            self.ws.settimeout(5)
            response = self.ws.recv()
            data = json.loads(response)

            if data.get("type") == "registered":
                self.connected = True

        except Exception:
            self.connected = False
            if self.ws:
                try:
                    self.ws.close()
                except Exception:
                    pass
                self.ws = None

    def _disconnect(self):
        """断开连接"""
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
        self.connected = False
        self.ws = None


class LongConnectionUser(User):
    """
    长连接稳定性测试专用用户类

    保持连接，定期心跳
    """

    wait_time = between(25, 35)  # 心跳间隔

    def __init__(self, environment):
        super().__init__(environment)
        self.ws_url = environment.parsed_options.ws_url
        self.ws: Optional[websocket.WebSocket] = None
        self.connected: bool = False
        self.device_id: str = ""
        self.heartbeat_count: int = 0

    def on_start(self):
        """开始时连接"""
        self.device_id = f"stability_{uuid.uuid4().hex[:8]}"
        self._connect()

    def on_stop(self):
        """结束时断开"""
        self._disconnect()

    @task
    def heartbeat(self):
        """发送心跳"""
        if not self.connected:
            self._connect()

        if not self.connected or not self.ws:
            return

        start_time = time.time()
        try:
            self.ws.send(json.dumps({"type": "ping"}))
            self.ws.settimeout(10)
            response = self.ws.recv()

            response_time = (time.time() - start_time) * 1000
            data = json.loads(response)

            if data.get("type") == "pong":
                self.heartbeat_count += 1
                events.request.fire(
                    request_type="ws",
                    name="heartbeat",
                    response_time=response_time,
                    response_length=len(response),
                    exception=None
                )
            else:
                events.request.fire(
                    request_type="ws",
                    name="heartbeat",
                    response_time=response_time,
                    response_length=len(response),
                    exception=Exception(f"Unexpected response: {data.get('type')}")
                )

        except Exception as e:
            events.request.fire(
                request_type="ws",
                name="heartbeat",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=e
            )
            # 连接可能已断开
            self.connected = False

    def _connect(self):
        """建立连接"""
        if self.connected:
            return

        try:
            self.ws = websocket.create_connection(
                self.ws_url,
                timeout=10
            )

            register_msg = {
                "type": "register",
                "instance_type": "local",
                "device_id": self.device_id,
                "device_type": "bare",
                "machine_id": uuid.uuid4().hex[:16],
                "system_username": "stability_test",
                "client_version": "1.2.0",
                "min_server_version": "1.0.0",
                "is_new_device": True
            }
            self.ws.send(json.dumps(register_msg))

            self.ws.settimeout(5)
            response = self.ws.recv()
            data = json.loads(response)

            if data.get("type") == "registered":
                self.connected = True
                events.request.fire(
                    request_type="ws",
                    name="stability_connect",
                    response_time=0,
                    response_length=0,
                    exception=None
                )

        except Exception as e:
            events.request.fire(
                request_type="ws",
                name="stability_connect",
                response_time=0,
                response_length=0,
                exception=e
            )
            self.connected = False
            if self.ws:
                try:
                    self.ws.close()
                except Exception:
                    pass
                self.ws = None

    def _disconnect(self):
        """断开连接"""
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
        self.connected = False
        self.ws = None


# ==================== 场景选择 ====================

# 根据命令行参数选择测试场景
# 默认使用 WeChatChannelUser（混合场景）


if __name__ == "__main__":
    """
    直接运行示例：

        python scripts/locustfile.py

    这将显示帮助信息。使用 locust 命令运行：

        locust -f scripts/locustfile.py --headless -u 10 -r 2 -t 60s
    """
    print(__doc__)
    print("\n使用 locust 命令运行此脚本:")
    print("  locust -f scripts/locustfile.py")
    print("\nHeadless 模式:")
    print("  locust -f scripts/locustfile.py --headless -u 10 -r 2 -t 60s")
    print("\n自定义参数:")
    print("  locust -f scripts/locustfile.py --headless -u 10 -r 2 -t 60s --ws-url wss://claw.7color.vip/ws-channel")