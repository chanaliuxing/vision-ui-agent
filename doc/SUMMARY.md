# Codebase Summary

This repository combines a local YOLO detection API with a small but capable UI‑automation engine. It supports a vision‑first ID picker that selects clickable targets directly from annotated screenshots, and a meta‑prompt workflow generator. LLM providers are pluggable (Gemini, OpenAI, DeepSeek, NVIDIA).

## Purpose & High‑Level Architecture

- Objective: Detect UI elements, decide what to click based on current intent, and execute reliable actions (click/scroll/type), while logging artifacts for debugging.
- Components:
  - FastAPI YOLO services: `app.py` (primary), `app_ocr.py` (YOLO+OCR), `app_nice_version.py` (variant).
  - Core engine: screen capture, detection, mapping, executor (mouse/keyboard), workflow runner, prompts.
  - Vision‑first Picker: LLM picks a single id (e.g., `c12`) from the overlay image + geometry candidates (no cls/txt dependency).
  - Workflow generation: meta‑prompt to synthesize `flows/*.json` from task description.
  - Multi‑provider LLM client: Gemini, OpenAI, DeepSeek, NVIDIA (OpenAI‑compatible) with unified request/response handling.

## Directory Overview

- `app.py`, `app_ocr.py`, `app_nice_version.py`: FastAPI servers (YOLO only; YOLO+OCR).
- `core/`: engine and helpers — capture, executor, candidates (geometry), mapper, prompts, reporter, workflow runner, LLM clients.
  - New strategy layer: `core/strategy_selector.py` (Strategy LLM), `core/strategy_store.py` (strategy memory), `core/ops.py` (operators), `core/landmarks.py` (page landmarks/summary).
- `flows/`: runnable workflows (`*.json`).
- `tools/`: CLI to generate workflows from the meta-prompt.
  - `tools/wam/`: Workflow Authoring Module — builder (`WF`), templates, and validator (schema + semantic checks).
- `out/`: run artifacts — logs, overlays, screenshots, HTML reports (not tracked by git).
  - With `FULL_CAPTURE=true`, full LLM request/response JSON is saved under `out/runs/.../llm/<provider>/`.
- `weights/`: local YOLO weights (ignored by git).

See `CODEMAP.md` for a tree and per‑file index (classes/functions).

## Key Modules & Responsibilities

- YOLO API (`app.py`)
  - `POST /predict`: runs YOLO, produces detections and optional annotated PNG; ID labels rendered inside boxes with adaptive font sizing.
  - Returns normalized metadata like `click_xy_norm`, `bbox_xyxy`, `label_bbox_xyxy`.
  - `POST /v1/autostep`: planner API with `phase=planner_next|planner_report`.
    - `planner_next`: accepts image from `image.base64` or OpenAI-style `content[].image_url`, forces vision-capable model routing, returns `{done}` or `{tool_call}`.
    - `planner_report`: idempotent by `request_id + operation_id`, returns `idempotent=true` on duplicate reports.
    - Provider/model selection now prioritizes `.env` (`LLM_PROVIDER`, `LLM_MODEL`) when request does not override.
    - AutoStep fallback chain can be disabled (default) via `AUTOSTEP_ALLOW_LLM_FALLBACKS=0` to avoid unexpected model jumps.
    - `planner_next` first asks a lightweight LLM tool planner for safe non-click actions (`keyboard.type_text`, `keyboard.hotkey`, `keyboard.press`, `wait.sleep`); visual mouse clicks still go through the YOLO+LLM picker.
    - AutoStep visual picker defaults to `AUTOSTEP_PICK_MIN_CONF=0.45` so LLM-selected low-score input boxes can still be clicked; override via env for stricter deployments.
    - Unified error envelope: `{ok:false,status,code,message}`.
- YOLO+OCR (`app_ocr.py`)
  - PaddleOCR preferred, EasyOCR fallback; global + crop OCR with fusion & de‑dup; can directly return PNG.
 - Workflow Engine (`core/workflow.py`)
  - `WorkflowRunner.run(...)`: executes states; actions include `open_url`, `screenshot`, `detect`, `autostep`, etc.
  - `autostep`: capture → detect → save overlay → build geometry candidates → PoP (optional) → Picker LLM → click → verify.
  - Saves per‑step artifacts: raw screenshot, YOLO overlay, YOLO JSON, LLM req/resp, picker output.
   - Strategy (disabled by default): when `STRATEGY_LAYER=1`, logs `[llm/strategy_req|resp]`, `[strategy/try|chosen|memory_hit|click|exec_ok|exec_fail|fallback]`.
   - Action Space v2: semantic `instr.*` actions compile to DOM (`ext.*`) with coordinate fallback (via `bbox_var`) for non‑DOM/desktop.
- Vision‑first Picker
  - Prompts in `core/prompt_builder.py` (`PICKER_VISION_SYSTEM`, `POP_VISION_SYSTEM`).
  - Candidates from `core/candidates.py`: `{id, cx, cy, w, h, area, aspect, region, overlap_modal}`; regions: `topbar|toolbar|content|bottombar`.
- LLM Client (`core/llm_client.py`)
  - `call_llm(...)`: unified call across Gemini/OpenAI/DeepSeek/NVIDIA with configurable retries/backoff.
  - `generate_json(...)`: parse strict JSON; also supports attached overlay image.
