# Improve 系统使用指南
# Improve System Usage Guide

## 概述 / Overview

Improve 文档描述了一个**可插拔的Action Engine**系统的完整演进路线，从基础的特性开关到复杂的多工作流并行、消息队列、计费系统等高级功能。该系统支持多种桌面自动化场景，包括微信自动回复、多平台聊天工具集成等。

**核心特性**:
- 🔧 可插拔Action Engine（变量/数据/控制流/异步/MQ/DB/LLM）
- 🚀 多工作流并行 + 高优先级抢占机制
- 🔄 异步解耦的LLM处理流程
- 🔐 登录/计费/授权/设备管理
- 🏪 工作流商店（下载/付费/授权）
- ☁️ 云端/客户端分层架构
- 📊 结构化日志与artifacts支持
- ⏸️ 暂停/继续/停止/断点恢复

---

## 阶段3: SQS消息队列 / Phase 3: SQS Message Queue

### 功能概述 / Feature Overview

阶段3将本地内存队列升级为真正的SQS消息队列，支持分布式环境和高可用部署。使用FIFO队列保证消息顺序，通过LocalStack实现本地开发环境。

#### 核心目标 / Core Objectives

1. **SQS集成**: 使用AWS SQS FIFO队列替代本地内存队列
2. **FIFO保证**: 通过MessageGroupId确保消息顺序
3. **去重机制**: ContentBasedDeduplication避免重复消息
4. **本地开发**: LocalStack提供本地SQS环境
5. **生产就绪**: 平滑迁移到真实AWS环境

### 在项目中使用 / Usage in Projects

#### 1. 环境配置 / Environment Setup

首先启动LocalStack SQS服务:

```bash
# docker-compose.sqs.yml
version: "3.9"
services:
  localstack:
    image: localstack/localstack:3
    ports:
      - "4566:4566"
    environment:
      - SERVICES=sqs
      - DEBUG=1
      - AWS_DEFAULT_REGION=us-east-1

# 启动LocalStack
docker compose -f docker-compose.sqs.yml up -d
```

配置环境变量:

```bash
# .env
AWS_REGION=us-east-1
AWS_ENDPOINT_URL=http://localhost:4566  # 本地LocalStack
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
```

#### 2. 队列初始化 / Queue Initialization

```bash
# 创建FIFO队列
python scripts/bootstrap_sqs.py
```

#### 3. 工作流配置 / Workflow Configuration

**LP轮询工作流** (examples/stage3_lp_poller.json):

```json
{
  "name": "LP Poller (SQS)",
  "meta": { "priority": "LOW" },
  "start": "poll",
  "vars": { "tick": 0 },
  "states": {
    "poll": {
      "actions": [
        { "do": "demo.fake_red_dot", "save": "rd" },
        { "do": "branch", "if": "@rd['has_red'] == True", "then": "publish_hp", "else": "sleep" }
      ],
      "transitions": [
        { "if": "@rd['has_red'] == True", "go_to": "publish_hp" },
        { "go_to": "sleep" }
      ]
    },
    "publish_hp": {
      "actions": [
        { "do": "mq.publish", "topic": "device.demo.hp.fifo", "payload": { "contact": "Alice", "text": "新消息..." } }
      ],
      "transitions": [ { "go_to": "poll" } ]
    }
  }
}
```

**HP响应工作流** (examples/stage3_hp_responder.json):

```json
{
  "name": "HP Responder (SQS)",
  "meta": { "priority": "HIGH" },
  "start": "wait",
  "states": {
    "wait": {
      "actions": [
        { "do": "mq.consume", "topic": "device.demo.hp.fifo", "save": "msg" }
      ],
      "transitions": [
        { "if": "@msg != None and @msg != 'pending'", "go_to": "send" },
        { "go_to": "wait" }
      ]
    },
    "send": {
      "actions": [
        { "do": "set_variable", "name": "last_contact", "value": "@msg['contact']" },
        { "do": "mq.ack", "topic": "device.demo.hp.fifo", "from_var": "msg" }
      ],
      "transitions": [ { "go_to": "wait" } ]
    }
  }
}
```

#### 4. 运行系统 / Running the System

```bash
# 启动演示
python scripts/run_stage3_demo.py
```

### 手动验证方法 / Manual Verification Methods

#### 1. 队列状态检查 / Queue Status Check

```bash
# 检查队列长度
aws --endpoint-url=http://localhost:4566 sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/device.demo.hp.fifo \
  --attribute-names ApproximateNumberOfMessages
```

#### 2. 消息流跟踪 / Message Flow Tracking

```bash
# 查看日志中的SQS操作
grep "mq\." logs/app.log

# 期望看到的日志模式:
# action=mq.publish ... priority=LOW topic=device.demo.hp.fifo
# action=mq.consume ... priority=HIGH topic=device.demo.hp.fifo
# action=mq.ack ... priority=HIGH
```

#### 3. 抢占机制验证 / Preemption Verification

观察日志中的优先级切换:

```
.. | v=0.4.0 | INFO | action=demo.fake_red_dot ... priority=LOW
.. | v=0.4.0 | INFO | action=mq.publish ... priority=LOW
.. | v=0.4.0 | INFO | action=mq.consume ... priority=HIGH      # 立刻抢占
.. | v=0.4.0 | INFO | action=set_variable ... priority=HIGH
.. | v=0.4.0 | INFO | action=mq.ack ... priority=HIGH
```

#### 4. LocalStack健康检查 / LocalStack Health Check

```bash
# 检查LocalStack状态
curl http://localhost:4566/health

# 检查SQS服务
aws --endpoint-url=http://localhost:4566 sqs list-queues
```

### 新增Actions / New Actions

#### mq.publish - 发布消息

```json
{
  "do": "mq.publish",
  "topic": "device.demo.hp.fifo",
  "payload": {
    "contact": "Alice",
    "text": "新消息内容",
    "priority": "high"
  }
}
```

#### mq.consume - 消费消息

```json
{
  "do": "mq.consume",
  "topic": "device.demo.hp.fifo",
  "save": "msg"
}
```

返回格式包含 `_sqs_receipt` 字段用于ack:

```json
{
  "contact": "Alice",
  "text": "新消息内容",
  "_sqs_receipt": "AQEB...receiptHandle"
}
```

#### mq.ack - 确认消息

```json
{
  "do": "mq.ack",
  "topic": "device.demo.hp.fifo",
  "from_var": "msg"
}
```

