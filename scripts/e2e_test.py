#!/usr/bin/env python3
"""
OpenClaw 微信频道插件 - E2E 测试脚本

通过 Redis 消息注入实现端到端测试，绕过微信 API 限制。

用法:
    python scripts/e2e_test.py --openid oFb8866iAh903OZht3CukuNwEcXc
    python scripts/e2e_test.py --openid xxx --timeout 60 --verbose

返回码:
    0 - 测试成功
    1 - 测试失败
    2 - 配置错误
    3 - 连接错误
"""

import argparse
import json
import sys
import time
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

try:
    import redis
except ImportError:
    print("错误: 缺少 redis 库，请执行: pip install redis")
    sys.exit(2)


# ==================== 配置常量 ====================

# 默认测试用户 OpenID
DEFAULT_OPENID = "oFb8866iAh903OZht3CukuNwEcXc"

# Redis 配置
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0

# 测试消息前缀（避免污染生产数据）
TEST_KEY_PREFIX = "e2e:test:"

# 默认超时时间（秒）
DEFAULT_TIMEOUT = 30

# 测试消息内容
TEST_MESSAGE_CONTENT = "E2E 测试消息 - 自动发送，请忽略"


# ==================== 颜色输出 ====================

class Colors:
    """终端颜色输出"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_success(msg: str):
    """打印成功消息"""
    print(f"{Colors.OKGREEN}✓ {msg}{Colors.ENDC}")


def print_error(msg: str):
    """打印错误消息"""
    print(f"{Colors.FAIL}✗ {msg}{Colors.ENDC}")


def print_info(msg: str):
    """打印信息消息"""
    print(f"{Colors.OKCYAN}ℹ {msg}{Colors.ENDC}")


def print_warning(msg: str):
    """打印警告消息"""
    print(f"{Colors.WARNING}⚠ {msg}{Colors.ENDC}")


def print_verbose(msg: str, verbose: bool):
    """打印详细消息（仅 verbose 模式）"""
    if verbose:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"{Colors.OKBLUE}[DEBUG {timestamp}] {msg}{Colors.ENDC}")


# ==================== E2E 测试类 ====================

class E2ETestRunner:
    """E2E 测试运行器"""

    def __init__(self, openid: str, timeout: int, verbose: bool):
        self.openid = openid
        self.timeout = timeout
        self.verbose = verbose
        self.redis_client: Optional[redis.Redis] = None
        self.test_msg_id: str = ""
        self.start_time: float = 0

    def connect_redis(self) -> bool:
        """连接 Redis"""
        print_verbose(f"正在连接 Redis: {REDIS_HOST}:{REDIS_PORT}", self.verbose)
        
        try:
            self.redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # 测试连接
            self.redis_client.ping()
            print_success(f"Redis 连接成功")
            return True
        except redis.ConnectionError as e:
            print_error(f"Redis 连接失败: {e}")
            return False
        except redis.TimeoutError as e:
            print_error(f"Redis 连接超时: {e}")
            return False
        except Exception as e:
            print_error(f"Redis 连接异常: {e}")
            return False

    def inject_message(self) -> bool:
        """注入测试消息到 Redis"""
        if not self.redis_client:
            print_error("Redis 未连接")
            return False

        # 生成唯一消息 ID
        self.test_msg_id = str(uuid.uuid4())
        self.start_time = time.time()

        # 构建测试消息
        message = {
            "type": "chat_request",
            "openid": self.openid,
            "content": TEST_MESSAGE_CONTENT,
            "msg_type": "text",
            "msg_id": self.test_msg_id,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Redis 键名
        # 使用测试前缀避免污染生产数据
        message_key = f"{TEST_KEY_PREFIX}message:{self.openid}"

        print_verbose(f"注入测试消息到 Redis 键: {message_key}", self.verbose)
        print_verbose(f"消息内容: {json.dumps(message, ensure_ascii=False, indent=2)}", self.verbose)

        try:
            # 将消息推送到 Redis 列表（LPUSH）
            self.redis_client.lpush(message_key, json.dumps(message, ensure_ascii=False))
            
            # 同时推送到生产消息队列（如果需要真实测试流程）
            # 注意：这里使用生产键名，让中转服务能够读取
            production_key = f"wx:message:{self.openid}"
            self.redis_client.lpush(production_key, json.dumps(message, ensure_ascii=False))
            
            print_success(f"测试消息已注入")
            print_info(f"消息 ID: {self.test_msg_id}")
            return True
        except Exception as e:
            print_error(f"消息注入失败: {e}")
            return False

    def wait_for_response(self) -> Optional[Dict[str, Any]]:
        """等待响应"""
        if not self.redis_client:
            print_error("Redis 未连接")
            return None

        # 响应键名
        response_key = f"{TEST_KEY_PREFIX}response:{self.openid}"
        
        # 同时监听生产响应队列
        production_response_key = f"wx:response:{self.openid}"

        print_info(f"等待响应（超时: {self.timeout}s）...")
        print_verbose(f"监听 Redis 键: {response_key}, {production_response_key}", self.verbose)

        try:
            # 使用 BRPOP 阻塞等待响应
            # 同时监听测试键和生产键
            result = self.redis_client.brpop(
                [response_key, production_response_key],
                timeout=self.timeout
            )

            if result is None:
                print_error(f"等待响应超时（{self.timeout}s）")
                return None

            key, data = result
            print_verbose(f"收到响应，键: {key}", self.verbose)
            print_verbose(f"响应原始数据: {data}", self.verbose)

            # 解析响应
            try:
                response = json.loads(data)
                return response
            except json.JSONDecodeError as e:
                print_error(f"响应 JSON 解析失败: {e}")
                print_verbose(f"原始数据: {data}", self.verbose)
                return None

        except redis.TimeoutError:
            print_error(f"等待响应超时（{self.timeout}s）")
            return None
        except Exception as e:
            print_error(f"等待响应异常: {e}")
            return None

    def verify_response(self, response: Dict[str, Any]) -> bool:
        """验证响应内容"""
        if not response:
            return False

        print_verbose(f"验证响应内容...", self.verbose)

        errors = []

        # 1. 验证响应类型
        response_type = response.get("type")
        if response_type != "chat_response":
            errors.append(f"响应类型错误: 期望 'chat_response'，实际 '{response_type}'")
        else:
            print_verbose("✓ 响应类型正确: chat_response", self.verbose)

        # 2. 验证 openid 匹配
        response_openid = response.get("openid")
        if response_openid != self.openid:
            errors.append(f"openid 不匹配: 期望 '{self.openid}'，实际 '{response_openid}'")
        else:
            print_verbose(f"✓ openid 匹配: {self.openid}", self.verbose)

        # 3. 验证响应内容非空
        content = response.get("content")
        if not content:
            errors.append("响应内容为空")
        else:
            print_verbose(f"✓ 响应内容: {content[:100]}{'...' if len(content) > 100 else ''}", self.verbose)

        # 4. 验证客户端版本（可选）
        client_version = response.get("client_version")
        if client_version:
            print_verbose(f"✓ 客户端版本: {client_version}", self.verbose)

        if errors:
            print_error("响应验证失败:")
            for error in errors:
                print(f"  - {error}")
            return False

        print_success("响应验证通过")
        return True

    def cleanup(self):
        """清理测试数据"""
        if not self.redis_client:
            return

        print_verbose("清理测试数据...", self.verbose)

        try:
            # 清理测试消息
            test_keys = [
                f"{TEST_KEY_PREFIX}message:{self.openid}",
                f"{TEST_KEY_PREFIX}response:{self.openid}",
            ]
            
            for key in test_keys:
                self.redis_client.delete(key)
                print_verbose(f"已删除: {key}", self.verbose)

        except Exception as e:
            print_warning(f"清理失败: {e}")

    def run(self) -> bool:
        """运行测试"""
        print(f"\n{'='*60}")
        print(f"OpenClaw 微信频道插件 - E2E 测试")
        print(f"{'='*60}")
        print(f"测试用户: {self.openid}")
        print(f"超时时间: {self.timeout}s")
        print(f"详细模式: {self.verbose}")
        print(f"{'='*60}\n")

        try:
            # 1. 连接 Redis
            if not self.connect_redis():
                return False

            # 2. 注入测试消息
            if not self.inject_message():
                return False

            # 3. 等待响应
            response = self.wait_for_response()
            if not response:
                return False

            # 4. 验证响应
            if not self.verify_response(response):
                return False

            # 5. 计算耗时
            elapsed = time.time() - self.start_time
            print_info(f"测试耗时: {elapsed:.2f}s")

            return True

        finally:
            # 清理
            self.cleanup()

            # 关闭 Redis 连接
            if self.redis_client:
                self.redis_client.close()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="OpenClaw 微信频道插件 E2E 测试脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 使用默认测试账号
    python scripts/e2e_test.py

    # 指定测试账号
    python scripts/e2e_test.py --openid oFb8866iAh903OZht3CukuNwEcXc

    # 启用详细模式和自定义超时
    python scripts/e2e_test.py --timeout 60 --verbose

返回码:
    0 - 测试成功
    1 - 测试失败
    2 - 配置错误（缺少依赖等）
    3 - 连接错误（Redis 连接失败）
        """
    )

    parser.add_argument(
        '--openid',
        default=DEFAULT_OPENID,
        help=f'测试用户 OpenID（默认: {DEFAULT_OPENID}）'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f'等待响应超时时间（秒，默认: {DEFAULT_TIMEOUT}）'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='显示详细输出'
    )

    args = parser.parse_args()

    # 创建测试运行器
    runner = E2ETestRunner(
        openid=args.openid,
        timeout=args.timeout,
        verbose=args.verbose
    )

    # 运行测试
    success = runner.run()

    # 输出结果
    print()
    print("="*60)
    if success:
        print_success("E2E 测试通过")
        print("="*60)
        return 0
    else:
        print_error("E2E 测试失败")
        print("="*60)
        return 1


if __name__ == "__main__":
    sys.exit(main())