- Mapping & Execution
  - `core/mapping.py`: map model box → screen click point; handles normalization/letterbox, DPR.
  - `core/executor.py`: DPR‑aware click/move/type/scroll/go_back; parks pointer safely (avoids failsafe corners).

## Autostep Data Flow (Vision‑First)

1) Screenshot saved as `out/screens/step_{n}.png`.
2) Detect: YOLO JSON saved to `out/logs/yolo_step_{n}.json`.
3) Server overlay saved as `out/screens/overlay_step_{n}.png`.
4) Candidates built (`yolo_to_geom_candidates`) → geometry‑only payload.
5) Optional PoP (`pop: "auto"`):
   - Request/response saved as `{provider}_{model}_pop_{req|resp}_step_{n}.json`.
6) Picker LLM decides `click_id`:
   - Request/response saved as `{provider}_{model}_picker_{req|resp}_step_{n}.json`.
7) Map `click_id` → detection → screen click; verify rules then transition.

Compound anchors and replay
- Successful steps promote both a legacy template anchor and a compound (Row+Action+Relation) anchor plus next‑page state anchors.
- On future runs, engine first attempts compound anchor replay (no LLM) with state‑anchors verification; falls back to legacy anchor or LLM picker.

## Logging & Artifact Naming

- Screenshots: `out/screens/step_{n}.png`
- Overlays: `out/screens/overlay_step_{n}.png`
- YOLO JSON: `out/logs/yolo_step_{n}.json`
- Picker LLM: `{provider}_{model}_picker_req_step_{n}.json`, `{provider}_{model}_picker_resp_step_{n}.json`
- PoP LLM: `{provider}_{model}_pop_req_step_{n}.json`, `{provider}_{model}_pop_resp_step_{n}.json`
- decide_with_gemini (legacy op): `{provider}_{model}_decide_req_{ts}.json`, `{provider}_{model}_decide_resp_{ts}.json`

Provider/model names are normalized for filesystem safety (`/` → `-`).

## Configuration (.env)

- LLM selection: `LLM_PROVIDER=gemini|openai|deepseek|nvidia`, `LLM_MODEL=<name>`
  - Provider keys: `GEMINI_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `NVIDIA_API_KEY`
  - Optional endpoints: `OPENAI_API_URL`, `DEEPSEEK_API_URL`, `NVIDIA_API_URL`
  - Retries: `LLM_RETRY_ATTEMPTS` (default 1), `LLM_RETRY_BASE_DELAY_S` (default 1), `LLM_RETRY_MAX_DELAY_S` (default 8)
- YOLO: `YOLO_WEIGHTS`, `YOLO_CONF`, `YOLO_IOU`, `YOLO_IMGSZ`
- Engine: `SCREENSHOT_WAIT_S=6.0` (delay before each screenshot)

Examples are in `README.md`.

## Strategy Layer Configuration (.env)

- Enable: `STRATEGY_LAYER=1`
- Triggers: `STRATEGY_AMBIG_DELTA=0.05`, `STRATEGY_TRIG_FAILS=1`, `STRATEGY_TRIG_LOW_SV=1`
- Limits: `STRATEGY_MAX_CALLS_PER_SIG=1`, `STRATEGY_MAX_CALLS=3`
- Strict matching (optional): `STRATEGY_MATCH_LANDMARK=1`, `STRATEGY_MATCH_YHIST=1`
- Logs: requests/responses at `out/logs/{provider}_{model}_strategy_{req|resp}_step_{n}.json`; memory at `out/logs/strategies.jsonl`

## Typical Workflows

- Run API server: `uvicorn app:app --reload --host 0.0.0.0 --port 8000`
- Run a flow: `python run_workflow.py --workflow flows/xhs_longform_vision.json --endpoint http://127.0.0.1:8000`
- Generate a flow: `python tools/run_workflow_gen.py --task "..." --provider gemini --model gemini-1.5-flash --out flows/new.json`

## Extending the System

- Add a provider: extend `core/llm_client.py` (`call_llm`, `extract_text_generic`).
- New “vision bias” rules: adjust `POP_VISION_SYSTEM` and/or `build_pop_messages`.
- New actions: implement `act_*` in `core/workflow.py` and wire in `run_actions`. The `instr.*` layer maps to `ext.*`/coordinate primitives and can be extended similarly.
- Authoring/validation: use `tools/wam` to programmatically assemble flows and validate (schema + reachability + var checks).
- New states: add to `flows/*.json` (`autostep` preferred; verify rules for transition).

## Debugging Tips

- Cross‑check `step_{n}.png` vs `overlay_step_{n}.png` to confirm detections.
- Inspect picker requests/responses to understand LLM decisions.
- Check `out/reports/run_report_*.html` for a visual run summary.
- If pointer triggers fail‑safe, confirm parking behavior (now `(24,24)`), or adjust in `core/executor.py`.

## Known Notes

- PoP is optional; when disabled, defaults are applied.
- Legacy id‑only picker is still available for backward compatibility.
- Avoid committing `weights/` and `.env` — keep keys and large binaries local.

## Old Tool + SQS (New Docs)

- One‑click SQS: `make sqs-up` (or `bash scripts/one_click_sqs.sh`).
- Queues are provisioned automatically: `llm.request.fifo`, `llm.invoke.fifo`, `device.demo.hp.fifo` (+ lp/control).
- Runbook: see `docs/old_tool_runbook.md` for end‑to‑end steps (DB restore, Node server.js, Python consumer, WeChat engine, env exports).
