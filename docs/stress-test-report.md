# OpenClaw 微信频道插件 - 压力测试报告

> 版本: v1.0.0
> 创建日期: 2026-03-24
> 测试环境: 预生产环境

---

## 一、测试目标

验证系统在 **10 万用户规模**下的性能表现，确保：

1. **连接稳定性**：WebSocket 长连接可靠建立和维持
2. **消息吞吐量**：消息收发延迟在可接受范围内
3. **系统容量**：识别系统瓶颈和极限承载能力
4. **故障恢复**：高负载下的自动恢复能力

### 1.1 性能基准

| 指标 | 目标值 | 说明 |
|------|--------|------|
| P50 响应时间 | < 100ms | 50% 请求的响应时间 |
| P95 响应时间 | < 500ms | 95% 请求的响应时间 |
| P99 响应时间 | < 1000ms | 99% 请求的响应时间 |
| 吞吐量 | > 1000 QPS | 每秒处理请求数 |
| 错误率 | < 0.1% | 请求失败比例 |
| 连接成功率 | > 99.9% | WebSocket 连接建立成功率 |

---

## 二、测试场景设计

### 2.1 场景一：基础连接测试 (100 用户)

**目的**：验证基本功能正常

| 参数 | 值 |
|------|-----|
| 并发用户数 | 100 |
| 启动速率 | 10 用户/秒 |
| 测试时长 | 5 分钟 |
| 测试类型 | 快速连接/断开 |

**预期结果**：
- 所有连接成功建立
- 响应时间 < 50ms
- 错误率 = 0%

**测试命令**：
```bash
locust -f scripts/locustfile.py --headless -u 100 -r 10 -t 5m --ws-url wss://claw.7color.vip/ws-channel
```

### 2.2 场景二：中等负载测试 (1000 用户)

**目的**：验证中等规模下的系统稳定性

| 参数 | 值 |
|------|-----|
| 并发用户数 | 1000 |
| 启动速率 | 50 用户/秒 |
| 测试时长 | 15 分钟 |
| 测试类型 | 混合场景（连接 + 消息 + 心跳） |

**预期结果**：
- P95 响应时间 < 200ms
- 错误率 < 0.01%
- 内存使用 < 2GB

**测试命令**：
```bash
locust -f scripts/locustfile.py --headless -u 1000 -r 50 -t 15m --test-scenario mixed --ws-url wss://claw.7color.vip/ws-channel
```

### 2.3 场景三：高负载测试 (10000 用户)

**目的**：验证高负载下的系统表现和瓶颈

| 参数 | 值 |
|------|-----|
| 并发用户数 | 10000 |
| 启动速率 | 100 用户/秒 |
| 测试时长 | 30 分钟 |
| 测试类型 | 消息吞吐量测试 |

**预期结果**：
- P99 响应时间 < 500ms
- 错误率 < 0.1%
- 识别系统瓶颈点

**测试命令**：
```bash
locust -f scripts/locustfile.py --headless -u 10000 -r 100 -t 30m --test-scenario throughput --ws-url wss://claw.7color.vip/ws-channel
```

### 2.4 场景四：极限压力测试 (100000 用户)

**目的**：验证系统极限承载能力

| 参数 | 值 |
|------|-----|
| 并发用户数 | 100000 |
| 启动速率 | 500 用户/秒 |
| 测试时长 | 60 分钟 |
| 测试类型 | 分布式压力测试 |

**注意**：此场景需要多台压测机分布式执行。

**预期结果**：
- 识别系统崩溃点
- 验证熔断机制
- 记录资源消耗峰值

---

## 三、预期瓶颈分析

