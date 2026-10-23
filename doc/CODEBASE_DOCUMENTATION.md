# M3 Vision-First UI Automation Engine - Codebase Documentation

## Directory Structure

```
├── README.md                           # Project overview and setup instructions
├── CLAUDE.md                          # Development commands and architecture guide
├── ROADMAP.md                         # Future development plans
├── STRATEGY_IMPLEMENTATION_STATUS.md   # M2 strategy implementation status
├── SUMMARY.md                         # Project summary
├── TODO.md                            # Current tasks and improvements
├── notDone.md                         # Incomplete features
├── startYolo.md                       # YOLO setup instructions
├── yolo_nice_version_endpoint.md      # YOLO API documentation
├── yolo_ocr_endpoint.md               # OCR API documentation
├── AGENTS.md                          # Agent configuration documentation
├── CODEMAP.md                         # Code mapping documentation
│
├── config/                            # Configuration files
│   └── classes.json                   # YOLO object class definitions
│
├── core/                              # Core engine modules
│   ├── workflow.py                    # Main workflow engine
│   ├── llm_client.py                  # Unified LLM client (multi-provider)
│   ├── llm_router.py                  # M3 cost-controlled LLM routing
│   ├── prompt_builder.py              # Prompt templates and builders
│   ├── candidates.py                  # YOLO detection to candidate conversion
│   ├── executor.py                    # Mouse/keyboard automation
│   ├── capture.py                     # Screen capture with DPR detection
│   ├── reporter.py                    # Logging and HTML report generation
│   ├── anchors.py                     # Template matching and anchor system
│   ├── strategy_selector.py           # Strategy-based LLM decision making
│   ├── strategy_adapter.py            # M2 strategy integration adapter
│   ├── strategy_exec.py               # Strategy execution engine
│   ├── strategy_store.py              # Strategy caching and persistence
│   ├── strategy_schema.py             # Strategy definition schemas
│   ├── memory.py                      # Memory system for UI interactions
│   ├── memory_strategy.py             # Strategy-specific memory handling
│   ├── yolo_client.py                 # YOLO detection API client
│   ├── ocr_client.py                  # OCR API client
│   ├── gemini_client.py               # Gemini-specific client utilities
│   ├── mapping.py                     # Coordinate mapping utilities
│   ├── locator.py                     # Element location utilities
│   ├── detectors.py                   # Modal/loading/toast detection
│   ├── landmarks.py                   # UI landmark detection
│   ├── ops.py                         # Utility operations
│   ├── ops_new.py                     # New utility operations
│   ├── sm.py                          # State machine utilities
│   ├── costs.py                       # M3 cost tracking and budgeting
│   ├── report_events.py               # Event emission for reporting
│   ├── timeline.py                    # Timeline event tracking
│   └── types.py                       # Type definitions
│
├── flows/                             # Workflow definitions
│   ├── auto_workflow.json             # Auto-generated workflow
│   ├── xhs_search_reply.json          # XHS search and reply workflow
│   ├── xhs_search_reply_fixed.json    # Fixed version of XHS workflow
│   └── xhs_longform_vision.json       # Long-form content workflow
│
├── tools/                             # CLI utilities and generators
│   ├── run_workflow_gen.py            # Workflow generation from descriptions
│   ├── report_gen.py                  # Report generation utilities
│   ├── replay_run.py                  # Workflow replay utilities
│   ├── smoke_suite.py                 # Test suite
│   └── build_timeline.py              # Timeline building utilities
│
├── out/                               # Runtime outputs
│   ├── logs/                          # Execution logs and LLM responses
│   ├── screens/                       # Screenshots and overlays
│   └── reports/                       # Generated HTML reports
│
├── app.py                             # Primary YOLO detection API
├── app_ocr.py                         # YOLO + OCR fusion API
├── app_workflow.py                    # Workflow generation API
├── app_nice_version.py                # Enhanced YOLO API
├── run_workflow.py                    # Main workflow runner
├── run_gemini.py                      # Direct LLM testing utility
├── run_post.py                        # Post-processing utilities
├── autogui.py                         # PyAutoGUI utilities
├── yolo.py                            # Basic YOLO implementation
├── yolo_ui.py                         # YOLO UI implementation
├── yolo_omni_style.py                 # Omnidirectional YOLO styling
├── solar.py                           # Solar-specific utilities
├── test.py                            # Test scripts
└── drawing.js                         # JavaScript drawing utilities
```

