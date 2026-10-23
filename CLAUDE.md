# CLAUDE.md

Vision-first UI automation engine combining YOLO object detection with LLM decision making.

## Quick Start

### Environment Setup
- Virtual environment: `python -m venv myenv && source myenv/bin/activate` OR use `yolovenv`
- Dependencies: `pip install -r requirements.txt`
- Configuration: Copy `.env.example` to `.env` and set API keys
- **YOLO Hybrid**: Set `YOLO_MODE`, `YOLO_REMOTE_URL` in `.env`

### Launch System
```bash
# One-click launch all services
./scripts/start_all_services.sh

# Check status
./scripts/check_services.sh

# Stop all services
./scripts/stop_all_services.sh
```

### Manual Launch
```bash
# 1. Infrastructure
docker compose --profile gateway --profile localstack up -d
python scripts/bootstrap_infrastructure.py

# 2. APIs (separate terminals)
uvicorn app:app --reload --host 0.0.0.0 --port 8000       # YOLO
uvicorn app_ocr:app --reload --host 0.0.0.0 --port 8001   # OCR
uvicorn app_workflow:app --reload --host 0.0.0.0 --port 8002  # Workflow
uvicorn server.services.recall_api:app --reload --host 0.0.0.0 --port 8003  # Memory

# 3. Chrome Extension
cd getcontent/backend && npm run dev  # Port 8787
cd getcontent/backend && node tools/add-user.js test test test_account

# 4. Load extension: Chrome → Extensions → Load unpacked → getcontent/extension/
```

### Verify System
```bash
# Health checks
curl -s http://127.0.0.1:8000/health  # All should return 200 OK
curl -s http://127.0.0.1:8001/health
curl -s http://127.0.0.1:8002/health
curl -s http://127.0.0.1:8003/health
curl -s http://127.0.0.1:8787/health

# Test workflow
python run_workflow.py --workflow flows/xhs_search_reply.json --endpoint http://127.0.0.1:8000
```

## Service Ports
- **8000**: YOLO API (hybrid cloud/local support)
- **8001**: OCR API
- **8002**: Workflow Generation API
- **8003**: Memory/RAG API
- **8787**: Chrome Extension Backend
- **8080**: Traefik Dashboard
- **4566**: LocalStack (AWS simulation)

## YOLO Hybrid Configuration

### Modes
- **Local** (default): Local YOLO model
- **Remote**: Cloud server inference
- **Hybrid**: Cloud first, local fallback

### Configuration (.env)
```bash
YOLO_MODE=local|remote|hybrid
YOLO_REMOTE_URL=http://server:8080/infer
YOLO_TIMEOUT=30
```

### API Endpoints
```bash
GET /yolo/mode          # Check current mode
POST /yolo/mode         # Switch mode
POST /detect            # Enhanced detection
POST /calibrate         # Element baselines
POST /reacquire         # Re-find elements
POST /verify            # Check UI changes
```

## Core Services

### Vision & Workflow
- **YOLO**: `uvicorn app:app --reload --host 0.0.0.0 --port 8000`
- **OCR**: `uvicorn app_ocr:app --reload --host 0.0.0.0 --port 8001`
- **Workflow**: `uvicorn app_workflow:app --reload --host 0.0.0.0 --port 8002`
- **Memory**: `uvicorn server.services.recall_api:app --reload --host 0.0.0.0 --port 8003`

### Advanced Services (Sprints)
- **DPO Training**: `uvicorn server.services.dpo_service:app --port 8004`
- **Model Manager**: `uvicorn server.services.model_manager:app --port 8005`
- **A/B Testing**: `uvicorn server.services.ab_testing:app --port 8006`
- **Vision Analysis**: `uvicorn vision.services.vision_api:app --port 8007`

## Testing

### Basic Health Checks
```bash
curl -s http://localhost:8000/health    # YOLO API
curl -s http://localhost:8001/health    # OCR API
curl -s http://localhost:8002/health    # Workflow API
curl -s http://localhost:8003/health    # Memory API
curl -s http://localhost:8787/health    # Chrome Extension
```

### YOLO Testing
```bash
# Mode switching
curl -X POST http://localhost:8000/yolo/mode -d "mode=hybrid"

# Detection test
curl -X POST http://localhost:8000/detect -F "image=@sample.png" -F "classes=[\"button\"]"

# Fallback test
python tests/test_detect_minimum.py
```

### Sprint Testing Tools
```bash
# Memory & RAG
python tools/wf_sprint_h.py test-embeddings --text "sample"

# DPO Training
python tools/wf_sprint_i.py generate-pairs --host example.com

# Skills & Macros
python tools/wf_sprint_j.py registry-status

# Vision & Adaptive
python tools/wf_sprint_k.py analyze-page --screenshot sample.png
```

