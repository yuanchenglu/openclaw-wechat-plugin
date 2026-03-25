# 灰度发布架构设计文档

> 版本: v1.0.0
> 更新时间: 2026-03-24
> 状态: 设计中

---

## 一、概述

### 1.1 什么是灰度发布

灰度发布（Canary Deployment）是一种渐进式发布策略，通过将部分流量导向新版本服务，在真实生产环境中验证新版本的稳定性和正确性，逐步扩大流量比例直至全量发布。

```
┌─────────────────────────────────────────────────────────────────────┐
│                      灰度发布流量分配示意图                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   用户请求 ─────────────────────────────────────────┐              │
│                                                      │              │
│                                                      ▼              │
│                              ┌───────────────────────────────┐      │
│                              │       流量路由层              │      │
│                              │   (基于 device_id 哈希)       │      │
│                              └───────────┬───────────────────┘      │
│                                          │                          │
│                     ┌────────────────────┼────────────────────┐     │
│                     │                    │                    │     │
│                     ▼                    ▼                    ▼     │
│              ┌────────────┐       ┌────────────┐       ┌────────────┐
│              │  稳定版本  │       │  灰度版本  │       │  其他版本  │
│              │   v1.2.0   │       │   v1.3.0   │       │   (预留)   │
│              │   (90%)    │       │   (10%)    │       │    (0%)    │
│              └────────────┘       └────────────┘       └────────────┘
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 为什么需要灰度发布

| 问题 | 传统发布 | 灰度发布 |
|------|----------|----------|
| Bug 影响 | 全量用户受影响 | 仅部分用户受影响 |
| 回滚速度 | 需要重新部署全量 | 自动/快速回滚 |
| 风险控制 | 发布即全量，风险高 | 逐步验证，风险可控 |
| 问题定位 | 全量日志混杂 | 灰度版本独立监控 |

### 1.3 适用场景

1. **服务端版本升级**：WebSocket 服务、API 接口变更
2. **协议变更**：消息格式、通信协议升级
3. **重大功能发布**：新增功能模块、架构调整
4. **性能优化验证**：在真实流量下验证优化效果

---

## 二、灰度路由算法

### 2.1 核心原理

基于 `device_id` 进行哈希计算，确保同一设备始终路由到同一版本（一致性）。

```
路由公式:
    hash_value = MD5(device_id) → 取前 8 位转整数
    percentage = (hash_value % 10000) / 100    # 得到 0.00 ~ 99.99 的值
    version = 灰度配置.lookup(percentage)
```

### 2.2 一致性保证

**关键特性**：同一 `device_id` 在灰度比例不变的情况下，始终路由到同一版本。

```python
def get_canary_version(device_id: str, canary_config: dict) -> str:
    """
    根据 device_id 计算灰度版本
    
    Args:
        device_id: 设备唯一标识，格式 {type}_{machine_id}_{username}_{timestamp}_{random}
        canary_config: 灰度配置
            {
                "stable_version": "1.2.0",
                "canary_version": "1.3.0",
                "canary_percentage": 10,  # 0-100
            }
    
    Returns:
        版本号: "1.2.0" 或 "1.3.0"
    """
    import hashlib
    
    # 1. 计算 device_id 的哈希值
    hash_hex = hashlib.md5(device_id.encode()).hexdigest()[:8]
    hash_int = int(hash_hex, 16)
    
    # 2. 计算该设备落入的百分位 (0.00 ~ 99.99)
    percentage = (hash_int % 10000) / 100
    
    # 3. 判断是否命中灰度版本
    if percentage < canary_config["canary_percentage"]:
        return canary_config["canary_version"]
    else:
        return canary_config["stable_version"]