### 故障排除 / Troubleshooting

#### 1. 连接问题 / Connection Issues

```bash
# 检查LocalStack是否运行
docker ps | grep localstack

# 检查端口是否可达
telnet localhost 4566
```

#### 2. 权限问题 / Permission Issues

```bash
# 验证AWS配置
aws --endpoint-url=http://localhost:4566 sts get-caller-identity
```

#### 3. 队列问题 / Queue Issues

```bash
# 重新创建队列
python scripts/bootstrap_sqs.py

# 清空队列消息
aws --endpoint-url=http://localhost:4566 sqs purge-queue \
  --queue-url http://localhost:4566/000000000000/device.demo.hp.fifo
```

### 生产环境迁移 / Production Migration

#### 1. 环境变量调整 / Environment Variables

```bash
# 生产环境 - 移除LocalStack配置
unset AWS_ENDPOINT_URL  # 或设为空
export AWS_REGION=us-east-1
# 配置真实的AWS凭证或使用IAM角色
```

#### 2. 队列命名策略 / Queue Naming Strategy

```bash
# 从固定设备ID迁移到动态设备ID
device.demo.hp.fifo → device.${DEVICE_ID}.hp.fifo
```

#### 3. 安全配置 / Security Configuration

```bash
# IAM策略示例 - 限制队列访问权限
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["sqs:*"],
      "Resource": "arn:aws:sqs:*:*:device.${aws:userid}.*"
    }
  ]
}
```

### 成功标准 / Success Criteria

✅ **LocalStack SQS**: FIFO队列创建成功，支持消息发布/消费/确认
✅ **优先级抢占**: LP轮询触发HP立即抢占执行
✅ **消息持久化**: 系统重启后消息不丢失（SQS保证）
✅ **故障恢复**: LocalStack重启后客户端自动重连
✅ **日志可观测**: 清晰显示mq操作和优先级切换

---

## 阶段4: LLM异步处理 / Phase 4: Async LLM Processing

### 功能概述 / Feature Overview

阶段4建立了客户端-云端解耦的LLM处理架构，客户端通过SQS提交LLM任务，云端Worker处理后将结果回投到设备队列，实现异步回环处理。

#### 核心目标 / Core Objectives

1. **异步解耦**: 客户端不直接调用LLM，通过SQS解耦
2. **云端路由**: 支持多LLM提供商(OpenAI/DeepSeek/Mock)
3. **Schema校验**: 结构化输出校验与自动修复
4. **队列回环**: llm.request.fifo → 云端处理 → device.hp.fifo
5. **幂等保证**: 通过idempotency_key避免重复处理

### 在项目中使用 / Usage in Projects

#### 1. 队列扩展 / Queue Extension

扩展bootstrap脚本添加LLM请求队列:

```bash
# scripts/bootstrap_sqs.py 新增
ensure_fifo("llm.request.fifo")   # LLM请求全局队列
```

#### 2. 客户端LLM Action / Client LLM Action

**llm.submit** 配置示例:

```json
{
  "do": "llm.submit",
  "job": "wechat_reply",
  "prompt_pack": "wechat.sales.reply.v1",
  "schema": "WeChatReplyV1",
  "provider_hint": "mock",
  "inputs": {
    "new_messages": [
      { "contact": "Alice", "text": "在吗？" }
    ],
    "history": []
  }
}
```

#### 3. LP轮询工作流 / LP Polling Workflow

**更新后的LP工作流** (examples/stage4_lp_poller.json):

```json
{
  "name": "LP Poller (SQS -> LLM)",
  "meta": { "priority": "LOW" },
  "start": "poll",
  "states": {
    "submit_llm": {
      "actions": [
        {
          "do": "llm.submit",
          "job": "wechat_reply",
          "prompt_pack": "wechat.sales.reply.v1",
          "schema": "WeChatReplyV1",
          "provider_hint": "mock",
          "inputs": { "new_messages": [{"contact": "Alice", "text": "在吗？"}] }
        }
      ],
      "transitions": [{ "go_to": "poll" }]
    }
  }
}
```

#### 4. HP响应工作流 / HP Response Workflow

**更新后的HP工作流** (examples/stage4_hp_responder.json):

```json
{
  "name": "HP Responder (SQS <- LLM)",
  "meta": { "priority": "HIGH" },
  "states": {
    "send": {
      "actions": [
        { "do": "set_variable", "name": "last_contact", "value": "@msg['contact_name']" },
        { "do": "set_variable", "name": "last_reply", "value": "@msg['reply_text']" },
        { "do": "mq.ack", "topic": "device.demo.hp.fifo", "from_var": "msg" }
      ],
      "transitions": [{ "go_to": "wait" }]
    }
  }
}
```

#### 5. 云端LLM Worker / Cloud LLM Worker

**Worker启动** (server/worker.js):

```bash
# 环境配置
export AWS_REGION=us-east-1
export AWS_ENDPOINT_URL=http://localhost:4566
export MOCK_LLM=1  # 本地Mock模式
# export OPENAI_API_KEY=sk-...  # 生产环境

# 启动Worker
cd server && node worker.js
```

**Schema定义** (server/schema/WeChatReplyV1.json):

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "WeChatReplyV1",
  "type": "object",
  "required": ["contact_name", "reply_text"],
  "properties": {
    "contact_name": { "type": "string" },
    "reply_text": { "type": "string" },
    "audit_rows": {
      "type": "array",
      "items": { "type": "object" }
    }
  }
}
```

### 手动验证方法 / Manual Verification Methods

#### 1. LLM请求流程验证 / LLM Request Flow Verification

```bash
# 1. 检查LLM请求队列
aws --endpoint-url=http://localhost:4566 sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/llm.request.fifo \
  --attribute-names ApproximateNumberOfMessages

# 2. 监控Worker日志
node server/worker.js

# 期望看到:
# [worker] listening http://localhost:4566/000000000000/llm.request.fifo
# [worker] done job <job_id> -> device device.demo
```

#### 3. 端到端流程验证 / End-to-End Flow Verification

观察完整的LLM处理流程:

```
LP: action=llm.submit ... job=wechat_reply
Worker: [worker] done job abc123 -> device device.demo
HP: action=mq.consume ... priority=HIGH msg.contact_name=Alice
HP: action=set_variable ... last_reply=你好，Alice，我在的哈～
```

#### 4. Provider切换验证 / Provider Switch Verification

```bash
# Mock模式 → OpenAI模式
export MOCK_LLM=0
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-4o-mini