## Core Architecture Components

### 1. Main APIs (`app*.py`)

#### `app.py` - Primary YOLO Detection API
**FastAPI server providing YOLO object detection with in-box ID labeling**

**Key Functions:**
- `predict()` - Main prediction endpoint with image upload
- `health()` - Health check endpoint
- `startup_event()` - Initialize YOLO model on startup

**Features:**
- Image upload and processing
- YOLO detection with confidence filtering
- Bounding box visualization with IDs
- Base64 image return option

#### `app_ocr.py` - YOLO + OCR Fusion API  
**Combines YOLO detection with OCR text recognition**

**Key Functions:**
- `predict()` - YOLO + OCR fusion prediction
- `health()` - OCR service health check

**Features:**
- PaddleOCR/EasyOCR integration
- Text detection within YOLO bounding boxes
- Multi-language OCR support

#### `app_workflow.py` - Workflow Generation API
**Generates workflows from natural language descriptions**

**Key Functions:**
- `generate_workflow()` - Create workflow from task description
- `health()` - Workflow service health check

**Features:**
- LLM-powered workflow generation
- JSON workflow definition output
- Multi-provider LLM support

### 2. Core Engine (`core/`)

#### `core/workflow.py` - Main Workflow Engine
**Central orchestrator for vision-first automation workflows**

**Key Classes:**
- `WorkflowRunner` - Main workflow execution engine
- `WFConfig` - Workflow configuration parameters

**Key Functions:**
- `run(start_state)` - Execute workflow from starting state
- `_autostep(cfg)` - Vision-first LLM decision making with verification
- `_grab()` - Screen capture
- `_detect()` - YOLO object detection
- `_signature(bgr, dets)` - Generate page signature for state tracking
- `_resolve_or_create_state(sig)` - State management based on signatures
- `act_*()` - Action implementations (click, type, scroll, etc.)

**Features:**
- JSON-driven workflow definitions
- Vision-first UI element picking
- Multi-modal anchoring system
- State transition verification
- Cost-controlled LLM integration
- Replay system for reliability

#### `core/llm_client.py` - Unified LLM Client
**Multi-provider LLM client with consistent interface**

**Key Functions:**
- `call_llm(provider, model, messages, image_path)` - Universal LLM calling
- `extract_text_generic(response)` - Extract text from any provider response
- `_call_gemini()` - Gemini-specific implementation
- `_call_openai()` - OpenAI-specific implementation  
- `_call_deepseek()` - DeepSeek-specific implementation
- `_call_nvidia()` - NVIDIA NIM-specific implementation

**Features:**
- Provider abstraction (Gemini, OpenAI, DeepSeek, NVIDIA)
- Image attachment support
- Consistent error handling
- Response format normalization

#### `core/llm_router.py` - M3 Cost-Controlled LLM Routing
**Budget management and cost optimization for LLM calls**

**Key Classes:**
- `LLMRouter` - Main routing and cost control
- `CostGuard` - Budget enforcement
- `Budget` - Budget configuration

**Key Functions:**
- `maybe_call(kind, messages, ...)` - Cost-controlled LLM invocation
- `check_budget(estimated_cost)` - Budget validation
- `record_usage(actual_cost)` - Usage tracking

**Features:**
- Token estimation and cost calculation
- Budget enforcement with fallbacks
- Usage analytics and reporting
- Provider-specific cost models

#### `core/prompt_builder.py` - Prompt Templates and Builders
**Generates structured prompts for different automation tasks**