```

### 2.3 流量分配示例

假设灰度比例为 10%：

| device_id | 哈希值 | 百分位 | 路由版本 |
|-----------|--------|--------|----------|
| `bare_82fe9c38_bluth_20260318_63c8` | `a3f2b1c8` | 63.25% | 稳定版 (v1.2.0) |
| `bare_74d3e2f1_alice_20260318_a1b2` | `09c8d4e2` | 09.12% | 灰度版 (v1.3.0) |
| `docker_12ab34cd_bot_20260318_x9y8` | `f7e8d9c0` | 98.45% | 稳定版 (v1.2.0) |

**一致性验证**：
- 灰度比例从 10% 提升到 20% 时，原先命中灰度版本的设备继续命中灰度版本
- 灰度比例从 20% 降到 10% 时，部分设备会从灰度版本切回稳定版本（需谨慎操作）

---

## 三、流量比例控制

### 3.1 阶段划分

```
┌─────────────────────────────────────────────────────────────────────┐
│                       灰度发布阶段流程                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   [阶段 0] 准备阶段                                                  │
│   ├─ 部署灰度版本到生产环境                                          │
│   ├─ 灰度比例: 0%                                                   │
│   └─ 验证: 健康检查通过                                              │
│                    ↓                                                │
│   [阶段 1] 初始灰度                                                  │
│   ├─ 灰度比例: 5%                                                   │
│   ├─ 持续时间: 2-4 小时                                             │
│   └─ 验证: 错误率 < 0.5%, P99 < 2s                                  │
│                    ↓                                                │
│   [阶段 2] 小规模灰度                                                │
│   ├─ 灰度比例: 10%                                                  │
│   ├─ 持续时间: 4-8 小时                                             │
│   └─ 验证: 错误率 < 0.3%, P99 < 1.5s                                │
│                    ↓                                                │
│   [阶段 3] 中规模灰度                                                │
│   ├─ 灰度比例: 25%                                                  │
│   ├─ 持续时间: 8-24 小时                                            │
│   └─ 验证: 错误率 < 0.2%, P99 < 1s                                  │
│                    ↓                                                │
│   [阶段 4] 大规模灰度                                                │
│   ├─ 灰度比例: 50%                                                  │
│   ├─ 持续时间: 24-48 小时                                           │
│   └─ 验证: 错误率 < 0.1%, P99 < 1s                                  │
│                    ↓                                                │
│   [阶段 5] 全量发布                                                  │
│   ├─ 灰度比例: 100%                                                 │
│   ├─ 持续时间: 永久                                                 │
│   └─ 灰度版本成为新的稳定版本                                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 阶段配置

| 阶段 | 灰度比例 | 最短持续时间 | 最长持续时间 | 自动推进条件 |
|------|----------|--------------|--------------|--------------|
| 0 | 0% | - | - | 部署完成，健康检查通过 |
| 1 | 5% | 2 小时 | 24 小时 | 错误率 < 0.5% |
| 2 | 10% | 4 小时 | 48 小时 | 错误率 < 0.3% |
| 3 | 25% | 8 小时 | 72 小时 | 错误率 < 0.2% |
| 4 | 50% | 24 小时 | 168 小时 | 错误率 < 0.1% |
| 5 | 100% | - | - | 手动确认 |

### 3.3 推进策略

**自动推进**：
- 系统自动监控关键指标
- 满足条件后自动进入下一阶段
- 需要人工确认阶段 4 → 5

**手动推进**：
- 运维人员手动调整灰度比例
- 适用于紧急发布或风险较高的版本
- 每个阶段需要人工确认

---

## 四、回滚条件

### 4.1 自动回滚触发条件

| 指标 | 阈值 | 检测窗口 | 动作 |
|------|------|----------|------|
| 错误率 | ≥ 5% | 5 分钟 | 立即回滚 |
| 错误率 | ≥ 2% | 15 分钟 | 立即回滚 |
| 错误率 | ≥ 1% | 30 分钟 | 警告 + 人工确认 |
| P99 延迟 | ≥ 5s | 5 分钟 | 立即回滚 |
| P99 延迟 | ≥ 3s | 15 分钟 | 警告 |
| WebSocket 断连率 | ≥ 10% | 5 分钟 | 立即回滚 |
| Redis 连接失败 | 任意 | 立即 | 立即回滚 |