# 重启Worker验证真实LLM调用
node server/worker.js
```

### 新增Actions / New Actions

#### llm.submit - LLM任务提交

```json
{
  "do": "llm.submit",
  "job": "wechat_reply",
  "prompt_pack": "wechat.sales.reply.v1",
  "schema": "WeChatReplyV1",
  "provider_hint": "openai",
  "inputs": {
    "new_messages": [{"contact": "Alice", "text": "咨询价格"}],
    "history": []
  },
  "device_target": "device.demo",
  "idempotency_key": "optional_custom_key"
}
```

返回格式:
```json
{
  "ok": true,
  "enqueued": true,
  "job_id": "abc-123-def",
  "device_target": "device.demo"
}
```

### 故障排除 / Troubleshooting

#### 1. Worker连接问题 / Worker Connection Issues

```bash
# 检查Worker是否能连接SQS
aws --endpoint-url=http://localhost:4566 sqs list-queues

# 验证Worker权限
node -e "console.log(process.env.AWS_ACCESS_KEY_ID)"
```

#### 2. LLM调用失败 / LLM Call Failures

```bash
# 检查Worker日志错误
# Mock模式调试
export MOCK_LLM=1

# OpenAI调试
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  https://api.openai.com/v1/models
```

#### 3. Schema验证失败 / Schema Validation Failures

Worker会自动修复常见Schema问题:

```javascript
// 自动补齐缺失字段
if (out.reply_text && !out.contact_name) {
  const nm = job.inputs?.new_messages?.[0]?.contact || "客户";
  out.contact_name = nm;
}
```

#### 4. 消息重复处理 / Duplicate Message Processing

```bash
# 检查idempotency_key机制
# SQS ContentBasedDeduplication自动去重相同内容
```

### 生产环境配置 / Production Configuration

#### 1. LLM Provider配置 / LLM Provider Configuration

```bash
# OpenAI配置
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-4o

# DeepSeek配置
export DEEPSEEK_API_KEY=sk-...
export DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

#### 2. Worker扩展 / Worker Scaling

```bash
# 多Worker实例并行处理
node server/worker.js &  # Worker 1
node server/worker.js &  # Worker 2
node server/worker.js &  # Worker 3
```

#### 3. 监控指标 / Monitoring Metrics

```bash
# 队列长度监控
# LLM调用成功率
# Schema验证通过率
# Worker处理延迟
```

### 成功标准 / Success Criteria

✅ **异步解耦**: 客户端llm.submit成功提交到llm.request.fifo
✅ **云端处理**: Worker消费请求并调用LLM(Mock/真实)
✅ **Schema校验**: 输出结构化验证和自动修复
✅ **队列回环**: 结果正确投递到device.hp.fifo
✅ **HP抢占**: 客户端HP立即消费LLM结果并执行
✅ **幂等保证**: 重复请求被正确去重
✅ **Provider切换**: Mock/OpenAI/DeepSeek无缝切换

---

## 阶段5-13: 高级功能概览 / Phases 5-13: Advanced Features Overview

### 阶段5: 多桌面聊天工具通用方案 / Phase 5: Multi-Desktop Chat Tools

**核心功能**: 跨应用聊天自动化架构
- **ChatAppAdapter**: 支持WeChat/Slack/Telegram/WhatsApp等多平台
- **本地OCR**: 客户端离线OCR引擎(Tesseract/PaddleOCR)
- **资源锁**: 防止多应用UI冲突的锁机制
- **API上报**: 客户端仅通过API上报数据，禁止直连数据库

**关键使用方法**:
```json
{
  "do": "chat.detect_app",
  "target_app": "wechat"
}
```

```bash
# 启动多应用监控
python run_workflow.py --workflow examples/stage5_lp_generic.json --app wechat
```

### 阶段6: Checkpoint暂停恢复系统 / Phase 6: Checkpoint & Resume

**核心功能**: 工作流暂停/继续/停止机制
- **安全点**: 在动作完成后安全暂停，避免状态不一致
- **快照保存**: 序列化工作流状态、变量、SQS消息句柄
- **控制队列**: 通过SQS控制队列接收PAUSE/RESUME/STOP指令
- **断网容错**: 本地WAL缓存，网络恢复后补交

**关键使用方法**:
```bash
# 暂停运行中的工作流
curl -X POST /api/devices/demo/control \
  -H "Authorization: Bearer $JWT" \
  -d '{"action": "PAUSE"}'

# 恢复工作流
curl -X POST /api/devices/demo/control \
  -d '{"action": "RESUME", "snapshot_id": "snap_123"}'
```

### 阶段7: 登录设备注册 / Phase 7: Authentication & Device Registration

**核心功能**: 用户账号和设备管理
- **用户登录**: JWT认证体系
- **设备注册**: 机器识别码绑定设备
- **计划校验**: 设备权限和订阅状态检查
- **动态队列**: 基于真实device_id的队列命名

**关键使用方法**:
```bash
# 用户注册登录
curl -X POST /auth/register \
  -d '{"username": "user1", "password": "pass", "email": "user@example.com"}'

# 设备注册
curl -X POST /auth/device/register \
  -H "Authorization: Bearer $JWT" \
  -d '{"device_name": "MacBook-Pro", "device_type": "desktop"}'
```

### 阶段8: 多LLM路由 / Phase 8: Multi-LLM Routing

**核心功能**: 用户自带API Key的LLM管理
- **多Provider支持**: OpenAI/DeepSeek/Anthropic/Gemini等
- **用户API Key**: 允许用户配置自己的LLM API密钥
- **明文存储**: 支持后台可查看的密钥管理(可选加密)
- **计量统计**: Token使用量和成本跟踪

**关键使用方法**:
```bash
# 配置用户LLM API Key
curl -X PUT /api/user/llm-keys \
  -H "Authorization: Bearer $JWT" \
  -d '{"provider": "openai", "api_key": "sk-...", "model": "gpt-4o"}'

# 查看使用统计
curl -X GET /api/user/llm-usage \
  -H "Authorization: Bearer $JWT"
```

### 阶段9: 结算与账单 / Phase 9: Billing & Payments

**核心功能**: 订阅计费和支付系统
- **订阅计划**: 基础版/专业版/企业版等套餐
- **用量计费**: 按LLM Token、动作次数等计费
- **多渠道支付**: 支持支付宝/微信/信用卡等
- **逾期限流**: 欠费自动限制服务

