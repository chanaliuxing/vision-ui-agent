# Vision-UI-Agent: 视觉驱动的 Computer Use 桌面自动化引擎

[English](README.md) | [简体中文](README_CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-brightgreen.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![YOLO](https://img.shields.io/badge/YOLO-v8%2Fv11-00FFFF.svg)](https://github.com/ultralytics/ultralytics)

> **结合“本地轻量级 YOLO 视觉感知”与“云端多模态大模型决策”的工业级 GUI 智能体与自动化底座，支持 Gemini、DeepSeek、OpenAI、NVIDIA NIM 等主流多模态大模型。**

---

> [!IMPORTANT]
> **版本与商业化说明**
>
> - **开源基线版本**：本仓库公开的代码为约 **12 个月前的基线版本（Baseline Release from ~12 months ago）**，主要供开源社区进行技术研究、架构参考与交流学习。
> - **商业/企业专有版**：具备更高稳定性、工业级高可用与持续演化的**最新版本已作为商业化/企业版交付**。如需了解最新企业版架构或洽谈商业合作，请联系项目维护团队。

---

## 🌟 核心突破与设计哲学

传统基于纯 VLM（视觉多模态大模型）直接输出坐标的 Computer Use 智能体存在三个典型痛点：
1. **高延迟与高昂 Token 消耗**：每一步都将 2K/4K 大图上传至云端模型，单步耗时长达 3–8 秒。
2. **坐标漂移**：大模型对小图标、微小按钮或滚动条经常出现 10–30 像素的偏差。
3. **脆弱的恢复能力**：微小布局变动或动画加载容易导致整条动作链执行中断。

`Vision-UI-Agent` 采用**端云协同的混合双引擎架构**：
- ⚡ **本地 YOLO 微感知**：本地 50ms 内快速完成全屏幕可交互元素、图标与输入框的亚像素级检测。
- 🧠 **可插拔多模态决策大脑**：将精准检测到的元素候选与上下文输送给主流多模态模型（**Gemini 1.5/2.0、DeepSeek V3/R1、GPT-4o、NVIDIA NIM**）进行语义规划。
- 🎯 **多尺度相对锚点 (Visual Anchors)**：支持 SIFT/ORB 特征匹配与模板自适应，在跨分辨率与响应式布局下自动稳定相对位移。
- 🛡️ **内置安全审查哨兵 (Danger Guard)**：自动对高危动作（“删除”、“转账”、“提交支付”）进行拦截并要求人工授权。
- 🔄 **自愈式步进规划器 (Autostep Planner)**：基于期望状态转移规则（如等待加载中消失、确认弹窗出现）进行闭环容错与重试。

---

## 🏗️ 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    屏幕截图 / API 输入                       │
└──────────────────────────────┬──────────────────────────────┘
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
┌───────────────────────┐             ┌───────────────────────┐
│   本地 YOLO 感知引擎  │             │   云端多模态 LLM      │
│  (Ultralytics v8/v11) │             │ (Gemini/DeepSeek/GPT) │
│  - 边界框与候选坐标   │             │ - 语义意图理解        │
│  - 图标与控件分类     │             │ - 任务规划拆解        │
│  - 延迟: ~50ms        │             │ - 目标动作挑选        │
└───────────┬───────────┘             └───────────┬───────────┘
            │                                     │
            └──────────────────┬──────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 特征融合与决策执行引擎                      │
│  - 视觉锚点与多尺度特征对其 (SIFT / ORB / Color)            │
│  - 坐标缩放与视网膜屏幕适配 (HiDPI / Retina)                │
│  - 高危操作拦截过滤 (Safety Guard)                          │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│           操作系统输入驱动 (PyAutoGUI / Chrome CDP)         │
│            点击 • 键盘输入 • 拖拽 • 滚动 • 状态验证         │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 快速上手

### 1. 安装

```bash
# 克隆仓库
git clone https://github.com/chanaliuxing/vision-ui-agent.git
cd vision-ui-agent

# 创建并激活虚拟环境
python3 -m venv .venv && source .venv/bin/activate

# 安装 Python 依赖
pip install -r requirements.txt
```

### 2. 下载视觉检测权重

一键下载预训练界面元素感知权重（OmniParser v2 icon_detect）：

```bash
bash scripts/download_weights.sh
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 配置您的模型供应商：

```ini
# 可选: gemini | openai | deepseek | nvidia
LLM_PROVIDER=gemini
LLM_MODEL=gemini-1.5-flash
GEMINI_API_KEY=your_actual_gemini_api_key

# 本地 YOLO 权重路径
YOLO_WEIGHTS=weights/model.pt
```

### 4. 启动服务

```bash
# 启动 FastAPI 服务 (8000 端口)
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

验证服务健康状态：
```bash
curl -s http://localhost:8000/health
# {"status":"ok"}
```

---

## 📡 核心 API 概览

| 接口端点 (Endpoint) | 请求方式 | 功能描述 |
|---|---|---|
| `/health` | `GET` | 服务健康检查与当前模型加载状态 |
| `/predict` | `POST` | YOLO 纯视觉元素检测（返回边界框与置信度） |
| `/v1/pick` | `POST` | 语义选点：结合自然语言目标（如“点击搜索按钮”）定位最佳坐标 |
| `/v1/verify` | `POST` | 动作执行后验证页面状态变化 |
| `/v1/autostep` | `POST` | 端到端全自动步进执行器（支持重试与容错） |

---

## 📄 License

本项目采用 [MIT 许可证](LICENSE)。