### 4.2 回滚流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                          回滚流程                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   [触发] 监控系统检测到异常指标                                      │
│                              │                                      │
│                              ▼                                      │
│   [判断] 是否满足自动回滚条件？                                      │
│           ┌───────────────┴───────────────┐                         │
│           │ 是                            │ 否                       │
│           ▼                               ▼                         │
│   [执行] 立即回滚              [警告] 发送告警通知                   │
│           │                           │                             │
│           ▼                           ▼                             │
│   [调整] 灰度比例 → 0%         [等待] 人工决策                      │
│           │                           │                             │
│           ▼                           ├─→ [确认回滚] → 灰度比例 → 0%
│   [通知] 发送回滚通知                 │                             │
│           │                           └─→ [继续观察] → 保持当前状态
│           ▼                                                         │
│   [记录] 记录回滚原因和时间                                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.3 回滚后操作

1. **问题分析**：收集灰度版本日志，定位问题根因
2. **修复验证**：在测试环境复现并修复问题
3. **重新发布**：修复后重新开始灰度发布流程

---

## 五、监控阈值

### 5.1 核心监控指标

| 指标类别 | 指标名称 | 计算方式 | 正常范围 | 告警阈值 |
|----------|----------|----------|----------|----------|
| **可用性** | 服务可用率 | 成功请求/总请求 | ≥ 99.9% | < 99.5% |
| **可用性** | WebSocket 连接成功率 | 成功连接/尝试连接 | ≥ 99% | < 95% |
| **性能** | P50 响应延迟 | 第 50 百分位 | < 100ms | > 500ms |
| **性能** | P99 响应延迟 | 第 99 百分位 | < 500ms | > 2s |
| **性能** | 消息处理吞吐量 | 每秒处理消息数 | 基线 ± 10% | < 基线 50% |
| **错误** | 错误率 | 错误请求/总请求 | < 0.1% | > 1% |
| **错误** | 5xx 错误率 | 5xx 响应/总响应 | 0% | > 0.1% |
| **资源** | CPU 使用率 | 平均 CPU 占用 | < 50% | > 80% |
| **资源** | 内存使用率 | 平均内存占用 | < 70% | > 85% |
| **资源** | Redis 连接数 | 活跃连接数 | < 100 | > 500 |

### 5.2 灰度版本独立监控

```json
{
    "canary_metrics": {
        "version": "1.3.0",
        "device_count": 125,
        "message_count": 1523,
        "error_count": 2,
        "error_rate": 0.0013,
        "p50_latency_ms": 85,
        "p99_latency_ms": 312,
        "websocket_connections": 125,
        "websocket_disconnects": 3,
        "disconnect_rate": 0.024
    },
    "stable_metrics": {
        "version": "1.2.0",
        "device_count": 1125,
        "message_count": 15623,
        "error_count": 8,
        "error_rate": 0.0005,
        "p50_latency_ms": 78,
        "p99_latency_ms": 289,
        "websocket_connections": 1125,
        "websocket_disconnects": 15,
        "disconnect_rate": 0.013
    }
}
```

### 5.3 对比分析

```python
def compare_canary_with_stable(canary_metrics: dict, stable_metrics: dict) -> dict:
    """
    对比灰度版本与稳定版本的关键指标
    
    Returns:
        对比结果，包含是否需要回滚的建议
    """
    result = {
        "should_rollback": False,
        "warnings": [],
        "comparison": {}
    }
    
    # 错误率对比
    error_rate_diff = canary_metrics["error_rate"] - stable_metrics["error_rate"]
    result["comparison"]["error_rate_diff"] = error_rate_diff
    if error_rate_diff > 0.01:  # 错误率高出 1%
        result["warnings"].append(f"灰度版本错误率高出 {error_rate_diff:.2%}")
        result["should_rollback"] = True
    
    # P99 延迟对比
    p99_diff_pct = (canary_metrics["p99_latency_ms"] - stable_metrics["p99_latency_ms"]) / stable_metrics["p99_latency_ms"]
    result["comparison"]["p99_diff_pct"] = p99_diff_pct
    if p99_diff_pct > 0.5:  # P99 延迟高出 50%
        result["warnings"].append(f"灰度版本 P99 延迟高出 {p99_diff_pct:.1%}")
    
    # 断连率对比
    disconnect_diff = canary_metrics["disconnect_rate"] - stable_metrics["disconnect_rate"]
    result["comparison"]["disconnect_diff"] = disconnect_diff
    if disconnect_diff > 0.05:  # 断连率高出 5%
        result["warnings"].append(f"灰度版本断连率高出 {disconnect_diff:.2%}")
        result["should_rollback"] = True
    
    return result
```

