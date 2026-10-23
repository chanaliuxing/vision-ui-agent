# Codebase Map (Tree + Index)

This document provides a tree view of the repository and a quick index of important modules, classes, and functions to speed up navigation and debugging.

## Tree

```
.
├── AGENTS.md
├── README.md
├── CODEMAP.md
├── app.py
├── app_ocr.py
├── app_nice_version.py
├── app_workflow.py
├── autogui.py
├── config/
│   └── classes.json
├── core/
│   ├── candidates.py
│   ├── capture.py
│   ├── executor.py
│   ├── gemini_client.py
│   ├── llm_client.py
│   ├── locator.py
│   ├── mapping.py
│   ├── prompt_builder.py
│   ├── reporter.py
│   ├── sm.py
│   └── workflow.py
├── ddl/
├── docs/
│   └── old_tool_runbook.md
├── flows/
│   ├── auto_workflow.json
│   └── xhs_longform_vision.json
├── index.html
├── drawing.js
├── out/
│   ├── logs/
│   ├── reports/
│   └── screens/
├── requirements.txt
├── run_gemini.py
├── run_post.py
├── run_workflow.py
├── scripts/
│   ├── one_click_sqs.sh
│   └── one_click_sqs.md
├── solar.py
├── startYolo.md
├── docker-compose.sqs.yml
├── config/
│   └── localstack/
│       └── 10-queues.sh
├── test.py
├── tools/
│   └── run_workflow_gen.py
├── weights/
│   └── (local model files, ignored by git)
├── yolo_nice_version_endpoint.md
└── yolo_ocr_endpoint.md
```

Note: The `out/` and `weights/` contents are environment/runtime artifacts and not fully tracked in git.

---

## Index by File (Key Classes/Functions)

### app.py
- Purpose: Primary FastAPI YOLO API (IDs inside-box labeling, adaptive font sizing).
- Key routes:
  - `GET /health` → returns status, model path, device.
  - `POST /predict` → runs YOLO, returns detections JSON, optional annotated image.
  - `POST /v1/autostep` → AutoStep planner endpoint (`planner_next|planner_report`) with multimodal routing + report idempotency.
  - `POST /v1/autostep/patch-proposal` → failure recovery patch suggestion (placeholder).
- AutoStep helpers:
  - `_resolve_autostep_image` → image extraction from `image.base64` or OpenAI-style `content[].image_url`.
  - `_select_provider_model` → provider/model routing (vision-capable fallback for `planner_next`).
  - `_get_trace_request_id`, `_get_operation_id` → trace/idempotency identifiers.
  - `_build_autostep_tool_planner_prompt`, `_normalize_autostep_tool_call` → pre-click LLM tool planner for safe keyboard/wait actions before the visual picker.
  - `AUTOSTEP_ALLOW_LLM_FALLBACKS` (default off) controls whether `planner_next` can use `LLM_FALLBACKS`.
  - `AUTOSTEP_TOOL_PLANNER` (default on) controls the safe non-click tool planner.
  - `AUTOSTEP_PICK_MIN_CONF` defaults to `0.45` for AutoStep visual picks; deployments can raise it by env.
- Helpers: `_np_to_base64_png`, `_read_image_bytes`, `_draw_scene_inside`, `_draw_inside_label`, `_sort_indices_tl`.

### app_ocr.py
- Purpose: YOLO + OCR fusion (PaddleOCR preferred, EasyOCR fallback).
- Classes: `OCRBackend` (unified OCR wrapper; `read()` returns line polygons/text/conf).
- Routes: `GET /health`, `POST /predict`.

### app_nice_version.py
- Purpose: Alternate API variant mirroring `app.py` with the same in-box labeling logic.

### app_workflow.py
- Purpose: Workflow generator API endpoint.
- Route: `POST /workflow/generate` → builds meta-prompt, calls LLM, writes JSON under `flows/`.

### autogui.py
- Purpose: Simple screen watcher using `pyautogui`.
- Functions: `bring_terminal_to_front`, `locate`, `press_enter`, `type_and_enter`, `main`.

### core/candidates.py
- Purpose: Convert YOLO detections to geometry-only candidates for vision-first picker.
- Functions: `iou`, `box_to_geom`, `region_tag`, `is_overlap_modal`, `yolo_to_geom_candidates`.

### core/capture.py
- Purpose: Screen capture with DPR detection.
- Classes:
  - `GrabResult(image, dpr, size_px)` dataclass.
  - `ScreenCapture`: `screenshot`, `pil_to_bgr`, `bgr_to_png_bytes`.

### core/executor.py
- Purpose: Mouse/keyboard actions via `pyautogui`.
- Class `Executor`: `move_to`, `click` (parks at 24,24), `type_text`, `scroll`, `go_back`.

### core/gemini_client.py
- Purpose: Minimal Gemini 1.5 call utilities.
- Functions: `load_env_from_dotenv`, `read_image_b64`, `call_gemini`, `extract_text`, `parse_first_json`, `generate_json`.

### core/llm_client.py
- Purpose: Unified LLM client (Gemini, OpenAI, DeepSeek, NVIDIA/OpenAI-compatible).
- Functions: `call_llm` (retries/backoff), `extract_text_generic`, `generate_json`.
- Helpers: `_attach_image_gemini`, `_to_openai_messages_from_gemini`.

### core/locator.py
- Purpose: Select “best” detection by class and center bias.
- Classes: `LocateResult(chosen, candidates, score)`.
- Functions: `_center_bias`, `select_best`, `bbox_center`.