**关键使用方法**:
```bash
# 购买订阅
curl -X POST /api/billing/subscribe \
  -H "Authorization: Bearer $JWT" \
  -d '{"plan": "pro", "billing_cycle": "monthly"}'

# 查看账单
curl -X GET /api/billing/invoices \
  -H "Authorization: Bearer $JWT"
```

### 阶段10: 工作流市场 / Phase 10: Workflow Marketplace

**核心功能**: 工作流商店和授权管理
- **工作流打包**: .wfpack格式的签名工作流包
- **商店上架**: 工作流发布和版本管理
- **付费购买**: 工作流购买和授权验证
- **自动安装**: 客户端拉取并验证签名后安装

**关键使用方法**:
```bash
# 搜索工作流
curl -X GET "/api/marketplace/search?q=微信自动回复"

# 购买工作流
curl -X POST /api/marketplace/purchase \
  -H "Authorization: Bearer $JWT" \
  -d '{"workflow_id": "wf_123", "license_type": "personal"}'
```

### 阶段11: 稳健性与反检测 / Phase 11: Robustness & Anti-Detection

**核心功能**: 人性化自动化和容错机制
- **随机延迟**: 模拟人类操作的自然延迟
- **鼠标轨迹**: 贝塞尔曲线轨迹模拟
- **UI变化适应**: 自动检测和适应界面变化
- **错误自恢复**: 失败时的自动重试和降级策略

**关键使用方法**:
```json
{
  "do": "click_coordinates",
  "bbox": "@target_bbox",
  "human_like": true,
  "delay_range": [200, 800]
}
```

### 阶段12: 跨端支持 / Phase 12: Cross-Platform Support

**核心功能**: 移动端和远程桌面支持
- **Android自动化**: 通过ADB/Appium支持手机自动化
- **远程桌面**: RDP/VNC环境下的自动化
- **云端回放**: 会话录制和云端诊断
- **近实时协助**: 远程技术支持和问题诊断

**关键使用方法**:
```bash
# Android设备连接
adb connect device_ip:5555
python run_workflow.py --platform android --device device_id

# 开启会话录制
curl -X POST /api/devices/demo/recording/start \
  -H "Authorization: Bearer $JWT"
```

### 阶段13: 自动回归测试 / Phase 13: Automated Testing

**核心功能**: 端到端测试和CI/CD集成
- **回归测试套件**: 自动化测试用例和数据驱动
- **Chaos工程**: 故障注入和恢复测试
- **性能基准**: 自动化性能测试和回归检测
- **CI/CD集成**: 自动化测试门槛和发布流程

**关键使用方法**:
```bash
# 运行回归测试套件
python tools/regression_suite.py --suite full --env staging

# Chaos测试
python tools/chaos_test.py --scenario network_partition --duration 300

# 性能基准测试
python tools/benchmark.py --workload standard --duration 600
```

### 使用顺序建议 / Recommended Usage Order

1. **阶段0-1**: 基础架构和Action Engine
2. **阶段2-4**: 队列系统和LLM异步处理
3. **阶段5-6**: 多应用支持和暂停恢复
4. **阶段7-8**: 用户管理和LLM路由
5. **阶段9-10**: 商业化功能(可选)
6. **阶段11-13**: 稳定性和测试(生产必需)

### 总体架构优势 / Overall Architecture Benefits

✅ **渐进式演进**: 每个阶段都可独立部署和验证
✅ **云端解耦**: 客户端仅通过API/SQS与云端通信
✅ **多租户支持**: 完整的用户、设备、计费隔离
✅ **高可用设计**: SQS队列、快照恢复、故障自愈
✅ **商业就绪**: 计费、支付、市场、授权完整闭环
✅ **企业级**: 审计日志、性能监控、安全控制

---

## 阶段0: 基线冻结 & 特性开关 / Phase 0: Baseline & Feature Flags

### 功能概述 / Feature Overview

阶段0建立了系统的基础架构，包括版本管理、特性开关和结构化日志，为后续功能提供可进化的骨架。

#### 核心目标 / Core Objectives

1. **版本管理**: 固定引擎版本号，便于排障和兼容性判断
2. **特性开关**: 通过feature flags控制新功能的启用/关闭
3. **结构化日志**: 统一日志格式和artifacts目录结构
4. **向后兼容**: 不改变现有行为，仅添加基础设施

### 在项目中使用 / Usage in Projects

#### 1. 目录结构设置 / Directory Structure Setup

```
repo/
├─ core/
│  ├─ __init__.py              # 版本号、对外常量
│  ├─ flags.py                 # 读取/合并 feature flags
│  ├─ logging_setup.py         # 结构化日志配置
│  └─ artifacts.py             # 产物快照目录 & 帮助函数
├─ config/
│  ├─ feature_flags.default.json
│  └─ settings.example.yaml
├─ examples/
│  └─ demo_baseline.json       # 演示用最小工作流
└─ run_workflow.py             # 入口脚本
```

#### 2. 核心配置文件 / Core Configuration Files

**config/feature_flags.default.json**:
```json
{
  "async_engine": false,
  "hp_lp_scheduler": false,
  "mq_rabbit": false,
  "auth_billing": false,
  "marketplace": false,
  "checkpoints": false,
  "strict_schema_llm": false
}
```

**core/__init__.py**:
```python
ENGINE_VERSION = "0.4.0"

# 可添加其他全局常量
DEFAULT_TIMEOUT = 30000
MAX_RETRY_COUNT = 3
```

#### 3. 特性开关系统 / Feature Flag System

**core/flags.py**:
```python
import json, os
from pathlib import Path

def load_flags(override_path: str | None = None) -> dict:
    """加载特性开关配置，支持文件覆盖和环境变量"""
    # 加载默认配置
    default_path = Path(__file__).parent.parent / "config" / "feature_flags.default.json"
    with open(default_path, "r", encoding="utf-8") as f:
        flags = json.load(f)

    # 用户配置文件覆盖
    if override_path and os.path.exists(override_path):
        with open(override_path, "r", encoding="utf-8") as f:
            user_flags = json.load(f)
        flags.update(user_flags)

    # 环境变量覆盖（FLAG_async_engine=true）
    for key in list(flags.keys()):
        env_val = os.getenv(f"FLAG_{key}")
        if env_val is not None:
            flags[key] = env_val.lower() in ("1", "true", "yes", "on")

    return flags
```