### 3.1 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        压力测试架构                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐      │
│   │ Locust 压测机│ ... │ Locust 压测机│     │ Locust 压测机│      │
│   │  (客户端模拟) │     │  (客户端模拟) │     │  (客户端模拟) │      │
│   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘      │
│          │                   │                   │              │
│          └───────────────────┼───────────────────┘              │
│                              │                                  │
│                              ▼                                  │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │                    ECS 服务端                            │  │
│   │  ┌──────────────────────────────────────────────────┐   │  │
│   │  │              Nginx (反向代理)                      │   │  │
│   │  │              端口: 443 (HTTPS)                    │   │  │
│   │  └──────────────────────┬───────────────────────────┘   │  │
│   │                         │                                │  │
│   │  ┌──────────────────────▼───────────────────────────┐   │  │
│   │  │           FastAPI + WebSocket                     │   │  │
│   │  │           端口: 8765                               │   │  │
│   │  │           ⚠️ 瓶颈点 1: 连接池内存                   │   │  │
│   │  │           ⚠️ 瓶颈点 2: 单进程事件循环               │   │  │
│   │  └──────────────────────┬───────────────────────────┘   │  │
│   │                         │                                │  │
│   │  ┌──────────────────────▼───────────────────────────┐   │  │
│   │  │              Redis (单节点)                       │   │  │
│   │  │              端口: 6379                           │   │  │
│   │  │              ⚠️ 瓶颈点 3: 单节点 QPS 上限           │   │  │
│   │  │              ⚠️ 瓶颈点 4: 内存容量                 │   │  │
│   │  └──────────────────────────────────────────────────┘   │  │
│   └─────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 瓶颈点详细分析

#### 瓶颈点 1：WebSocket 连接数限制

**位置**：`relay/src/services/connection_pool.py`

**当前实现**：
```python
class ConnectionPool:
    def __init__(self):
        # device_id -> UserConnection (内存存储)
        self._connections: Dict[str, UserConnection] = {}
        # device_id -> WebSocket (内存存储)
        self._websockets: Dict[str, WebSocket] = {}
```

**问题分析**：
- 每个连接占用约 **10-20KB 内存**（WebSocket 对象 + UserConnection 对象）
- 10000 连接 ≈ **100-200MB**
- 100000 连接 ≈ **1-2GB**
- 单进程内存限制可能导致 OOM

**预期瓶颈值**：
| 连接数 | 内存占用 | 风险等级 |
|--------|----------|----------|
| 1,000 | 10-20MB | 低 |
| 10,000 | 100-200MB | 中 |
| 50,000 | 500MB-1GB | 高 |
| 100,000 | 1-2GB | 极高 |

#### 瓶颈点 2：Redis 单节点瓶颈

**位置**：`relay/src/services/redis_service.py`

**当前实现**：
```python
class RedisService:
    def __init__(self, url: str):
        self._client: Optional[aioredis.Redis] = None

    async def increment_user_usage(self, openid: str) -> int:
        # 每条消息都会触发 Redis 写入
        key = f"credits:{openid}:{today}"
        new_value = await self.client.incr(key)
```

**问题分析**：
- 单节点 Redis QPS 上限约 **10-15 万**
- 每条消息至少 2-3 次 Redis 操作（绑定查询 + 用量增加）
- 高并发时 Redis 成为性能瓶颈

**预期瓶颈值**：
| 消息 QPS | Redis 操作 QPS | 风险等级 |
|----------|----------------|----------|
| 1,000 | 2,000-3,000 | 低 |
| 5,000 | 10,000-15,000 | 中 |
| 10,000 | 20,000-30,000 | 高 |
| 50,000 | 100,000-150,000 | 极高 |

#### 瓶颈点 3：消息处理延迟

**位置**：`relay/src/routers/websocket.py`

**当前实现**：
```python
async def handle_chat_response(device_id: str, data: dict):
    # 同步调用微信 API
    success = await wechat.send_text_message(openid, content)
```

**问题分析**：
- 微信 API 调用延迟约 **100-500ms**
- 同步等待会导致消息堆积
- 高并发时响应延迟显著增加

**预期延迟分布**：
| 并发数 | 平均延迟 | P99 延迟 |
|--------|----------|----------|
| 100 | 50ms | 100ms |
| 1,000 | 100ms | 300ms |
| 10,000 | 300ms | 800ms |
| 50,000 | 500ms+ | 2000ms+ |

#### 瓶颈点 4：单进程事件循环

**位置**：`relay/src/main.py`

**当前实现**：
```python
# 单进程 uvicorn
uvicorn.run("src.main:app", host="0.0.0.0", port=8765)
```

