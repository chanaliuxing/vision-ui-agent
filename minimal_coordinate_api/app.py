"""
Minimal FastAPI YOLO service that returns bounding boxes and click coordinates.
Drop this folder into any project, point YOLO_WEIGHTS to your model, and run uvicorn.
"""

import base64
import io
import os
import time
import tempfile
import uuid
from typing import List, Optional, Tuple

import numpy as np
from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from PIL import Image
from ultralytics import YOLO
from openai import OpenAI
from dotenv import load_dotenv

# Local copies of compression/optimization logic
from core.image_optimizer import LLMImageOptimizer
from core.image_compress_coords import compress_for_vlm

# Optional cv2 overlay; keep import local to avoid load cost when unused.
import cv2

# Import full system for parity on /pick (orchestrator, schemas, etc.)
import schemas
import app as full_app  # main project FastAPI app with orchestrator routes

# Load .env if present (helps when copying into another project)
load_dotenv()

# Configuration with sane defaults; override via env.
DEFAULT_WEIGHTS = os.getenv("YOLO_WEIGHTS", os.path.join(os.path.dirname(__file__), "weights", "model.pt"))
DEFAULT_CONF = float(os.getenv("YOLO_CONF", "0.25"))
DEFAULT_IOU = float(os.getenv("YOLO_IOU", "0.45"))
DEFAULT_IMGSZ = int(os.getenv("YOLO_IMGSZ", "1280"))

# LLM configuration: prefer explicit OpenAI_* vars; fall back to Ollama/LLM_MODEL hints
OPENAI_MODEL = os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or "gpt-4o-mini"
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
if not OPENAI_BASE_URL:
    ollama_base = os.getenv("OLLAMA_BASE_URL")
    if ollama_base:
        OPENAI_BASE_URL = ollama_base.rstrip("/") + "/v1"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OLLAMA_API_KEY") or "ollama"
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "12"))
LLM_IMAGE_TARGET_KB = int(os.getenv("LLM_IMAGE_TARGET_KB", "200"))
LLM_IMAGE_LONG_SIDE = int(os.getenv("LLM_IMAGE_LONG_SIDE", "1280"))

# Prefer Apple Metal if available; otherwise CPU.
DEVICE = "mps"
try:
    import torch

    if not torch.backends.mps.is_available():
        DEVICE = "cpu"
except Exception:
    DEVICE = "cpu"


class Detection(BaseModel):
    label: str
    conf: float
    bbox_xyxy: List[float]
    bbox_xyxy_norm: List[float]
    click: dict


class PredictResponse(BaseModel):
    model: str
    device: str
    time_ms: float
    detections: List[Detection]
    image_base64: Optional[str] = None


class PredictRequest(BaseModel):
    image_base64: Optional[str] = None
    return_image: Optional[bool] = False


class PickRequest(BaseModel):
    goal: str
    image_base64: Optional[str] = None
    return_image: Optional[bool] = False


class PickChoice(BaseModel):
    id: str
    label: str
    conf: float
    bbox_xyxy: List[float]
    bbox_xyxy_norm: List[float]
    click: dict


class PickResponse(BaseModel):
    ok: bool
    choice: PickChoice
    llm_used: bool
    raw_llm: Optional[dict] = None
    time_ms: float
    image_base64: Optional[str] = None
    compress_note: Optional[str] = None


app = FastAPI(title="Minimal Coordinate API", version="1.0")

# Load model once at startup.
if not os.path.isfile(DEFAULT_WEIGHTS):
    raise RuntimeError(
        f"YOLO weights not found at {DEFAULT_WEIGHTS}. "
        "Set YOLO_WEIGHTS env var or place your model at that path."
    )

model = YOLO(DEFAULT_WEIGHTS)


@app.get("/health")
def health():
    return {"status": "ok", "weights": DEFAULT_WEIGHTS, "device": DEVICE}


def _read_image_bytes(file: UploadFile = None, image_base64: Optional[str] = None) -> bytes:
    if file is not None:
        return file.file.read()
    if image_base64:
        # Strip data URI header if present.
        if image_base64.startswith("data:image"):
            image_base64 = image_base64.split(",", 1)[1]
        return base64.b64decode(image_base64)
    raise HTTPException(status_code=400, detail="No image provided. Upload a file or pass image_base64.")