#### 4. 在工作流中使用 / Using in Workflows

**基础工作流示例**:
```json
{
  "name": "基线测试工作流",
  "description": "验证阶段0基础功能",
  "version": "1.0.0",
  "engine_version": "0.4.0",
  "start": "initialize",
  "states": {
    "initialize": {
      "actions": [
        {
          "do": "log_info",
          "message": "工作流开始执行",
          "metadata": {
            "phase": "0",
            "feature": "baseline"
          }
        }
      ],
      "next": "complete"
    },
    "complete": {
      "actions": [
        {
          "do": "log_info",
          "message": "工作流执行完成"
        }
      ]
    }
  }
}
```

### 手动验证方法 / Manual Verification Methods

#### 1. 基础功能验证 / Basic Functionality Verification

```bash
# 运行基线工作流
python run_workflow.py --workflow examples/demo_baseline.json

# 使用自定义特性开关
python run_workflow.py --workflow examples/demo_baseline.json --flags my_flags.json

# 通过环境变量覆盖
FLAG_async_engine=true python run_workflow.py --workflow examples/demo_baseline.json
```

#### 2. 版本和日志验证 / Version and Logging Verification

**预期日志输出**:
```
21:12:10 | v=0.4.0 | lvl=INFO | engine boot flags={'async_engine': False, 'hp_lp_scheduler': False, ...}
21:12:10 | v=0.4.0 | lvl=INFO | artifacts=artifacts/2025-09-15T211210Z-abc123
21:12:11 | v=0.4.0 | lvl=INFO | workflow started name=基线测试工作流
21:12:11 | v=0.4.0 | lvl=INFO | workflow completed successfully
```

**验证artifacts目录**:
```bash
# 检查artifacts目录是否生成
ls -la artifacts/

# 查看运行详情
cat artifacts/2025-09-15T211210Z-abc123/README.txt

# 检查生成的JSON文件
cat artifacts/2025-09-15T211210Z-abc123/summary.json
```

#### 3. 特性开关测试 / Feature Flag Testing

```python
# 测试特性开关加载
from core.flags import load_flags

# 默认配置
flags = load_flags()
print("默认配置:", flags)

# 自定义配置
flags = load_flags("custom_flags.json")
print("自定义配置:", flags)

# 环境变量测试
import os
os.environ["FLAG_async_engine"] = "true"
flags = load_flags()
print("环境变量覆盖:", flags["async_engine"])  # 应该是True
```

#### 4. 日志系统测试 / Logging System Testing

```python
from core.logging_setup import setup_logger

# 设置日志系统
logger = setup_logger()

# 测试不同级别的日志
logger.info("这是信息日志")
logger.warning("这是警告日志")
logger.error("这是错误日志")

# 带额外信息的日志
logger.info("工作流执行", extra={
    "workflow_name": "test",
    "step_count": 5,
    "execution_time": 1.23
})
```

### 配置选项详解 / Configuration Options

| 特性开关 | 默认值 | 说明 | 适用阶段 |
|----------|--------|------|----------|
| `async_engine` | false | 启用异步引擎 | 阶段1+ |
| `hp_lp_scheduler` | false | 高低优先级调度器 | 阶段2+ |
| `mq_rabbit` | false | RabbitMQ消息队列 | 阶段3+ |
| `auth_billing` | false | 认证和计费系统 | 阶段7+ |
| `marketplace` | false | 工作流市场 | 阶段10+ |
| `checkpoints` | false | 断点恢复功能 | 阶段6+ |
| `strict_schema_llm` | false | 严格LLM模式验证 | 阶段8+ |

### 故障排除 / Troubleshooting

#### 常见问题 / Common Issues

1. **版本不匹配**: 检查ENGINE_VERSION是否正确设置
2. **特性开关不生效**: 确认文件路径和环境变量名称正确
3. **日志格式异常**: 检查logging_setup.py配置
4. **artifacts目录权限**: 确保有写入权限

#### 调试技巧 / Debug Tips

```python
# 调试特性开关
import json
from core.flags import load_flags

flags = load_flags()
print(json.dumps(flags, indent=2))

# 调试日志配置
import logging
logging.getLogger("auto").setLevel(logging.DEBUG)

# 检查artifacts目录
from core.artifacts import run_dir
run_id = "test-run"
artifacts_path = run_dir("artifacts", run_id)
print(f"Artifacts path: {artifacts_path}")
```

---

## 阶段1: Action Engine基座 / Phase 1: Action Engine Foundation

### 功能概述 / Feature Overview

阶段1实现了可插拔的Action Engine，支持变量系统、数据处理、控制流和基础的DOM/坐标操作。完成后可以用JSON语言编写"微脚本"，实现循环、条件判断等复杂逻辑。

#### 核心目标 / Core Objectives

1. **可插拔动作注册**: 通过装饰器注册新动作
2. **变量系统**: 支持变量设置、获取、表达式计算
3. **安全表达式**: 限制表达式能力，避免安全问题
4. **同步Runner**: 基础的状态机执行器
5. **首批动作**: 变量、流控制、等待、滚动、点击等

### 在项目中使用 / Usage in Projects

#### 1. 目录结构 / Directory Structure

```
core/
├─ registry.py        # 动作注册与获取
├─ context.py         # 上下文/服务适配器
├─ expr.py            # @变量解引用 & 安全表达式
└─ runner.py          # 同步状态机执行器

actions/
├─ vars.py            # 变量操作动作
├─ flow.py            # 流控制动作
├─ wait_scroll.py     # 等待和滚动动作
├─ exec.py            # 执行动作（点击等）
└─ ext.py             # 扩展动作（DOM操作）

examples/
└─ demo_loop_posts.json  # 演示工作流
```

#### 2. 动作注册系统 / Action Registration System

**core/registry.py**:
```python
from typing import Callable, Dict

_ACTIONS: Dict[str, Callable] = {}

def register_action(name: str):
    """动作注册装饰器"""
    def decorator(fn: Callable):
        _ACTIONS[name] = fn
        return fn
    return decorator

def get_action(name: str) -> Callable:
    """获取已注册的动作函数"""
    if name not in _ACTIONS:
        raise KeyError(f"Action '{name}' not registered")
    return _ACTIONS[name]

# 查看所有已注册动作
def list_actions():
    return list(_ACTIONS.keys())
```