## Chrome Extension Setup
1. Start backend: `cd getcontent/backend && npm run dev`
2. Create user: `node tools/add-user.js test test test_account`
3. Load extension: Chrome → Extensions → Load unpacked → `getcontent/extension/`
4. Login with `username: test`, `password: test`

## Workflow Execution

### Basic Commands
```bash
# Run workflow (must use myenv environment)
source myenv/bin/activate
python run_workflow.py --workflow flows/example.json --endpoint http://127.0.0.1:8000

# Generate workflow
python tools/run_workflow_gen.py --task "description" --provider gemini --out flows/new_flow.json

# Direct LLM test
python run_gemini.py --provider gemini --image out/screens/overlay.png --yolo out/logs/yolo.json
```

### Advanced Features
```bash
# Memory-enhanced
python run_workflow.py --workflow flows/example.json --enable-memory --recall-threshold 0.7

# Macro-enabled
python run_workflow.py --workflow flows/with_macros.json --macro-path skills/

# Adaptive
python run_workflow.py --workflow flows/adaptive.json --adaptive-mode --strategy-selection auto
```

## WAM (Workflow Authoring Module)

### CLI Tools
```bash
# Create workflow
python tools/wam_cli.py create my_workflow --description "工作流描述"
python tools/wam_cli.py create test --template indeed_apply_loop

# Validate & fix
python tools/wam_cli.py validate flows/my_workflow.json
python tools/wam_cli.py fix flows/broken.json --auto-apply

# List templates
python tools/wam_cli.py templates
```

### Available Templates
- `indeed_apply_loop`: Job application automation
- `wechat_poll_reply`: WeChat polling and reply
- `web_login_sequence`: Generic web login flow
- `data_extraction_pipeline`: Data extraction workflow

## Workflow Structure

### Basic Format
```json
{
  "version": "1.3",
  "name": "workflow_name",
  "start": "initial_state",
  "vars": {"variable_name": "default_value"},
  "states": {
    "state_name": {
      "actions": [...],
      "transitions": [...],
      "on_success": "next_state",
      "on_error": "error_state"
    }
  }
}
```

### Schema Validation
- Schema: `schema/workflow.schema.json`
- Validate: `python tools/wam/workflow_validator.py flows/example.json`

## Action Types (50+ Total)

### Core Actions
- `autostep`: Vision-first LLM decision making
- `click`, `type_text`, `scroll`: Basic interactions
- `detect`, `locate`: YOLO-based UI detection
- `screenshot`, `sleep_ms`: Capture and timing
- `open_url`, `go_back`: Browser navigation

### Extension Actions (Chrome)
- `ext.click_selector`: DOM-based clicking
- `ext.type_text`: DOM text input
- `ext.key`, `ext.scroll`, `ext.extract`: Keyboard, scroll, data extraction

### Instruction Actions (v2 - DOM-first + Vision fallback)
```json
{"do": "instr.click", "target": {"css": "#button", "text": "Submit"}}
```

**Available Instructions (14 types)**:
- `instr.click`, `instr.type_text`, `instr.select_option`: Core interactions
- `instr.scroll`, `instr.navigate`, `instr.history`: Navigation
- `instr.hover`, `instr.key`, `instr.upload`: Advanced input
- `instr.read`, `instr.wait`: Data extraction, timing
- `instr.task_complete`, `instr.answer_user`, `instr.annotate`: User interaction

**Target Resolution**:
- `css`: CSS selector (DOM-first)
- `xpath`: XPath alternative
- `role`: ARIA role
- `text`: Visible text
- `bbox_var`: Coordinate fallback

### Task System (Component Library)
```json
{"do": "task.run", "name": "login_sequence", "args": {"username": "@user"}}
```

**Task Actions (5 types)**:
- `task.run`: Execute reusable components
- `task.validate`, `task.list`: Validation and discovery
- `task.sync`, `task.install`: Registry management

### Advanced Actions
- `mem.recall`: RAG-based memory retrieval
- `plan.reflect`: Self-improvement reflexion
- `macro.execute`: Reusable skill macros
- `adaptive.run`: Context-aware execution
- `set_variable`, `increment_variable`: Variable operations
- `llm_decide`, `llm.submit`: LLM integration
- `authenticate`, `secure_operation`: Security operations

### State Management
```json
// Transitions
"transitions": [{"if": "@counter < 10", "go_to": "loop_state"}]

// Error handling
"on_success": "next_state",
"on_error": "error_recovery_state"
```

### Auto-Fix System
- Analyzes workflow failures and generates patches
- Supported errors: timeout, targeting, interaction, timing
- Auto-promotion based on success thresholds

```bash
# Fix workflow
python tools/wam_cli.py fix flows/broken.json --auto-apply --backup
```

## Configuration

### Environment Variables
- `LLM_PROVIDER=gemini` `LLM_MODEL=gemini-1.5-flash`
- `YOLO_CONF=0.5` `YOLO_IOU=0.45` `YOLO_IMGSZ=1280`
- `EXEC_TYPE_MODE=auto` (auto/paste/type)