**问题分析**：
- Python GIL 限制单进程 CPU 利用率
- 大量 WebSocket 连接竞争事件循环
- 单进程无法充分利用多核 CPU

**预期瓶颈值**：
| 连接数 | CPU 利用率 | 处理能力 |
|--------|------------|----------|
| 1,000 | 10-20% | 正常 |
| 10,000 | 50-70% | 接近瓶颈 |
| 50,000 | 90%+ | 瓶颈 |
| 100,000 | 100% | 过载 |

---

## 四、优化建议

### 4.1 短期优化（预期提升 2-5 倍）

#### 4.1.1 Redis 连接池优化

```python
# 当前：单连接
self._client = await aioredis.from_url(url)

# 优化：连接池
self._client = await aioredis.from_url(
    url,
    max_connections=100,  # 连接池大小
    socket_keepalive=True,
    socket_keepalive_options={
        socket.TCP_KEEPIDLE: 60,
        socket.TCP_KEEPINTVL: 10,
        socket.TCP_KEEPCNT: 3
    }
)
```

**预期效果**：Redis 吞吐量提升 3-5 倍

#### 4.1.2 Redis Pipeline 批量操作

```python
# 当前：逐个操作
await self.client.get(f"device:{device_id}")
await self.client.get(f"user:{openid}:vip")

# 优化：Pipeline 批量
async with self.client.pipeline() as pipe:
    pipe.get(f"device:{device_id}")
    pipe.get(f"user:{openid}:vip")
    results = await pipe.execute()
```

**预期效果**：Redis 操作延迟降低 50%

#### 4.1.3 消息处理异步化

```python
# 当前：同步等待
success = await wechat.send_text_message(openid, content)

# 优化：异步队列
import asyncio
from collections import deque

message_queue = deque()
async def message_worker():
    while True:
        msg = message_queue.popleft()
        await wechat.send_text_message(msg.openid, msg.content)
```

**预期效果**：消息处理吞吐量提升 2-3 倍

### 4.2 中期优化（预期提升 10 倍）

#### 4.2.1 Redis 集群方案

```
┌─────────────────────────────────────────────────────────────────┐
│                     Redis Cluster 架构                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐      │
│   │  Redis Master│     │  Redis Master│     │  Redis Master│      │
│   │  (Slot 0-5460)│    │ (Slot 5461-10922)│  │(Slot 10923-16383)│   │
│   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘      │
│          │                   │                   │              │
│   ┌──────▼──────┐     ┌──────▼──────┐     ┌──────▼──────┐      │
│   │ Redis Slave │     │ Redis Slave │     │ Redis Slave │      │
│   └─────────────┘     └─────────────┘     └─────────────┘      │
│                                                                 │
│   总 QPS: 30-50 万 (原单节点: 10-15 万)                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**配置示例**：
```yaml
# redis-cluster.conf
cluster-enabled yes
cluster-config-file nodes.conf
cluster-node-timeout 5000
```

**预期效果**：
- QPS 从 10-15 万提升至 30-50 万
- 高可用：单节点故障不影响服务

#### 4.2.2 多进程部署

```bash
# 当前：单进程
uvicorn src.main:app --host 0.0.0.0 --port 8765

# 优化：多进程 + Nginx 负载均衡
uvicorn src.main:app --host 0.0.0.0 --port 8765 --workers 4
```

**Nginx 配置**：
```nginx
upstream websocket_backend {
    least_conn;  # 最少连接负载均衡
    server 127.0.0.1:8765;
    server 127.0.0.1:8766;
    server 127.0.0.1:8767;
    server 127.0.0.1:8768;
}