#### 3. 变量系统 / Variable System

**core/expr.py**:
```python
import ast
import operator as op
from .context import Ctx

# 允许的操作符
_ALLOWED_OPS = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
    ast.Div: op.truediv, ast.Mod: op.mod, ast.Pow: op.pow,
    ast.Eq: op.eq, ast.NotEq: op.ne, ast.Lt: op.lt,
    ast.LtE: op.le, ast.Gt: op.gt, ast.GtE: op.ge,
}

def resolve(value, ctx: Ctx):
    """解析变量引用（@variable_name）"""
    if isinstance(value, str) and value.startswith("@"):
        var_name = value[1:]
        if var_name not in ctx.vars:
            raise KeyError(f"Variable '{var_name}' not found")
        return ctx.vars[var_name]
    return value

def eval_expr(expr: str, ctx: Ctx):
    """安全的表达式求值"""
    try:
        node = ast.parse(expr, mode="eval")
        return _eval_node(node, ctx)
    except Exception as e:
        raise ValueError(f"Expression evaluation failed: {e}")

def _eval_node(node, ctx: Ctx):
    """递归求值AST节点"""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, ctx)
    elif isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.Name):
        return ctx.vars.get(node.id, 0)
    elif isinstance(node, ast.BinOp):
        left = _eval_node(node.left, ctx)
        right = _eval_node(node.right, ctx)
        op_func = _ALLOWED_OPS.get(type(node.op))
        if op_func:
            return op_func(left, right)
        raise ValueError(f"Unsupported operator: {type(node.op)}")
    elif isinstance(node, ast.Compare):
        left = _eval_node(node.left, ctx)
        for op_node, comparator in zip(node.ops, node.comparators):
            right = _eval_node(comparator, ctx)
            op_func = _ALLOWED_OPS.get(type(op_node))
            if op_func and not op_func(left, right):
                return False
            left = right
        return True
    else:
        raise ValueError(f"Unsupported node type: {type(node)}")
```

#### 4. 工作流示例 / Workflow Examples

**循环处理帖子的工作流**:
```json
{
  "name": "循环处理帖子",
  "description": "演示变量、循环、条件判断的使用",
  "start": "initialize",
  "vars": {
    "current_index": 0,
    "max_posts": 5,
    "processed_count": 0
  },
  "states": {
    "initialize": {
      "actions": [
        {
          "do": "ext.open_url",
          "url": "https://example.com/posts"
        },
        {
          "do": "wait_until",
          "check": {
            "type": "dom",
            "selector": ".post-item"
          },
          "timeout_ms": 5000
        },
        {
          "do": "ext.extract",
          "query": { "posts": "CSS:.post-item" },
          "save": "posts_data"
        },
        {
          "do": "get_list_length",
          "from": "@posts_data",
          "save": "total_posts"
        }
      ],
      "transitions": [{ "go_to": "process_loop" }]
    },
    "process_loop": {
      "actions": [
        {
          "do": "branch",
          "if": "@current_index >= @total_posts",
          "then": "complete",
          "else": "process_post"
        }
      ],
      "transitions": [
        { "if": "@current_index >= @total_posts", "go_to": "complete" },
        { "go_to": "process_post" }
      ]
    },
    "process_post": {
      "actions": [
        {
          "do": "get_list_item",
          "from": "@posts_data",
          "index": "@current_index",
          "save": "current_post"
        },
        {
          "do": "query_data",
          "from": "@current_post",
          "query": "bbox",
          "save": "post_bbox"
        },
        {
          "do": "click_coordinates",
          "bbox": "@post_bbox"
        },
        {
          "do": "wait_until",
          "check": {
            "type": "dom",
            "selector": ".post-detail"
          },
          "timeout_ms": 3000
        },
        {
          "do": "ext.go_back"
        },
        {
          "do": "increment_variable",
          "name": "current_index"
        },
        {
          "do": "increment_variable",
          "name": "processed_count"
        }
      ],
      "transitions": [{ "go_to": "process_loop" }]
    },
    "complete": {
      "actions": [
        {
          "do": "set_variable",
          "name": "completion_message",
          "value": "处理完成，共处理 @processed_count 个帖子"
        }
      ]
    }
  }
}
```

### 手动验证方法 / Manual Verification Methods

#### 1. 动作注册验证 / Action Registration Verification

```python
from core.registry import register_action, get_action, list_actions

# 注册自定义动作
@register_action("custom.hello")
def hello_action(step, ctx, **kwargs):
    name = step.get("name", "World")
    message = f"Hello, {name}!"
    return {"message": message}

# 验证注册
print("已注册的动作:", list_actions())

# 测试动作执行
action_fn = get_action("custom.hello")
from core.context import Ctx, Services
ctx = Ctx()
result = action_fn({"name": "Claude"}, ctx)
print("动作执行结果:", result)
```

#### 2. 变量系统验证 / Variable System Verification

```python
from core.context import Ctx
from core.expr import resolve, eval_expr

# 创建测试上下文
ctx = Ctx()
ctx.vars = {
    "user_count": 10,
    "page_size": 5,
    "current_page": 2
}

# 测试变量解析
print("用户数量:", resolve("@user_count", ctx))  # 应输出: 10

# 测试表达式计算
total_items = eval_expr("@user_count + @page_size", ctx)
print("总计:", total_items)  # 应输出: 15

is_last_page = eval_expr("@current_page * @page_size >= @user_count", ctx)
print("是否最后一页:", is_last_page)  # 应输出: True

# 测试条件表达式
condition = eval_expr("@current_page > 1 and @user_count > 0", ctx)
print("条件满足:", condition)  # 应输出: True
```

#### 3. 工作流执行验证 / Workflow Execution Verification