**Key Functions:**
- `build_messages(system_template, payload)` - Build complete message structure
- `build_user_payload(yolo_json, viewport, spec)` - Create user prompt payload
- `build_picker_messages(goal, ...)` - Vision picker prompts
- `build_cross_confirm_messages(...)` - Cross-page confirmation prompts
- `build_planner_messages(...)` - Task planning prompts
- `build_pop_messages(...)` - Prompt-of-Prompt enhancement

**Templates:**
- `SYSTEM_TEMPLATE_UI_OUTLINE` - Main vision picker system prompt
- `SYSTEM_TEMPLATE_PLANNER` - Task planning system prompt
- `SYSTEM_TEMPLATE_CROSS_CONFIRM` - Verification system prompt

#### `core/candidates.py` - YOLO Detection Processing
**Converts YOLO detections to geometry-only candidates for LLM**

**Key Functions:**
- `yolo_to_geom_candidates(detections, viewport)` - Convert detections to candidates
- `_normalize_bbox(bbox, W, H)` - Normalize bounding box coordinates
- `_calculate_geometry(bbox)` - Calculate geometric properties

**Features:**
- Geometry extraction from YOLO results
- Coordinate normalization
- Spatial relationship calculation

#### `core/executor.py` - Mouse/Keyboard Automation
**Cross-platform automation using PyAutoGUI with enhanced capabilities**

**Key Classes:**
- `Executor` - Main automation executor

**Key Functions:**
- `click(x, y, dpr)` - DPR-aware clicking
- `type_text(text, mode)` - Intelligent text input with mode selection
- `scroll(clicks)` - Scrolling with customizable amount
- `move_to(x, y, duration)` - Mouse movement with timing
- `go_back()` - Browser back navigation

**Features:**
- Device Pixel Ratio (DPR) support
- Platform-specific Unicode text input
- Auto/paste/type mode selection
- Cross-platform compatibility (macOS Quartz, Windows SendInput)

#### `core/capture.py` - Screen Capture
**Screen capture with DPR detection and multi-platform support**

**Key Classes:**
- `ScreenCapture` - Main capture interface
- `CaptureResult` - Capture result container

**Key Functions:**
- `screenshot()` - Capture screen with DPR detection
- `_detect_dpr()` - Device pixel ratio detection
- `_capture_macos()` - macOS-specific capture
- `_capture_cross_platform()` - Cross-platform fallback

**Features:**
- High-DPI display support
- Platform-optimized capture methods
- Automatic DPR detection

#### `core/reporter.py` - Logging and Report Generation  
**Comprehensive logging, screenshot management, and HTML report generation**

**Key Classes:**
- `Reporter` - Main reporting interface
- `StepLog` - Individual step log entry

**Key Functions:**
- `log_step(step_log)` - Log individual workflow step
- `save_image(bgr, filename)` - Save screenshots with organization
- `draw_detections(bgr, boxes, labels, chosen_idx)` - Annotate detection overlays
- `write_html()` - Generate comprehensive HTML report
- `flush_jsonl()` - Flush logs to JSONL format

**Features:**
- Step-by-step execution logging
- Screenshot organization and annotation
- HTML report generation with metrics
- JSONL log format for analysis

#### `core/anchors.py` - Template Matching and Anchor System
**Robust replay system using multiple anchor types for reliability**

**Key Classes:**
- `RoutesStore` - Persistent route storage and management

**Key Functions:**
- `anchors_from(bgr, bbox)` - Generate template anchors
- `anchors_match(bgr, anchors)` - Match template anchors
- `auto_select_anchors(bgr, bbox)` - Generate compound anchors
- `locate_instance(bgr, row_anchor, action_anchor, relation)` - Compound anchor location
- `state_anchors_from(bgr, ...)` - Generate state anchors for verification
- `state_anchors_vote(bgr, state_anchors, ...)` - Vote on state matching

**Anchor Types:**
- **Template Anchors**: Image template matching
- **Compound Anchors**: Row + Action + Spatial relation
- **ORB/SIFT Anchors**: Feature-based matching  
- **State Anchors**: Next-page state validation