---

## 六、技术实现

### 6.1 服务端实现

#### 6.1.1 Redis 数据结构

```
# 灰度配置
canary:config
    {
        "stable_version": "1.2.0",
        "canary_version": "1.3.0",
        "canary_percentage": 10,
        "stage": 2,
        "started_at": "2026-03-24T10:00:00Z",
        "updated_at": "2026-03-24T14:00:00Z"
    }

# 灰度设备列表（用于监控）
canary:devices:set
    {device_id_1, device_id_2, ...}

# 灰度指标（按分钟聚合）
canary:metrics:{version}:{timestamp}
    {
        "message_count": 123,
        "error_count": 1,
        "latencies": [85, 92, 78, ...]
    }
```

#### 6.1.2 路由中间件

```python
class CanaryRouter:
    """灰度路由中间件"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.config_cache = None
        self.config_cache_time = 0
        self.cache_ttl = 60  # 配置缓存 60 秒
    
    async def get_canary_config(self) -> dict:
        """获取灰度配置（带缓存）"""
        import time
        current_time = time.time()
        
        if self.config_cache and (current_time - self.config_cache_time) < self.cache_ttl:
            return self.config_cache
        
        config = await self.redis.get("canary:config")
        if config:
            self.config_cache = json.loads(config)
            self.config_cache_time = current_time
        
        return self.config_cache or {
            "stable_version": "1.2.0",
            "canary_version": "1.3.0",
            "canary_percentage": 0
        }
    
    async def route_device(self, device_id: str) -> str:
        """
        路由设备到对应版本
        
        Returns:
            版本号
        """
        config = await self.get_canary_config()
        
        if config["canary_percentage"] == 0:
            return config["stable_version"]
        
        if config["canary_percentage"] == 100:
            return config["canary_version"]
        
        return get_canary_version(device_id, config)
    
    async def record_metrics(self, device_id: str, version: str, metrics: dict):
        """记录灰度指标"""
        import time
        timestamp = int(time.time() / 60) * 60  # 按分钟对齐
        key = f"canary:metrics:{version}:{timestamp}"
        
        await self.redis.hincrby(key, "message_count", metrics.get("message_count", 0))
        await self.redis.hincrby(key, "error_count", metrics.get("error_count", 0))
        await self.redis.expire(key, 86400)  # 保留 24 小时
```

#### 6.1.3 自动推进服务

```python
class CanaryProgression:
    """灰度自动推进服务"""
    
    STAGES = [
        {"percentage": 0, "min_duration_hours": 0},
        {"percentage": 5, "min_duration_hours": 2},
        {"percentage": 10, "min_duration_hours": 4},
        {"percentage": 25, "min_duration_hours": 8},
        {"percentage": 50, "min_duration_hours": 24},
        {"percentage": 100, "min_duration_hours": 0},
    ]
    
    def __init__(self, redis_client, alert_service):
        self.redis = redis_client
        self.alert = alert_service
    
    async def check_progression(self):
        """检查是否可以推进到下一阶段"""
        config = await self.get_canary_config()
        current_stage = config.get("stage", 0)
        
        if current_stage >= len(self.STAGES) - 1:
            return  # 已是最终阶段
        
        # 检查持续时间
        started_at = datetime.fromisoformat(config["started_at"].replace("Z", "+00:00"))
        duration_hours = (datetime.now(started_at.tzinfo) - started_at).total_seconds() / 3600
        
        if duration_hours < self.STAGES[current_stage]["min_duration_hours"]:
            return  # 持续时间不足
        
        # 检查指标
        metrics = await self.get_current_metrics(config["canary_version"])
        if not self._check_metrics(metrics):
            await self.alert.send_warning(f"灰度版本指标异常，暂停自动推进")
            return
        
        # 自动推进
        next_stage = current_stage + 1
        await self.progress_to_stage(next_stage)
    
    def _check_metrics(self, metrics: dict) -> bool:
        """检查指标是否满足推进条件"""
        if metrics.get("error_rate", 0) > 0.005:  # 错误率 > 0.5%
            return False
        if metrics.get("p99_latency_ms", 0) > 2000:  # P99 > 2s
            return False
        return True
    
    async def progress_to_stage(self, stage: int):
        """推进到指定阶段"""
        if stage >= len(self.STAGES):
            return
        
        percentage = self.STAGES[stage]["percentage"]
        config = await self.get_canary_config()
        config["stage"] = stage
        config["canary_percentage"] = percentage
        config["updated_at"] = datetime.utcnow().isoformat() + "Z"
        
        if stage > 0 and config.get("started_at") is None:
            config["started_at"] = config["updated_at"]
        
        await self.redis.set("canary:config", json.dumps(config))
        
        await self.alert.send_info(f"灰度发布已推进到阶段 {stage}，灰度比例: {percentage}%")
```

