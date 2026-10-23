# AI自动化系统使用指南
# AI Automation System Usage Guide

## 目录 / Table of Contents

1. [快速开始 / Quick Start](#快速开始--quick-start)
2. [核心功能使用 / Core Features Usage](#核心功能使用--core-features-usage)
3. [Sprint H: RAG记忆系统 / Memory & Reflexion](#sprint-h-rag记忆系统--memory--reflexion)
4. [Sprint I: DPO训练系统 / Training & Optimization](#sprint-i-dpo训练系统--training--optimization)
5. [Sprint J: 技能库系统 / Skills & Macros](#sprint-j-技能库系统--skills--macros)
6. [Sprint K: 多模态系统 / Multimodal & Adaptive](#sprint-k-多模态系统--multimodal--adaptive)
7. [Action Space v2: 语义指令 / Semantic Instructions](#action-space-v2-语义指令--semantic-instructions)
8. [Chrome扩展集成 / Chrome Extension Integration](#chrome扩展集成--chrome-extension-integration)
9. [AutoFix机制 / AutoFix Mechanism](#autofix机制--autofix-mechanism)
10. [工作流生成器 / Workflow Generator](#工作流生成器--workflow-generator)
11. [故障排除 / Troubleshooting](#故障排除--troubleshooting)

---

## 快速开始 / Quick Start

### 环境搭建 / Environment Setup

```bash
# 1. 克隆项目
git clone <repository-url>
cd game

# 2. 创建虚拟环境
python -m venv myenv
source myenv/bin/activate  # Linux/Mac
# myenv\Scripts\activate   # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，设置 API 密钥
```

### 基础服务启动 / Basic Service Startup

```bash
# 一键启动所有服务
./scripts/start_orchestrator_backend.sh

# 或分别启动核心服务
uvicorn app:app --reload --host 0.0.0.0 --port 8000 &     # YOLO API
uvicorn app_ocr:app --reload --host 0.0.0.0 --port 8001 & # OCR API
uvicorn app_workflow:app --reload --host 0.0.0.0 --port 8002 & # Workflow API
python app_replay.py &  # Web UI (http://localhost:8890)
```

### 第一个工作流 / First Workflow

```bash
# 运行预制工作流
python run_workflow.py --workflow flows/instr_demo.json --endpoint http://127.0.0.1:8000

# 生成新工作流
python tools/run_workflow_gen.py --task "打开百度搜索AI" --provider gemini --out flows/baidu_search.json

# 运行生成的工作流
python run_workflow.py --workflow flows/baidu_search.json --endpoint http://127.0.0.1:8000
```

---

## 核心功能使用 / Core Features Usage

### YOLO 目标检测 / YOLO Object Detection

**用途**: 自动识别页面UI元素（按钮、输入框、文本等）

```bash
# API调用
curl -F image=@screenshot.png "http://localhost:8000/predict?return_image=false"

# Python代码
import requests
with open('screenshot.png', 'rb') as f:
    response = requests.post('http://localhost:8000/predict', files={'image': f})
    detection_result = response.json()
```

**返回结果包含**:
- 检测框坐标 (bbox)
- 置信度 (confidence)
- 元素类型 (class)
- 唯一ID (id)

### OCR 文字识别 / OCR Text Recognition

**用途**: 识别页面中的文字内容，支持多语言

```bash
# API调用
curl -F image=@screenshot.png "http://localhost:8001/predict"

# 获取文字和位置信息
curl -F image=@screenshot.png "http://localhost:8001/predict?include_boxes=true"
```

### 工作流执行 / Workflow Execution

**基础执行**:
```bash
# 标准执行
python run_workflow.py --workflow flows/example.json --endpoint http://127.0.0.1:8000

# 调试模式
python run_workflow.py --workflow flows/example.json --debug --save-screenshots

# 指定LLM提供商
python run_workflow.py --workflow flows/example.json --provider gemini --model gemini-1.5-flash
```

**工作流JSON结构**:
```json
{
  "name": "示例工作流",
  "description": "演示基本操作",
  "start": "first_state",
  "states": {
    "first_state": {
      "actions": [
        {"do": "autostep", "instruction": "点击登录按钮"}
      ],
      "next": "second_state"
    }
  }
}
```

---

## Sprint H: RAG记忆系统 / Memory & Reflexion

### 功能概述 / Feature Overview

RAG记忆系统通过向量检索技术，让AI能够从历史执行轨迹中学习，提高自动化的成功率和智能化程度。

### 启动服务 / Start Services

```bash
# 启动嵌入服务
python -m server.services.embeddings &

# 启动召回API
uvicorn server.services.recall_api:app --reload --host 0.0.0.0 --port 8003 &
```

### 基础使用 / Basic Usage

#### 1. 轨迹召回 / Trajectory Recall

**API调用**:
```bash
curl -X POST http://localhost:8003/recall \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "登录LinkedIn",
    "k": 5,
    "threshold": 0.7
  }'
```

**工作流中使用**:
```json
{
  "actions": [
    {
      "do": "mem.recall",
      "goal": "登录{site_name}",
      "k": 3,
      "use_suggestions": true
    }
  ]
}
```

#### 2. 在线反思 / Online Reflexion

**成功分析**:
```json
{
  "actions": [
    {
      "do": "plan.reflect",
      "focus": "success_analysis",
      "context": "登录成功，分析关键步骤"
    }
  ]
}
```

**错误分析**:
```json
{
  "actions": [
    {
      "do": "plan.reflect",
      "focus": "error_analysis",
      "context": "登录失败，分析失败原因"
    }
  ]
}
```

### CLI工具使用 / CLI Tools

```bash
# 测试嵌入功能
python tools/wf_sprint_h.py test-embeddings --text "用户登录流程" --provider openai

# 生成轨迹嵌入
python tools/wf_sprint_h.py generate-embeddings --plan-ids 1,2,3 --batch-size 10

# 测试召回功能
python tools/wf_sprint_h.py test-recall --goal "登录LinkedIn" --k 5 --threshold 0.7

# 分析相似轨迹
python tools/wf_sprint_h.py analyze-similarities --host linkedin.com --days 30

# 导出记忆数据
python tools/wf_sprint_h.py export-memory --format json --output memory_backup.json
```

### 配置选项 / Configuration Options

**环境变量**:
```bash
# 嵌入提供商
EMBEDDING_PROVIDER=openai  # openai | sentence_transformers
EMBEDDING_MODEL=text-embedding-ada-002
EMBEDDING_DIMENSION=1024

# 数据库配置
DATABASE_URL=postgresql://user:pass@localhost:5432/automation_db
```

### 最佳实践 / Best Practices

1. **目标描述要清晰**: 使用具体的目标描述，如"登录LinkedIn并发送消息"而不是"登录"
2. **设置合适的k值**: 一般建议k=3-5，获取足够的相似轨迹
3. **调整阈值**: threshold=0.7是好的起点，可根据效果调整
4. **定期反思**: 在关键步骤后加入反思动作，提高学习效果

---

## Sprint I: DPO训练系统 / Training & Optimization

### 功能概述 / Feature Overview

DPO(Direct Preference Optimization)训练系统通过直接偏好优化，提升模型的决策质量，并支持A/B测试和自动回滚。

### 启动服务 / Start Services

```bash
# 启动DPO训练服务
uvicorn server.services.dpo_service:app --reload --host 0.0.0.0 --port 8004 &

# 启动模型管理服务
uvicorn server.services.model_manager:app --reload --host 0.0.0.0 --port 8005 &

# 启动A/B测试服务
uvicorn server.services.ab_testing:app --reload --host 0.0.0.0 --port 8006 &

# 启动后台服务
python -m server.services.teacher_scoring &
python -m server.services.auto_rollback &
```

### 训练流程 / Training Pipeline

#### 1. 生成偏好对 / Generate Preference Pairs

```bash
# 从历史数据生成偏好对
python tools/wf_sprint_i.py generate-pairs \
  --host example.com \
  --goal login \
  --days 7 \
  --min-success-rate 0.8 \
  --output data/preference_pairs.json
```

#### 2. 启动DPO训练 / Start DPO Training

```bash
# 训练模型
python tools/wf_sprint_i.py train \
  --dataset data/preference_pairs.json \
  --model workflow_optimizer \
  --epochs 3 \
  --learning-rate 5e-6 \
  --output-dir models/
```

**API调用**:
```bash
curl -X POST http://localhost:8004/train \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_path": "data/preference_pairs.json",
    "model_name": "workflow_optimizer",
    "epochs": 3,
    "learning_rate": 5e-6
  }'
```

#### 3. 模型评估 / Model Evaluation

```bash
# 评估模型性能
python tools/wf_sprint_i.py evaluate \
  --model workflow_optimizer \
  --version 1.2.0 \
  --test-set data/test.json
```

#### 4. 模型部署 / Model Deployment

```bash
# 部署到测试环境
python tools/wf_sprint_i.py deploy \
  --model workflow_optimizer \
  --version 1.2.0 \
  --environment staging \
  --traffic 10

# 部署到生产环境
python tools/wf_sprint_i.py deploy \
  --model workflow_optimizer \
  --version 1.2.0 \
  --environment production \
  --traffic 50
```

### A/B测试 / A/B Testing

#### 创建实验 / Create Experiment

```bash
# CLI方式
python tools/wf_sprint_i.py ab-test create \
  --name strategy_test \
  --config ab_config.json \
  --duration 7
```

**ab_config.json示例**:
```json
{
  "description": "比较新旧策略效果",
  "variants": {
    "control": {"strategy": "conservative", "model_version": "1.1.0"},
    "treatment": {"strategy": "aggressive", "model_version": "1.2.0"}
  },
  "traffic_split": {"control": 0.5, "treatment": 0.5},
  "success_metrics": ["completion_rate", "step_count", "error_rate"]
}
```

#### 查看实验结果 / View Results

```bash
# 查看实验状态
python tools/wf_sprint_i.py ab-test results --experiment-id 123 --export-report

# API查看
curl http://localhost:8006/experiments/123/results
```

### 自动回滚 / Auto Rollback

**配置回滚条件**:
```json
{
  "rollback_conditions": {
    "error_rate_threshold": 0.1,
    "success_rate_threshold": 0.8,
    "monitoring_window_minutes": 30
  }
}
```

**手动回滚**:
```bash
python tools/wf_sprint_i.py rollback \
  --model workflow_optimizer \
  --to-version 1.1.0 \
  --reason "性能下降"
```

### 监控与告警 / Monitoring & Alerts

```bash
# 实时监控模型性能
python tools/wf_sprint_i.py monitor \
  --model workflow_optimizer \
  --alert-threshold 0.1

# 查看性能指标
curl http://localhost:8005/models/workflow_optimizer/metrics
```

---

## Sprint J: 技能库系统 / Skills & Macros

### 功能概述 / Feature Overview

技能库系统通过可重用的宏动作，实现自动化技能的积累和复用，支持热加载和频繁模式挖掘。

### 启动服务 / Start Services

```bash
# 启动宏注册中心
python -m runtime.macros.registry &

# 启动技能挖掘任务
python -m jobs.skills.mine_subsequences &
```

### 技能包管理 / Skill Package Management

#### 1. 查看注册中心状态 / View Registry Status

```bash
# 查看已注册的技能
python tools/wf_sprint_j.py registry-status --detailed
```

#### 2. 加载技能包 / Load Skill Package

```bash
# 加载技能包
python tools/wf_sprint_j.py load-package \
  --path skills/web_automation.wfpack \
  --verify-signature
```

#### 3. 创建技能包 / Create Skill Package

```bash
# 创建新技能包
python tools/wf_sprint_j.py create-package \
  --name custom_skills \
  --version 1.0.0 \
  --macros macros/ \
  --output skills/
```

### 技能包结构 / Skill Package Structure

```
skill_package.wfpack
├── manifest.json        # 技能元数据
├── macros/              # 宏定义
│   ├── login.json       # 登录宏
│   ├── navigation.json  # 导航宏
│   └── form_fill.json   # 表单填写宏
├── signatures/          # 数字签名
└── resources/           # 资源文件
```

**manifest.json示例**:
```json
{
  "name": "web_automation_skills",
  "version": "1.0.0",
  "description": "通用网页自动化技能包",
  "author": "AI Automation Team",
  "macros": [
    {
      "name": "standard_login",
      "description": "标准登录流程",
      "parameters": ["username", "password", "remember_me"],
      "file": "macros/login.json"
    },
    {
      "name": "form_navigation",
      "description": "表单间导航",
      "parameters": ["target_field"],
      "file": "macros/navigation.json"
    }
  ]
}
```

### 工作流中使用宏 / Using Macros in Workflows

```json
{
  "states": {
    "login_step": {
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

### 技能挖掘 / Skill Mining

#### 自动挖掘频繁模式 / Auto Mine Frequent Patterns

```bash
# 挖掘特定网站的技能模式
python tools/wf_sprint_j.py mine-skills \
  --host linkedin.com \
  --min-support 0.3 \
  --min-length 3 \
  --days 30

# 从日志文件挖掘
python tools/wf_sprint_j.py mine-skills \
  --log-file execution_logs.jsonl \
  --min-support 0.5
```

**挖掘结果示例**:
```json
{
  "frequent_patterns": [
    {
      "pattern": ["click_username_field", "type_username", "click_password_field", "type_password", "click_login"],
      "support": 0.85,
      "confidence": 0.92,
      "suggested_macro_name": "standard_login_sequence"
    }
  ]
}
```

### 宏测试 / Macro Testing

```bash
# 测试宏执行
python tools/wf_sprint_j.py test-macro \
  --name login_sequence \
  --params '{"username":"test","password":"test"}' \
  --dry-run

# 验证技能包
python tools/wf_sprint_j.py validate-package \
  --path skills/test.wfpack \
  --strict
```

### 技能性能分析 / Skill Performance Analysis

```bash
# 分析技能使用情况
python tools/wf_sprint_j.py analyze-performance \
  --skill-name login_sequence \
  --days 7 \
  --detailed

# 导出技能统计
python tools/wf_sprint_j.py export-skills \
  --format json \
  --include-stats \
  --output skills_backup.json
```

---

## Sprint K: 多模态系统 / Multimodal & Adaptive

### 功能概述 / Feature Overview

多模态系统结合视觉、文本和几何特征，提供高级UI理解和自适应执行能力。

### 启动服务 / Start Services

```bash
# 启动视觉分析API
uvicorn vision.services.vision_api:app --reload --host 0.0.0.0 --port 8007 &

# 启动后台服务
python -m vision.services.multimodal_fusion &
python -m adaptive.engines.adaptive_executor &
```

### 多模态页面分析 / Multimodal Page Analysis

#### API调用 / API Calls

```bash
# 基础页面分析
curl -F image=@screenshot.png http://localhost:8007/analyze

# 包含布局分析
curl -F image=@screenshot.png \
  -F include_layout=true \
  -F include_text=true \
  http://localhost:8007/analyze
```

**返回结果示例**:
```json
{
  "page_understanding": {
    "layout_type": "login_form",
    "confidence": 0.94,
    "elements": [
      {
        "type": "input_field",
        "purpose": "username",
        "bbox": [100, 200, 250, 230],
        "confidence": 0.98,
        "text_content": "用户名",
        "interaction_suggestions": ["click", "type"]
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

### 自适应执行 / Adaptive Execution

#### 策略选择 / Strategy Selection

```bash
# API调用策略选择
curl -X POST http://localhost:8007/adaptive/select_strategy \
  -H "Content-Type: application/json" \
  -d '{
    "context": {
      "page_complexity": "medium",
      "user_priority": "balanced",
      "time_constraints": 30000,
      "historical_success_rate": 0.85
    }
  }'
```

#### 工作流中使用 / Using in Workflows

```json
{
  "states": {
    "adaptive_step": {
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

### 可用策略 / Available Strategies

1. **保守策略 (conservative)**: 稳定性优先，等待时间较长
2. **激进策略 (aggressive)**: 效率优先，快速执行
3. **学习策略 (learning)**: 探索优化，收集反馈
4. **融合策略 (fusion)**: 多模态信息融合决策
5. **自动策略 (auto)**: 根据上下文自动选择

### CLI工具 / CLI Tools

```bash
# 页面分析
python tools/wf_sprint_k.py analyze-page \
  --screenshot page.png \
  --save-analysis \
  --output-dir analysis/

# 测试自适应执行
python tools/wf_sprint_k.py adaptive-run \
  --context test_context.json \
  --strategy auto \
  --dry-run

# A/B实验管理
python tools/wf_sprint_k.py ab-test create \
  --name ui_understanding_test \
  --config experiments/ui_test.json

# 性能优化
python tools/wf_sprint_k.py optimize \
  --host ca.indeed.com \
  --goal apply_jobs \
  --dry-run
```

---

## Action Space v2: 语义指令 / Semantic Instructions

### 功能概述 / Feature Overview

Action Space v2 提供了语义级的指令集，使工作流更加易读和可维护，支持DOM优先+坐标回退的执行策略。

### 可用指令 / Available Instructions

#### 导航类指令 / Navigation Instructions

```json
// 导航到指定URL
{"do": "instr.navigate", "url": "https://example.com"}

// 浏览器历史操作
{"do": "instr.history", "op": "back"}     // 后退
{"do": "instr.history", "op": "forward"} // 前进
{"do": "instr.history", "op": "refresh"} // 刷新
```

#### 交互类指令 / Interaction Instructions

```json
// 点击元素
{"do": "instr.click", "target": {"css": "button.login"}}
{"do": "instr.click", "target": {"role": "button", "text": "登录"}}

// 输入文本
{"do": "instr.type_text", "target": {"css": "input[name=username]"}, "text": "用户名", "clear": true}

// 悬停
{"do": "instr.hover", "target": {"css": ".menu-item"}}

// 滚动
{"do": "instr.scroll", "dir": "down", "amount": 500}
```

#### 表单类指令 / Form Instructions

```json
// 选择下拉选项
{"do": "instr.select_option", "target": {"css": "select.country"}, "value": "China"}

// 文件上传
{"do": "instr.upload", "target": {"css": "input[type=file]"}, "file": "document.pdf"}

// 读取表单字段
{"do": "instr.read", "fields": ["username", "email", "status"]}
```

#### 等待类指令 / Wait Instructions

```json
// 等待页面安静
{"do": "instr.key", "key": "WaitQuiet"}

// 等待指定时间
{"do": "instr.wait", "ms": 2000}

// 按键操作
{"do": "instr.key", "key": "Tab"}
{"do": "instr.key", "key": "Enter"}
```

#### 任务控制指令 / Task Control Instructions

```json
// 任务完成
{"do": "instr.task_complete", "message": "登录成功"}

// 回复用户
{"do": "instr.answer_user", "text": "操作已完成"}
```

### 目标选择器 / Target Selectors

支持多种目标选择方式：

```json
// CSS选择器
{"target": {"css": "input[name=username]"}}

// XPath选择器
{"target": {"xpath": "//button[contains(text(), '登录')]"}}

// 角色+文本
{"target": {"role": "button", "text": "登录"}}

// 元素ID
{"target": {"element_id": "login-btn"}}

// 坐标变量
{"target": {"bbox_var": "saved_login_button"}}
```

### 示例工作流 / Example Workflows

**小红书搜索示例**:
```json
{
  "name": "小红书搜索",
  "start": "open_home",
  "states": {
    "open_home": {
      "actions": [
        {"do": "instr.navigate", "url": "https://www.xiaohongshu.com/explore"},
        {"do": "instr.key", "key": "WaitQuiet"},
        {"do": "instr.click", "target": {"css": "input[placeholder*='搜索']"}}
      ],
      "next": "search"
    },
    "search": {
      "actions": [
        {"do": "instr.type_text", "target": {"css": "input[type=search]"}, "text": "海边穿搭", "clear": true},
        {"do": "instr.key", "key": "Enter"},
        {"do": "instr.key", "key": "WaitQuiet"}
      ],
      "next": "browse_results"
    }
  }
}
```

---

## Chrome扩展集成 / Chrome Extension Integration

### 功能概述 / Feature Overview

Chrome扩展(GetContent)提供安全的浏览器自动化能力，支持DOM操作和加密签名验证。

### 安装配置 / Installation & Configuration

#### 1. 启动后端服务 / Start Backend Services

```bash
# 方式1: 一键启动脚本
./scripts/start_orchestrator_backend.sh

# 方式2: 手动启动
cd getcontent/backend
npm install
node src/index.js &      # Backend API (:8787)
node orchestrator.js &   # Orchestrator (:8788)
```

#### 2. 安装Chrome扩展 / Install Chrome Extension

1. 打开Chrome浏览器
2. 访问 `chrome://extensions/`
3. 开启"开发者模式"
4. 点击"加载已解压的扩展程序"
5. 选择 `getcontent/extension/` 目录

#### 3. 创建测试用户 / Create Test User

```bash
cd getcontent/backend
node tools/add-user.js test test test_account
```

### 使用方法 / Usage Methods

#### 1. 扩展登录 / Extension Login

- 点击Chrome工具栏中的扩展图标
- 使用用户名: `test`, 密码: `test` 登录
- 登录成功后可看到设备状态

#### 2. 工作流中使用扩展动作 / Using Extension Actions in Workflows

```json
{
  "actions": [
    // DOM点击 (优先)
    {"do": "ext.click_selector", "sel": "button.login"},

    // 文本输入
    {"do": "ext.type_text", "sel": "input[name=username]", "text": "用户名"},

    // 等待元素
    {"do": "ext.wait_for", "sel": ".loading", "timeout": 5000},

    // 页面导航
    {"do": "ext.open_url", "url": "https://example.com", "active": true}
  ]
}
```

#### 3. 环境变量配置 / Environment Configuration

```bash
# 启用扩展后端
export EXT_ORCH_BASE=http://127.0.0.1:8788

# 运行工作流
python run_workflow.py --workflow flows/example.json --endpoint http://127.0.0.1:8000
```

### DOM优先策略 / DOM-First Strategy

系统会自动选择最佳执行方式：

1. **DOM操作** (通过Chrome扩展) - 优先选择
2. **坐标点击** (通过YOLO+鼠标) - 回退方案

```json
{
  "actions": [
    {
      "do": "instr.click",
      "target": {"css": "button.submit"},
      "fallback": {"vision_click": {"label": "submit_button"}}
    }
  ]
}
```

### 安全机制 / Security Mechanisms

- **数字签名**: 所有自动化计划都经过Ed25519/P-256 ECDSA签名验证
- **设备绑定**: JWT授权绑定到唯一设备ID
- **域名白名单**: 扩展只在批准的域名上操作
- **实时撤销**: 支持即时许可证取消

### 健康检查 / Health Checks

```bash
# 检查后端API
curl -s http://127.0.0.1:8787/health

# 检查协调器
curl -s http://127.0.0.1:8788/health

# 测试登录
curl -X POST http://127.0.0.1:8787/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test"}'
```

---

## AutoFix机制 / AutoFix Mechanism

### 功能概述 / Feature Overview

AutoFix机制提供运行时热补丁和自动晋升功能，自动修复常见的执行问题。

### 配置选项 / Configuration Options

在工作流顶层添加`autofix`配置：

```json
{
  "name": "示例工作流",
  "autofix": {
    "mode": "auto_promote_on_success",
    "limits": {
      "max_patches_per_run": 2
    },
    "allowed_patch_kinds": [
      "wait_quiet_insert",
      "scroll_then_retry",
      "element_wait_timeout"
    ]
  },
  "start": "first_state",
  "states": {...}
}
```

### 可用模式 / Available Modes

1. **suggest_only**: 仅建议修复方案
2. **hot_patch_session**: 运行期热补重试
3. **auto_promote_on_success**: 热补+成功后固化补丁

### 支持的补丁类型 / Supported Patch Types

#### 1. 等待安静插入 (wait_quiet_insert)

**问题**: 页面加载未完成就执行操作
**修复**: 在关键操作前插入等待

```json
// 原始动作
{"do": "instr.click", "target": {"css": "button.submit"}}

// 自动插入
{"do": "instr.key", "key": "WaitQuiet"}
{"do": "instr.click", "target": {"css": "button.submit"}}
```

#### 2. 滚动重试 (scroll_then_retry)

**问题**: 目标元素不在可见区域
**修复**: 滚动后重试操作

```json
// 自动插入
{"do": "instr.scroll", "dir": "down", "amount": 300}
{"do": "instr.click", "target": {"css": "button.hidden"}}
```

#### 3. 元素等待超时 (element_wait_timeout)

**问题**: 等待元素超时
**修复**: 增加等待时间或添加备用策略

### 使用方法 / Usage Methods

#### 1. 启用AutoFix / Enable AutoFix

```bash
# 运行带AutoFix的工作流
python run_workflow.py \
  --workflow flows/autofix_demo.json \
  --endpoint http://127.0.0.1:8000 \
  --enable-autofix
```

#### 2. 查看补丁建议 / View Patch Suggestions

补丁建议会写入日志文件：

```bash
# 查看补丁建议
cat out/logs/patch_proposals.jsonl

# 示例输出
{"timestamp": "2024-01-15T10:30:00", "patch_type": "wait_quiet_insert", "reason": "元素未就绪", "suggestion": {...}}
```

#### 3. 手动应用补丁 / Manually Apply Patches

```bash
# 查看生成的修复版本
ls out/logs/patched_workflow_*.json

# 应用补丁后的工作流
python run_workflow.py --workflow out/logs/patched_workflow_20240115_103000.json
```

### 自动晋升 / Auto Promotion

当工作流成功完成时，系统会：

1. 将热补丁固化到 `.autofix.json` 文件
2. 保存审计副本到 `out/logs/`
3. 下次运行时自动使用修复版本

```bash
# 查看自动晋升的工作流
cat flows/example.autofix.json
```

### 最佳实践 / Best Practices

1. **保守使用**: 建议从 `suggest_only` 模式开始
2. **限制补丁数量**: 设置合理的 `max_patches_per_run`
3. **定期审查**: 检查生成的补丁是否合理
4. **备份原文件**: 保留原始工作流文件

---

## 工作流生成器 / Workflow Generator

### 功能概述 / Feature Overview

工作流生成器(WAM)提供链式构建和LLM自动生成两种方式创建工作流。

### WAM链式构建 / WAM Chain Builder

#### 基础使用 / Basic Usage

```python
from tools.wam import WF

# 创建工作流
wf = WF("登录示例") \
    .start("打开网站") \
    .action("instr.navigate", url="https://example.com") \
    .action("instr.key", key="WaitQuiet") \
    .next("登录") \
    .action("instr.click", target={"css": "input[name=username]"}) \
    .action("instr.type_text", target={"css": "input[name=username]"}, text="{username}") \
    .next("完成") \
    .build()

# 保存工作流
wf.save("flows/login_example.json")
```

#### 高级功能 / Advanced Features

```python
# 循环和条件
wf = WF("批量处理") \
    .start("初始化") \
    .for_range("处理项目", var="i", start=1, end=10) \
        .action("instr.click", target={"css": f".item-{i}"}) \
        .poll("等待加载", condition="页面加载完成", timeout=5000) \
    .end_for() \
    .next("完成") \
    .build()
```

### LLM自动生成 / LLM Auto Generation

#### CLI生成 / CLI Generation

```bash
# 使用LLM生成工作流
python -m tools.wam.gen_cli llm \
  --task "打开百度，搜索'人工智能'，点击第一个结果" \
  --provider gemini \
  --model gemini-1.5-flash \
  --output flows/baidu_search.json

# 使用模板生成
python -m tools.wam.gen_cli template xhs_search \
  --keywords "海边穿搭" \
  --output flows/xhs_search.json
```

#### API生成 / API Generation

```python
import requests

response = requests.post('http://localhost:8002/generate', json={
    "task": "登录LinkedIn并发送消息给特定用户",
    "provider": "gemini",
    "model": "gemini-1.5-flash",
    "constraints": {
        "use_instr_actions": True,
        "enable_autofix": True,
        "max_steps": 20
    }
})

workflow = response.json()
```

### 预置模板 / Preset Templates

#### 1. 小红书搜索模板 / XHS Search Template

```bash
python -m tools.wam.gen_cli template xhs_search \
  --keywords "旅游攻略" \
  --max_results 5 \
  --output flows/xhs_travel.json
```

#### 2. 微信回复模板 / WeChat Reply Template

```bash
python -m tools.wam.gen_cli template wechat_reply \
  --contact "张三" \
  --message "收到，谢谢！" \
  --output flows/wechat_reply.json
```

#### 3. Indeed求职模板 / Indeed Job Template

```bash
python -m tools.wam.gen_cli template indeed_loop \
  --position "软件工程师" \
  --location "北京" \
  --max_applications 10 \
  --output flows/indeed_jobs.json
```

### 工作流验证 / Workflow Validation

#### 语法验证 / Syntax Validation

```python
from tools.wam.validator import WorkflowValidator

validator = WorkflowValidator()
issues = validator.validate("flows/example.json")

for issue in issues:
    print(f"错误: {issue.message} (位置: {issue.location})")
```

#### 干运行验证 / Dry Run Validation

```bash
# 验证工作流逻辑
python -m tools.wam.sim \
  --workflow flows/example.json \
  --dry-run \
  --output-issues issues.json
```

### 最佳实践 / Best Practices

1. **使用语义指令**: 优先使用 `instr.*` 动作
2. **启用AutoFix**: 在生成时添加AutoFix配置
3. **模块化设计**: 将复杂流程拆分为多个状态
4. **添加验证**: 在关键步骤添加验证逻辑
5. **参数化**: 使用变量替换硬编码值

---

## 故障排除 / Troubleshooting

### 常见问题 / Common Issues

#### 1. 服务启动失败 / Service Startup Failures

**问题**: 端口被占用
```bash
# 解决方案
lsof -i :8000  # 检查端口占用
kill -9 <PID>  # 终止占用进程
```

**问题**: 数据库连接失败
```bash
# 解决方案
sudo systemctl start postgresql  # 启动PostgreSQL
psql -h localhost -U automation_user -d automation_db -c "SELECT 1;"  # 测试连接
```

#### 2. 工作流执行失败 / Workflow Execution Failures

**问题**: 元素未找到
```json
// 解决方案：使用多种选择器
{
  "do": "instr.click",
  "target": {"css": "button.submit"},
  "fallback": {"xpath": "//button[contains(text(),'提交')]"}
}
```

**问题**: 页面加载慢
```json
// 解决方案：增加等待时间
{
  "do": "instr.key",
  "key": "WaitQuiet",
  "timeout": 10000
}
```

#### 3. Chrome扩展问题 / Chrome Extension Issues

**问题**: 扩展未加载
1. 检查是否开启开发者模式
2. 重新加载扩展
3. 检查控制台错误信息

**问题**: 登录失败
```bash
# 检查后端服务
curl -s http://127.0.0.1:8787/health

# 重新创建用户
cd getcontent/backend
node tools/add-user.js test test test_account
```

### 日志分析 / Log Analysis

#### 查看执行日志 / View Execution Logs

```bash
# 工作流执行日志
cat out/logs/workflow_execution.log

# 错误日志
grep "ERROR" out/logs/*.log

# YOLO检测日志
cat out/logs/yolo.json | jq '.detections'
```

#### 调试模式 / Debug Mode

```bash
# 启用详细日志
python run_workflow.py \
  --workflow flows/example.json \
  --debug \
  --save-screenshots \
  --step-mode
```

### 性能优化 / Performance Optimization

#### 1. YOLO检测优化 / YOLO Detection Optimization

```bash
# 调整检测参数
export YOLO_CONF=0.3      # 降低置信度阈值
export YOLO_IOU=0.5       # 调整IoU阈值
export YOLO_IMGSZ=416     # 使用更小的图像尺寸
```

#### 2. LLM调用优化 / LLM Call Optimization

```bash
# 使用更快的模型
export LLM_MODEL=gemini-1.5-flash
export LLM_PROVIDER=gemini

# 启用缓存
export ENABLE_LLM_CACHE=true
```

#### 3. 内存优化 / Memory Optimization

```bash
# 限制PyTorch内存使用
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512

# 清理临时文件
find out/ -name "*.png" -mtime +7 -delete
```

### 监控与告警 / Monitoring & Alerts

#### 健康检查脚本 / Health Check Script

```bash
# 一键健康检查
bash tools/health_check.sh

# 输出示例
✅ YOLO API (端口 8000): 正常
✅ OCR API (端口 8001): 正常
❌ Workflow API (端口 8002): 异常
```

#### 性能监控 / Performance Monitoring

```bash
# 查看系统资源
htop
df -h          # 磁盘使用
free -h        # 内存使用
nvidia-smi     # GPU使用(如果有)
```

### 获取帮助 / Getting Help

1. **查看文档**: 参考 `CLAUDE.md` 和 `SYSTEM_DOCUMENTATION.md`
2. **检查日志**: 查看 `out/logs/` 目录下的日志文件
3. **运行测试**: 使用 `tools/integration_test_suite.py` 进行全面测试
4. **社区支持**: 在项目仓库提交Issue

---

**文档版本**: v1.0.0
**最后更新**: 2024年12月
**维护团队**: AI自动化系统开发团队

如有问题，请参考故障排除章节或联系开发团队。