#### `core/strategy_selector.py` - Strategy-Based Decision Making
**M2 strategy layer for intelligent UI interaction patterns**

**Key Classes:**
- `StrategySelector` - Main strategy selection engine

**Key Functions:**
- `decide(step_n, sig_key, goal_text, page_summary)` - Strategy decision making
- `_should_trigger_strategy(...)` - Strategy trigger logic
- `_extract_features(page_summary)` - Feature extraction for strategy

**Features:**
- Caching and timeline events
- Enhanced trigger logic with workflow state
- Memory integration for strategy learning

#### `core/memory.py` - Memory System
**Persistent memory for UI interactions and learning**

**Key Classes:**
- `MemoryStore` - Main memory interface

**Key Functions:**
- `record(sig_key, element_id, outcome, reason)` - Record interaction results
- `summarize(sig_key)` - Summarize interaction history
- `get_blacklist(sig_key, k)` - Get failed element blacklist

**Features:**
- Interaction outcome tracking
- Blacklist management for failed elements
- Historical pattern analysis

### 3. Strategy System (M2 Layer)

#### `core/strategy_adapter.py` - M2 Strategy Integration
**Adapter for integrating M2 strategies into M3 workflow**

**Key Functions:**
- `create_strategy_context(dets, bgr, ocr_lines, url_hint)` - Create strategy context
- `extract_page_features(context)` - Extract page-level features
- `determine_page_kind(context)` - Classify page type

#### `core/strategy_exec.py` - Strategy Execution
**Execute strategies with fallback to standard picker**

**Key Functions:**
- `exec_strategy_with_fallback(spec, items, landmarks)` - Execute with fallback
- `execute_strategy(strategy_id, params, items, landmarks)` - Core execution

#### `core/strategy_store.py` - Strategy Persistence
**Strategy caching and learning system**

**Key Functions:**
- `lookup(sig_key, goal_text, ...)` - Find cached strategy
- `record(sig_key, goal_text, strategy, success, ...)` - Record strategy result

### 4. Utilities and Support

#### `core/yolo_client.py` - YOLO Detection Client
**Client for YOLO detection API with result processing**

**Key Functions:**
- `infer(image, return_image, imgsz)` - Run YOLO inference
- `to_detections(response)` - Convert API response to detection objects

#### `core/ocr_client.py` - OCR Client
**OCR integration with multiple backend support**

**Key Functions:**
- `read_texts(image)` - Extract text from image
- `read_lines(image)` - Extract text lines with positioning

#### `core/detectors.py` - Specialized Detectors
**Template-based detection for UI states**

**Key Functions:**
- `detect_loading(bgr)` - Detect loading indicators
- `detect_toast(bgr)` - Detect toast notifications
- `detect_modal(bgr)` - Detect modal dialogs

#### `core/landmarks.py` - UI Landmark Detection
**Detect common UI landmarks and structural elements**

**Key Functions:**
- `detect_landmarks(all_items, ocr_lines, viewport)` - Detect UI landmarks
- `_score_candidate(item, role, ocr_lines, ...)` - Score landmark candidates

#### `core/costs.py` - M3 Cost Management
**Cost tracking, budgeting, and optimization**

**Key Classes:**
- `CostGuard` - Budget enforcement
- `Budget` - Budget configuration
- `UsageTracker` - Usage analytics

### 5. Tools and Utilities

#### `tools/run_workflow_gen.py` - Workflow Generation Tool
**CLI tool for generating workflows from natural language**

**Usage:**
```bash
python tools/run_workflow_gen.py --task "search for cars" --provider gemini --model gemini-1.5-flash --out flows/car_search.json
```

#### `tools/report_gen.py` - Report Generation
**Generate analysis reports from execution logs**

#### `tools/replay_run.py` - Workflow Replay
**Replay and debug workflow executions**

#### `tools/smoke_suite.py` - Test Suite
**Comprehensive testing suite for system validation**