```python
import json
from core.runner import WorkflowRunner
from core.context import Ctx, Services

# 模拟服务
class MockDOMService:
    def open(self, url):
        print(f"模拟打开: {url}")
        return {"ok": True}

    def exists(self, selector):
        return True

    def extract(self, query):
        # 返回模拟数据
        return [
            {"bbox": {"x": 100, "y": 200, "w": 150, "h": 30}, "title": "帖子1"},
            {"bbox": {"x": 100, "y": 250, "w": 150, "h": 30}, "title": "帖子2"},
            {"bbox": {"x": 100, "y": 300, "w": 150, "h": 30}, "title": "帖子3"}
        ]

    def go_back(self):
        print("模拟返回")
        return {"ok": True}

class MockOSService:
    def move_to(self, x, y):
        print(f"移动鼠标到: ({x}, {y})")

    def click(self):
        print("执行点击")

    def scroll(self, pixels):
        print(f"滚动 {pixels} 像素")

# 设置上下文
ctx = Ctx()
ctx.services = Services(
    dom=MockDOMService(),
    os=MockOSService(),
    vision=None,
    logger=None
)

# 加载并执行工作流
with open("examples/demo_loop_posts.json", "r") as f:
    workflow_spec = json.load(f)

runner = WorkflowRunner(workflow_spec, ctx)

# 逐步执行验证
print("开始执行工作流...")
runner.run()
print("工作流执行完成")

# 检查最终变量状态
print("最终变量状态:", ctx.vars)
```

#### 4. artifacts验证 / Artifacts Verification

```bash
# 检查生成的artifacts
ls -la artifacts/

# 查看具体执行步骤
ls artifacts/dev/*/

# 检查动作执行记录
cat artifacts/dev/open_and_extract_step001/action.json
cat artifacts/dev/open_and_extract_step001/result.json

# 查看变量变化
grep -r "current_index" artifacts/dev/*/
```

---

## 阶段2: 本地抢占式调度 / Phase 2: Local Preemptive Scheduling

### 功能概述 / Feature Overview

阶段2实现了高优先级(HP)和低优先级(LP)工作流的抢占式调度机制，使用本地内存队列模拟消息队列，实现LP工作流被HP工作流打断的效果。

#### 核心目标 / Core Objectives

1. **本地内存总线**: LocalBus模拟MQ的publish/consume
2. **抢占式调度器**: 基于asyncio的HP/LP调度器
3. **异步step接口**: 工作流支持逐步执行和让出
4. **优先级抢占**: LP检查HP队列，有消息立即让渡

### 在项目中使用 / Usage in Projects

#### 1. 抢占式调度器 / Preemptive Scheduler

**client/scheduler.py**:
```python
import asyncio
from typing import Dict
from core.runner import WorkflowRunner

class Scheduler:
    def __init__(self, hp_runner: WorkflowRunner, lp_runners: Dict[str, WorkflowRunner], services):
        self.hp_runner = hp_runner
        self.lp_runners = lp_runners
        self.services = services

    async def start(self):
        """启动HP和LP调度循环"""
        await asyncio.gather(
            self._loop_hp(),
            self._loop_lp()
        )

    async def _loop_hp(self):
        """HP工作流循环：持续检查并处理高优先级任务"""
        while True:
            # HP不被抢占
            async def no_preempt():
                return False

            await self.hp_runner.step(no_preempt)
            await asyncio.sleep(0)  # 让出时间片

    async def _loop_lp(self):
        """LP工作流循环：支持被HP抢占"""
        while True:
            # 轮询所有LP工作流
            for workflow_id, runner in self.lp_runners.items():
                async def should_preempt():
                    # 检查HP队列是否有待处理消息
                    return self.services.mq.qsize("hp") > 0

                await runner.step(should_preempt)

                # 如果有HP消息，立即让出
                if self.services.mq.qsize("hp") > 0:
                    await asyncio.sleep(0)

            await asyncio.sleep(0.01)  # 避免忙等
```

#### 2. 本地消息总线 / Local Message Bus

**client/bus_local.py**:
```python
import asyncio
from typing import Dict, Any

class LocalBus:
    def __init__(self):
        self._topics: Dict[str, asyncio.Queue] = {}

    def topic(self, name: str) -> asyncio.Queue:
        """获取或创建topic对应的队列"""
        if name not in self._topics:
            self._topics[name] = asyncio.Queue()
        return self._topics[name]

    async def publish(self, topic: str, message: Any):
        """发布消息到指定topic"""
        await self.topic(topic).put(message)

    async def consume(self, topic: str, timeout_ms: int = None):
        """从指定topic消费消息"""
        queue = self.topic(topic)
        if timeout_ms is None:
            return await queue.get()

        try:
            timeout_sec = timeout_ms / 1000
            return await asyncio.wait_for(queue.get(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            return None

    def qsize(self, topic: str) -> int:
        """获取指定topic的队列大小"""
        return self.topic(topic).qsize()
```

#### 3. 消息队列动作 / Message Queue Actions

**actions/mq_local.py**:
```python
import asyncio
from core.registry import register_action

@register_action("mq.publish")
def mq_publish(step, ctx, **kwargs):
    """发布消息到指定topic"""
    topic = step["topic"]
    payload = step.get("payload", {})

    # 异步发布消息
    loop = asyncio.get_event_loop()
    loop.create_task(ctx.services.mq.publish(topic, payload))

    return {
        "ok": True,
        "enqueued": True,
        "topic": topic,
        "payload": payload
    }

@register_action("mq.consume")
def mq_consume(step, ctx, **kwargs):
    """从指定topic消费消息（非阻塞）"""
    topic = step["topic"]
    save_to = step.get("save", "msg")

    # 非阻塞检查
    if ctx.services.mq.qsize(topic) == 0:
        return {"msg": None, "status": "no_message"}

    # 异步获取消息
    async def get_message():
        msg = await ctx.services.mq.consume(topic, timeout_ms=100)
        if msg is not None:
            ctx.vars[save_to] = msg

    asyncio.get_event_loop().create_task(get_message())
    return {"msg": "pending", "status": "fetching"}
```

#### 4. 示例工作流 / Example Workflows

**LP轮询工作流 (examples/stage2_lp_poller.json)**:
```json
{
  "name": "LP微信轮询器",
  "meta": { "priority": "LOW" },
  "start": "check_messages",
  "vars": { "poll_count": 0 },
  "states": {
    "check_messages": {
      "actions": [
        {
          "do": "increment_variable",
          "name": "poll_count"
        },
        {
          "do": "demo.fake_red_dot",
          "save": "red_dot_result"
        },
        {
          "do": "branch",
          "if": "@red_dot_result['has_red'] == True",
          "then": "发现新消息",
          "else": "无新消息"
        }
      ],
      "transitions": [
        {
          "if": "@red_dot_result['has_red'] == True",
          "go_to": "publish_task"
        },
        { "go_to": "wait_and_retry" }
      ]
    },
    "publish_task": {
      "actions": [
        {
          "do": "mq.publish",
          "topic": "hp",
          "payload": {
            "type": "reply_request",
            "contact": "张三",
            "message": "收到新消息，需要回复",
            "timestamp": "@poll_count"
          }
        }
      ],
      "transitions": [{ "go_to": "wait_and_retry" }]
    },
    "wait_and_retry": {
      "actions": [
        {
          "do": "set_variable",
          "name": "last_check",
          "value": "@poll_count"
        }
      ],
      "transitions": [{ "go_to": "check_messages" }]
    }
  }
}
```