### core/mapping.py
- Purpose: Map YOLO boxes to screen coordinates.
- Dataclasses: `CaptureMeta`, `PreprocMeta`.
- Functions: `to_capture_coords`, `click_point_from_box`, `map_id_to_screen_point`.

### core/prompt_builder.py
- Purpose: Prompt templates/builders for workflows, picker, and PoP.
- Dataclass: `PromptSpec`.
- Constants: `SYSTEM_TEMPLATE_UI_OUTLINE`, `SYSTEM_ID_ONLY_JSON`, `DECISION_PROMPT_TEMPLATE`, `VERIFIER_PROMPT_TEMPLATE`, `META_WORKFLOW_PROMPT`, `PICKER_VISION_SYSTEM`, `POP_VISION_SYSTEM`.
- Builders: `build_user_payload`, `build_messages`, `build_id_only_messages`, `build_workflow_prompt`, `build_picker_payload`, `build_picker_messages`, `build_pop_messages`.

### core/reporter.py
- Purpose: Persist screenshots, logs, and HTML reports.
- Dataclass: `StepLog`.
- Class `Reporter`: `save_image`, `draw_detections`, `log_step`, `flush_jsonl`, `write_html`.

### core/sm.py
- Purpose: Simple state machine helper for waiting until targets appear via YOLO.
- Class `StateMachine`: `wait_for_any`.

### core/workflow.py
- Purpose: JSON-driven workflow engine and vision-first autostep.
- Dataclass `WFConfig`: `conf_min`, `poll_interval_s`, `wait_timeout_s`, `click_padding_px`, `imgsz`, `screenshot_wait_s`.
- Class `WorkflowRunner`:
  - Context: `ctx` (`last_pil`, `last_bgr`, `detections`, `dpr`, `step_n`, `next_state_id`...).
  - Helpers: `_grab`, `_detect`, `_locate`, `_draw_overlay`.
  - Signatures/graph: `_signature`, `_tile_hashes`, `_yolo_hist`, `_sig_sim`, `_resolve_or_create_state`, `_link_edge`, `_save_graph_workflow`.
  - Actions: `act_screenshot`, `act_detect`, `act_locate`, `act_click`, `act_type_text`, `act_scroll`, `act_sleep_ms`, `act_wait_for`, `act_open_url`, `act_go_back`.
  - Instruction layer: handles `instr.*` (click/type/scroll/hover/key/navigate/history/upload/read/wait/task_complete/answer_user) → maps to `ext.*` or coordinate fallbacks.
  - `run_actions(actions)`: executes declared steps (including `detect`, `decide_with_gemini`).
  - `run(start_state)`: state loop and reporter integration.
  - `_autostep(cfg)`: vision-first picker
    - Saves `step_{n}.png`, `overlay_step_{n}.png`, `yolo_step_{n}.json`.
    - Builds geometry candidates; optional PoP; logs all LLM req/resp with `{provider}_{model}` prefix.
    - Maps `click_id` → detection, optional pre-hover probe, clicks, verifies transition.
    - Replays via saved anchors: legacy template and compound Row+Action+Relation anchors with next-page state anchors.

### core/anchors.py
- Purpose: Anchor utilities (template + compound) and state anchors.
- Functions: `anchors_from`, `anchors_match`, `gen_templates`, `gen_orb_features`, `auto_select_anchors`, `locate_instance`, `state_anchors_from`, `state_anchors_vote`.

### core/strategy_selector.py
- Purpose: Strategy LLM caller (strict JSON), request/response logs, in-memory cache, timeline events.
- Key: `StrategySelector.decide(step_n, sig_key, goal, page_summary)`

### core/ops.py
- Purpose: Structural operators scaffolding for strategy execution (within/below/right_of/nearest_to/cluster_list/nth/has_attr/sort_by_y).

### core/landmarks.py
- Purpose: Page summary and basic landmark scaffolding for Strategy inputs.

### flows/
- `auto_workflow.json`: minimal auto-advance demo.
- `xhs_longform_vision.json`: XHS longform posting, two states: `open_home` → `post_longform`.

### run_workflow.py
- Purpose: Run JSON workflow.
- Args: `--workflow`, `--endpoint`, `--conf`, `--imgsz`, `--timeout`, `--poll`, `--shot-wait`.

### run_post.py
- Purpose: Minimal detect-and-click MVP; produces a small HTML report.

### run_gemini.py
- Purpose: Send overlay + YOLO JSON to an LLM with structured prompts (multi-provider).
- Args: `--provider`, `--model`, `--image`, `--yolo`, `--goal`, `--page`, `--temperature`.

### tools/run_workflow_gen.py
- Purpose: Generate a workflow from the meta-prompt (multi-provider).

### yolo_ocr_endpoint.md, yolo_nice_version_endpoint.md
- API docs for HTTP services.

### index.html, drawing.js
- Small demo UI (unrelated to engine); drawing board.

### solar.py, test.py
- Experimental/demo scripts.

---

## Search Tips
- Vision picker messages: search `picker_req_step_` in `out/logs/`.
- PoP bias per step: search `pop_req_step_`.
- Image pair per decision: `out/screens/step_{n}.png` vs `overlay_step_{n}.png`.
- Engine internals: `core/workflow.py` (`_autostep`, `run_actions`, `act_*`).
- LLM provider selection: `core/llm_client.py`; defaults via `.env` (`LLM_PROVIDER`, `LLM_MODEL`).
- Geometry candidates: `core/candidates.py` (region/area/aspect).

## Conventions
- Filenames include step index `{n}` and LLM provider/model prefixes where relevant.
- Secrets/weights are not committed; `.env` and `weights/` are local-only.
