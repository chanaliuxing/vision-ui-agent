# Vision-UI-Agent: Vision-First Computer Use Automation Engine

[English](README.md) | [简体中文](README_CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-brightgreen.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![YOLO](https://img.shields.io/badge/YOLO-v8%2Fv11-00FFFF.svg)](https://github.com/ultralytics/ultralytics)

> **High-performance, vision-first GUI automation and Computer Use agent powered by local YOLO element detection and pluggable multimodal LLMs (Gemini, DeepSeek, OpenAI, NVIDIA NIM).**

---

> [!IMPORTANT]
> **Release & Commercial Notice**
>
> - **Open Source Baseline**: The code in this public repository represents a functional baseline release from approximately **12 months ago**, shared for academic research, technical study, and architectural reference.
> - **Commercial & Production Edition**: Advanced industrial-grade features, enhanced reliability, and ongoing evolutions are part of our **proprietary commercial suite**. For commercial inquiries or enterprise deployments, please contact the team.

---

## 🌟 Why Vision-UI-Agent?

Traditional "Computer Use" agents (like pure VLM screenshot-to-coordinate systems) suffer from:
1. **High Latency & Token Burn**: Uploading 2K/4K screenshots to cloud VLMs on every step costs 3–8 seconds per action and drains API quotas.
2. **Coordinate Drift**: VLMs frequently miss small icons, buttons, or scrollbars by 10–30 pixels.
3. **Fragile State Recovery**: Minor layout shifts or animations cause action chains to fail completely.

`Vision-UI-Agent` solves this with a **Hybrid Dual-Engine Architecture**:
- ⚡ **Local YOLO Micro-Perception**: Runs locally in ~50ms to detect all clickable bounding boxes, icons, inputs, and text blocks with pixel precision.
- 🧠 **Pluggable Multimodal Brain**: Feeds detected element candidates and visual context to the LLM of your choice (**Gemini 1.5/2.0, DeepSeek V3/R1, GPT-4o, NVIDIA NIM**).
- 🎯 **Robust Visual Anchors & Landmarks**: Uses multi-scale feature matching (**SIFT, ORB, Template Matching**) to lock onto relative target positions even across resolution changes.
- 🛡️ **Built-in Safety & Danger Guard**: Automatic keyword interception (e.g., "Delete", "Pay", "Submit") requiring human confirmation before execution.
- 🔄 **Autostep Planner with Self-Healing**: Dynamic goal planning, verification rules (`appear:loading`, `disappear:toast`), and automatic retry strategies.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Screen Capture / API Input               │
└──────────────────────────────┬──────────────────────────────┘
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
┌───────────────────────┐             ┌───────────────────────┐
│   Local YOLO Engine   │             │   Multimodal LLM      │
│  (Ultralytics v8/v11) │             │ (Gemini/DeepSeek/GPT) │
│  - Bounding Boxes     │             │ - Semantic Intent     │
│  - Icon Detection     │             │ - Strategy Planning   │
│  - Latency: ~50ms     │             │ - Action Selection    │
└───────────┬───────────┘             └───────────┬───────────┘
            │                                     │
            └──────────────────┬──────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 Fusion & Action Engine                      │
│  - Relative Anchors & Landmarks (SIFT / ORB / Color)        │
│  - Coordinate Scaling & Compression (HiDPI / Retina)        │
│  - Safety & Danger Guard Check                              │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│           OS Execution (PyAutoGUI / Chrome CDP)             │
│            Click • Type • Drag • Scroll • Verify            │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/chanaliuxing/vision-ui-agent.git
cd vision-ui-agent

# Create virtual environment
python3 -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Download Model Weights

Download the pre-trained UI element detection model (OmniParser v2 icon_detect):

```bash
bash scripts/download_weights.sh
```

### 3. Configure Environment

Copy the example configuration:

```bash
cp .env.example .env
```

Edit `.env` to configure your preferred LLM provider:

```ini
# Choose provider: gemini | openai | deepseek | nvidia
LLM_PROVIDER=gemini
LLM_MODEL=gemini-1.5-flash
GEMINI_API_KEY=your_actual_gemini_api_key

# Local YOLO weights path
YOLO_WEIGHTS=weights/model.pt
```

### 4. Start Server

```bash
# Start FastAPI service on port 8000
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Verify service status:
```bash
curl -s http://localhost:8000/health
# {"status":"ok"}
```

---

## 📡 API Overview

| Endpoint | Method | Description |
|---|---|---|
| `/health` | `GET` | Service health status and loaded model information |
| `/predict` | `POST` | YOLO visual element detection (returns bounding boxes and confidences) |
| `/v1/pick` | `POST` | Semantic element picking (targets element from natural language prompt) |
| `/v1/verify` | `POST` | Verifies page state change after an action |
| `/v1/autostep` | `POST` | End-to-end automated action execution with retry and fallback |

### Example: Semantic Element Pick

```bash
curl -X POST "http://localhost:8000/v1/pick" \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Click search button",
    "image": {
      "base64": "<base64_encoded_screenshot>",
      "format": "png"
    }
  }'
```

Response:
```json
{
  "status": "success",
  "chosen_id": 4,
  "point": {"x": 820, "y": 142},
  "confidence": 0.94,
  "reasoning": "Detected magnifying glass icon adjacent to the search input field."
}
```

---

## 🐳 Docker Deployment

The repository includes complete multi-container orchestration (FastAPI, PostgreSQL, and optional queue support):

```bash
docker compose up -d
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