### 6.2 客户端适配

#### 6.2.1 版本上报

客户端在注册时上报当前版本：

```python
# client.py 注册消息
{
    "type": "register",
    "device_id": "bare_82fe9c38_bluth_20260318_63c8",
    "client_version": "1.2.0",  # 当前客户端版本
    ...
}
```

#### 6.2.2 版本兼容性检查

```python
# 服务端响应
{
    "type": "registered",
    "server_version": "1.0.0",
    "assigned_version": "1.2.0",  # 服务端分配的版本（用于灰度）
    "force_update": false,  # 是否需要强制更新
    "download_url": "https://wechat.clawadmin.org/release/client_1.3.0.py"
}
```

### 6.3 管理接口

#### 6.3.1 查询灰度状态

```bash
# API: GET /api/canary/status
curl https://claw.7color.vip/api/canary/status

# 响应
{
    "stable_version": "1.2.0",
    "canary_version": "1.3.0",
    "canary_percentage": 10,
    "stage": 2,
    "started_at": "2026-03-24T10:00:00Z",
    "updated_at": "2026-03-24T14:00:00Z",
    "canary_devices": 125,
    "stable_devices": 1125,
    "metrics": {
        "canary": {"error_rate": 0.0013, "p99_latency_ms": 312},
        "stable": {"error_rate": 0.0005, "p99_latency_ms": 289}
    }
}
```

#### 6.3.2 调整灰度比例

```bash
# API: POST /api/canary/config
curl -X POST https://claw.7color.vip/api/canary/config \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "canary_percentage": 25,
    "auto_progression": false
  }'
```

#### 6.3.3 紧急回滚

```bash
# API: POST /api/canary/rollback
curl -X POST https://claw.7color.vip/api/canary/rollback \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## 七、操作流程

### 7.1 发布流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                        灰度发布操作流程                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   [1] 准备工作                                                      │
│       ├─ 代码审查通过                                                │
│       ├─ 测试环境验证通过                                            │
│       └─ 准备回滚方案                                                │
│                              ↓                                      │
│   [2] 部署灰度版本                                                  │
│       ├─ 部署新版本到 ECS                                           │
│       ├─ 配置灰度比例 = 0%                                          │
│       └─ 验证服务健康                                                │
│                              ↓                                      │
│   [3] 启动灰度                                                      │
│       ├─ 设置灰度比例 = 5%                                          │
│       ├─ 配置自动推进规则                                            │
│       └─ 开启监控告警                                                │
│                              ↓                                      │
│   [4] 监控观察                                                      │
│       ├─ 实时监控错误率、延迟                                        │
│       ├─ 对比灰度版本与稳定版本                                      │
│       └─ 等待自动推进或手动推进                                      │
│                              ↓                                      │
│   [5] 全量发布                                                      │
│       ├─ 灰度比例 = 100%                                            │
│       ├─ 灰度版本成为稳定版本                                        │
│       └─ 清理旧版本                                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.2 回滚流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                        紧急回滚流程                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   [触发条件]                                                        │
│       ├─ 自动触发：监控指标超过阈值                                  │
│       └─ 手动触发：运维人员确认问题                                  │
│                              ↓                                      │
│   [执行回滚]                                                        │
│       ├─ 灰度比例 → 0%                                              │
│       ├─ 所有流量切回稳定版本                                        │
│       └─ 保留灰度版本服务（用于排查）                                │
│                              ↓                                      │
│   [通知相关方]                                                      │
│       ├─ 发送回滚通知                                                │
│       └─ 记录回滚原因                                                │
│                              ↓                                      │
│   [问题排查]                                                        │
│       ├─ 收集灰度版本日志                                            │
│       ├─ 分析根因                                                    │
│       └─ 制定修复方案                                                │
│                              ↓                                      │
│   [修复后重新发布]                                                  │
│       └─ 从步骤 2 重新开始                                           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.3 日常监控

```bash
# 查看灰度状态
curl -s https://claw.7color.vip/api/canary/status | jq