### Integration Testing
```bash
# Full test suite
python tools/integration_test_suite.py

# Telegram test (requires API keys)
python tools/telegram_real_test.py
```

## Architecture Overview

**Vision-first UI automation engine** combining YOLO object detection with LLM decision making.

### Key Principles
1. **Vision-First**: YOLO detects UI → LLM makes decisions
2. **Multi-Provider LLM**: Gemini, OpenAI, DeepSeek, NVIDIA
3. **Workflow-Driven**: JSON-based definitions with autostep
4. **Self-Healing**: Anchor replay + AutoFixer patches
5. **Memory-Enhanced**: RAG trajectory retrieval
6. **Schema-Validated**: 50+ action types with validation

### Core Modules (`core/`)
- `workflow.py`: Main engine with `WorkflowRunner` and `_autostep()`
- `executor/`: Mouse/keyboard automation via PyAutoGUI
- `observability/`: Event tracking with `RunEventRecorder`
- `llm_client.py`: Multi-provider LLM client
- `candidates.py`: YOLO → geometry candidates for LLM
- `anchors.py`: Template matching for replay reliability

### Advanced Modules
- **Memory (H)**: `embeddings.py`, `recall_api.py`, `mem_recall.py`
- **Training (I)**: `dpo_service.py`, `model_manager.py`, `ab_testing.py`
- **Skills (J)**: `registry.py`, `macro_execute.py`, `packager.py`
- **Vision (K)**: `layout_analyzer.py`, `adaptive_executor.py`
- **WAM**: `workflow_builder.py`, `autofixer.py`, `wam_cli.py`

### Data Flow
Screenshot → YOLO Detection → Candidate Generation → LLM Decision → Action Execution → State Transition

### Output Structure
- `out/screens/`: Screenshots and overlays
- `out/logs/`: YOLO detections, LLM requests/responses
- `out/reports/`: HTML reports with timeline
- `flows/`: JSON workflow definitions

## Troubleshooting

### Common Issues
```bash
# Import errors - ensure only core/executor.py exists (no directory)
# API errors - workflow JSON must include "task" field
# Port conflicts - kill processes: lsof -ti:PORT | xargs kill
# Docker issues - ensure Docker Desktop running: docker compose logs
# Extension issues - verify backend on 8787, reload extension
# YOLO issues - check weights/ directory permissions
```

## Implementation Notes

### Current Status
- Event recording system with `RunEventRecorder`
- Dynamic module loading for `core.executor`
- Hybrid YOLO execution (local/remote/cloud)

### LLM Configuration
- Global: `.env` with `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-1.5-flash`
- Per-workflow: Add `llm_provider`/`llm_model` to autostep actions
- CLI: `--provider` and `--model` flags

### LLM Client Architecture
**Call Chain**: `app.py` → `dependencies.py` → `HybridLLMClient` → `core/llm_client.py`

**Key Components**:
- **HybridLLMClient**: MQ-first routing with direct fallback, handles vision data
- **LLMClient**: Base implementation with image compression support
- **Orchestrator**: Coordinates YOLO+LLM decisions, passes vision data

**Image Compression**:
- Target: 70% token reduction for GPT-4o vision (26k+ → 6-8k tokens)
- Implementation: `_encode_image_file_for_llm()` in `app.py` + `core/llm_client.py`
- Results: 88% file size reduction (135KB → 16KB WebP compressed images)
- Coordinate mapping: `map_bbox_back()` preserves pixel-perfect UI automation accuracy

**Vision Processing**:
1. Original images stored in `out/originals/` and `out/overlays/`
2. Vision data flows through `orchestrator.py` → `hybrid_llm_client.py`
3. Compression applied in `core/llm_client.py` via WebP optimization
4. `vision_meta.size` logs original size (misleading), actual LLM receives compressed images

### Text Input & Anchoring
- Auto mode: Intelligent paste vs. type selection
- Unicode support: Platform-specific key events
- Anchoring: Template matching + ORB/SIFT features

## File Organization
- `app*.py`: FastAPI services (ports 8000-8002)
- `core/`: Engine components (workflow, executor, observability)
- `flows/`: JSON workflow definitions
- `tools/`: CLI utilities and generators
- `out/`: Runtime artifacts (screens, logs, reports)
- `weights/`: YOLO model files (gitignored)
- `server/services/`: Advanced APIs (ports 8003-8007)
- `runtime/`: Actions, macros, task system
- `getcontent/`: Chrome extension integration

## Chrome Extension (GetContent)

### Architecture
- **Extension**: Cryptographically-signed execution system
- **Backend**: Authentication, command queues, plan resolution
- **Strategy**: DOM-first → Vision fallback
- **Security**: Ed25519/P-256 ECDSA signatures, device binding

### Integration Benefits
- DOM-first for standard web interactions
- Vision fallback for complex/dynamic UI
- Unified workflow orchestration
- Secure execution with crypto signatures