### 6. Main Runners

#### `run_workflow.py` - Main Workflow Runner
**Primary entry point for executing workflows**

**Usage:**
```bash
python run_workflow.py --workflow flows/example.json --endpoint http://127.0.0.1:8000
```

#### `run_gemini.py` - Direct LLM Testing
**Test LLM calls directly with images and YOLO data**

**Usage:**
```bash
python run_gemini.py --provider gemini --model gemini-1.5-flash --image screenshot.png --yolo yolo_results.json
```

## Key Design Patterns

### 1. Vision-First UI Picking
The system uses YOLO to detect all UI elements, then provides LLM with numbered overlays for intelligent selection based on semantic understanding.

### 2. Multi-Modal Anchoring
Combines multiple anchor types (template, ORB/SIFT, spatial relations) for robust replay capabilities.

### 3. Provider Abstraction
Unified interface across multiple LLM providers (Gemini, OpenAI, DeepSeek, NVIDIA) with consistent message formatting.

### 4. Cost-Controlled Operations (M3)
Comprehensive cost tracking and budget management with fallback strategies when limits are reached.

### 5. State-Based Workflows
JSON-driven state machine approach with signature-based state recognition and transition verification.

### 6. Strategy Layer (M2)
Intelligent pattern recognition for common UI interaction scenarios with learning and caching.

## Configuration and Environment

### Environment Variables
- `LLM_PROVIDER` - Default LLM provider (gemini/openai/deepseek/nvidia)
- `LLM_MODEL` - Default model name
- `YOLO_WEIGHTS` - Path to YOLO model weights
- `YOLO_CONF` - Confidence threshold for detections
- `OCR_ENDPOINT` - OCR service endpoint
- `SCREENSHOT_WAIT_S` - Wait time before screenshots
- `W_RULE`, `W_HINT`, `W_LLM` - Fusion weights for verification
- `TH_PASS` - Pass threshold for verification

### Workflow JSON Structure
```json
{
  "start": "state_name",
  "states": {
    "state_name": {
      "actions": [
        {
          "do": "autostep",
          "goal": "description of what to accomplish",
          "picker": "vision",
          "k": 12,
          "verify": {
            "timeout_ms": 8000,
            "poll_ms": 600,
            "rules": ["page_change"]
          },
          "fallback": {"action": "scroll"},
          "save": {
            "shot": "step_{n}.png",
            "yolo": "yolo_{n}.json"
          }
        }
      ],
      "on_success": "next_state"
    }
  }
}
```

## Output Structure
- `out/screens/` - Screenshots and annotated overlays per step
- `out/logs/` - YOLO detections, LLM requests/responses, workflow state
- `out/reports/` - HTML reports with timeline and metrics
- `flows/` - JSON workflow definitions

## Detailed Function Inventory

### Core Module Functions

#### `core/workflow.py` - Main Workflow Engine (2344+ lines)
**Classes:**
- `WFConfig` - Configuration dataclass
  - `conf_min: float = 0.5` - Minimum confidence threshold
  - `poll_interval_s: float = 0.6` - Polling interval for verification
  - `wait_timeout_s: float = 8.0` - Wait timeout for actions
  - `click_padding_px: int = -6` - Click coordinate padding
  - `imgsz: int = 1280` - YOLO image size
  - `screenshot_wait_s: float` - Wait before screenshots
  - `max_retries_per_step: int` - Maximum retries per step

- `WorkflowRunner` - Main execution engine
  - `__init__(workflow, endpoint, out_dir, cfg)` - Initialize runner
  - `_grab()` - Capture screenshot with DPR detection
  - `_detect()` - Run YOLO detection on current screen
  - `_signature(bgr, dets) -> Dict[str, Any]` - Generate page signature
  - `_sig_sim(a, b) -> float` - Calculate signature similarity
  - `_resolve_or_create_state(sig) -> str` - Resolve or create state ID
  - `_autostep(cfg)` - Vision-first LLM decision making with verification
  - `act_screenshot(save_as)` - Screenshot action
  - `act_click()` - Click action with DPR handling
  - `act_type_text(text)` - Text input action
  - `act_scroll(clicks)` - Scroll action
  - `act_sleep_ms(value)` - Sleep action
  - `act_wait_for(until) -> bool` - Wait for conditions
  - `act_open_url(url, app)` - Open URL in browser
  - `run_actions(actions)` - Execute action list
  - `run(start_state)` - Main workflow execution