# 查看灰度版本日志
ssh -i ~/.ssh/ecs_claw.pem root@claw.7color.vip \
  "docker logs wechat-channel-canary --tail 100"

# 查看实时指标
ssh -i ~/.ssh/ecs_claw.pem root@claw.7color.vip \
  "redis-cli GET canary:metrics:1.3.0:$(date +%s -d '1 minute ago')"
```

---

## 八、风险与应对

### 8.1 潜在风险

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 哈希碰撞导致流量分配不均 | 部分用户集中到某版本 | 使用 MD5 前 8 位，碰撞概率极低 |
| 回滚期间服务中断 | 用户体验下降 | 灰度比例调整是原子操作，无中断 |
| 监控延迟导致问题扩大 | 影响更多用户 | 设置多个检测窗口，快速响应 |
| 配置错误导致全量切灰度 | 全量用户受影响 | 配置变更需要管理员确认 |
| 数据库连接池耗尽 | 服务不可用 | 灰度版本独立连接池 |

### 8.2 最佳实践

1. **小步快跑**：灰度比例从 5% 开始，逐步扩大
2. **充分验证**：每个阶段至少持续 2 小时
3. **及时回滚**：发现问题立即回滚，不要犹豫
4. **保留证据**：回滚后保留灰度版本服务用于排查
5. **用户沟通**：重大发布提前通知用户

---

## 九、附录

### 9.1 配置文件示例

```json
{
    "canary": {
        "enabled": true,
        "stable_version": "1.2.0",
        "canary_version": "1.3.0",
        "canary_percentage": 10,
        "stage": 2,
        "auto_progression": true,
        "rollback_thresholds": {
            "error_rate": 0.05,
            "p99_latency_ms": 5000,
            "disconnect_rate": 0.10
        },
        "progression_thresholds": {
            "error_rate": 0.005,
            "p99_latency_ms": 2000
        }
    }
}
```

### 9.2 告警规则示例

```yaml
# Prometheus AlertManager 规则
groups:
  - name: canary-alerts
    rules:
      - alert: CanaryHighErrorRate
        expr: |
          canary_error_rate{version="canary"} > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "灰度版本错误率过高"
          description: "灰度版本 {{ $labels.version }} 错误率为 {{ $value }}"
      
      - alert: CanaryHighLatency
        expr: |
          canary_p99_latency_ms{version="canary"} > 5000
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "灰度版本延迟过高"
          description: "灰度版本 P99 延迟为 {{ $value }}ms"
```

### 9.3 变更历史

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0.0 | 2026-03-24 | 初始版本，定义灰度发布架构 |

---

## 十、参考资料

1. [Google SRE Book - Canary Releases](https://sre.google/sre-book/canary-releases/)
2. [Martin Fowler - CanaryRelease](https://martinfowler.com/bliki/CanaryRelease.html)
3. [Kubernetes - Canary Deployments](https://kubernetes.io/docs/concepts/cluster-administration/manage-deployment/#canary-deployments)