**HP响应工作流 (examples/stage2_hp_responder.json)**:
```json
{
  "name": "HP消息响应器",
  "meta": { "priority": "HIGH" },
  "start": "wait_for_task",
  "vars": { "processed_count": 0 },
  "states": {
    "wait_for_task": {
      "actions": [
        {
          "do": "mq.consume",
          "topic": "hp",
          "save": "task_message"
        }
      ],
      "transitions": [
        {
          "if": "@task_message != None and @task_message != 'pending'",
          "go_to": "process_task"
        },
        { "go_to": "wait_for_task" }
      ]
    },
    "process_task": {
      "actions": [
        {
          "do": "increment_variable",
          "name": "processed_count"
        },
        {
          "do": "set_variable",
          "name": "current_contact",
          "value": "@task_message['payload']['contact']"
        },
        {
          "do": "set_variable",
          "name": "reply_text",
          "value": "自动回复：已收到您的消息"
        },
        {
          "do": "demo.simulate_reply",
          "contact": "@current_contact",
          "text": "@reply_text"
        }
      ],
      "transitions": [{ "go_to": "wait_for_task" }]
    }
  }
}
```

### 手动验证方法 / Manual Verification Methods

#### 1. 调度器测试 / Scheduler Testing

```python
import asyncio
import json
from client.scheduler import Scheduler
from client.bus_local import LocalBus
from client.services_local import build_services
from core.runner import WorkflowRunner
from core.context import Ctx

async def test_scheduler():
    # 创建本地总线
    bus = LocalBus()

    # 创建模拟服务
    class MockLogger:
        def info(self, msg, **kwargs):
            print(f"[LOG] {msg}")

    services = build_services(
        dom=None, os=None, vision=None,
        logger=MockLogger(), bus=bus
    )

    # 加载工作流
    with open("examples/stage2_lp_poller.json") as f:
        lp_spec = json.load(f)

    with open("examples/stage2_hp_responder.json") as f:
        hp_spec = json.load(f)

    # 创建工作流实例
    lp_ctx = Ctx(services=services, run_id="lp_test")
    hp_ctx = Ctx(services=services, run_id="hp_test")

    lp_runner = WorkflowRunner(lp_spec, lp_ctx)
    hp_runner = WorkflowRunner(hp_spec, hp_ctx)

    # 创建调度器
    scheduler = Scheduler(
        hp_runner=hp_runner,
        lp_runners={"lp_poller": lp_runner},
        services=services
    )

    # 运行测试（10秒后停止）
    try:
        await asyncio.wait_for(scheduler.start(), timeout=10.0)
    except asyncio.TimeoutError:
        print("测试完成")

# 运行测试
asyncio.run(test_scheduler())
```

#### 2. 抢占效果验证 / Preemption Effect Verification

```python
async def test_preemption():
    """验证HP工作流是否能正确抢占LP工作流"""
    bus = LocalBus()

    # 监控队列状态
    async def monitor_queues():
        while True:
            hp_size = bus.qsize("hp")
            if hp_size > 0:
                print(f"⚡ HP队列有 {hp_size} 个待处理任务")
            await asyncio.sleep(0.5)

    # 模拟LP发布任务
    async def simulate_lp():
        for i in range(5):
            await asyncio.sleep(2)  # 每2秒发布一个任务
            await bus.publish("hp", {
                "task_id": f"task_{i}",
                "priority": "urgent",
                "message": f"紧急任务 {i}"
            })
            print(f"📤 LP发布了任务 {i}")

    # 模拟HP处理任务
    async def simulate_hp():
        processed = 0
        while processed < 5:
            msg = await bus.consume("hp", timeout_ms=1000)
            if msg:
                print(f"⚡ HP处理任务: {msg['task_id']}")
                processed += 1
                await asyncio.sleep(1)  # 模拟处理时间

    # 并发运行
    await asyncio.gather(
        monitor_queues(),
        simulate_lp(),
        simulate_hp()
    )

# 运行抢占测试
asyncio.run(test_preemption())
```

#### 3. 性能和调度延迟测试 / Performance and Scheduling Latency Testing

```python
import time
import statistics

async def test_scheduling_latency():
    """测试调度延迟"""
    bus = LocalBus()
    latencies = []

    async def producer():
        for i in range(10):
            start_time = time.time()
            await bus.publish("test", {"id": i, "timestamp": start_time})
            await asyncio.sleep(0.1)

    async def consumer():
        for i in range(10):
            msg = await bus.consume("test")
            end_time = time.time()
            latency = (end_time - msg["timestamp"]) * 1000  # 转换为毫秒
            latencies.append(latency)
            print(f"消息 {msg['id']} 延迟: {latency:.2f}ms")

    await asyncio.gather(producer(), consumer())

    print(f"\n延迟统计:")
    print(f"平均延迟: {statistics.mean(latencies):.2f}ms")
    print(f"最大延迟: {max(latencies):.2f}ms")
    print(f"最小延迟: {min(latencies):.2f}ms")

asyncio.run(test_scheduling_latency())
```

#### 4. 工作流状态监控 / Workflow State Monitoring

```bash
# 检查artifacts中的调度日志
grep -r "priority=HIGH" artifacts/*/
grep -r "priority=LOW" artifacts/*/

# 分析抢占频率
grep -r "action=" artifacts/*/ | grep -c "priority=HIGH"
grep -r "action=" artifacts/*/ | grep -c "priority=LOW"

# 查看消息队列操作
grep -r "mq\." artifacts/*/action.json

# 检查抢占点
grep -r "should_preempt" logs/
```

---

## 待续... / To be continued...

本文档将继续分析**阶段3: SQS消息队列**和后续阶段。

---

**当前进度**: 阶段0 ✅ 阶段1 ✅ 阶段2 ✅
**下一步**: 阶段3-13分析

**文档版本**: v1.0.0
**最后更新**: 2024年12月
**适用版本**: Improve 完整实现路线图