**Functions:**
- `load_workflow(path: str) -> Dict[str, Any]` - Load JSON workflow

#### `core/llm_client.py` - Unified LLM Client
**Functions:**
- `call_llm(provider, model, messages, image_path, mime_type, temperature) -> Dict` - Universal LLM API
- `extract_text_generic(response_json) -> str` - Extract text from any provider
- `generate_json(messages, image_path, mime_type, temperature, provider, model) -> Dict` - Get JSON response
- `_attach_image_gemini(messages, image_path, mime_type)` - Gemini image attachment
- `_to_openai_messages_from_gemini(messages, image_path, mime_type)` - Format conversion

#### `core/llm_router.py` - M3 Cost-Controlled Routing
**Classes:**
- `LLMRouter` - Central LLM gateway
  - `__init__(guard: CostGuard)` - Initialize with cost guard
  - `maybe_call(kind, messages, image_path, provider, model, fallback_result)` - Cost-controlled call
  - `_estimate_tokens_for_call(kind, degradation, has_image, messages) -> int` - Token estimation
  - `_apply_image_degradation(image_path, kind, degradation) -> str` - Image processing
  - `get_call_stats() -> Dict` - Usage statistics

#### `core/prompt_builder.py` - Prompt Templates
**Classes:**
- `PromptSpec` - Prompt specification dataclass
  - `goal: str` - Primary objective
  - `page: str` - Page context
  - `preferred_classes: List[str]` - Preferred UI element types
  - `negative_classes: List[str]` - Elements to avoid
  - `hints: List[str]` - Additional guidance
  - `viewport: Tuple[int, int]` - Screen dimensions

**Functions:**
- `build_user_payload(yolo_json, viewport_wh, spec) -> str` - Build LLM payload
- `build_messages(system_text, user_payload) -> List[Dict]` - Complete message structure
- `build_picker_messages(pop_spec, candidates_obj) -> List[Dict]` - Vision picker prompts
- `build_planner_messages(task, recent, sig_hint) -> List[Dict]` - Task planning prompts
- `build_cross_confirm_messages(goal, prev_click, expected_state) -> List[Dict]` - Verification prompts

#### `core/candidates.py` - YOLO Processing
**Functions:**
- `yolo_to_geom_candidates(yolo_json, page_w, page_h, modal_bbox_list, k) -> Dict` - Convert detections
- `box_to_geom(bbox, page_w, page_h) -> Dict` - Geometric feature extraction
- `region_tag(cx, cy) -> str` - Assign UI region tags
- `iou(a, b) -> float` - Intersection over union calculation

#### `core/executor.py` - Automation Execution
**Classes:**
- `Executor` - Cross-platform automation
  - `__init__(jitter_px=2)` - Initialize with jitter
  - `click(x, y, duration=0.25, post_sleep=0.1, dpr=1.0)` - DPR-aware clicking
  - `type_text(text, interval=0.02, mode="auto")` - Unicode text input
  - `scroll(clicks=-400)` - Scroll with customizable amount
  - `move_to(x, y, duration=0.5)` - Mouse movement with easing
  - `go_back()` - Browser back navigation

#### `core/capture.py` - Screen Capture
**Classes:**
- `GrabResult` - Capture result container
  - `image: Image.Image` - PIL image
  - `dpr: float` - Device pixel ratio
  - `size_px: Tuple[int, int]` - Physical pixel size

