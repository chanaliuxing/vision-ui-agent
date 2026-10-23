# AI自动化系统完整说明书
# Complete AI Automation System Documentation

## 目录 / Table of Contents

1. [系统概述 / System Overview](#系统概述--system-overview)
2. [架构设计 / Architecture Design](#架构设计--architecture-design)
3. [Sprint功能详解 / Sprint Features](#sprint功能详解--sprint-features)
4. [服务启动指南 / Service Startup Guide](#服务启动指南--service-startup-guide)
5. [API接口文档 / API Documentation](#api接口文档--api-documentation)
6. [工作流使用指南 / Workflow Usage Guide](#工作流使用指南--workflow-usage-guide)
7. [CLI工具参考 / CLI Tools Reference](#cli工具参考--cli-tools-reference)
8. [数据库配置 / Database Configuration](#数据库配置--database-configuration)
9. [部署指南 / Deployment Guide](#部署指南--deployment-guide)
10. [故障排除 / Troubleshooting](#故障排除--troubleshooting)

11. [Action Space v2（instr.*）](#action-space-v2instr)
12. [AutoFix 与自动晋升](#autofix-与自动晋升)
13. [工作流编写与生成（WAM/LLM）](#工作流编写与生成wamllm)

---

## 系统概述 / System Overview

### 系统简介 / System Introduction

本系统是一个**视觉优先的UI自动化引擎**，结合YOLO目标检测与LLM智能决策，实现Web和桌面自动化。通过四个主要Sprint的迭代开发，系统具备了以下核心能力：

- **Sprint H**: RAG轨迹检索 + 在线Reflexion
- **Sprint I**: DPO/RLAIF离线训练与上线
- **Sprint J**: 技能库与宏动作自动化
- **Sprint K**: 多模态UI理解与自适应执行

### 核心特性 / Core Features

#### 🎯 视觉优先架构 / Vision-First Architecture
- YOLO目标检测驱动的UI元素识别
- LLM智能决策与视觉候选对象选择
- 多模态融合（视觉+文本+几何特征）

#### 🧠 智能学习能力 / Intelligent Learning
- RAG检索增强的轨迹记忆
- DPO直接偏好优化训练
- 在线反思与自我改进
- A/B测试与渐进部署

#### 🔧 技能库系统 / Skill Library System
- 可重用的宏动作库
- 热加载技能包(.wfpack)
- 频繁模式挖掘与自动化技能生成

#### 🎛️ 自适应执行 / Adaptive Execution
- 上下文感知的策略选择
- 实时参数优化
- 执行监控与自动调整

---

## 架构设计 / Architecture Design

### 整体架构图 / Overall Architecture

```mermaid
graph TB
    subgraph "Core Services (Ports 8000-8002)"
        A[YOLO API :8000] --> B[OCR API :8001]
        B --> C[Workflow API :8002]
    end

    subgraph "Sprint H: Memory & Reflexion (Port 8003)"
        D[Recall API :8003]
        E[Embedding Service]
        F[Memory Database]
    end

    subgraph "Sprint I: Training & Optimization (Ports 8004-8006)"
        G[DPO Service :8004]
        H[Model Manager :8005]
        I[A/B Testing :8006]
        J[Auto Rollback]
    end

    subgraph "Sprint J: Skills & Macros"
        K[Macro Registry]
        L[Skill Mining]
        M[Package Manager]
    end

    subgraph "Sprint K: Multimodal & Adaptive (Port 8007)"
        N[Vision API :8007]
        O[Multimodal Fusion]
        P[Adaptive Executor]
    end

    subgraph "Storage Layer"
        Q[(PostgreSQL + pgvector)]
        R[(Model Storage)]
        S[(Skill Library)]
    end

    C --> D
    D --> E
    E --> F
    G --> H
    H --> I
    K --> L
    L --> M
    N --> O
    O --> P

    F --> Q
    H --> R
    M --> S
```

### 技术栈 / Technology Stack

| 层级 / Layer | 技术 / Technology |
|--------------|-------------------|
| **AI/ML** | YOLO, OpenAI/Gemini LLMs, TRL, scikit-learn |
| **后端 / Backend** | FastAPI, asyncio, uvicorn |
| **数据库 / Database** | PostgreSQL, pgvector |
| **工作流 / Workflow** | JSON状态机, Python异步执行 |
| **UI自动化 / UI Automation** | PyAutoGUI, 跨平台输入处理 |
| **安全 / Security** | Ed25519/P-256 ECDSA签名验证 |

---

## Sprint功能详解 / Sprint Features

### Sprint H: RAG轨迹检索 + 在线Reflexion

#### 核心功能 / Core Features
- **轨迹记忆**: 基于pgvector的语义检索
- **相似性搜索**: 余弦相似度轨迹匹配
- **在线反思**: 自我改进与错误分析
- **多提供商嵌入**: OpenAI, SentenceTransformers支持

#### 关键组件 / Key Components
```python
# 记忆召回动作
{"do": "mem.recall", "goal": "登录网站", "k": 5}

# 反思动作
{"do": "plan.reflect", "focus": "error_analysis"}
```

#### 数据库表结构 / Database Schema
- `plans_history`: 增加嵌入向量列
- `plan_reflections`: 反思记录表
- `embeddings_cache`: 嵌入缓存表

### Sprint I: DPO/RLAIF离线训练与上线

#### 核心功能 / Core Features
- **偏好对生成**: 自动化数据准备
- **DPO训练**: 直接偏好优化
- **教师评分**: RLAIF反馈机制
- **模型版本管理**: 版本控制与部署
- **A/B测试**: 流量分割与效果评估
- **自动回滚**: 性能监控与智能回滚

#### 训练流程 / Training Pipeline
```python
# 1. 生成偏好对
python tools/wf_sprint_i.py generate-pairs --host example.com

# 2. 启动DPO训练
python tools/wf_sprint_i.py train --dataset pairs.json

# 3. 部署模型
python tools/wf_sprint_i.py deploy --model trained_model --version 1.0.0

# 4. 创建A/B测试
python tools/wf_sprint_i.py ab-test create --name "strategy_test"
```

### Sprint J: 技能库与宏动作自动化

#### 核心功能 / Core Features
- **技能库**: 可重用宏动作库
- **热加载**: 运行时技能更新
- **模式挖掘**: PrefixSpan频繁序列挖掘
- **技能打包**: .wfpack签名验证包
- **宏执行**: 工作流中的宏动作支持

#### 技能包结构 / Skill Package Structure
```
skill_package.wfpack
├── manifest.json        # 技能元数据
├── macros/              # 宏定义
│   ├── login.json
│   └── navigation.json
├── signatures/          # 数字签名
└── resources/           # 资源文件
```

#### 使用示例 / Usage Examples
```python
# 加载技能包
python tools/wf_sprint_j.py load-package --path skills/web_automation.wfpack

# 执行宏动作
{"do": "macro.execute", "name": "login_sequence", "params": {"username": "test"}}

# 挖掘新技能
python tools/wf_sprint_j.py mine-skills --host linkedin.com --min-support 0.3
```

### Sprint K: 多模态UI理解与自适应执行

#### 核心功能 / Core Features
- **多模态融合**: 视觉+文本+几何特征
- **布局分析**: 高级页面结构理解
- **自适应执行**: 上下文感知策略选择
- **参数优化**: 实时执行参数调优
- **在线学习**: 持续性能改进

#### 自适应策略 / Adaptive Strategies
1. **保守策略**: 稳定性优先，低风险操作
2. **激进策略**: 效率优先，快速执行
3. **学习策略**: 探索优化，收集反馈
4. **融合策略**: 多模态信息融合决策

#### 使用示例 / Usage Examples
```python
# 多模态页面分析
curl -F image=@screenshot.png http://localhost:8007/analyze

# 自适应执行
{"do": "adaptive.run", "strategy": "auto", "context": {...}}

# 布局分析
python tools/wf_sprint_k.py analyze-page --screenshot page.png --save-analysis
```

---

## 服务启动指南 / Service Startup Guide

### 环境准备 / Environment Setup

```bash
# 1. 创建虚拟环境
python -m venv myenv && source myenv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑.env文件，设置API密钥

# 4. 初始化数据库
# 确保PostgreSQL已安装并运行
createdb automation_db
psql automation_db -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 5. 运行数据库迁移
psql automation_db -f db/migrations/sprint_h_rag_reflexion.sql
psql automation_db -f db/migrations/sprint_i_dpo_rlaif.sql
psql automation_db -f db/migrations/sprint_j_skills_macros.sql
psql automation_db -f db/migrations/sprint_k_multimodal.sql
```

### 核心服务启动 / Core Services Startup

```bash
# 启动核心视觉服务
uvicorn app:app --reload --host 0.0.0.0 --port 8000 &
uvicorn app_ocr:app --reload --host 0.0.0.0 --port 8001 &
uvicorn app_workflow:app --reload --host 0.0.0.0 --port 8002 &

# 启动Web界面
python app_replay.py &  # http://localhost:8890
```

### Sprint H服务启动 / Sprint H Services

```bash
# 启动嵌入服务
python -m server.services.embeddings &

# 启动召回API
uvicorn server.services.recall_api:app --reload --host 0.0.0.0 --port 8003 &
```

### Sprint I服务启动 / Sprint I Services

```bash
# 启动DPO训练服务
uvicorn server.services.dpo_service:app --reload --host 0.0.0.0 --port 8004 &

# 启动模型管理服务
uvicorn server.services.model_manager:app --reload --host 0.0.0.0 --port 8005 &

# 启动A/B测试服务
uvicorn server.services.ab_testing:app --reload --host 0.0.0.0 --port 8006 &

# 启动教师评分服务
python -m server.services.teacher_scoring &

# 启动自动回滚监控
python -m server.services.auto_rollback &
```

### Sprint J服务启动 / Sprint J Services

```bash
# 启动宏注册中心
python -m runtime.macros.registry &

# 启动技能挖掘任务（定时任务）
python -m jobs.skills.mine_subsequences &
```

### Sprint K服务启动 / Sprint K Services

```bash
# 启动视觉分析API
uvicorn vision.services.vision_api:app --reload --host 0.0.0.0 --port 8007 &

# 启动多模态融合服务
python -m vision.services.multimodal_fusion &

# 启动自适应执行引擎
python -m adaptive.engines.adaptive_executor &
```

### 一键启动脚本 / One-Click Startup Script

```bash
#!/bin/bash
# start_all_services.sh

# 启动核心服务
uvicorn app:app --reload --host 0.0.0.0 --port 8000 &
uvicorn app_ocr:app --reload --host 0.0.0.0 --port 8001 &
uvicorn app_workflow:app --reload --host 0.0.0.0 --port 8002 &

# 启动Sprint H服务
python -m server.services.embeddings &
uvicorn server.services.recall_api:app --reload --host 0.0.0.0 --port 8003 &

# 启动Sprint I服务
uvicorn server.services.dpo_service:app --reload --host 0.0.0.0 --port 8004 &
uvicorn server.services.model_manager:app --reload --host 0.0.0.0 --port 8005 &
uvicorn server.services.ab_testing:app --reload --host 0.0.0.0 --port 8006 &

# 启动Sprint K服务
uvicorn vision.services.vision_api:app --reload --host 0.0.0.0 --port 8007 &

# 启动Web界面
python app_replay.py &

echo "所有服务已启动完成！"
echo "核心API: http://localhost:8000"
echo "Web界面: http://localhost:8890"
```

### Orchestrator + Backend API 一键启动 / One-Click (8787 + 8788)

DOM 执行栈需要两个服务：
- Backend API（:8787）：扩展的 API_BASE，处理签名/日志等
- Orchestrator（:8788）：与扩展的 WS 通道以及 run 绑定/动作分发

脚本（仓库已提供）：
```bash
./scripts/start_orchestrator_backend.sh
# Backend : http://127.0.0.1:8787/health
# Orchestrator : http://127.0.0.1:8788/health
# 引擎环境：export EXT_ORCH_BASE=http://127.0.0.1:8788
```

或手动启动：
```bash
# 8787 Backend API
node getcontent/backend/src/index.js

# 8788 Orchestrator
node getcontent/backend/orchestrator.js

# 健康检查
curl -s http://127.0.0.1:8787/health
curl -s http://127.0.0.1:8788/health
```

---

## API接口文档 / API Documentation

### 核心API / Core APIs

#### YOLO检测API (Port 8000)
```bash
# 健康检查
GET http://localhost:8000/health

# 目标检测
POST http://localhost:8000/predict
Content-Type: multipart/form-data
Body: image=@screenshot.png&return_image=false
```

#### OCR API (Port 8001)
```bash
# OCR文字识别
POST http://localhost:8001/predict
Content-Type: multipart/form-data
Body: image=@screenshot.png
```

#### 工作流API (Port 8002)
```bash
# 生成工作流
POST http://localhost:8002/generate
Content-Type: application/json
Body: {"task": "登录LinkedIn并发送消息", "provider": "gemini"}
```

### Sprint H API / Memory & Reflexion APIs

#### 召回API (Port 8003)
```bash
# 轨迹召回
POST http://localhost:8003/recall
Content-Type: application/json
Body: {
  "goal": "登录网站",
  "fingerprint": "optional_fingerprint",
  "k": 5,
  "threshold": 0.7
}

# 响应示例
{
  "similar_trajectories": [
    {
      "plan_id": 123,
      "similarity": 0.89,
      "trajectory": {...},
      "success_rate": 0.95
    }
  ],
  "suggestions": ["建议使用记住密码功能"]
}
```

#### 嵌入API
```bash
# 生成嵌入向量
POST http://localhost:8003/embed
Content-Type: application/json
Body: {
  "texts": ["用户登录流程", "密码输入步骤"],
  "provider": "openai"
}
```

### Sprint I API / Training & Optimization APIs

#### DPO训练API (Port 8004)
```bash
# 启动训练
POST http://localhost:8004/train
Content-Type: application/json
Body: {
  "dataset_path": "data/preference_pairs.json",
  "model_name": "workflow_optimizer",
  "epochs": 3,
  "learning_rate": 5e-6
}

# 训练状态查询
GET http://localhost:8004/training/status/{job_id}
```

#### 模型管理API (Port 8005)
```bash
# 部署模型
POST http://localhost:8005/deploy
Content-Type: application/json
Body: {
  "model_name": "workflow_optimizer",
  "version": "1.2.0",
  "environment": "production",
  "traffic_percentage": 10
}

# 模型回滚
POST http://localhost:8005/rollback
Content-Type: application/json
Body: {
  "model_name": "workflow_optimizer",
  "target_version": "1.1.0"
}
```

#### A/B测试API (Port 8006)
```bash
# 创建实验
POST http://localhost:8006/experiments
Content-Type: application/json
Body: {
  "name": "strategy_comparison",
  "description": "比较保守策略vs激进策略",
  "variants": {
    "control": {"strategy": "conservative"},
    "treatment": {"strategy": "aggressive"}
  },
  "traffic_split": {"control": 0.5, "treatment": 0.5}
}

# 获取实验结果
GET http://localhost:8006/experiments/{experiment_id}/results
```

### Sprint K API / Multimodal & Adaptive APIs

#### 视觉分析API (Port 8007)
```bash
# 多模态页面分析
POST http://localhost:8007/analyze
Content-Type: multipart/form-data
Body: image=@screenshot.png&include_layout=true&include_text=true

# 响应示例
{
  "page_understanding": {
    "layout_type": "login_form",
    "confidence": 0.94,
    "elements": [
      {
        "type": "input_field",
        "purpose": "username",
        "bbox": [100, 200, 250, 230],
        "confidence": 0.98
      }
    ],
    "interaction_zones": [...],
    "recommendations": [
      "使用Tab键在输入框间导航",
      "检测到记住密码选项"
    ]
  }
}
```

#### 自适应执行API
```bash
# 自适应策略选择
POST http://localhost:8007/adaptive/select_strategy
Content-Type: application/json
Body: {
  "context": {
    "page_complexity": "medium",
    "user_priority": "balanced",
    "time_constraints": 30000,
    "historical_success_rate": 0.85
  }
}

# 参数优化
POST http://localhost:8007/adaptive/optimize_params
Content-Type: application/json
Body: {
  "workflow_context": {...},
  "current_performance": {...}
}
```

---

## 工作流使用指南 / Workflow Usage Guide

### 基础工作流结构 / Basic Workflow Structure（v1.1 要点）

- 建议使用语义指令层 `instr.*`（Action Space v2）；引擎会优先走 DOM（扩展 `ext.*`），失败回退坐标。
- 顶层可配置 `autofix`：支持运行期热补与成功后自动晋升（生成 `.autofix.json`）。

```json
{
  "name": "网站登录流程",
  "description": "自动登录到指定网站",
  "start": "navigate_to_login",
  "states": {
    "navigate_to_login": {
      "actions": [
        {"do": "instr.navigate", "url": "https://example.com/login"},
        {"do": "instr.key", "key": "WaitQuiet"}
      ],
      "next": "perform_login"
    },
    "perform_login": {
      "actions": [
        {"do": "instr.click", "target": {"css": "input[name=username]"}},
        {"do": "instr.type_text", "target": {"css": "input[name=username]"}, "text": "{username}", "clear": true},
        {"do": "instr.click", "target": {"css": "input[name=password]"}},
        {"do": "instr.type_text", "target": {"css": "input[name=password]"}, "text": "{password}", "clear": true},
        {"do": "instr.click", "target": {"role": "button", "text": "登录"}},
        {"do": "instr.key", "key": "WaitQuiet"}
      ],
      "next": "verify_login"
    }
  }
}
```

### 高级工作流特性 / Advanced Workflow Features

#### 使用记忆增强 / Memory-Enhanced Workflows
```json
{
  "states": {
    "smart_login": {
      "actions": [
        {
          "do": "mem.recall",
          "goal": "登录{site_name}",
          "k": 3,
          "use_suggestions": true
        },
        {"do": "autostep", "instruction": "根据记忆建议执行登录"}
      ]
    }
  }
}
```

#### 使用宏动作 / Macro Actions
```json
{
  "states": {
    "automated_login": {
      "actions": [
        {
          "do": "macro.execute",
          "name": "standard_login",
          "params": {
            "username": "{username}",
            "password": "{password}",
            "remember_me": true
          }
        }
      ]
    }
  }
}
```

#### 自适应执行 / Adaptive Execution
```json
{
  "states": {
    "adaptive_navigation": {
      "actions": [
        {
          "do": "adaptive.run",
          "strategy": "auto",
          "context": {
            "page_type": "dynamic",
            "priority": "accuracy",
            "timeout": 15000
          },
          "fallback_strategy": "conservative"
        }
      ]
    }
  }
}
```

#### 反思与改进 / Reflexion & Improvement
```json
{
  "states": {
    "learning_step": {
      "actions": [
        {"do": "autostep", "instruction": "尝试点击提交按钮"},
        {
          "do": "plan.reflect",
          "focus": "success_analysis",
          "if_failed": {
            "do": "plan.reflect",
            "focus": "error_analysis"
          }
        }
      ]
    }
  }
}
```

### 执行命令 / Execution Commands

#### 基础执行 / Basic Execution
```bash
# 运行标准工作流
python run_workflow.py --workflow flows/login.json --endpoint http://127.0.0.1:8000

# 使用特定LLM提供商
python run_workflow.py --workflow flows/login.json --provider gemini --model gemini-1.5-flash
```

#### 高级执行选项 / Advanced Execution Options
```bash
# 启用记忆功能
python run_workflow.py --workflow flows/login.json --enable-memory --recall-threshold 0.7

# 启用宏支持
python run_workflow.py --workflow flows/login.json --macro-path skills/ --allow-macros

# 自适应模式
python run_workflow.py --workflow flows/login.json --adaptive-mode --strategy-selection auto

# A/B测试模式
python run_workflow.py --workflow flows/login.json --ab-experiment login_test --variant treatment
```

#### 调试模式 / Debug Mode
```bash
# 详细日志模式
python run_workflow.py --workflow flows/login.json --debug --save-screenshots

# 步进模式（每步确认）
python run_workflow.py --workflow flows/login.json --step-mode --interactive

# 干运行模式（不执行实际操作）
python run_workflow.py --workflow flows/login.json --dry-run --show-plan
```

---

## CLI工具参考 / CLI Tools Reference

### Sprint H工具 / Sprint H Tools

```bash
# wf_sprint_h.py - RAG记忆与反思工具

# 测试嵌入功能
python tools/wf_sprint_h.py test-embeddings --text "用户登录流程" --provider openai

# 生成轨迹嵌入
python tools/wf_sprint_h.py generate-embeddings --plan-ids 1,2,3 --batch-size 10

# 测试召回功能
python tools/wf_sprint_h.py test-recall --goal "登录LinkedIn" --k 5 --threshold 0.7

# 分析相似轨迹
python tools/wf_sprint_h.py analyze-similarities --host linkedin.com --days 30

# 测试反思功能
python tools/wf_sprint_h.py test-reflection --plan-id 123 --focus error_analysis

# 导出记忆数据
python tools/wf_sprint_h.py export-memory --format json --output memory_backup.json
```

### Sprint I工具 / Sprint I Tools

```bash
# wf_sprint_i.py - DPO训练与优化工具

# 生成偏好对数据
python tools/wf_sprint_i.py generate-pairs --host example.com --goal login --days 7 --min-success-rate 0.8

# 启动DPO训练
python tools/wf_sprint_i.py train --dataset data/pairs.json --model workflow_optimizer --epochs 3 --learning-rate 5e-6

# 评估模型性能
python tools/wf_sprint_i.py evaluate --model workflow_optimizer --version 1.2.0 --test-set data/test.json

# 部署模型
python tools/wf_sprint_i.py deploy --model workflow_optimizer --version 1.2.0 --environment staging --traffic 10

# 创建A/B测试
python tools/wf_sprint_i.py ab-test create --name strategy_test --config ab_config.json --duration 7

# 查看A/B测试结果
python tools/wf_sprint_i.py ab-test results --experiment-id 123 --export-report

# 监控模型性能
python tools/wf_sprint_i.py monitor --model workflow_optimizer --alert-threshold 0.1

# 执行模型回滚
python tools/wf_sprint_i.py rollback --model workflow_optimizer --to-version 1.1.0 --reason "性能下降"
```

### Sprint J工具 / Sprint J Tools

```bash
# wf_sprint_j.py - 技能与宏工具

# 查看注册中心状态
python tools/wf_sprint_j.py registry-status --detailed

# 加载技能包
python tools/wf_sprint_j.py load-package --path skills/web_automation.wfpack --verify-signature

# 创建新技能包
python tools/wf_sprint_j.py create-package --name custom_skills --version 1.0.0 --macros macros/ --output skills/

# 挖掘频繁技能模式
python tools/wf_sprint_j.py mine-skills --host linkedin.com --min-support 0.3 --min-length 3 --days 30

# 测试宏执行
python tools/wf_sprint_j.py test-macro --name login_sequence --params '{"username":"test","password":"test"}' --dry-run

# 验证技能包
python tools/wf_sprint_j.py validate-package --path skills/test.wfpack --strict

# 导出技能库
python tools/wf_sprint_j.py export-skills --format json --include-stats --output skills_backup.json

# 技能性能分析
python tools/wf_sprint_j.py analyze-performance --skill-name login_sequence --days 7 --detailed
```

### Sprint K工具 / Sprint K Tools

```bash
# wf_sprint_k.py - 多模态与自适应工具

# 页面分析
python tools/wf_sprint_k.py analyze-page --screenshot page.png --save-analysis --output-dir analysis/

# 训练视觉模型
python tools/wf_sprint_k.py train-vision --data-dir training_data --epochs 10 --model-type layout_classifier

# 测试自适应执行
python tools/wf_sprint_k.py adaptive-run --context test_context.json --strategy auto --dry-run

# 创建A/B实验
python tools/wf_sprint_k.py ab-test create --name ui_understanding_test --config experiments/ui_test.json

# 查看实验状态
python tools/wf_sprint_k.py ab-test status --experiment-id 123 --detailed

# 生成实验报告
python tools/wf_sprint_k.py ab-test report --experiment-id 123 --format html --output reports/

# 部署模型
python tools/wf_sprint_k.py model deploy --name layout_classifier --version 1.2.0 --environment production

# 模型回滚
python tools/wf_sprint_k.py model rollback --name layout_classifier --to-version 1.1.0

# 分析反馈模式
python tools/wf_sprint_k.py feedback analyze --days 7 --host ca.indeed.com --export-report

# 查看反馈模式
python tools/wf_sprint_k.py feedback patterns --host ca.indeed.com --pattern-type failure

# 性能优化建议
python tools/wf_sprint_k.py optimize --host ca.indeed.com --goal apply_jobs --dry-run

# 应用优化建议
python tools/wf_sprint_k.py optimize apply-suggestions --suggestion-id 456 --confirm
```

### 通用工具 / General Tools

```bash
# 集成测试套件
python tools/integration_test_suite.py --include-all --detailed-report

# LLM管理工具
python tools/llm_admin_corrected.py --provider gemini --test-connection

# 工作流生成器
python tools/run_workflow_gen.py --task "自动化LinkedIn发消息" --provider gemini --out flows/linkedin_message.json
```

---

## 数据库配置 / Database Configuration

### PostgreSQL设置 / PostgreSQL Setup

```bash
# 1. 安装PostgreSQL (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib

# 2. 安装pgvector扩展
sudo apt-get install postgresql-15-pgvector

# 3. 创建数据库
sudo -u postgres createdb automation_db

# 4. 创建用户
sudo -u postgres psql -c "CREATE USER automation_user WITH PASSWORD 'your_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE automation_db TO automation_user;"

# 5. 启用pgvector扩展
sudo -u postgres psql automation_db -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 环境变量配置 / Environment Variables

```bash
# .env文件配置示例
DATABASE_URL=postgresql://automation_user:your_password@localhost:5432/automation_db
POSTGRES_USER=automation_user
POSTGRES_PASSWORD=your_password
POSTGRES_DB=automation_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# LLM提供商配置
LLM_PROVIDER=gemini
LLM_MODEL=gemini-1.5-flash
OPENAI_API_KEY=your_openai_key
GEMINI_API_KEY=your_gemini_key

# 嵌入服务配置
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-ada-002
EMBEDDING_DIMENSION=1024

# 其他配置
YOLO_WEIGHTS=weights/best.pt
YOLO_CONF=0.25
YOLO_IOU=0.45
REDIS_URL=redis://localhost:6379
```

### 数据库迁移 / Database Migrations

```sql
-- 运行所有迁移
psql automation_db -f db/migrations/sprint_h_rag_reflexion.sql
psql automation_db -f db/migrations/sprint_i_dpo_rlaif.sql
psql automation_db -f db/migrations/sprint_j_skills_macros.sql
psql automation_db -f db/migrations/sprint_k_multimodal.sql

-- 验证表创建
psql automation_db -c "\dt"

-- 检查pgvector扩展
psql automation_db -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
```

### 数据备份与恢复 / Backup & Restore

```bash
# 备份数据库
pg_dump automation_db > backup_$(date +%Y%m%d_%H%M%S).sql

# 恢复数据库
psql automation_db < backup_20241201_120000.sql

# 备份特定表
pg_dump automation_db -t plans_history -t embeddings_cache > memory_backup.sql
```

---

## 部署指南 / Deployment Guide

### Docker部署 / Docker Deployment

#### Dockerfile示例 / Dockerfile Example

```dockerfile
FROM python:3.9-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    postgresql-client \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8000 8001 8002 8003 8004 8005 8006 8007 8890

# 启动命令
CMD ["./start_all_services.sh"]
```

#### Docker Compose配置 / Docker Compose Configuration

```yaml
version: '3.8'

services:
  # 数据库服务
  postgres:
    image: pgvector/pgvector:pg15
    environment:
      POSTGRES_DB: automation_db
      POSTGRES_USER: automation_user
      POSTGRES_PASSWORD: your_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./db/migrations:/docker-entrypoint-initdb.d
    ports:
      - "5432:5432"

  # Redis缓存
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  # 核心API服务
  yolo-api:
    build: .
    command: uvicorn app:app --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
    environment:
      - DATABASE_URL=postgresql://automation_user:your_password@postgres:5432/automation_db

  ocr-api:
    build: .
    command: uvicorn app_ocr:app --host 0.0.0.0 --port 8001
    ports:
      - "8001:8001"
    depends_on:
      - postgres

  workflow-api:
    build: .
    command: uvicorn app_workflow:app --host 0.0.0.0 --port 8002
    ports:
      - "8002:8002"
    depends_on:
      - postgres

  # Sprint H服务
  recall-api:
    build: .
    command: uvicorn server.services.recall_api:app --host 0.0.0.0 --port 8003
    ports:
      - "8003:8003"
    depends_on:
      - postgres

  # Sprint I服务
  dpo-service:
    build: .
    command: uvicorn server.services.dpo_service:app --host 0.0.0.0 --port 8004
    ports:
      - "8004:8004"
    depends_on:
      - postgres

  model-manager:
    build: .
    command: uvicorn server.services.model_manager:app --host 0.0.0.0 --port 8005
    ports:
      - "8005:8005"
    depends_on:
      - postgres

  ab-testing:
    build: .
    command: uvicorn server.services.ab_testing:app --host 0.0.0.0 --port 8006
    ports:
      - "8006:8006"
    depends_on:
      - postgres

  # Sprint K服务
  vision-api:
    build: .
    command: uvicorn vision.services.vision_api:app --host 0.0.0.0 --port 8007
    ports:
      - "8007:8007"
    depends_on:
      - postgres

  # Web界面
  web-ui:
    build: .
    command: python app_replay.py
    ports:
      - "8890:8890"
    depends_on:
      - yolo-api

volumes:
  postgres_data:
```

### Kubernetes部署 / Kubernetes Deployment

#### 配置清单示例 / Configuration Manifests

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: ai-automation

---
# postgres-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: ai-automation
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: pgvector/pgvector:pg15
        env:
        - name: POSTGRES_DB
          value: automation_db
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: username
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: password
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
      volumes:
      - name: postgres-storage
        persistentVolumeClaim:
          claimName: postgres-pvc

---
# core-apis-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: core-apis
  namespace: ai-automation
spec:
  replicas: 3
  selector:
    matchLabels:
      app: core-apis
  template:
    metadata:
      labels:
        app: core-apis
    spec:
      containers:
      - name: yolo-api
        image: ai-automation:latest
        command: ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: url
```

### 生产环境配置 / Production Configuration

#### 负载均衡 / Load Balancing

```nginx
# nginx.conf
upstream yolo_api {
    server api1.example.com:8000;
    server api2.example.com:8000;
    server api3.example.com:8000;
}

upstream advanced_apis {
    server api1.example.com:8003;
    server api1.example.com:8004;
    server api1.example.com:8005;
    server api1.example.com:8006;
    server api1.example.com:8007;
}

server {
    listen 80;
    server_name api.yourdomain.com;

    location /yolo/ {
        proxy_pass http://yolo_api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /advanced/ {
        proxy_pass http://advanced_apis/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

#### 监控配置 / Monitoring Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'ai-automation-apis'
    static_configs:
      - targets: ['localhost:8000', 'localhost:8001', 'localhost:8002']

  - job_name: 'advanced-apis'
    static_configs:
      - targets: ['localhost:8003', 'localhost:8004', 'localhost:8005', 'localhost:8006', 'localhost:8007']
```

---

## 故障排除 / Troubleshooting

---

## Action Space v2（instr.*）

- 语义指令集（暴露给 LLM/作者）：`instr.click`、`instr.type_text(clear?)`、`instr.select_option(value)`、`instr.scroll(dir,amount)`、`instr.navigate(url)`、`instr.history(op)`、`instr.hover`、`instr.key(key|WaitQuiet)`、`instr.upload(file)`、`instr.read(fields)`、`instr.wait(ms)`、`instr.task_complete(message)`、`instr.answer_user(text)`。
- 统一目标 `target`：支持 `element_id / css / xpath / role+text / bbox_var`；执行器先 DOM 解析（扩展 `ext.resolve`）→ 失败回退坐标。
- DOM 原语补齐：`ext.resolve`、`ext.hover`、`ext.select_option`、`ext.upload_file`（CDP）、`ext.history`。

示例（XHS 搜索）
```json
{
  "start": "open_home",
  "states": {
    "open_home": {
      "actions": [
        {"do":"instr.navigate","url":"https://www.xiaohongshu.com/explore"},
        {"do":"instr.key","key":"WaitQuiet"},
        {"do":"instr.click","target":{"css":"input[placeholder*='搜索'], input[type=search]"}}
      ],
      "on_success": "search"
    }
  }
}
```

---

## AutoFix 与自动晋升

- 顶层 `autofix`：
  - `mode`: `suggest_only`（仅建议）、`hot_patch_session`（运行期热补重试）、`auto_promote_on_success`（热补+成功后固化补丁）。
  - `limits.max_patches_per_run`: 本次运行热补次数（默认 2）。
  - `allowed_patch_kinds`: 安全补丁白名单（默认 `wait_quiet_insert`、`scroll_then_retry`）。
- 运行期：
  - 建议写入 `out/logs/patch_proposals.jsonl`；
  - 热补（启用时）：插入一次 WaitQuiet 或小滚动后重试关键动作（点击/输入/导航）。
- 自动晋升：
  - run 成功时，将安全补丁固化为 `flows/<name>.autofix.json` 并保存审计副本 `out/logs/patched_workflow_*.json`。

---

## 工作流编写与生成（WAM/LLM）

- WAM 构建器与校验：`tools/wam/`
  - `WF`：链式拼装 `start/state/for_range/poll`；
  - `validator`: schema + 语义校验（start/非空 actions/可达/变量引用）；
  - `sim`：干跑 PageState，输出 issues 与建议补丁。
- 统一生成 CLI：`python -m tools.wam.gen_cli ...`
  - 模板：`template xhs_search|wechat_reply|indeed_loop`（默认 `instr.*` + `autofix`）
  - LLM：`llm --task "..." --provider ... --model ...`（系统约束生成 `instr.*` + 顶层 `autofix`）

### 捕获配置（Capture Config）

为更精确的定位/点击，可以在工作流里声明截图模式（不改变现有全屏逻辑）：

```json
{
  "vars": {
    "capture": {
      "mode": "full | active_window | region",
      "window_offset_px": [x, y],     // 可选：区域左上角相对屏幕的偏移（px）
      "window_size_px": [w, h],       // 可选：区域大小（px）
      "apply_offset": false,          // 可选：若检测/截图基于区域，请显式开启以在映射中应用偏移
      "dpr_hint": 2.0                 // 可选：DPR 提示
    }
  }
}
```

说明：
- 目前默认仍使用全屏截图；当开启 `active_window/region` 时，需要在映射中加入 `window_offset_px` 校正以保证点击坐标正确（引擎读取该配置后进行偏移校正）。
- 若系统无法获取活动窗口边界，将回退全屏并记录日志，保持稳健性。
- 为避免错位，只有当 `apply_offset=true` 且提供 `window_offset_px` 时，引擎才会在坐标映射中应用偏移。

### 常见问题 / Common Issues

#### 1. 服务启动失败 / Service Startup Failures

**问题**: 端口被占用
```bash
# 检查端口占用
lsof -i :8000
netstat -tulpn | grep 8000

# 终止占用进程
kill -9 <PID>
```

**问题**: 数据库连接失败
```bash
# 检查PostgreSQL状态
sudo systemctl status postgresql

# 检查数据库连接
psql -h localhost -U automation_user -d automation_db -c "SELECT 1;"

# 检查pgvector扩展
psql automation_db -c "SELECT * FROM pg_available_extensions WHERE name = 'vector';"
```

**问题**: 依赖包缺失
```bash
# 重新安装依赖
pip install -r requirements.txt --force-reinstall

# 检查特定包
python -c "import torch; print(torch.__version__)"
python -c "import transformers; print(transformers.__version__)"
```

#### 2. API响应错误 / API Response Errors

**问题**: YOLO检测失败
```bash
# 检查模型文件
ls -la weights/
file weights/best.pt

# 测试图片格式
python -c "from PIL import Image; img = Image.open('test.png'); print(img.format, img.size)"
```

**问题**: LLM调用失败
```bash
# 检查API密钥
echo $GEMINI_API_KEY
echo $OPENAI_API_KEY

# 测试连接
curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models
```

#### 3. 内存与性能问题 / Memory & Performance Issues

**问题**: 内存不足
```bash
# 监控内存使用
free -h
htop

# 调整服务配置
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
```

**问题**: 响应时间过长
```bash
# 检查日志
tail -f logs/app.log

# 性能分析
python -m cProfile -o profile.stats run_workflow.py
```

### 日志分析 / Log Analysis

#### 日志配置 / Logging Configuration

```python
# logging_config.py
import logging.config

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
        'detailed': {
            'format': '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s'
        }
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'standard'
        },
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': 'logs/ai_automation.log',
            'formatter': 'detailed'
        }
    },
    'loggers': {
        '': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False
        }
    }
}
```

#### 日志分析脚本 / Log Analysis Scripts

```bash
# 分析错误模式
grep "ERROR" logs/ai_automation.log | awk '{print $4}' | sort | uniq -c | sort -nr

# 分析API响应时间
grep "response_time" logs/ai_automation.log | awk '{print $NF}' | sort -n

# 分析失败的工作流
grep "workflow_failed" logs/ai_automation.log | jq '.workflow_id' | sort | uniq
```

### 健康检查脚本 / Health Check Scripts

```bash
#!/bin/bash
# health_check.sh

echo "=== AI自动化系统健康检查 ==="

# 检查核心服务
services=(
    "8000:YOLO API"
    "8001:OCR API"
    "8002:Workflow API"
    "8003:Recall API"
    "8004:DPO Service"
    "8005:Model Manager"
    "8006:A/B Testing"
    "8007:Vision API"
)

for service in "${services[@]}"; do
    port=$(echo $service | cut -d: -f1)
    name=$(echo $service | cut -d: -f2)

    if curl -s http://localhost:$port/health > /dev/null; then
        echo "✅ $name (端口 $port): 正常"
    else
        echo "❌ $name (端口 $port): 异常"
    fi
done

# 检查数据库
if psql -h localhost -U automation_user -d automation_db -c "SELECT 1;" > /dev/null 2>&1; then
    echo "✅ PostgreSQL数据库: 正常"
else
    echo "❌ PostgreSQL数据库: 异常"
fi

# 检查磁盘空间
disk_usage=$(df -h / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $disk_usage -lt 90 ]; then
    echo "✅ 磁盘空间: 正常 (使用率: ${disk_usage}%)"
else
    echo "⚠️ 磁盘空间: 警告 (使用率: ${disk_usage}%)"
fi

# 检查内存使用
memory_usage=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
echo "📊 内存使用率: ${memory_usage}%"

echo "=== 健康检查完成 ==="
```

### 性能优化建议 / Performance Optimization Tips

#### 1. 服务级优化 / Service-Level Optimization

```bash
# 调整工作进程数
uvicorn app:app --workers 4 --worker-class uvicorn.workers.UvicornWorker

# 启用HTTP/2
uvicorn app:app --http h2

# 配置缓存
export REDIS_URL=redis://localhost:6379
```

#### 2. 数据库优化 / Database Optimization

```sql
-- 创建索引
CREATE INDEX CONCURRENTLY idx_plans_history_embed ON plans_history USING ivfflat (trajectory_embed vector_cosine_ops);

-- 分析查询性能
EXPLAIN ANALYZE SELECT * FROM plans_history WHERE trajectory_embed <-> '[...]' < 0.3;

-- 更新统计信息
VACUUM ANALYZE plans_history;
```

#### 3. 模型优化 / Model Optimization

```python
# YOLO模型量化
model = YOLO('weights/best.pt')
model.export(format='onnx', int8=True)

# 批处理优化
async def batch_predict(images: List[bytes], batch_size: int = 8):
    # 批量处理逻辑
    pass
```

---

## 附录 / Appendix

### 配置文件模板 / Configuration Templates

#### .env模板 / .env Template
```bash
# 数据库配置
DATABASE_URL=postgresql://automation_user:password@localhost:5432/automation_db
POSTGRES_USER=automation_user
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=automation_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# LLM提供商配置
LLM_PROVIDER=gemini
LLM_MODEL=gemini-1.5-flash
OPENAI_API_KEY=sk-your-openai-key
GEMINI_API_KEY=your-gemini-key
DEEPSEEK_API_KEY=your-deepseek-key

# 嵌入服务配置
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-ada-002
EMBEDDING_DIMENSION=1024

# YOLO配置
YOLO_WEIGHTS=weights/best.pt
YOLO_CONF=0.25
YOLO_IOU=0.45
YOLO_IMGSZ=640

# 服务配置
REDIS_URL=redis://localhost:6379
LOG_LEVEL=INFO
DEBUG=false

# 安全配置
JWT_SECRET=your-jwt-secret-key
ENCRYPTION_KEY=your-encryption-key
```

#### 工作流模板 / Workflow Templates

**标准登录模板**
```json
{
  "name": "标准网站登录",
  "description": "通用网站登录流程",
  "parameters": {
    "username": {"type": "string", "required": true},
    "password": {"type": "string", "required": true},
    "remember_me": {"type": "boolean", "default": false}
  },
  "start": "navigate_to_site",
  "states": {
    "navigate_to_site": {
      "actions": [{"do": "goto", "url": "{login_url}"}],
      "next": "detect_login_form"
    },
    "detect_login_form": {
      "actions": [
        {"do": "mem.recall", "goal": "登录{site_name}", "k": 3},
        {"do": "autostep", "instruction": "识别登录表单"}
      ],
      "next": "fill_credentials"
    },
    "fill_credentials": {
      "actions": [
        {"do": "autostep", "instruction": "点击用户名输入框"},
        {"do": "type_text", "text": "{username}"},
        {"do": "autostep", "instruction": "点击密码输入框"},
        {"do": "type_text", "text": "{password}"},
        {
          "do": "autostep",
          "instruction": "勾选记住我选项",
          "condition": "{remember_me}"
        }
      ],
      "next": "submit_login"
    },
    "submit_login": {
      "actions": [
        {"do": "autostep", "instruction": "点击登录按钮"},
        {"do": "wait_for", "target": "登录成功指示器", "timeout": 10000}
      ],
      "next": "verify_success",
      "on_error": "handle_login_failure"
    },
    "verify_success": {
      "actions": [
        {"do": "plan.reflect", "focus": "success_analysis"}
      ],
      "next": "end"
    },
    "handle_login_failure": {
      "actions": [
        {"do": "plan.reflect", "focus": "error_analysis"},
        {"do": "autostep", "instruction": "检查错误信息"}
      ],
      "next": "end"
    }
  }
}
```

### API示例代码 / API Example Code

#### Python客户端 / Python Client

```python
import asyncio
import aiohttp
from typing import Dict, List, Optional

class AIAutomationClient:
    def __init__(self, base_url: str = "http://localhost"):
        self.base_url = base_url

    async def detect_objects(self, image_path: str) -> Dict:
        """YOLO目标检测"""
        async with aiohttp.ClientSession() as session:
            with open(image_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('image', f, filename='image.png')

                async with session.post(
                    f"{self.base_url}:8000/predict",
                    data=data
                ) as response:
                    return await response.json()

    async def recall_memory(self, goal: str, k: int = 5) -> Dict:
        """记忆召回"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}:8003/recall",
                json={"goal": goal, "k": k}
            ) as response:
                return await response.json()

    async def run_workflow(self, workflow_path: str, params: Dict) -> Dict:
        """运行工作流"""
        async with aiohttp.ClientSession() as session:
            with open(workflow_path, 'r') as f:
                workflow = json.load(f)

            async with session.post(
                f"{self.base_url}:8002/execute",
                json={"workflow": workflow, "parameters": params}
            ) as response:
                return await response.json()

# 使用示例
async def main():
    client = AIAutomationClient()

    # 检测页面元素
    detection_result = await client.detect_objects("screenshot.png")
    print("检测结果:", detection_result)

    # 召回相似轨迹
    memory_result = await client.recall_memory("登录LinkedIn")
    print("记忆召回:", memory_result)

    # 执行工作流
    workflow_result = await client.run_workflow("flows/login.json", {
        "username": "test@example.com",
        "password": "password123"
    })
    print("工作流结果:", workflow_result)

if __name__ == "__main__":
    asyncio.run(main())
```

### 系统架构图 / System Architecture Diagrams

```mermaid
graph TB
    subgraph "用户接口层 User Interface Layer"
        UI1[Web界面 :8890]
        UI2[CLI工具]
        UI3[API客户端]
    end

    subgraph "API网关层 API Gateway Layer"
        GW[Nginx负载均衡器]
    end

    subgraph "核心服务层 Core Services Layer"
        API1[YOLO API :8000]
        API2[OCR API :8001]
        API3[Workflow API :8002]
    end

    subgraph "高级服务层 Advanced Services Layer"
        subgraph "Sprint H"
            SH1[Recall API :8003]
            SH2[Embedding Service]
        end

        subgraph "Sprint I"
            SI1[DPO Service :8004]
            SI2[Model Manager :8005]
            SI3[A/B Testing :8006]
        end

        subgraph "Sprint K"
            SK1[Vision API :8007]
            SK2[Multimodal Fusion]
            SK3[Adaptive Executor]
        end
    end

    subgraph "数据持久层 Data Persistence Layer"
        DB1[(PostgreSQL + pgvector)]
        DB2[(Redis缓存)]
        DB3[(模型存储 Model Storage)]
        DB4[(技能库 Skill Library)]
    end

    subgraph "外部服务 External Services"
        EXT1[OpenAI API]
        EXT2[Gemini API]
        EXT3[监控系统 Monitoring]
    end

    UI1 --> GW
    UI2 --> GW
    UI3 --> GW

    GW --> API1
    GW --> API2
    GW --> API3

    API3 --> SH1
    API3 --> SI1
    API3 --> SK1

    SH1 --> SH2
    SI1 --> SI2
    SI2 --> SI3
    SK1 --> SK2
    SK2 --> SK3

    SH2 --> DB1
    SI2 --> DB3
    SK3 --> DB1

    SH1 --> DB2
    SI1 --> DB2

    SH2 --> EXT1
    SK2 --> EXT2

    EXT3 --> API1
    EXT3 --> SH1
    EXT3 --> SI1
```

---

## Task积木化系统 / Task Component System

### 概述 / Overview

Task积木化系统提供可重用的工作流组件，通过模块化设计实现复杂自动化任务的标准化和规模化部署。

### 核心架构 / Core Architecture

#### TaskRegistry - 任务注册器
```python
from runtime.tasks.task_registry import TaskRegistry

# 初始化任务注册器
registry = TaskRegistry()

# 注册新任务
registry.register_task("login_sequence", {
    "name": "login_sequence",
    "version": "1.0",
    "description": "通用登录序列",
    "parameters": ["username", "password", "remember_me"],
    "implementation": "workflows/login.json"
})

# 查询任务
task = registry.get_task("login_sequence")
print(f"Task: {task.name}, Version: {task.version}")
```

### Task Actions - 任务动作

#### task.run - 执行任务组件
```json
{
  "do": "task.run",
  "name": "login_sequence",
  "args": {
    "username": "@username",
    "password": "@password",
    "remember_me": true
  },
  "version": "1.0",
  "save": "login_result"
}
```

#### task.validate - 验证任务定义
```json
{
  "do": "task.validate",
  "name": "login_sequence",
  "save": "validation_result"
}
```

#### task.list - 列出可用任务
```json
{
  "do": "task.list",
  "category": "authentication",
  "host": "api.example.com",
  "save": "available_tasks"
}
```

#### task.sync - 同步任务注册表
```json
{
  "do": "task.sync",
  "host": "registry.company.com",
  "save": "sync_status"
}
```

#### task.install - 安装任务包
```json
{
  "do": "task.install",
  "name": "advanced_login",
  "version": "2.0",
  "source": "internal_registry",
  "save": "install_result"
}
```

### 任务组件示例 / Task Component Examples

#### 复合登录任务
```json
{
  "name": "enterprise_login",
  "version": "1.0",
  "description": "企业级登录流程",
  "states": {
    "start": {
      "actions": [
        {"do": "task.run", "name": "detect_login_form", "save": "form_info"},
        {"do": "task.run", "name": "fill_credentials", "args": {"form": "@form_info"}},
        {"do": "task.run", "name": "handle_2fa", "save": "auth_result"}
      ]
    }
  }
}
```

---

## WAM工作流创作模块 / Workflow Authoring Module

### 概述 / Overview

WAM (Workflow Authoring Module) 提供完整的工作流创作、验证和自愈工具链，支持从图形化构建到程序化生成的全方位工作流开发。

### CLI工具 / CLI Tools

#### wam_cli.py - 统一命令行工具

##### 创建工作流
```bash
# 基础创建
python tools/wam_cli.py create my_workflow --description "我的自动化流程"

# 从模板创建
python tools/wam_cli.py create job_application --template indeed_apply_loop

# 指定输出路径
python tools/wam_cli.py create test_flow --output flows/test/my_flow.json
```

##### 验证工作流
```bash
# 验证单个文件
python tools/wam_cli.py validate flows/my_workflow.json

# 批量验证
python tools/wam_cli.py validate flows/*.json
```

##### 自动修复
```bash
# 交互式修复
python tools/wam_cli.py fix flows/broken_workflow.json

# 自动应用修复
python tools/wam_cli.py fix flows/broken_workflow.json --auto-apply --backup

# 指定错误类型
python tools/wam_cli.py fix flows/broken_workflow.json \
  --error-type "element_not_found" \
  --error-message "Target button not found" \
  --auto-apply
```

##### 列出可用模板
```bash
python tools/wam_cli.py templates
```

##### 从任务描述构建
```bash
# 生成工作流
python tools/wam_cli.py build "循环申请10个职位" --name job_hunter

# 指定参数
python tools/wam_cli.py build "微信群发消息" \
  --name wechat_broadcast \
  --period 5000 \
  --count 50
```

### WorkflowBuilder - 程序化构建

#### 链式API构建
```python
from tools.wam.workflow_builder import WorkflowBuilder

# 创建基础工作流
workflow = (WorkflowBuilder()
    .name("automated_application")
    .description("自动化求职申请")
    .set_vars({
        "max_applications": 10,
        "delay_between": 2000
    })
    .for_range("apply", "i", "@max_applications", [
        {"do": "instr.scroll", "dir": "down", "amount": 300},
        {"do": "instr.click", "target": {"css": ".job-card:nth-child(@i+1)"}},
        {"do": "instr.wait", "ms": "@delay_between"},
        {"do": "instr.click", "target": {"role": "button", "text": "Apply"}}
    ])
    .state("completion", [
        {"do": "instr.answer_user", "text": "已完成@max_applications个申请"}
    ])
    .build())

# 保存为JSON
with open("flows/automated_application.json", "w") as f:
    json.dump(workflow, f, indent=2)
```

#### 高级构建模式
```python
# 条件分支
builder.conditional("check_login_status", "@user_logged_in == false", [
    {"do": "task.run", "name": "login_sequence"}
], [
    {"do": "instr.navigate", "url": "/dashboard"}
], "continue_workflow")

# 错误恢复
builder.error_recovery("retry_click", [
    {"do": "sleep_ms", "duration": 1000},
    {"do": "instr.scroll", "dir": "up", "amount": 100}
], "main_action", max_retries=3)

# 轮询模式
builder.poll("check_status", 5000, [
    {"do": "instr.read", "target": {"css": ".status"}, "save": "current_status"},
    {"do": "instr.click", "target": {"css": ".refresh"}}
], max_iterations=20)
```

### AutoFixer - 自愈系统

#### 故障分析与修复
```python
from tools.wam.autofixer import AutoFixer

autofixer = AutoFixer()

# 分析失败原因
error_context = {
    "error_type": "target_not_found",
    "error_message": "Element not found: button[type=submit]",
    "failed_state": "submit_form",
    "screenshot_path": "debug/error_screenshot.png",
    "workflow_path": "flows/broken_workflow.json"
}

# 生成分析报告
analysis = autofixer.analyze_failure(error_context)
print(f"问题类别: {analysis['category']}")
print(f"置信度: {analysis['confidence']}")

# 生成修复补丁
patches = autofixer.generate_patches(error_context, analysis)
for i, patch in enumerate(patches):
    print(f"{i+1}. {patch['description']} (置信度: {patch['confidence']})")

# 应用最佳补丁
if patches:
    best_patch = max(patches, key=lambda p: p['confidence'])
    result = autofixer.apply_patch("flows/broken_workflow.json", best_patch)
    if result['success']:
        print("✅ 修复成功应用")
    else:
        print(f"❌ 修复失败: {result['error']}")
```

#### 自动晋升配置
```json
{
  "autofix": {
    "mode": "auto_promote_on_success",
    "promote": {
      "enabled": true,
      "strategy": "auto_promote_on_success",
      "threshold": {
        "successes": 20,
        "window": 50,
        "min_runs": 30,
        "max_error_rate": 0.05,
        "p95_latency_ms": 10000
      },
      "rollout": {
        "staging_percent": 10,
        "soak_minutes": 60
      },
      "cooldown_minutes": 30
    }
  }
}
```

### WorkflowValidator - 验证系统

#### 完整验证流程
```python
from tools.wam.workflow_validator import WorkflowValidator

validator = WorkflowValidator()

# 验证工作流文件
result = validator.validate_file("flows/my_workflow.json")

print(f"验证结果: {'通过' if result['valid'] else '失败'}")

if result['errors']:
    print("错误列表:")
    for error in result['errors']:
        print(f"  - {error}")

if result['warnings']:
    print("警告列表:")
    for warning in result['warnings']:
        print(f"  - {warning}")
```

#### 语义验证功能
- **结构验证**: 必需字段、状态定义、动作列表
- **变量引用验证**: 未定义变量、作用域检查
- **状态可达性验证**: 孤立状态、循环检测
- **循环终止性验证**: 无限循环检测、终止条件分析
- **动作语义验证**: 参数完整性、动作类型检查

### 预设模板库 / Template Library

#### 可用模板
- **indeed_apply_loop**: Indeed循环申请模板
- **wechat_poll_reply**: 微信轮询回复模板
- **web_login_sequence**: 通用网页登录序列模板
- **data_extraction_pipeline**: 数据提取管道模板

#### 模板使用示例
```bash
# 使用Indeed申请模板
python tools/wam_cli.py create job_hunt --template indeed_apply_loop

# 使用微信轮询模板
python tools/wam_cli.py create wechat_auto --template wechat_poll_reply

# 自定义模板参数
python tools/wam_cli.py build "申请50个职位" \
  --template indeed_apply_loop \
  --count 50 \
  --name massive_application
```

---

## JSON Schema完整验证 / Complete JSON Schema Validation

### Schema概述 / Schema Overview

系统使用完整的JSON Schema (`schema/workflow.schema.json`) 验证所有工作流定义，确保语法正确性和语义一致性。

### 支持的动作类型 / Supported Action Types

#### Action Space v2 - 统一指令集 (14种)
```json
{
  "do": "instr.click",
  "target": {
    "css": "#submit-button",
    "role": "button",
    "text": "提交",
    "bbox_var": "@button_coords"
  }
}
```

**可用指令**:
- `instr.click`: 通用点击 (DOM优先 + 坐标回退)
- `instr.type_text`: 文本输入 (支持清空选项)
- `instr.select_option`: 下拉选择
- `instr.scroll`: 方向滚动
- `instr.navigate`: URL导航
- `instr.history`: 浏览器历史记录
- `instr.hover`: 鼠标悬停
- `instr.key`: 键盘输入
- `instr.upload`: 文件上传
- `instr.read`: 元素数据提取
- `instr.wait`: 智能等待
- `instr.task_complete`: 任务完成标记
- `instr.answer_user`: 用户反馈
- `instr.annotate`: 添加注释

#### Task积木化系统 (5种)
```json
{
  "do": "task.run",
  "name": "login_sequence",
  "args": {"username": "@user", "password": "@pass"},
  "version": "1.0",
  "save": "task_result"
}
```

**Task动作**:
- `task.run`: 执行任务组件
- `task.validate`: 验证任务定义
- `task.list`: 列出可用任务
- `task.sync`: 同步任务注册表
- `task.install`: 安装任务包

#### 扩展动作 (Chrome MV3)
- `ext.click_selector`: DOM点击
- `ext.type_text`: DOM文本输入
- `ext.key`: 键盘事件
- `ext.scroll`: 页面滚动
- `ext.extract`: 数据提取

#### 核心检测动作
- `detect`: YOLO目标检测
- `locate`: UI元素定位
- `wait_for`: 条件等待
- `screenshot`: 屏幕捕获

#### 变量与系统操作
- `set_variable`, `increment_variable`: 变量操作
- `get_list_length`, `get_list_item`: 数组操作
- `query_data`: 数据查询
- `authenticate`, `secure_operation`: 安全操作

### 目标解析系统 / Target Resolution System

#### instruction_target 定义
```json
{
  "target": {
    "css": "button.submit",           // CSS选择器 (DOM优先)
    "xpath": "//button[@type='submit']", // XPath替代
    "role": "button",                 // ARIA角色
    "text": "提交申请",                // 可见文本
    "placeholder": "请输入用户名",     // 输入占位符
    "bbox_var": "@saved_coordinates"  // 坐标变量 (回退)
  }
}
```

### 验证层次 / Validation Layers

#### 1. JSON Schema验证
- 语法结构验证
- 类型检查
- 必需字段验证
- 枚举值检查

#### 2. 语义验证
- 变量引用检查
- 状态可达性分析
- 循环终止性验证
- 动作参数完整性

#### 3. 运行时验证
- 目标元素可访问性
- LLM提供商可用性
- 文件路径有效性
- 网络连接状态

### Schema使用示例 / Schema Usage Examples

#### CLI验证
```bash
# 验证单个文件
python tools/wam/workflow_validator.py flows/my_workflow.json

# WAM CLI集成验证
python tools/wam_cli.py validate flows/my_workflow.json

# 批量验证
for file in flows/*.json; do
    python tools/wam_cli.py validate "$file"
done
```

#### 程序化验证
```python
from tools.wam.workflow_validator import validate_workflow_file

result = validate_workflow_file("flows/test.json")
if result["valid"]:
    print("✅ 工作流验证通过")
else:
    print("❌ 验证失败:")
    for error in result["errors"]:
        print(f"  - {error}")
```

---

**文档版本**: v1.0.0
**最后更新**: 2024年12月
**维护团队**: AI自动化系统开发团队

如有问题或建议，请联系开发团队或在项目仓库中提交Issue。
