# Minimal Coordinate API (YOLO + LLM, same behavior/logs as main system)

This folder is a portable subset of the project that exposes `/predict` and `/pick` with the same YOLO+LLM behavior and logs as the main system. Copy `minimal_coordinate_api` into any project, set env vars, and run.

## Quick start
```bash
cd minimal_coordinate_api
python -m pip install -r requirements.txt
export YOLO_WEIGHTS=/path/to/weights/model.pt
# Use your existing .env (OLLAMA_BASE_URL, LLM_MODEL=qwen2.5vl, etc.)
source ../.env  # or export env vars manually
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Endpoints
- `POST /predict` — runs YOLO, returns detections and optional overlay (no LLM).
- `POST /pick` — full YOLO+LLM orchestrator (defaults to main system behavior & logs).

## Env vars (key ones)
- `YOLO_WEIGHTS` (e.g., `weights/model.pt`)
- `OPENAI_BASE_URL` (e.g., `http://127.0.0.1:11434/v1` for Ollama)
- `OPENAI_MODEL` / `LLM_MODEL` (e.g., `qwen2.5vl`)
- `OPENAI_API_KEY` (non-empty; Ollama accepts any string)
- `OPENAI_TIMEOUT` (seconds, default 12; bump for slower local models)
- `LLM_IMAGE_TARGET_KB` (default 200), `LLM_IMAGE_LONG_SIDE` (default 1280)
- `MINI_FULL_LOGS` (default `1`):  
  - `1` → `/pick` delegates to the main orchestrator and writes the same `out/runs/...` logs as the full system (recommended for parity).  
  - `0` → use the lightweight internal path (no `out/runs` logs).

## Example: call `/pick`
```bash
curl -X POST http://127.0.0.1:8000/pick \
  -H "Content-Type: application/json" \
  -d '{"goal":"find the search box","image_base64":"data:image/png;base64,<b64>","return_image":false}'
```
Response matches main system’s `UnifiedResponse`:
- `data.decision.point_in_capture` / `bbox_in_capture` → click point/bbox
- `data.telemetry` → stage timings
- LLM choice (e.g., `click_id: "7"`) is also logged under `out/runs/...` when `MINI_FULL_LOGS=1`.

## Notes
- Uses the same image optimization/compression logic as the main system.
- With `MINI_FULL_LOGS=1`, logs and behavior (LLM choice, coordinates) mirror the main `/v1/pick`.  
- With `MINI_FULL_LOGS=0`, you get a lighter path (no `out/runs` logs).