- `ScreenCapture` - Screen capture utility
  - `__init__(force_dpr=None)` - Initialize capture
  - `screenshot() -> GrabResult` - Take screenshot with DPR
  - `pil_to_bgr(img) -> np.ndarray` - Convert to OpenCV format
  - `bgr_to_png_bytes(bgr) -> bytes` - Convert to PNG bytes

#### `core/reporter.py` - Logging and Reports
**Classes:**
- `StepLog` - Step logging dataclass
  - `name: str` - Step identifier
  - `status: str` - Execution status (success/fail/info)
  - `message: str` - Status message
  - `conf: Optional[float]` - Confidence score
  - `chosen_cls: Optional[str]` - Selected element class
  - `before_img: Optional[str]` - Before screenshot path
  - `after_img: Optional[str]` - After screenshot path
  - `overlay_img: Optional[str]` - Overlay image path
  - `click_xy: Optional[Tuple[int, int]]` - Click coordinates

- `Reporter` - Report generation
  - `__init__(out_dir="out")` - Initialize reporter
  - `save_image(bgr, name) -> str` - Save BGR image with timestamp
  - `draw_detections(bgr, boxes, labels, chosen_idx) -> np.ndarray` - Annotate overlays
  - `log_step(step: StepLog)` - Log workflow step
  - `flush_jsonl()` - Write logs to JSONL
  - `write_html(filename=None) -> str` - Generate HTML report

#### `core/anchors.py` - Anchor System
**Classes:**
- `RoutesStore` - Persistent anchor storage
  - `__init__(logs_dir, filename="routes.jsonl")` - Initialize storage
  - `append(rec)` - Add new route record
  - `lookup(sig_key, goal) -> Optional[Dict]` - Find matching route
  - `window_success_rate(sig_key, goal, window=50) -> float` - Success rate calculation

**Functions:**
- `anchors_from(bgr, bbox, pad_ratio=0.1) -> Dict` - Create template anchor
- `anchors_match(bgr, anchors) -> float` - Match template anchor
- `auto_select_anchors(bgr, bbox) -> Dict` - Generate compound anchors
- `locate_instance(bgr, row_anchor, action_anchor, relation) -> Optional[List]` - Compound matching
- `state_anchors_from(bgr, url_hint, ocr_texts, ocr_lines) -> Dict` - State anchors
- `state_anchors_vote(bgr, state, ocr_texts, current_url, expected_texts, ocr_lines) -> float` - State verification

#### `core/strategy_selector.py` - Strategy Decision Making
**Classes:**
- `TriggerCondition` - Strategy trigger conditions
  - `min_picker_failures: int` - Minimum picker failures to trigger
  - `min_need_input_count: int` - Minimum need_input events
  - `min_deny_hits: int` - Minimum deny list hits
  - `memory_health_threshold: float` - Memory health threshold

- `StrategySelector` - Strategy selection engine
  - `__init__(logs_dir)` - Initialize selector
  - `decide(step_n, sig_key, goal, page_summary, workflow_state=None) -> Optional[Dict]` - Main decision
  - `should_trigger_strategy_llm(workflow_state) -> bool` - M2 trigger logic
  - `get_cached(sig_key, goal) -> Optional[Dict]` - Get cached strategy
  - `put_cached(sig_key, goal, strat)` - Cache strategy result

#### `core/memory.py` - Decision Memory
**Classes:**
- `MemoryStore` - Persistent decision memory
  - `__init__(logs_dir, filename="memory.jsonl", max_keep=2000)` - Initialize store
  - `record(sig_key, click_id, outcome, reason="")` - Record interaction outcome
  - `get_blacklist(sig_key, k=5, ttl_minutes=None) -> List[str]` - Get failed elements
  - `summarize(sig_key, limit=2) -> Optional[str]` - Generate history summary

#### `core/yolo_client.py` - YOLO Detection Client
**Classes:**
- `Detection` - Detection result dataclass
  - `id: int` - Detection ID
  - `class_name: str` - Object class
  - `conf: float` - Confidence score
  - `bbox_xyxy: List[float]` - Bounding box coordinates

