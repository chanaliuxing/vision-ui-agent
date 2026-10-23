# Minimal Coordinate API

A tiny FastAPI service that runs a YOLO model and (optionally) a lightweight LLM picker to choose one detection and return its coordinates. Copy this folder into any project, drop your YOLO weights into `weights/model.pt`, install requirements, and start the server. `/v1/pick` only; other heavy routes removed.

## Quick start

```bash
cd minimal_coordinate_api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# point to your weights (defaults to weights/model.pt relative to this folder)
export YOLO_WEIGHTS=weights/model.pt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Or run the helper script (creates a venv if missing):

```bash
./start.sh
```

## Health check

```bash
curl -s http://127.0.0.1:8000/health
```

## Predict (upload a file)

```bash
curl -X POST http://127.0.0.1:8000/predict \
  -F image=@sample.png
```

## Predict (base64 JSON)

```bash
curl -X POST http://127.0.0.1:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"image_base64":"<base64 string>","return_image":false}'
```

## Response shape

```json
{
  "model": "yolo",
  "device": "cpu",
  "time_ms": 42.5,
  "detections": [
    {
      "label": "object",
      "conf": 0.87,
      "bbox_xyxy": [100.0, 120.0, 200.0, 220.0],
      "bbox_xyxy_norm": [0.1, 0.12, 0.2, 0.22],
      "click": {"x": 150.0, "y": 170.0, "x_norm": 0.15, "y_norm": 0.17}
    }
  ],
  "image_base64": "data:image/png;base64,... (only when return_image=true)"
}
```

## LLM pick (optional, chooses one detection id)

- Set `OPENAI_API_KEY` (and optional `OPENAI_BASE_URL`, `OPENAI_MODEL`, defaults to `gpt-4o-mini`).
- Send a goal and image; returns the picked detection and coordinates.

```bash
curl -X POST http://127.0.0.1:8000/pick \
  -H "Content-Type: application/json" \
  -d '{"goal":"click the search icon","image_base64":"<base64>"}'
```

Response contains `choice.id` (e.g., `"7"`) and `choice.click` with pixel + normalized coordinates. If no LLM key is set, it falls back to the highest-confidence box.

## Configuration (env vars)

- `YOLO_WEIGHTS` (default `weights/model.pt`)
- `YOLO_CONF` (default `0.25`)
- `YOLO_IOU` (default `0.45`)
- `YOLO_IMGSZ` (default `1280`)
- `OPENAI_API_KEY` (optional; if set, `/pick` will call the model)
- `OPENAI_BASE_URL` (optional OpenAI-compatible endpoint; if missing but `OLLAMA_BASE_URL` is set, uses `OLLAMA_BASE_URL/v1`)
- `OPENAI_MODEL` (default `gpt-4o-mini`; falls back to `LLM_MODEL` if set)
- `OLLAMA_BASE_URL` (optional shortcut for local Ollama)
- `OPENAI_TIMEOUT` (seconds, default 12)
- `LLM_IMAGE_TARGET_KB` (default 200)
- `LLM_IMAGE_LONG_SIDE` (default 1280)
- `MINI_FULL_LOGS` (default `1`): when `1`, `/pick` delegates to the main orchestrator and writes the same `out/runs/...` logs; set `0` to use the lightweight path without those logs.

Copy `minimal_coordinate_api` anywhere, set `YOLO_WEIGHTS` to your model path, and you are ready to call `/predict` for coordinates.