server {
    listen 443 ssl;
    server_name claw.7color.vip;

    location /ws-channel {
        proxy_pass http://websocket_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

**预期效果**：
- 连接容量提升 4 倍
- CPU 利用率从 100% 降至 25%/进程

### 4.3 长期优化（预期提升 100 倍）

#### 4.3.1 消息队列架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     消息队列架构                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐      │
│   │ WebSocket   │     │ WebSocket   │     │ WebSocket   │      │
│   │   Server    │     │   Server    │     │   Server    │      │
│   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘      │
│          │                   │                   │              │
│          └───────────────────┼───────────────────┘              │
│                              │                                  │
│                              ▼                                  │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │                 Kafka / RabbitMQ                         │  │
│   │              (消息缓冲队列)                              │  │
│   └─────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐      │
│   │   Worker    │     │   Worker    │     │   Worker    │      │
│   │  (消费消息)  │     │  (消费消息)  │     │  (消费消息)  │      │
│   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘      │
│          │                   │                   │              │
│          └───────────────────┼───────────────────┘              │
│                              │                                  │
│                              ▼                                  │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │                 微信 API                                 │  │
│   └─────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**预期效果**：
- 消息处理解耦，支持水平扩展
- 峰值流量平滑处理
- 系统整体吞吐量提升 100 倍

#### 4.3.2 分布式连接池

```python
# 当前：内存连接池
self._connections: Dict[str, UserConnection] = {}

# 优化：Redis 分布式连接池
class DistributedConnectionPool:
    async def register(self, device_id: str, websocket: WebSocket):
        # 连接元数据存 Redis
        await redis.hset(
            "connections:metadata",
            device_id,
            json.dumps({"openid": openid, "connected_at": now})
        )
        # WebSocket 路由信息存本地
        self._local_websockets[device_id] = websocket
```

**预期效果**：
- 支持跨进程连接查询
- 无限水平扩展能力

---

## 五、监控指标

### 5.1 Prometheus 指标

已在 `relay/src/metrics.py` 中定义：

| 指标名 | 类型 | 说明 |
|--------|------|------|
| `wechat_active_connections` | Gauge | 活跃 WebSocket 连接数 |
| `wechat_message_latency_seconds` | Histogram | 消息处理延迟 |
| `wechat_errors_total` | Counter | 错误总数 |
| `wechat_messages_total` | Counter | 消息总数 |
| `wechat_connections_total` | Counter | 连接总数 |

### 5.2 关键监控仪表盘

```
┌─────────────────────────────────────────────────────────────────┐
│                     Grafana 监控仪表盘                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────┐  ┌─────────────────────┐              │
│  │   活跃连接数         │  │   消息吞吐量         │              │
│  │   当前: 5,234       │  │   当前: 1,234 QPS   │              │
│  │   峰值: 10,000      │  │   峰值: 5,000 QPS   │              │
│  └─────────────────────┘  └─────────────────────┘              │
│                                                                 │
│  ┌─────────────────────┐  ┌─────────────────────┐              │
│  │   响应时间 (P99)     │  │   错误率            │              │
│  │   当前: 156ms       │  │   当前: 0.01%       │              │
│  │   目标: < 500ms     │  │   目标: < 0.1%      │              │
│  └─────────────────────┘  └─────────────────────┘              │
│                                                                 │
│  ┌─────────────────────┐  ┌─────────────────────┐              │
│  │   Redis 内存使用     │  │   CPU 使用率        │              │
│  │   当前: 512MB       │  │   当前: 45%         │              │
│  │   上限: 4GB         │  │   上限: 80%         │              │
│  └─────────────────────┘  └─────────────────────┘              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 告警规则

```yaml
# alert_rules.yml
groups:
  - name: wechat-channel
    rules:
      # 连接数告警
      - alert: HighConnectionCount
        expr: wechat_active_connections > 50000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "WebSocket 连接数过高"
          description: "当前连接数 {{ $value }}，超过阈值 50000"

      # 响应时间告警
      - alert: HighLatency
        expr: histogram_quantile(0.99, wechat_message_latency_seconds) > 0.5
        for: 3m
        labels:
          severity: warning
        annotations:
          summary: "消息处理延迟过高"
          description: "P99 延迟 {{ $value }}s，超过阈值 0.5s"

      # 错误率告警
      - alert: HighErrorRate
        expr: rate(wechat_errors_total[5m]) / rate(wechat_messages_total[5m]) > 0.001
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "错误率过高"
          description: "错误率 {{ $value }}，超过阈值 0.1%"
```

---

## 六、测试执行计划

### 6.1 测试前准备

| 步骤 | 操作 | 验证 |
|------|------|------|
| 1 | 备份 Redis 数据 | `redis-cli BGSAVE` |
| 2 | 检查服务健康 | `curl https://claw.7color.vip/api/health` |
| 3 | 启动监控 | Grafana 仪表盘就绪 |
| 4 | 准备压测机 | 安装 Locust，验证网络连通 |

### 6.2 测试执行顺序

```
┌─────────────────────────────────────────────────────────────────┐
│                     测试执行流程                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [1] 基础测试 (100 用户, 5分钟)                                 │
│      ↓                                                          │
│  [2] 分析结果，调整参数                                         │
│      ↓                                                          │
│  [3] 中等负载测试 (1000 用户, 15分钟)                           │
│      ↓                                                          │
│  [4] 分析结果，记录瓶颈                                         │
│      ↓                                                          │
│  [5] 高负载测试 (10000 用户, 30分钟)                            │
│      ↓                                                          │
│  [6] 分析结果，确认瓶颈点                                       │
│      ↓                                                          │
│  [7] 极限测试 (可选, 100000 用户, 60分钟)                       │
│      ↓                                                          │
│  [8] 汇总报告，提出优化建议                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.3 测试命令汇总

```bash
# 场景 1：基础连接测试
locust -f scripts/locustfile.py --headless -u 100 -r 10 -t 5m \
  --ws-url wss://claw.7color.vip/ws-channel \
  --html reports/stress-test-100.html

# 场景 2：中等负载测试
locust -f scripts/locustfile.py --headless -u 1000 -r 50 -t 15m \
  --test-scenario mixed \
  --ws-url wss://claw.7color.vip/ws-channel \
  --html reports/stress-test-1000.html

# 场景 3：高负载测试
locust -f scripts/locustfile.py --headless -u 10000 -r 100 -t 30m \
  --test-scenario throughput \
  --ws-url wss://claw.7color.vip/ws-channel \
  --html reports/stress-test-10000.html

# 场景 4：极限测试（分布式）
# Master 节点
locust -f scripts/locustfile.py --master

# Worker 节点（多台机器）
locust -f scripts/locustfile.py --worker --master-host=<master-ip>
```

---

## 七、风险评估

### 7.1 测试风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 服务崩溃 | 中 | 高 | 准备快速回滚方案 |
| Redis 内存溢出 | 中 | 高 | 设置内存上限 + LRU 淘汰 |
| 网络带宽饱和 | 低 | 中 | 监控网络流量 |
| 影响真实用户 | 高 | 高 | 使用独立测试环境 |

### 7.2 回滚方案

```bash
# 服务崩溃时快速恢复
ssh root@claw.7color.vip << 'EOF'
  # 重启 Redis
  docker restart redis

  # 重启 WebSocket 服务
  docker restart wechat-channel

  # 验证服务恢复
  curl -s https://claw.7color.vip/api/health
EOF
```

---

## 八、结论

### 8.1 预期测试结果

| 用户规模 | 预期表现 | 建议 |
|----------|----------|------|
| 100 | 稳定运行 | 无需优化 |
| 1,000 | 稳定运行 | 监控资源使用 |
| 10,000 | 接近瓶颈 | 实施短期优化 |
| 100,000 | 需要优化 | 实施中长期优化 |

### 8.2 优化优先级

| 优先级 | 优化项 | 预期效果 | 工作量 |
|--------|--------|----------|--------|
| P0 | Redis 连接池 + Pipeline | 3-5 倍提升 | 低 |
| P1 | 多进程部署 | 4 倍提升 | 中 |
| P2 | Redis 集群 | 3-5 倍提升 | 中 |
| P3 | 消息队列架构 | 100 倍提升 | 高 |

---

## 附录

### A. 测试环境配置

| 组件 | 配置 |
|------|------|
| ECS 服务器 | 4 核 8GB |
| Redis | 单节点 4GB |
| 网络带宽 | 10Mbps |

### B. 参考资料

- [Locust 官方文档](https://docs.locust.io/)
- [Redis 性能优化指南](https://redis.io/docs/management/optimization/)
- [FastAPI 性能最佳实践](https://fastapi.tiangolo.com/deployment/concepts/)

---

> 报告创建者: OpenCode AI
> 最后更新: 2026-03-24