- `YoloClient` - YOLO API client
  - `__init__(endpoint="http://127.0.0.1:8000")` - Initialize client
  - `infer(image, return_image=False, conf=None, iou=None, imgsz=None) -> Dict` - Run inference
  - `to_detections(resp) -> List[Detection]` - Convert response to objects

#### `core/ocr_client.py` - OCR Client
**Classes:**
- `OcrClient` - OCR API client
  - `__init__(endpoint)` - Initialize OCR client
  - `read_texts(pil, lang="auto", min_conf=0.1) -> List[str]` - Extract text strings
  - `read_lines(pil, lang="auto", min_conf=0.1) -> List[Dict]` - Extract text with positions

#### `core/detectors.py` - State Detectors
**Functions:**
- `detect_loading(bgr) -> Dict[str, Any]` - Detect loading states
- `detect_toast(bgr) -> Dict[str, Any]` - Detect toast notifications  
- `detect_modal(bgr) -> Dict[str, Any]` - Detect modal dialogs
- `detect_close(bgr, roi_norm=None) -> Dict[str, Any]` - Detect close controls

#### `core/landmarks.py` - UI Landmark Detection
**Functions:**
- `detect_landmarks(all_items, ocr_lines=None, img=None) -> List[Dict]` - Detect UI landmarks
- `detect_landmarks_cached(all_items, ocr_lines=None, img=None, cache_ttl_s=30) -> List[Dict]` - Cached detection
- `_score_candidate(item, role, ocr_lines, screen_w, screen_h, tpl_score=0.0) -> float` - Score candidates

#### `core/costs.py` - M3 Cost Management
**Classes:**
- `Budget` - Cost budget configuration
  - `max_strategy_calls: int` - Maximum strategy LLM calls
  - `max_picker_calls: int` - Maximum picker LLM calls
  - `max_arbiter_calls: int` - Maximum arbiter LLM calls
  - `max_tokens_per_run: int` - Token limit per run
  - `from_env() -> Budget` - Load from environment variables

- `Usage` - Current usage tracking
  - `strategy_calls: int` - Strategy call count
  - `picker_calls: int` - Picker call count
  - `tokens: int` - Total token usage
  - `reset_step()` - Reset step counters

- `CostGuard` - Budget enforcement
  - `__init__(budget=None)` - Initialize guard
  - `begin_step()`, `end_step()` - Step tracking
  - `can_call(kind: str) -> bool` - Check call permission
  - `should_degrade(kind: str) -> str` - Get degradation level
  - `get_stats() -> Dict` - Usage statistics

- `ImageDegradationPolicy` - Image processing policies
  - `get_picker_policy(degradation: str) -> Dict` - Picker image settings
  - `estimate_tokens(kind: str, degradation: str, has_image: bool) -> int` - Token estimation

## Parameter Type Patterns

**Common Types:**
- `bgr: np.ndarray` - BGR format images (OpenCV)
- `pil: Image.Image` - PIL images for API calls
- `bbox: List[float]` - Bounding boxes [x1, y1, x2, y2]
- `messages: List[Dict[str, Any]]` - LLM message format
- `provider: str` - LLM provider ("gemini"/"openai"/"deepseek"/"nvidia")
- `model: str` - Model identifier
- `sig_key: str` - Signature key for caching
- `goal: str` - Task description
- `viewport: Tuple[int, int]` - Screen dimensions (width, height)
- `dpr: float` - Device pixel ratio

**Return Type Patterns:**
- `Dict[str, Any]` - JSON responses and structured data
- `Optional[T]` - Nullable returns for error cases
- `List[T]` - Collections of detections, candidates
- `float` - Confidence scores, similarity metrics
- `bool` - Success flags, condition checks
- `str` - File paths, text content, identifiers

This comprehensive documentation provides complete coverage of the M3 Vision-First UI Automation Engine codebase, enabling AI systems to understand the architecture, locate specific functionality, and make informed improvements to the system.