def _bytes_to_rgb_array(image_bytes: bytes) -> np.ndarray:
    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return np.array(pil_image)


def _encode_png(image_rgb: np.ndarray) -> str:
    success, buf = cv2.imencode(".png", cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR))
    if not success:
        return ""
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode("utf-8")


def _optimize_and_compress(image_rgb: np.ndarray) -> Tuple[str, dict]:
    """
    Run token-reduction optimization then compress to WebP for LLM use.
    Returns (data_url_base64, stats_dict).
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        Image.fromarray(image_rgb).save(tmp.name)
        src_path = tmp.name

    try:
        optimizer = LLMImageOptimizer()
        optimized_path, stats = optimizer.optimize_for_llm(src_path)

        with tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as compressed_tmp:
            compress_for_vlm(
                optimized_path,
                compressed_tmp.name,
                long_side=LLM_IMAGE_LONG_SIDE,
                target_kb=LLM_IMAGE_TARGET_KB,
                fmt="WEBP",
                quality=85,
                write_sidecar_json=False,
            )
            with open(compressed_tmp.name, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
            return "data:image/webp;base64," + img_b64, stats
    finally:
        try:
            os.unlink(src_path)
        except:
            pass


def _run_yolo(image_rgb: np.ndarray, return_overlay: bool) -> PredictResponse:
    h, w, _ = image_rgb.shape
    t0 = time.time()

    results = model.predict(
        source=image_rgb,
        conf=DEFAULT_CONF,
        iou=DEFAULT_IOU,
        imgsz=DEFAULT_IMGSZ,
        device=DEVICE,
        verbose=False,
    )
    elapsed_ms = (time.time() - t0) * 1000.0

    detections: List[Detection] = []
    overlay = image_rgb.copy()
    names = model.model.names if hasattr(model, "model") else {}

    for idx, box in enumerate(results[0].boxes):
        xyxy = box.xyxy[0].tolist()
        x1, y1, x2, y2 = [float(v) for v in xyxy]
        cls_id = int(box.cls[0])
        label = names.get(cls_id, str(cls_id))
        conf = float(box.conf[0])

        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2

        det = Detection(
            label=label,
            conf=conf,
            bbox_xyxy=[x1, y1, x2, y2],
            bbox_xyxy_norm=[x1 / w, y1 / h, x2 / w, y2 / h],
            click={"x": cx, "y": cy, "x_norm": cx / w, "y_norm": cy / h},
        )
        detections.append(det)

        if return_overlay:
            color = (0, 255, 0)
            cv2.rectangle(overlay, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            cv2.putText(
                overlay,
                f"{idx+1}:{label} {conf:.2f}",
                (int(x1), int(y1) - 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                1,
                cv2.LINE_AA,
            )

    overlay_b64 = _encode_png(overlay) if return_overlay else None

    return PredictResponse(
        model="yolo",
        device=DEVICE,
        time_ms=elapsed_ms,
        detections=detections,
        image_base64=overlay_b64,
    )


def _choose_with_llm(goal: str, detections: List[Detection]) -> Tuple[str, dict]:
    """
    Ask an LLM to pick one detection id. Returns (picked_id, raw_response).
    Falls back to top confidence if no key or errors.
    """
    if not OPENAI_API_KEY:
        return "1", {"fallback": "no_api_key"}

    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL, timeout=OPENAI_TIMEOUT)
    det_lines = [
        f"id={i+1}, label={d.label}, conf={d.conf:.2f}, center=({d.click['x']:.1f},{d.click['y']:.1f})"
        for i, d in enumerate(detections)
    ]
    prompt = (
        "You are selecting one UI element by id from detections. "
        "Return only the id number. If unsure, choose the most relevant to the goal.\n"
        f"Goal: {goal}\n"
        "Detections:\n" + "\n".join(det_lines)
    )
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Return only the id number (e.g., 1)."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=4,
        )
        content = resp.choices[0].message.content.strip()
        # Extract first integer token
        picked = None
        for token in content.replace(",", " ").split():
            if token.isdigit():
                picked = token
                break
        if picked is None:
            picked = "1"
        return picked, resp.model_dump()
    except Exception as exc:
        return "1", {"fallback": f"llm_error: {exc}"}


def _pick_response(goal: str, image_rgb: np.ndarray, return_overlay: bool) -> PickResponse:
    # Optimize/compress input for LLM token reduction (does not alter YOLO input)
    compress_note = None
    try:
        _, comp_stats = _optimize_and_compress(image_rgb)
        compress_note = f"optimized tokens: {comp_stats.get('original_tokens')} -> {comp_stats.get('final_tokens')}"
    except Exception as e:
        compress_note = f"compression_failed: {e}"

    yolo_resp = _run_yolo(image_rgb, return_overlay=return_overlay)
    if not yolo_resp.detections:
        raise HTTPException(status_code=404, detail="No detections found")

    # Assign sequential IDs for LLM/user readability
    detections = yolo_resp.detections
    llm_used = bool(OPENAI_API_KEY)
    picked_id_str, raw_llm = _choose_with_llm(goal, detections)
    try:
        picked_idx = max(0, min(len(detections) - 1, int(picked_id_str) - 1))
    except Exception:
        picked_idx = 0

    choice_det = detections[picked_idx]
    # Normalize to string id aligned with presented order
    choice = PickChoice(
        id=str(picked_idx + 1),
        label=choice_det.label,
        conf=choice_det.conf,
        bbox_xyxy=choice_det.bbox_xyxy,
        bbox_xyxy_norm=choice_det.bbox_xyxy_norm,
        click=choice_det.click,
    )

    return PickResponse(
        ok=True,
        choice=choice,
        llm_used=llm_used,
        raw_llm=raw_llm,
        time_ms=yolo_resp.time_ms,
        image_base64=yolo_resp.image_base64 if return_overlay else None,
        compress_note=compress_note,
    )


@app.post("/predict", response_model=PredictResponse)
async def predict(
    file: UploadFile = File(None),
    body: PredictRequest = Body(None),
):
    """Run detection and return coordinates."""
    image_base64 = None
    return_image = False

    if body is not None:
        image_base64 = body.image_base64
        return_image = bool(body.return_image)

    image_bytes = _read_image_bytes(file, image_base64)
    image_rgb = _bytes_to_rgb_array(image_bytes)

    try:
        return _run_yolo(image_rgb, return_overlay=return_image)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"YOLO inference failed: {exc}") from exc


@app.post("/pick", response_model=PickResponse)
async def pick(
    body: PickRequest = Body(...),
):
    """
    YOLO + LLM picker.
    - 默认：委托给主系统 orchestrator（写同样的 out/runs 日志）。
    - 若设置 MINI_FULL_LOGS=0，则使用轻量内置路径（无 out/runs 日志）。
    """
    if not body.image_base64:
        raise HTTPException(status_code=400, detail="image_base64 is required")

    use_full = os.getenv("MINI_FULL_LOGS", "1") != "0"

    if use_full:
        # Build full PickRequest for main app
        image_spec = schemas.ImageSpec(base64=body.image_base64, format="png")
        context = schemas.ContextSpec(
            goal=body.goal,
            intent=body.goal,
            vars={},
            history=[],
            allow_rewrite=False,
        )
        opts = schemas.OptionsSpec(
            timeout_ms=60000,
            max_candidates=64,
            yolo=schemas.YoloOptionsSpec(
                conf=DEFAULT_CONF,
                iou=DEFAULT_IOU,
            ),
            llm_provider=os.getenv("LLM_PROVIDER", "ollama"),
            llm_method=os.getenv("LLM_METHOD", "direct"),
            llm_timeout_ms=int(float(os.getenv("OPENAI_TIMEOUT", "12")) * 1000),
            llm_topk_crops=0,
            return_overlay=bool(body.return_image),
        )
        req = schemas.PickRequest(
            image=image_spec,
            capture=None,  # main app will infer if missing
            context=context,
            anchors_known=[],
            options=opts,
            idempotency_key=f"lite-{uuid.uuid4().hex[:8]}",
        )

        try:
            return await full_app.v1_pick(req)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Pick failed: {exc}") from exc

    # Fallback: lightweight path (no orchestrator logs)
    image_bytes = _read_image_bytes(None, body.image_base64)
    image_rgb = _bytes_to_rgb_array(image_bytes)
    try:
        return _pick_response(body.goal, image_rgb, return_overlay=bool(body.return_image))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pick failed: {exc}") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
