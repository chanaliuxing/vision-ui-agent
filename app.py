# app.py
import io
import os
import time
import base64
import subprocess
import json
import uuid
import tempfile
import threading
import traceback
import hashlib
import asyncio
from typing import Optional, List, Tuple, Dict, Any, Union
import logging
from contextvars import ContextVar
from dotenv import load_dotenv

# Load .env file at the very beginning
load_dotenv()

import numpy as np
from fastapi import FastAPI, File, UploadFile, Form, Query, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ultralytics import YOLO
from PIL import Image
from vision_utils import to_ndarray, crop_by_norm, calc_phash64, calc_ssim64, calc_red_ratio, calc_phash_delta
from yolo.logging_setup import setup_json_logging, get_logger

# Optional: URL input support
try:
    import requests
    HAS_REQUESTS = True
except Exception:
    HAS_REQUESTS = False

# ---------- Config ----------
# Hardcode YOLO weights to ensure consistent model usage (ignore env)
DEFAULT_WEIGHTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weights", "model.pt")
WEIGHTS = os.getenv("YOLO_WEIGHTS", DEFAULT_WEIGHTS)
DEFAULT_CONF  = float(os.getenv("YOLO_CONF",  "0.25"))
DEFAULT_IOU   = float(os.getenv("YOLO_IOU",   "0.45"))
DEFAULT_IMGSZ = int(os.getenv("YOLO_IMGSZ",  "1280"))

# Compression settings for LLM vision token reduction
LLM_IMAGE_TARGET_KB = int(os.getenv("LLM_IMAGE_TARGET_KB", "10"))  # Aggressive compression for 70% token reduction

# YOLO execution mode configuration
YOLO_MODE = os.getenv("YOLO_MODE", "local")  # local|remote|hybrid
YOLO_REMOTE_URL = os.getenv("YOLO_REMOTE_URL", "")
YOLO_TIMEOUT = int(os.getenv("YOLO_TIMEOUT", "30"))  # Timeout for remote requests

# Prefer Apple Metal (MPS) on M1 if available
device = "mps"
try:
    import torch
    if not torch.backends.mps.is_available():
        device = "cpu"
except Exception:
    device = "cpu"

# Load once - suppress Ultralytics settings warnings
import warnings
warnings.filterwarnings("ignore", message=".*Ultralytics settings reset.*")
setup_json_logging()
# Initialize loggers early
logger = logging.getLogger(__name__)
jsonlog = get_logger()


def _enable_timestamp_for_uvicorn_access_logs() -> None:
    """
    Ensure uvicorn access/error logs include timestamps.
    This mutates existing uvicorn logger handlers when running via `uvicorn app:app`.
    """
    try:
        fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
        datefmt = "%Y-%m-%d %H:%M:%S"
        for lname in ("uvicorn.access", "uvicorn.error", "uvicorn"):
            lg = logging.getLogger(lname)
            if not lg:
                continue
            for h in (lg.handlers or []):
                try:
                    h.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
                except Exception:
                    pass
    except Exception:
        pass


_enable_timestamp_for_uvicorn_access_logs()

model = YOLO(WEIGHTS)
try:
    import hashlib
    with open(WEIGHTS, 'rb') as _f:
        _sha1 = hashlib.sha1(_f.read()).hexdigest()[:12]
    logger.info(f"YOLO weights: {WEIGHTS} (sha1:{_sha1})")
except Exception:
    logger.info(f"YOLO weights: {WEIGHTS}")

app = FastAPI(title="YOLO FastAPI Server", version="2.2")
# Full capture handled by existing out/ directory system
# Legacy yolo.capture system removed - all logging now goes to out/

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ---------- API Observability ----------
API_OBS_ENABLED = os.getenv("API_OBS_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
API_OBS_DIR = os.getenv("API_OBS_DIR", "out/api_observability")
API_OBS_MAX_BODY = int(os.getenv("API_OBS_MAX_BODY", "40960"))  # 40KB
API_OBS_MAX_FIELD = int(os.getenv("API_OBS_MAX_FIELD", "2048"))
API_OBS_REDACT_KEYS = {"authorization", "api_key", "apikey", "token", "password", "secret", "access_token", "refresh_token"}
_OBS_LOCK = threading.Lock()
_OBS_ID_CVAR: ContextVar[str] = ContextVar("obs_id", default="")


def _obs_now_ms() -> int:
    return int(time.time() * 1000)


def _obs_clip_text(v: str, max_len: int = API_OBS_MAX_FIELD) -> str:
    if not isinstance(v, str):
        return str(v)
    if len(v) <= max_len:
        return v
    return v[:max_len] + f"...<truncated:{len(v)-max_len}>"


def _obs_safe(obj: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "<max_depth>"
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            key = str(k)
            if key.lower() in API_OBS_REDACT_KEYS:
                out[key] = "<redacted>"
            else:
                out[key] = _obs_safe(v, depth + 1)
        return out
    if isinstance(obj, list):
        if len(obj) > 100:
            return [_obs_safe(x, depth + 1) for x in obj[:100]] + ["<truncated_list>"]
        return [_obs_safe(x, depth + 1) for x in obj]
    if isinstance(obj, str):
        return _obs_clip_text(obj)
    if isinstance(obj, (int, float, bool)) or obj is None:
        return obj
    return _obs_clip_text(str(obj))


def _obs_write(record: Dict[str, Any]) -> None:
    if not API_OBS_ENABLED:
        return
    try:
        os.makedirs(API_OBS_DIR, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        path_latest = os.path.join(API_OBS_DIR, "events.latest.jsonl")
        day = time.strftime("%Y%m%d")
        path_day = os.path.join(API_OBS_DIR, f"events.{day}.jsonl")
        with _OBS_LOCK:
            with open(path_latest, "a", encoding="utf-8") as f:
                f.write(line)
            with open(path_day, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception as e:
        logger.warning(f"api observability write failed: {e}")


def _obs_event(event: str, request: Optional[Request] = None, **payload: Any) -> None:
    obs_id = ""
    if request is not None:
        try:
            obs_id = str(getattr(request.state, "obs_id", "") or "")
        except Exception:
            obs_id = ""
    if not obs_id:
        obs_id = _OBS_ID_CVAR.get("")
    record = {
        "ts_ms": _obs_now_ms(),
        "event": event,
        "obs_id": obs_id,
        "payload": _obs_safe(payload),
    }
    _obs_write(record)


async def _obs_capture_request_payload(request: Request) -> Dict[str, Any]:
    content_type = (request.headers.get("content-type") or "").lower()
    content_len = int(request.headers.get("content-length") or "0")
    base = {"content_type": content_type, "content_length": content_len}
    if "application/json" in content_type and content_len <= API_OBS_MAX_BODY:
        body = await request.body()
        if not body:
            return base
        text = body.decode("utf-8", errors="replace")
        try:
            base["json"] = _obs_safe(json.loads(text))
        except Exception:
            base["text"] = _obs_clip_text(text, API_OBS_MAX_BODY)
        return base
    if "application/x-www-form-urlencoded" in content_type and content_len <= API_OBS_MAX_BODY:
        body = await request.body()
        base["form_raw"] = _obs_clip_text(body.decode("utf-8", errors="replace"), API_OBS_MAX_BODY)
        return base
    if "multipart/form-data" in content_type:
        base["multipart"] = {"captured": False, "reason": "stream_payload_skipped"}
        return base
    base["body"] = {"captured": False, "reason": "unsupported_or_large"}
    return base


def _obs_capture_response_payload(response: Any) -> Dict[str, Any]:
    content_type = (response.headers.get("content-type") or "").lower() if hasattr(response, "headers") else ""
    out = {
        "status_code": int(getattr(response, "status_code", 0)),
        "content_type": content_type,
        "content_length": response.headers.get("content-length") if hasattr(response, "headers") else None,
    }
    body = getattr(response, "body", None)
    if not isinstance(body, (bytes, bytearray)):
        out["body"] = {"captured": False, "reason": "streaming_or_unavailable"}
        return out
    if len(body) > API_OBS_MAX_BODY:
        out["body"] = {"captured": False, "reason": "too_large", "size": len(body)}
        return out
    if "application/json" in content_type:
        try:
            out["json"] = _obs_safe(json.loads(body.decode("utf-8", errors="replace")))
        except Exception:
            out["text"] = _obs_clip_text(body.decode("utf-8", errors="replace"), API_OBS_MAX_BODY)
        return out
    if "text/" in content_type:
        out["text"] = _obs_clip_text(body.decode("utf-8", errors="replace"), API_OBS_MAX_BODY)
        return out
    out["body"] = {"captured": False, "reason": "non_text_binary", "size": len(body)}
    return out


async def _obs_drain_response_body(response: Any) -> Tuple[bytes, bytes, bool]:
    """
    Drain response body from body_iterator and return bytes.
    Returns (body_bytes, truncated).
    """
    full_chunks: List[bytes] = []
    preview_chunks: List[bytes] = []
    total = 0
    preview_size = 0
    truncated = False
    try:
        async for chunk in response.body_iterator:
            if not isinstance(chunk, (bytes, bytearray)):
                chunk = str(chunk).encode("utf-8", errors="replace")
            b = bytes(chunk)
            full_chunks.append(b)
            total += len(b)
            if preview_size < API_OBS_MAX_BODY:
                remaining = API_OBS_MAX_BODY - preview_size
                preview_piece = b[:remaining]
                preview_chunks.append(preview_piece)
                preview_size += len(preview_piece)
            else:
                truncated = True
        if total > API_OBS_MAX_BODY:
            truncated = True
        return b"".join(full_chunks), b"".join(preview_chunks), truncated
    except Exception:
        return b"", b"", True


@app.middleware("http")
async def api_observability_middleware(request: Request, call_next):
    if not API_OBS_ENABLED:
        return await call_next(request)
    obs_id = str(uuid.uuid4())
    request.state.obs_id = obs_id
    token = _OBS_ID_CVAR.set(obs_id)
    start = time.perf_counter()
    try:
        req_payload = await _obs_capture_request_payload(request)
    except Exception as e:
        req_payload = {"capture_error": str(e)}
    # Replay request body for downstream handlers after observability capture.
    # Without this, downstream body parsing can block or fail on some ASGI paths.
    try:
        cached_body = await request.body()
        replay_done = False

        async def _replay_receive():
            nonlocal replay_done
            if not replay_done:
                replay_done = True
                return {"type": "http.request", "body": cached_body, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        request._receive = _replay_receive  # type: ignore[attr-defined]
    except Exception:
        pass
    _obs_write({
        "ts_ms": _obs_now_ms(),
        "event": "api.request.received",
        "obs_id": obs_id,
        "method": request.method,
        "path": request.url.path,
        "query": _obs_safe(dict(request.query_params)),
        "client": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "request": _obs_safe(req_payload),
    })
    try:
        response = await call_next(request)
    except Exception as e:
        duration_ms = round((time.perf_counter() - start) * 1000.0, 2)
        _obs_write({
            "ts_ms": _obs_now_ms(),
            "event": "api.response.error",
            "obs_id": obs_id,
            "method": request.method,
            "path": request.url.path,
            "duration_ms": duration_ms,
            "error": _obs_clip_text(str(e), 6000),
            "traceback": _obs_clip_text(traceback.format_exc(), 12000),
        })
        _obs_write({
            "ts_ms": _obs_now_ms(),
            "event": "api.response.sent",
            "obs_id": obs_id,
            "method": request.method,
            "path": request.url.path,
            "duration_ms": duration_ms,
            "status_code": 500,
            "response": {
                "ok": False,
                "code": "UNHANDLED_EXCEPTION",
                "error": _obs_clip_text(str(e), 3000),
            },
            "response_body_truncated": False,
            "generated_in_middleware": True,
        })
        _OBS_ID_CVAR.reset(token)
        raise
    body_full, body_for_log, body_truncated = await _obs_drain_response_body(response)
    rebuilt = Response(
        content=body_full,
        status_code=int(getattr(response, "status_code", 200)),
        headers=dict(getattr(response, "headers", {})),
        media_type=getattr(response, "media_type", None),
        background=getattr(response, "background", None),
    )
    if body_truncated:
        rebuilt.headers["X-Obs-Body-Truncated"] = "1"
    duration_ms = round((time.perf_counter() - start) * 1000.0, 2)
    rebuilt.headers["X-Obs-Id"] = obs_id
    # Best effort attach body for payload parser.
    try:
        setattr(rebuilt, "body", body_for_log)
    except Exception:
        pass
    _obs_write({
        "ts_ms": _obs_now_ms(),
        "event": "api.response.sent",
        "obs_id": obs_id,
        "method": request.method,
        "path": request.url.path,
        "duration_ms": duration_ms,
        "response": _obs_safe(_obs_capture_response_payload(rebuilt)),
        "response_body_truncated": body_truncated,
    })
    _OBS_ID_CVAR.reset(token)
    return rebuilt

# In-memory idempotency cache for planner_report
_AUTOSTEP_REPORT_CACHE: Dict[str, Dict[str, Any]] = {}
_AUTOSTEP_REPORT_CACHE_LOCK = threading.Lock()
AUTOSTEP_MAX_CONCURRENCY = int(os.getenv("AUTOSTEP_MAX_CONCURRENCY", "8"))
AUTOSTEP_QUEUE_TIMEOUT_MS = int(os.getenv("AUTOSTEP_QUEUE_TIMEOUT_MS", "5000"))
AUTOSTEP_MODEL_TIMEOUT_SEC = float(os.getenv("AUTOSTEP_MODEL_TIMEOUT_SEC", "600"))
_AUTOSTEP_SEM = asyncio.Semaphore(max(1, AUTOSTEP_MAX_CONCURRENCY))

# Optional: include workflow generation router if available
try:
    from app_workflow import router as workflow_router

    app.include_router(workflow_router)
except Exception:
    pass

# ---------- Image Compression Helper ----------
def _encode_image_file_for_llm(file_path: str) -> str:
    """
    Force LLM to use compressed image files only.

    This function ensures the LLM pipeline gets compressed images,
    preventing the token leak where LLM receives uncompressed images.
    """
    logger.info(f"🔧 _encode_image_file_for_llm called with: {file_path}")
    try:
        from core.image_compress_coords import compress_for_vlm
        from PIL import Image
        import tempfile

        # Always compress for LLM to reduce tokens
        with tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as tmp_file:
            logger.info(f"📦 Compressing for LLM: {file_path} → {tmp_file.name}")

            # Compress with aggressive target for token reduction
            transform = compress_for_vlm(   # ← returns a Transform, not a tuple
                file_path,
                tmp_file.name,
                target_kb=LLM_IMAGE_TARGET_KB,
                quality=85
            )

            # Encode compressed file
            with open(tmp_file.name, 'rb') as f:
                img_data = f.read()

            # Calculate token estimation for GPT-4o-mini vision
            try:
                import os
                from PIL import Image

                orig_sz = os.path.getsize(file_path)
                comp_sz = len(img_data)
                ratio = (1.0 - (comp_sz / max(1, orig_sz))) * 100.0

                # Get compressed image dimensions
                with Image.open(tmp_file.name) as img:
                    w, h = img.size
                    # GPT-4o vision: 765 tokens per 1024x1024 tile
                    tiles_w = (w + 1023) // 1024
                    tiles_h = (h + 1023) // 1024
                    estimated_tokens = tiles_w * tiles_h * 765

                logger.info(f"📊 LLM COMPRESSION METRICS:")
                logger.info(f"   File size: {orig_sz} → {comp_sz} bytes ({ratio:.1f}% reduction)")
                logger.info(f"   Dimensions: {w}x{h}")
                logger.info(f"   Estimated tokens: {estimated_tokens} (tiles: {tiles_w}x{tiles_h})")
                logger.info(f"   Base64 size: {len(base64.b64encode(img_data).decode('utf-8'))} chars")

            except Exception as e:
                logger.warning(f"⚠️  Failed to calculate metrics: {e}")

            # Clean up temp file
            import os
            os.unlink(tmp_file.name)

            # Return base64 encoded compressed image
            b64_result = base64.b64encode(img_data).decode('utf-8')
            logger.info(f"✅ Returning compressed base64 ({len(b64_result)} chars)")
            return b64_result

    except Exception as e:
        logger.warning(f"Image compression failed: {e}, falling back to original")
        # Fallback to original file if compression fails
        with open(file_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')

# ---------- Schemas ----------
class PredictResponse(BaseModel):
    model: str
    device: str
    time_ms: float
    detections: List[dict]
    image_base64: Optional[str] = None  # only when requested

class DetRequest(BaseModel):
    image_b64: Optional[str] = None
    image_url: Optional[str] = None
    classes: Optional[List[str]] = None
    top_k: int = 5
    min_conf: float = 0.6
    llm_picker: bool = False
    prompt: Optional[str] = None
    return_image: bool = False
    roi_hint: Optional[List[float]] = None  # [x,y,w,h] normalized

class Det(BaseModel):
    label: str
    conf: float
    bbox: List[float]  # [x,y,w,h] in pixels

class UnifiedResponse(BaseModel):
    ok: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, str]] = None

# ---------- Helpers ----------
def _np_to_base64_png(img_np: np.ndarray) -> str:
    import cv2
    ok, buf = cv2.imencode(".png", img_np)
    if not ok:
        return ""
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode("utf-8")

def _read_image_bytes(file: UploadFile = None, image_base64: str = None, image_url: str = None) -> bytes:
    if file is not None:
        return file.file.read()
    if image_base64:
        return base64.b64decode(image_base64)
    if image_url:
        if not HAS_REQUESTS:
            raise ValueError("requests is not installed; cannot fetch image_url")
        r = requests.get(image_url, timeout=10)
        r.raise_for_status()
        return r.content
    raise ValueError("No image provided")

def _pil_to_bgr(pil_im) -> np.ndarray:
    import cv2
    rgb = np.array(pil_im)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

def _sort_indices_tl(xyxy: List[List[float]]) -> List[int]:
    """Top->bottom, then left->right（阅读顺序）"""
    return sorted(range(len(xyxy)), key=lambda i: (xyxy[i][1], xyxy[i][0]))

def _font_scale_from_px(desired_px: int, thickness: int = 1) -> float:
    """把“期望像素高度”转换为 OpenCV 的 fontScale。"""
    import cv2
    font = cv2.FONT_HERSHEY_SIMPLEX
    lo, hi = 0.05, 5.0
    for _ in range(20):
        mid = (lo + hi) / 2.0
        (_, h), _ = cv2.getTextSize("Ag", font, mid, thickness)
        if h > desired_px:
            hi = mid
        else:
            lo = mid
    return lo

def _clip_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))

def load_image_from_any(image_b64: Optional[str] = None, upload: Optional[UploadFile] = None, image_url: Optional[str] = None) -> Image.Image:
    """
    Load image from any source: base64, upload file, or URL.

    Args:
        image_b64: Base64 encoded image string
        upload: FastAPI UploadFile object
        image_url: URL to image

    Returns:
        PIL.Image: Loaded image in RGB format

    Raises:
        ValueError: If no image source provided or loading fails
    """
    if upload is not None:
        buf = upload.file.read()
        return Image.open(io.BytesIO(buf)).convert("RGB")

    if image_b64:
        # Remove data URL prefix if present
        if image_b64.startswith('data:image'):
            image_b64 = image_b64.split(',', 1)[1]
        buf = base64.b64decode(image_b64)
        return Image.open(io.BytesIO(buf)).convert("RGB")

    if image_url:
        if not HAS_REQUESTS:
            raise ValueError("requests is not installed; cannot fetch image_url")
        r = requests.get(image_url, timeout=10)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")

    raise ValueError("No image provided")

def run_yolo_local(img_array: np.ndarray, conf: float = DEFAULT_CONF, iou: float = DEFAULT_IOU,
                   imgsz: int = DEFAULT_IMGSZ, max_det: int = 300) -> List[Det]:
    """
    Run YOLO inference locally on numpy array.
    """
    import PIL.Image as Image
    import cv2

    # Convert BGR to RGB for PIL
    if len(img_array.shape) == 3 and img_array.shape[2] == 3:
        rgb_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
    else:
        rgb_array = img_array

    pil_img = Image.fromarray(rgb_array)

    # Run inference
    results = model.predict(
        pil_img,
        conf=conf,
        iou=iou,
        imgsz=imgsz,
        max_det=max_det,
        device=device,
        verbose=False
    )[0]

    detections = []
    names = results.names if hasattr(results, "names") and results.names else model.names

    if results.boxes is not None and len(results.boxes) > 0:
        xyxy = results.boxes.xyxy.cpu().tolist()
        confs = [float(x) for x in results.boxes.conf.cpu().tolist()]
        clss = [int(x) for x in results.boxes.cls.cpu().tolist()]

        for (x1, y1, x2, y2), conf_val, cls_idx in zip(xyxy, confs, clss):
            class_name = names.get(cls_idx, str(cls_idx)) if isinstance(names, dict) else str(cls_idx)

            detection = Det(
                label=class_name,
                conf=conf_val,
                bbox=[x1, y1, x2-x1, y2-y1]  # Convert to x,y,w,h format
            )
            detections.append(detection)

    return detections


def run_yolo_remote(img_array: np.ndarray, conf: float = DEFAULT_CONF, iou: float = DEFAULT_IOU,
                    imgsz: int = DEFAULT_IMGSZ, max_det: int = 300) -> List[Det]:
    """
    Run YOLO inference on remote cloud server.

    Args:
        img_array: Input image as numpy array (BGR format)
        conf: Confidence threshold
        iou: IOU threshold for NMS
        imgsz: Image size for inference
        max_det: Maximum detections

    Returns:
        List[Det]: List of detection objects with label, conf, bbox

    Raises:
        Exception: If remote inference fails
    """
    import cv2
    import requests

    if not YOLO_REMOTE_URL:
        raise Exception("YOLO_REMOTE_URL not configured")

    # Convert numpy array to base64
    _, buffer = cv2.imencode('.png', img_array)
    img_b64 = base64.b64encode(buffer).decode()

    # Prepare request payload
    payload = {
        "image_b64": img_b64,
        "conf": conf,
        "iou": iou,
        "imgsz": imgsz,
        "max_det": max_det
    }

    # Make request to cloud YOLO service
    response = requests.post(
        YOLO_REMOTE_URL,
        json=payload,
        timeout=YOLO_TIMEOUT,
        headers={"Content-Type": "application/json"}
    )

    if response.status_code != 200:
        raise Exception(f"Remote YOLO failed with status {response.status_code}: {response.text}")

    result = response.json()

    # Handle different response formats
    if "detections" in result:
        detection_data = result["detections"]
    elif "data" in result and "detections" in result["data"]:
        detection_data = result["data"]["detections"]
    else:
        detection_data = result

    # Convert response to Det objects
    detections = []
    for det_data in detection_data:
        detection = Det(
            label=det_data.get("label", det_data.get("class_name", "unknown")),
            conf=float(det_data.get("conf", det_data.get("confidence", 0.0))),
            bbox=det_data.get("bbox", [0, 0, 0, 0])
        )
        detections.append(detection)

    return detections


def run_yolo(img_array: np.ndarray, conf: float = DEFAULT_CONF, iou: float = DEFAULT_IOU,
             imgsz: int = DEFAULT_IMGSZ, max_det: int = 300) -> List[Det]:
    """
    Run YOLO inference with hybrid support (local/remote/auto-fallback).

    Args:
        img_array: Input image as numpy array (BGR format)
        conf: Confidence threshold
        iou: IOU threshold for NMS
        imgsz: Image size for inference
        max_det: Maximum detections

    Returns:
        List[Det]: List of detection objects with label, conf, bbox
    """

    if YOLO_MODE == "remote":
        # Remote only mode
        return run_yolo_remote(img_array, conf, iou, imgsz, max_det)

    elif YOLO_MODE == "hybrid":
        # Try remote first, fallback to local
        try:
            print(f"[YOLO] Attempting remote inference: {YOLO_REMOTE_URL}")
            return run_yolo_remote(img_array, conf, iou, imgsz, max_det)
        except Exception as e:
            print(f"[YOLO] Remote inference failed ({e}), falling back to local")
            return run_yolo_local(img_array, conf, iou, imgsz, max_det)

    else:
        # Local only mode (default)
        return run_yolo_local(img_array, conf, iou, imgsz, max_det)

def _draw_inside_label(
    img: np.ndarray,
    box: Tuple[int,int,int,int],
    text: str,
    base_font_px: int,
    line_width: int,
    img_h: int,
    min_band_px: int,
    min_band_px_ratio: float,
    color_box=(255,0,0),
    color_text=(255,255,255),
    alpha_bg=0.45,
) -> Tuple[np.ndarray, Tuple[int,int,int,int], int]:
    """
    尝试把标签画在框内四角；放不下自动减小字号；仍放不下则用“顶部半透明带”（仍在框内）；
    极端情况用中心小圆点 + 极小 ID。
    返回：(img, label_rect_xyxy, used_mode)
      used_mode: 0=corner, 1=top-band, 2=center-dot
    """
    import cv2
    x1, y1, x2, y2 = [int(v) for v in box]
    w, h = x2 - x1, y2 - y1
    out = img

    pad = 4
    thickness_text = max(1, line_width - 1)
    font_px = max(7, base_font_px)

    def draw_filled(rect):
        rx1, ry1, rx2, ry2 = rect
        overlay = out.copy()
        cv2.rectangle(overlay, (rx1, ry1), (rx2, ry2), color_box, -1)
        cv2.addWeighted(overlay, alpha_bg, out, 1 - alpha_bg, 0, out)

    font = cv2.FONT_HERSHEY_SIMPLEX

    # 1) 角落优先（左上/右上/左下/右下）
    while font_px >= 7:
        scale = _font_scale_from_px(font_px, thickness=thickness_text)
        (tw, th), _ = cv2.getTextSize(text, font, scale, thickness_text)
        bw, bh = tw + 2*pad, th + 2*pad

        candidates = [
            (x1 + line_width,               y1 + line_width),
            (x2 - line_width - bw,          y1 + line_width),
            (x1 + line_width,               y2 - line_width - bh),
            (x2 - line_width - bw,          y2 - line_width - bh),
        ]
        for (lx, ly) in candidates:
            if lx >= x1 and ly >= y1 and (lx + bw) <= x2 and (ly + bh) <= y2:
                rect = (int(lx), int(ly), int(lx + bw), int(ly + bh))
                draw_filled(rect)
                cv2.putText(out, text, (rect[0] + pad, rect[3] - pad - 1),
                            font, scale, color_text, thickness_text, cv2.LINE_AA)
                return out, rect, 0
        font_px = int(font_px * 0.9)

    # 2) 顶部半透明带（在框内），带高带“全局最小值”防止高清图上过小
    min_band = max(min_band_px, int(min_band_px_ratio * img_h))
    band_h_px = max(min_band, int(h * 0.20))
    rx1, ry1, rx2, ry2 = x1 + line_width, y1 + line_width, x2 - line_width, y1 + band_h_px
    rx1, ry1 = _clip_int(rx1, 0, img.shape[1]-1), _clip_int(ry1, 0, img.shape[0]-1)
    rx2, ry2 = _clip_int(rx2, 0, img.shape[1]-1), _clip_int(ry2, 0, img.shape[0]-1)
    rect = (rx1, ry1, rx2, ry2)

    scale = _font_scale_from_px(max(9, band_h_px - 6), thickness=thickness_text)
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness_text)
    tries = 0
    while tw + 8 > (rx2 - rx1) and tries < 8:
        scale *= 0.9
        (tw, th), _ = cv2.getTextSize(text, font, scale, thickness_text)
        tries += 1

    overlay = out.copy()
    cv2.rectangle(overlay, (rx1, ry1), (rx2, ry2), color_box, -1)
    cv2.addWeighted(overlay, 0.45, out, 0.55, 0, out)
    cx = int((rx1 + rx2 - tw) / 2)
    cy = int((ry1 + ry2 + th) / 2) - 2
    cv2.putText(out, text, (cx, cy), font, scale, color_text, thickness_text, cv2.LINE_AA)
    return out, rect, 1

def _draw_scene_inside(
    base_bgr: np.ndarray,
    xyxy: List[List[float]],
    ids: List[int],
    confs: List[float],
    label_prefix: str,
    show_conf: bool,
    line_width: int,
    font_mode: str,
    font_px_fixed: int,
    font_scale_global: float,
    min_band_px: int,
    min_band_px_ratio: float,
    text_mode: str,
    draw_center: bool,
) -> Tuple[np.ndarray, List[Tuple[int,int,int,int]]]:
    """
    画矩形 + 框内标签（自适应）。返回图像及每个标签的实际矩形位置列表。
    font_mode: "auto"（默认，每个框自适应）或 "fixed"（使用 font_px_fixed）
    text_mode: "short" -> 只画 ID；"full" -> 'icon 12 0.92'
    """
    import cv2

    H, W = base_bgr.shape[:2]
    out = base_bgr.copy()
    color_box = (255, 0, 0)
    thickness_box = line_width
    color_text = (255, 255, 255)

    # 先画框
    for (x1, y1, x2, y2) in xyxy:
        cv2.rectangle(out, (int(x1), int(y1)), (int(x2), int(y2)), color_box, thickness_box)

    label_rects: List[Tuple[int,int,int,int]] = []
    N = max(1, len(xyxy))

    for (x1, y1, x2, y2), uid, c in zip(xyxy, ids, confs):
        h = int(y2 - y1)
        # 文本
        if text_mode == "short":
            text = f"{uid}"
        else:
            text = f"{label_prefix} {uid}" + (f" {c:.2f}" if show_conf else "")

        # ---- 动态字号计算 ----
        if font_mode == "fixed":
            base_px = font_px_fixed
        else:
            # 基于框高与图高联合决定（经验系数可按需要微调）
            img_based = max(12, int(0.016 * H))                # ~1.6% 的图高
            box_based = max(9, int(0.28 * h))                  # ~28% 的框高
            base_px = min(max(img_based, box_based), 36)       # 上限 36px

            # 文本较长（full 模式）适当降一点
            if text_mode == "full":
                base_px = int(base_px * 0.92)

            # 目标密度调节：太多 -> 略缩小；太少 -> 略放大
            if N > 70:
                base_px = int(base_px * 0.88)
            elif N < 15:
                base_px = int(base_px * 1.12)

        # 全局倍率
        base_px = max(7, int(base_px * float(font_scale_global)))

        out, label_rect, _ = _draw_inside_label(
            out,
            (int(x1), int(y1), int(x2), int(y2)),
            text=text,
            base_font_px=base_px,
            line_width=line_width,
            img_h=H,
            min_band_px=min_band_px,
            min_band_px_ratio=min_band_px_ratio,
            color_box=color_box,
            color_text=color_text,
            alpha_bg=0.45
        )
        label_rects.append(label_rect)

        # 中心点（用于点击）
        if draw_center:
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            cv2.circle(out, (cx, cy), radius=3, color=color_box, thickness=-1)

    return out, label_rects

# ---------- Routes ----------
@app.get("/health")
def health():
    return {"status": "ok", "model": WEIGHTS, "device": device}

@app.post("/predict", response_model=PredictResponse)
async def predict(
    request: Request,
    image: UploadFile = File(default=None, description="Image file (multipart/form-data)"),
    image_base64: Optional[str] = Form(default=None, description="Base64 image string (no data: prefix)"),
    image_url: Optional[str] = Form(default=None, description="Public URL to an image"),

    conf: float = Query(default=DEFAULT_CONF, ge=0.0, le=1.0),
    iou:  float = Query(default=DEFAULT_IOU,  ge=0.0, le=1.0),
    imgsz: int   = Query(default=DEFAULT_IMGSZ),
    max_det: int = Query(default=300),

    # 可调参数（新增/保留）
    return_image: bool = Query(default=False, description="Return annotated PNG as data URL"),
    label_prefix: str   = Query(default="icon", description="Prefix when text_mode=full"),
    id_order: str       = Query(default="tl", description="ID assignment: 'tl' or 'model'"),
    show_conf: bool     = Query(default=True, description="Include confidence when text_mode=full"),
    line_width: int     = Query(default=2, description="Rectangle line width"),

    # 字体相关控制
    font_mode: str      = Query(default="auto", description="'auto' or 'fixed'"),
    font_px: int        = Query(default=12, description="Used when font_mode='fixed'"),
    font_scale_global: float = Query(default=1.0, description="Multiply computed font px"),

    # 顶带最小高度（避免高清图上顶带过小）
    min_band_px: int        = Query(default=14, description="Absolute minimum top-band px"),
    min_band_px_ratio: float= Query(default=0.012, description="Min top-band as ratio of image height"),

    # 文本样式
    text_mode: str      = Query(default="short", description="'short' -> just ID; 'full' -> 'icon 12 0.92'"),
    draw_center: bool   = Query(default=True, description="Draw a small center dot"),
):
    """
    - 稳定编号（默认按顶->底、左->右）
    - **框内** 标注：角落优先；自适应字号，必要时顶部带；极端时中心点
    - 动态字号：随框高/图高/目标密度/文本长度联动，必要时你可用 font_scale_global 一键放大/缩小
    - 返回 click_xy_norm 与 label_bbox_xyxy，方便自动点击与对齐
    """
    import PIL.Image as Image

    _obs_event(
        "predict.start",
        request=request,
        has_upload=bool(image is not None),
        has_base64=bool(image_base64),
        has_url=bool(image_url),
        conf=conf,
        iou=iou,
        imgsz=imgsz,
        max_det=max_det,
        return_image=return_image,
    )

    raw = _read_image_bytes(image, image_base64, image_url)
    pil_img = Image.open(io.BytesIO(raw)).convert("RGB")
    W, H = pil_img.size

    t0 = time.time()
    res = model.predict(
        pil_img,
        conf=conf,
        iou=iou,
        imgsz=imgsz,
        max_det=max_det,
        device=device,
        verbose=False
    )[0]
    dt_ms = (time.time() - t0) * 1000.0
    _obs_event(
        "predict.yolo.done",
        request=request,
        infer_ms=round(dt_ms, 2),
    )

    # ---- Extract ----
    dets: List[dict] = []
    xyxy: List[List[float]] = []
    confs: List[float] = []
    clss:  List[int] = []
    names = res.names if hasattr(res, "names") and res.names else model.names

    if res.boxes is not None and len(res.boxes) > 0:
        xyxy = res.boxes.xyxy.cpu().tolist()
        confs = [float(x) for x in res.boxes.conf.cpu().tolist()]
        clss  = [int(x)   for x in res.boxes.cls.cpu().tolist()]

        # Stable IDs
        if id_order == "tl":
            order = _sort_indices_tl(xyxy)
        else:
            order = list(range(len(xyxy)))
        ids = [0] * len(xyxy)
        for n, i in enumerate(order, start=1):
            ids[i] = n

        for (x1, y1, x2, y2), c, k, uid in zip(xyxy, confs, clss, ids):
            dets.append({
                "id": uid,
                "name": f"{label_prefix} {uid}",
                "label": f"{label_prefix} {uid}",
                "conf": c,
                "class_id": k,
                "class_name": names.get(k, str(k)) if isinstance(names, dict) else str(k),
                "bbox_xyxy": [float(x1), float(y1), float(x2), float(y2)],
                "bbox_xyxy_norm": [x1/W, y1/H, x2/W, y2/H],
                "center_xy_norm": [((x1+x2)/2)/W, ((y1+y2)/2)/H],
                "size_wh_norm": [(x2-x1)/W, (y2-y1)/H],
                "click_xy_norm": None,
                "label_bbox_xyxy": None,
            })
    else:
        ids = []

    payload = {
        "model": WEIGHTS,
        "device": device,
        "time_ms": round(dt_ms, 2),
        "detections": dets,
    }

    # ---- 绘制（框内/自适应） ----
    if return_image:
        base_bgr = _pil_to_bgr(pil_img)
        if dets:
            draw_xyxy = [d["bbox_xyxy"] for d in dets]
            draw_ids  = [d["id"] for d in dets]
            draw_confs= [d["conf"] for d in dets]

            annotated, label_rects = _draw_scene_inside(
                base_bgr,
                draw_xyxy, draw_ids, draw_confs,
                label_prefix=label_prefix,
                show_conf=show_conf,
                line_width=line_width,
                font_mode=font_mode,
                font_px_fixed=font_px,
                font_scale_global=font_scale_global,
                min_band_px=min_band_px,
                min_band_px_ratio=min_band_px_ratio,
                text_mode=text_mode,
                draw_center=draw_center,
            )

            # 回填 label_bbox 与 click 点（中心）
            for d, lab_rect in zip(dets, label_rects):
                d["label_bbox_xyxy"] = [float(lab_rect[0]), float(lab_rect[1]), float(lab_rect[2]), float(lab_rect[3])]
                cx = (d["bbox_xyxy"][0] + d["bbox_xyxy"][2]) / 2.0
                cy = (d["bbox_xyxy"][1] + d["bbox_xyxy"][3]) / 2.0
                d["click_xy_norm"] = [cx / W, cy / H]

            payload["image_base64"] = _np_to_base64_png(annotated)
        else:
            payload["image_base64"] = _np_to_base64_png(base_bgr)
    else:
        for d in dets:
            cx = (d["bbox_xyxy"][0] + d["bbox_xyxy"][2]) / 2.0
            cy = (d["bbox_xyxy"][1] + d["bbox_xyxy"][3]) / 2.0
            d["click_xy_norm"] = [cx / W, cy / H]

    _obs_event(
        "predict.done",
        request=request,
        detection_count=len(dets),
        returned_image=bool(return_image),
    )
    return payload

# ---------- New /detect endpoint for DOM->Vision fallback ----------

# Label mapping for UI element detection
LABEL_ALIAS = {
    "search_box": ["search", "搜索", "input", "textbox"],
    "post_card": ["post", "note", "卡片", "article", "content"],
    "button": ["button", "btn", "按钮", "submit"],
    "comment": ["comment", "评论", "reply", "回复"],
    "send": ["send", "发送", "submit", "提交"],
    "login": ["login", "登录", "signin", "登入"],
    "apply": ["apply", "申请", "应聘", "投递"]
}

def _match_label(detection_class: str, target_label: str) -> float:
    """Match detection class against target label using aliases"""
    if not target_label:
        return 1.0  # No filter, return all
    
    target_aliases = LABEL_ALIAS.get(target_label, [target_label])
    detection_lower = detection_class.lower()
    
    # Exact match
    if detection_lower == target_label.lower():
        return 1.0
    
    # Alias match
    for alias in target_aliases:
        if alias.lower() in detection_lower or detection_lower in alias.lower():
            return 0.8
    
    # Partial substring match
    for alias in target_aliases:
        if alias.lower() in detection_lower:
            return 0.6
    
    return 0.0

def _center(x1, y1, x2, y2) -> Tuple[int, int]:
    """Calculate center point of bounding box"""
    return int((x1 + x2) / 2), int((y1 + y2) / 2)

# Old /detect endpoint removed to avoid FastAPI routing conflicts
# The new unified /detect endpoint below supports both JSON and multipart formats


# ---------- New Unified API Endpoints ----------

@app.post("/detect", response_model=UnifiedResponse)
async def detect(
    request: Request,
    image: Optional[UploadFile] = File(default=None),         # multipart 路径
    meta: Optional[str] = Form(default=None),                 # multipart 附带 JSON 字段（可选）
):
    """
    Enhanced /detect endpoint supporting both JSON and multipart formats.

    Multipart usage: -F 'image=@xxx.png' -F 'meta={"classes":["button"],"min_conf":0.6}'
    JSON usage: {"image_b64":"...","classes":["button"],"min_conf":0.6}
    """
    try:
        _obs_event("detect.start", request=request)
        # Determine request type
        content_type = request.headers.get("content-type", "")
        is_json = "application/json" in content_type

        if not is_json and image is not None:
            # Multipart/form-data 路径
            meta_dict: Dict[str, Any] = {}
            if meta:
                try:
                    meta_dict = json.loads(meta)
                except json.JSONDecodeError:
                    return UnifiedResponse(
                        ok=False,
                        error={"code": "INVALID_META", "msg": "Invalid JSON in meta field"}
                    )

            classes_list = meta_dict.get("classes", [])
            roi_hint_list = meta_dict.get("roi_hint")
            min_conf = float(meta_dict.get("min_conf", 0.6))
            top_k = int(meta_dict.get("top_k", 5))
            llm_picker = bool(meta_dict.get("llm_picker", False))
            prompt = meta_dict.get("prompt")
            return_image = bool(meta_dict.get("return_image", False))

            pil_img = load_image_from_any(upload=image)

        elif is_json:
            # Application/json 路径
            try:
                body = await request.json()
            except Exception:
                return UnifiedResponse(
                    ok=False,
                    error={"code": "INVALID_JSON", "msg": "Invalid JSON body"}
                )

            classes_list = body.get("classes", [])
            roi_hint_list = body.get("roi_hint")
            min_conf = float(body.get("min_conf", 0.6))
            top_k = int(body.get("top_k", 5))
            llm_picker = bool(body.get("llm_picker", False))
            prompt = body.get("prompt")
            return_image = bool(body.get("return_image", False))

            pil_img = load_image_from_any(
                image_b64=body.get("image_b64"),
                image_url=body.get("image_url")
            )

        # Convert PIL to numpy array (BGR format for OpenCV)
        import cv2

        # Optimize image for token reduction AND compress for file size reduction
        try:
            from core.image_optimizer import LLMImageOptimizer
            from core.image_compress_coords import compress_for_vlm
            import tempfile
            import os

            # First save the PIL image to a temporary file so we can process it
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                temp_path = temp_file.name
            pil_img.save(temp_path)

            print(f"🔧 API: Starting image optimization for token reduction")
            optimizer = LLMImageOptimizer()

            # Step 1: Optimize the image for token reduction
            optimized_path, stats = optimizer.optimize_for_llm(temp_path)

            # Step 2: Compress the image for file size reduction (target 200KB)
            try:
                print(f"🗜️ API: Starting file compression (target 200KB)")
                current_image_path = optimized_path if stats.get('optimized', False) else temp_path

                with tempfile.NamedTemporaryFile(suffix='.webp', delete=False) as compressed_tmp:
                    compressed_path = compressed_tmp.name

                compression_transform = compress_for_vlm(current_image_path, compressed_path, target_kb=200)

                orig_size = os.path.getsize(current_image_path)
                compressed_size = os.path.getsize(compressed_path)
                reduction_percent = ((orig_size - compressed_size) / orig_size) * 100

                print(f"📦 API: File compressed: {reduction_percent:.1f}% size reduction "
                      f"({orig_size//1024}KB → {compressed_size//1024}KB)")

                # Use compressed image for further processing
                final_image_path = compressed_path

            except Exception as compress_error:
                print(f"❌ API: Compression failed: {compress_error}")
                final_image_path = optimized_path if stats.get('optimized', False) else temp_path
                compression_transform = None

            # Load the final processed image
            pil_img = Image.open(final_image_path)

            # Clean up temporary files
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                if 'optimized_path' in locals() and optimized_path != temp_path and os.path.exists(optimized_path):
                    os.unlink(optimized_path)
                if 'compressed_path' in locals() and final_image_path == compressed_path:
                    # Keep compressed file for now, will be cleaned up later if needed
                    pass
            except Exception as cleanup_error:
                print(f"⚠️ API: Cleanup warning: {cleanup_error}")

        except Exception as opt_error:
            print(f"❌ API: Optimization failed: {opt_error}")
            # Fall back to original image - no changes needed
            compression_transform = None

        rgb_array = np.array(pil_img)
        img_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)

        # Apply ROI cropping if specified
        original_img = img_array.copy()
        if roi_hint_list and len(roi_hint_list) == 4:
            img_array = crop_by_norm(img_array, roi_hint_list)

        # Run YOLO detection
        t0 = time.time()
        detections = run_yolo(img_array, conf=min_conf)
        dt_ms = (time.time() - t0) * 1000.0
        _obs_event(
            "detect.yolo.done",
            request=request,
            infer_ms=round(dt_ms, 2),
            raw_detection_count=len(detections),
        )

        # Filter by classes if specified
        if classes_list:
            filtered_dets = []
            for det in detections:
                for target_class in classes_list:
                    if target_class.lower() in det.label.lower():
                        filtered_dets.append(det)
                        break
            detections = filtered_dets

        # Sort by confidence and take top_k
        detections.sort(key=lambda d: d.conf, reverse=True)
        detections = detections[:top_k]

        # Convert detections to response format
        candidates = []
        selected = None

        h, w = img_array.shape[:2]

        # If compression was applied, use original dimensions from transform
        if 'compression_transform' in locals() and compression_transform is not None:
            orig_h, orig_w = compression_transform.orig_h, compression_transform.orig_w
        else:
            orig_h, orig_w = original_img.shape[:2]

        for i, det in enumerate(detections):
            x, y, bbox_w, bbox_h = det.bbox

            # Convert back to original image coordinates
            if 'compression_transform' in locals() and compression_transform is not None:
                # Use compression transform for reverse mapping
                from core.image_compress_coords import map_bbox_back
                print(f"🗺️ API: Using compression transform for coordinate mapping")
                print(f"🗺️ API: Original bbox: x={x}, y={y}, w={bbox_w}, h={bbox_h}")
                # FIXED: map_bbox_back returns (x, y, width, height), not (x1, y1, x2, y2)
                mx, my, mw, mh = map_bbox_back(x, y, bbox_w, bbox_h, compression_transform)
                x1, y1, x2, y2 = mx, my, mx + mw, my + mh
                print(f"🗺️ API: Mapped bbox: x1={x1}, y1={y1}, x2={x2}, y2={y2}")

            elif roi_hint_list:
                # Original ROI mapping (no compression)
                roi_x, roi_y, roi_w, roi_h = roi_hint_list
                # Scale back to original coordinates
                x = roi_x * orig_w + (x / w) * roi_w * orig_w
                y = roi_y * orig_h + (y / h) * roi_h * orig_h
                bbox_w = (bbox_w / w) * roi_w * orig_w
                bbox_h = (bbox_h / h) * roi_h * orig_h
                x1, y1, x2, y2 = x, y, x + bbox_w, y + bbox_h
            else:
                # No compression, no ROI - direct coordinates
                x1, y1, x2, y2 = x, y, x + bbox_w, y + bbox_h

            candidate = {
                "label": det.label,
                "conf": det.conf,
                "rect_abs": [x1, y1, x2, y2],
                "rect_norm": [x1/orig_w, y1/orig_h, x2/orig_w, y2/orig_h],
                "click_point": {"x": int((x1 + x2) / 2), "y": int((y1 + y2) / 2)}
            }
            candidates.append(candidate)

            # Set first (highest confidence) as selected
            if i == 0:
                selected = candidate

        data = {
            "candidates": candidates,
            "selected": selected,
            "time_ms": round(dt_ms, 2)
        }

        # Add annotated image if requested
        if return_image and candidates:
            import cv2
            annotated = original_img.copy()
            for cand in candidates:
                x1, y1, x2, y2 = [int(v) for v in cand["rect_abs"]]
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(annotated, f"{cand['label']} {cand['conf']:.2f}",
                           (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            # Convert to base64
            _, buffer = cv2.imencode('.png', annotated)
            img_b64 = base64.b64encode(buffer).decode()
            data["image_base64"] = f"data:image/png;base64,{img_b64}"

        _obs_event(
            "detect.done",
            request=request,
            detection_count=len(candidates),
            selected=bool(selected is not None),
            return_image=bool(return_image),
        )
        return UnifiedResponse(ok=True, data=data)

    except Exception as e:
        _obs_event("detect.error", request=request, error=str(e))
        return UnifiedResponse(
            ok=False,
            error={"code": "DETECTION_ERROR", "msg": str(e)}
        )


@app.post("/calibrate", response_model=UnifiedResponse)
async def calibrate(
    request: Request,
    image: Optional[UploadFile] = File(default=None),         # multipart 路径
    meta: Optional[str] = Form(default=None),                 # multipart 附带 JSON 字段（可选）
):
    """
    Enhanced /calibrate endpoint supporting both JSON and multipart formats.

    Multipart usage: -F 'image=@xxx.png' -F 'meta={"element_key":"test_button","classes":["button"]}'
    JSON usage: {"image_b64":"...","element_key":"test_button","classes":["button"]}
    """
    try:
        if image is not None:
            # Multipart/form-data 路径
            meta_dict: Dict[str, Any] = {}
            if meta:
                try:
                    meta_dict = json.loads(meta)
                except json.JSONDecodeError:
                    return UnifiedResponse(
                        ok=False,
                        error={"code": "INVALID_META", "msg": "Invalid JSON in meta field"}
                    )

            element_key = meta_dict.get("element_key")
            if not element_key:
                return UnifiedResponse(
                    ok=False,
                    error={"code": "MISSING_ELEMENT_KEY", "msg": "element_key is required"}
                )

            classes_list = meta_dict.get("classes", [])
            roi_hint_list = meta_dict.get("roi_hint")
            window_fingerprint = meta_dict.get("window_fingerprint")
            dpi_bucket = meta_dict.get("dpi_bucket")
            theme = meta_dict.get("theme")
            persist = bool(meta_dict.get("persist", False))

            pil_img = load_image_from_any(upload=image)

        else:
            # Application/json 路径
            try:
                body = await request.json()
            except Exception:
                return UnifiedResponse(
                    ok=False,
                    error={"code": "INVALID_JSON", "msg": "Invalid JSON body"}
                )

            element_key = body.get("element_key")
            if not element_key:
                return UnifiedResponse(
                    ok=False,
                    error={"code": "MISSING_ELEMENT_KEY", "msg": "element_key is required"}
                )

            classes_list = body.get("classes", [])
            roi_hint_list = body.get("roi_hint")
            window_fingerprint = body.get("window_fingerprint")
            dpi_bucket = body.get("dpi_bucket")
            theme = body.get("theme")
            persist = bool(body.get("persist", False))

            pil_img = load_image_from_any(
                image_b64=body.get("image_b64"),
                image_url=body.get("image_url")
            )

        # Convert PIL to numpy array (BGR format for OpenCV)
        import cv2
        rgb_array = np.array(pil_img)
        img_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)

        # Run detection to find most stable target
        detections = run_yolo(img_array, conf=0.3)

        if classes_list:
            # Filter by classes
            filtered_dets = []
            for det in detections:
                for target_class in classes_list:
                    if target_class.lower() in det.label.lower():
                        filtered_dets.append(det)
                        break
            detections = filtered_dets

        if not detections:
            return UnifiedResponse(
                ok=False,
                error={"code": "NO_DETECTIONS", "msg": "No elements found for calibration"}
            )

        # Take the highest confidence detection as the stable target
        best_det = max(detections, key=lambda d: d.conf)
        x, y, w, h = best_det.bbox

        # Calculate ROI (add some padding)
        img_h, img_w = img_array.shape[:2]
        padding = 0.1  # 10% padding
        roi_x = max(0, (x - w * padding) / img_w)
        roi_y = max(0, (y - h * padding) / img_h)
        roi_w = min(1.0, (w * (1 + 2 * padding)) / img_w)
        roi_h = min(1.0, (h * (1 + 2 * padding)) / img_h)

        roi_abs = [roi_x * img_w, roi_y * img_h, roi_w * img_w, roi_h * img_h]
        roi_norm = [roi_x, roi_y, roi_w, roi_h]

        # Extract ROI for baseline calculation
        roi_img = crop_by_norm(img_array, roi_norm)

        # Calculate baseline metrics
        phash = calc_phash64(roi_img)
        red_ratio = calc_red_ratio(roi_img)

        # For SSIM, we'll use the same image as baseline (perfect similarity = 1.0)
        ssim_val = 1.0

        data = {
            "element_key": element_key,
            "roi_abs": roi_abs,
            "roi_norm": roi_norm,
            "baseline": {
                "phash": phash,
                "ssim": ssim_val,
                "red_ratio": red_ratio
            },
            "screen": {"w": img_w, "h": img_h},
            "confidence": best_det.conf,
            "label": best_det.label
        }

        return UnifiedResponse(ok=True, data=data)

    except Exception as e:
        return UnifiedResponse(
            ok=False,
            error={"code": "CALIBRATE_ERROR", "msg": str(e)}
        )


@app.post("/reacquire", response_model=UnifiedResponse)
async def reacquire(
    request: Request,
    image: Optional[UploadFile] = File(default=None),         # multipart 路径
    meta: Optional[str] = Form(default=None),                 # multipart 附带 JSON 字段（可选）
):
    """
    Enhanced /reacquire endpoint supporting both JSON and multipart formats.

    Multipart usage: -F 'image=@xxx.png' -F 'meta={"element_key":"test","last_roi_norm":[0.1,0.1,0.2,0.2]}'
    JSON usage: {"image_b64":"...","element_key":"test","last_roi_norm":[0.1,0.1,0.2,0.2]}
    """
    try:
        if image is not None:
            # Multipart/form-data 路径
            meta_dict: Dict[str, Any] = {}
            if meta:
                try:
                    meta_dict = json.loads(meta)
                except json.JSONDecodeError:
                    return UnifiedResponse(
                        ok=False,
                        error={"code": "INVALID_META", "msg": "Invalid JSON in meta field"}
                    )

            element_key = meta_dict.get("element_key")
            last_roi_norm = meta_dict.get("last_roi_norm")
            scope = meta_dict.get("scope", "auto")
            classes_list = meta_dict.get("classes", [])
            min_conf = float(meta_dict.get("min_conf", 0.5))

            pil_img = load_image_from_any(upload=image)

        else:
            # Application/json 路径
            try:
                body = await request.json()
            except Exception:
                return UnifiedResponse(
                    ok=False,
                    error={"code": "INVALID_JSON", "msg": "Invalid JSON body"}
                )

            element_key = body.get("element_key")
            last_roi_norm = body.get("last_roi_norm")
            scope = body.get("scope", "auto")
            classes_list = body.get("classes", [])
            min_conf = float(body.get("min_conf", 0.5))

            pil_img = load_image_from_any(
                image_b64=body.get("image_b64"),
                image_url=body.get("image_url")
            )

        # Validate required fields
        if not element_key:
            return UnifiedResponse(
                ok=False,
                error={"code": "MISSING_ELEMENT_KEY", "msg": "element_key is required"}
            )

        if not last_roi_norm:
            return UnifiedResponse(
                ok=False,
                error={"code": "MISSING_ROI", "msg": "last_roi_norm is required"}
            )

        # Parse last_roi_norm if it's a string
        if isinstance(last_roi_norm, str):
            try:
                last_roi = json.loads(last_roi_norm)
            except:
                return UnifiedResponse(
                    ok=False,
                    error={"code": "INVALID_ROI", "msg": "Invalid last_roi_norm format"}
                )
        else:
            last_roi = last_roi_norm

        # Convert PIL to numpy array (BGR format for OpenCV)
        import cv2
        rgb_array = np.array(pil_img)
        img_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)

        img_h, img_w = img_array.shape[:2]
        method_used = "global"

        # Try local search first (2x area around last ROI)
        if scope in ["auto", "local"]:
            roi_x, roi_y, roi_w, roi_h = last_roi

            # Expand search area by 2x
            search_x = max(0, roi_x - roi_w * 0.5)
            search_y = max(0, roi_y - roi_h * 0.5)
            search_w = min(1.0, roi_w * 2.0)
            search_h = min(1.0, roi_h * 2.0)

            search_roi = [search_x, search_y, search_w, search_h]
            local_img = crop_by_norm(img_array, search_roi)

            # Run detection on local area
            local_detections = run_yolo(local_img, conf=min_conf)

            if classes_list:
                filtered_dets = []
                for det in local_detections:
                    for target_class in classes_list:
                        if target_class.lower() in det.label.lower():
                            filtered_dets.append(det)
                            break
                local_detections = filtered_dets

            if local_detections:
                # Found in local area
                best_det = max(local_detections, key=lambda d: d.conf)
                x, y, w, h = best_det.bbox

                # Convert back to full image coordinates
                local_h, local_w = local_img.shape[:2]
                x = search_x * img_w + (x / local_w) * search_w * img_w
                y = search_y * img_h + (y / local_h) * search_h * img_h
                w = (w / local_w) * search_w * img_w
                h = (h / local_h) * search_h * img_h

                # Calculate new ROI
                padding = 0.1
                new_roi_x = max(0, (x - w * padding) / img_w)
                new_roi_y = max(0, (y - h * padding) / img_h)
                new_roi_w = min(1.0, (w * (1 + 2 * padding)) / img_w)
                new_roi_h = min(1.0, (h * (1 + 2 * padding)) / img_h)

                method_used = "local"

                data = {
                    "element_key": element_key,
                    "roi_norm": [new_roi_x, new_roi_y, new_roi_w, new_roi_h],
                    "roi_abs": [new_roi_x * img_w, new_roi_y * img_h, new_roi_w * img_w, new_roi_h * img_h],
                    "method": method_used,
                    "confidence": best_det.conf,
                    "label": best_det.label
                }

                return UnifiedResponse(ok=True, data=data)

        # Fall back to global search
        if scope in ["auto", "global"]:
            global_detections = run_yolo(img_array, conf=min_conf)

            if classes_list:
                filtered_dets = []
                for det in global_detections:
                    for target_class in classes_list:
                        if target_class.lower() in det.label.lower():
                            filtered_dets.append(det)
                            break
                global_detections = filtered_dets

            if global_detections:
                best_det = max(global_detections, key=lambda d: d.conf)
                x, y, w, h = best_det.bbox

                # Calculate new ROI
                padding = 0.1
                new_roi_x = max(0, (x - w * padding) / img_w)
                new_roi_y = max(0, (y - h * padding) / img_h)
                new_roi_w = min(1.0, (w * (1 + 2 * padding)) / img_w)
                new_roi_h = min(1.0, (h * (1 + 2 * padding)) / img_h)

                data = {
                    "element_key": element_key,
                    "roi_norm": [new_roi_x, new_roi_y, new_roi_w, new_roi_h],
                    "roi_abs": [new_roi_x * img_w, new_roi_y * img_h, new_roi_w * img_w, new_roi_h * img_h],
                    "method": method_used,
                    "confidence": best_det.conf,
                    "label": best_det.label
                }

                return UnifiedResponse(ok=True, data=data)

        return UnifiedResponse(
            ok=False,
            error={"code": "ELEMENT_NOT_FOUND", "msg": f"Could not reacquire element with scope: {scope}"}
        )

    except Exception as e:
        return UnifiedResponse(
            ok=False,
            error={"code": "REACQUIRE_ERROR", "msg": str(e)}
        )


@app.post("/verify", response_model=UnifiedResponse)
async def verify(
    request: Request,
    image: Optional[UploadFile] = File(default=None),         # multipart 路径
    meta: Optional[str] = Form(default=None),                 # multipart 附带 JSON 字段（可选）
):
    """
    Enhanced /verify endpoint supporting both JSON and multipart formats.

    Multipart usage: -F 'image=@xxx.png' -F 'meta={"rules":{"red_ratio_lt":0.1},"baseline_b64":"..."}'
    JSON usage: {"image_b64":"...","rules":{"red_ratio_lt":0.1},"baseline_b64":"..."}
    """
    try:
        if image is not None:
            # Multipart/form-data 路径
            meta_dict: Dict[str, Any] = {}
            if meta:
                try:
                    meta_dict = json.loads(meta)
                except json.JSONDecodeError:
                    return UnifiedResponse(
                        ok=False,
                        error={"code": "INVALID_META", "msg": "Invalid JSON in meta field"}
                    )

            rules_dict = meta_dict.get("rules")
            if not rules_dict:
                return UnifiedResponse(
                    ok=False,
                    error={"code": "MISSING_RULES", "msg": "rules are required"}
                )

            baseline_b64 = meta_dict.get("baseline_b64")
            baseline_url = meta_dict.get("baseline_url")

            pil_img = load_image_from_any(upload=image)

        else:
            # Application/json 路径
            try:
                body = await request.json()
            except Exception:
                return UnifiedResponse(
                    ok=False,
                    error={"code": "INVALID_JSON", "msg": "Invalid JSON body"}
                )

            rules_dict = body.get("rules")
            if not rules_dict:
                return UnifiedResponse(
                    ok=False,
                    error={"code": "MISSING_RULES", "msg": "rules are required"}
                )

            baseline_b64 = body.get("baseline_b64")
            baseline_url = body.get("baseline_url")

            pil_img = load_image_from_any(
                image_b64=body.get("image_b64"),
                image_url=body.get("image_url")
            )

        # Parse rules if it's a string
        if isinstance(rules_dict, str):
            try:
                rules_dict = json.loads(rules_dict)
            except:
                return UnifiedResponse(
                    ok=False,
                    error={"code": "INVALID_RULES", "msg": "Invalid rules JSON format"}
                )

        # Convert PIL to numpy array (BGR format for OpenCV)
        import cv2
        rgb_array = np.array(pil_img)
        current_img = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)

        # Calculate current metrics
        current_phash = calc_phash64(current_img)
        current_red_ratio = calc_red_ratio(current_img)

        # Calculate metrics against baseline if provided
        phash_delta = 0
        ssim_val = 1.0

        if baseline_b64 or baseline_url:
            baseline_pil = load_image_from_any(image_b64=baseline_b64, image_url=baseline_url)
            baseline_rgb = np.array(baseline_pil)
            baseline_img = cv2.cvtColor(baseline_rgb, cv2.COLOR_RGB2BGR)
            baseline_phash = calc_phash64(baseline_img)
            phash_delta = calc_phash_delta(current_phash, baseline_phash)
            ssim_val = calc_ssim64(current_img, baseline_img)

        metrics = {
            "red_ratio": current_red_ratio,
            "phash_delta": phash_delta,
            "ssim": ssim_val
        }

        # Apply verification rules
        changed = False

        if "red_ratio_lt" in rules_dict:
            if current_red_ratio < rules_dict["red_ratio_lt"]:
                changed = True

        if "phash_delta_gt" in rules_dict:
            if phash_delta > rules_dict["phash_delta_gt"]:
                changed = True

        if "ssim_lt" in rules_dict:
            if ssim_val < rules_dict["ssim_lt"]:
                changed = True

        data = {
            "changed": changed,
            "metrics": metrics
        }

        return UnifiedResponse(ok=True, data=data)

    except Exception as e:
        return UnifiedResponse(
            ok=False,
            error={"code": "VERIFY_ERROR", "msg": str(e)}
        )


@app.get("/version", response_model=UnifiedResponse)
async def get_version():
    """
    Get engine version and build information.
    """
    try:
        # Get git short SHA if available
        build_info = "unknown"
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(__file__)
            )
            if result.returncode == 0:
                build_info = result.stdout.strip()
        except:
            # Fall back to timestamp
            build_info = str(int(time.time()))

        # Detect backend
        backend = "torch"
        try:
            import torch
            if torch.backends.mps.is_available():
                backend = "torch-mps"
            elif torch.cuda.is_available():
                backend = "torch-cuda"
        except:
            backend = "cpu"

        data = {
            "engine": "yolo",
            "model": WEIGHTS,
            "build": build_info,
            "backend": backend,
            "device": device
        }

        return UnifiedResponse(ok=True, data=data)

    except Exception as e:
        return UnifiedResponse(
            ok=False,
            error={"code": "VERSION_ERROR", "msg": str(e)}
        )


@app.get("/yolo/mode", response_model=UnifiedResponse)
async def get_yolo_mode():
    """
    Get current YOLO execution mode and configuration.
    """
    try:
        data = {
            "mode": YOLO_MODE,
            "remote_url": YOLO_REMOTE_URL,
            "timeout": YOLO_TIMEOUT,
            "local_model": WEIGHTS,
            "local_device": device
        }
        return UnifiedResponse(ok=True, data=data)
    except Exception as e:
        return UnifiedResponse(
            ok=False,
            error={"code": "MODE_ERROR", "msg": str(e)}
        )


@app.post("/yolo/mode", response_model=UnifiedResponse)
async def set_yolo_mode(
    mode: str = Form(...),  # local|remote|hybrid
    remote_url: Optional[str] = Form(default=None),
    timeout: Optional[int] = Form(default=None)
):
    """
    Dynamically change YOLO execution mode.
    """
    try:
        global YOLO_MODE, YOLO_REMOTE_URL, YOLO_TIMEOUT

        if mode not in ["local", "remote", "hybrid"]:
            return UnifiedResponse(
                ok=False,
                error={"code": "INVALID_MODE", "msg": "Mode must be one of: local, remote, hybrid"}
            )

        YOLO_MODE = mode

        if remote_url:
            YOLO_REMOTE_URL = remote_url

        if timeout:
            YOLO_TIMEOUT = timeout

        # Validate remote configuration if using remote/hybrid
        if mode in ["remote", "hybrid"] and not YOLO_REMOTE_URL:
            return UnifiedResponse(
                ok=False,
                error={"code": "MISSING_REMOTE_URL", "msg": "remote_url required for remote/hybrid mode"}
            )

        data = {
            "mode": YOLO_MODE,
            "remote_url": YOLO_REMOTE_URL,
            "timeout": YOLO_TIMEOUT,
            "message": f"YOLO mode changed to: {mode}"
        }

        return UnifiedResponse(ok=True, data=data)

    except Exception as e:
        return UnifiedResponse(
            ok=False,
            error={"code": "MODE_CHANGE_ERROR", "msg": str(e)}
        )


# ========== V1 API - Unified YOLO+LLM Decision Service ==========

# Import new schemas and dependencies
try:
    from schemas import (
        PickRequest, PickResponse, VerifyRequest, VerifyResponse,
        AnchorResolveRequest, AnchorResolveResponse, AutoStepPatchRequest, AutoStepPatchResponse,
        AutoStepRequest,
        ErrorResponse, HealthStatus
    )
    from dependencies import get_orchestrator, get_services_health, startup_hook, shutdown_hook

    # Add startup and shutdown event handlers
    app.add_event_handler("startup", startup_hook)
    app.add_event_handler("shutdown", shutdown_hook)

except ImportError as e:
    logger.warning(f"V1 API dependencies not available: {e}")


# Helper function to decode image from request
def decode_image_to_bgr(image_spec) -> np.ndarray:
    """Convert image spec to BGR numpy array"""
    import base64
    import cv2
    from PIL import Image
    import io

    # Handle base64 image data
    image_data = image_spec.base64
    if image_data.startswith('data:image'):
        image_data = image_data.split(',', 1)[1]

    # Decode base64 to bytes
    image_bytes = base64.b64decode(image_data)

    # Convert to PIL image
    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Convert to BGR numpy array
    rgb_array = np.array(pil_image)
    bgr_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)

    return bgr_array


def _autostep_headers(http_request: Optional[Request], request_id: Optional[str], operation_id: Optional[str]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if request_id:
        headers["X-Request-Id"] = str(request_id)
    if operation_id:
        headers["X-Operation-Id"] = str(operation_id)
    try:
        obs_id = str(getattr(http_request.state, "obs_id", "") if http_request is not None else "")
        if obs_id:
            headers["X-Obs-Id"] = obs_id
    except Exception:
        pass
    return headers


def _autostep_json(
    payload: Dict[str, Any],
    *,
    status: int = 200,
    http_request: Optional[Request] = None,
    request_id: Optional[str] = None,
    operation_id: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
):
    headers = _autostep_headers(http_request, request_id, operation_id)
    if extra_headers:
        headers.update({str(k): str(v) for k, v in extra_headers.items()})
    return JSONResponse(
        status_code=status,
        content=payload,
        headers=headers,
    )


def _autostep_error(
    status: int,
    code: str,
    message: str,
    *,
    http_request: Optional[Request] = None,
    request_id: Optional[str] = None,
    operation_id: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
):
    return _autostep_json(
        {
            "ok": False,
            "status": status,
            "code": code,
            "message": message,
        },
        status=status,
        http_request=http_request,
        request_id=request_id,
        operation_id=operation_id,
        extra_headers=extra_headers,
    )


def _autostep_stage(
    http_request: Optional[Request],
    *,
    stage: str,
    request_id: str,
    operation_id: str,
    phase: Optional[str],
    started_at: float,
    **extra: Any,
) -> None:
    elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
    payload = {
        "stage": stage,
        "request_id": request_id,
        "operation_id": operation_id,
        "phase": phase,
        "elapsed_ms": elapsed_ms,
    }
    payload.update(extra or {})
    _obs_event("autostep.stage", request=http_request, **payload)


def _get_trace_request_id(request: AutoStepRequest) -> str:
    if request.request_id:
        return str(request.request_id)
    trace = request.trace or {}
    for key in ("requestId", "request_id"):
        if trace.get(key):
            return str(trace.get(key))
    return f"req_{uuid.uuid4().hex[:16]}"


def _get_operation_id(request: AutoStepRequest) -> str:
    if request.operation_id:
        return str(request.operation_id)
    trace = request.trace or {}
    for key in ("operationId", "operation_id"):
        if trace.get(key):
            return str(trace.get(key))
    return f"op_{uuid.uuid4().hex[:16]}"


def _is_provider_vision_capable(provider: Optional[str]) -> bool:
    prov = (provider or "").strip().lower()
    # DeepSeek text endpoint in this code path does not reliably support image_url payload.
    return prov in {"gemini", "openai", "nvidia", "nim", "nvidia_openai", "ollama"}


def _provider_is_configured(provider: str) -> bool:
    prov = provider.strip().lower()
    if prov == "openai":
        return bool(os.getenv("OPENAI_API_KEY"))
    if prov == "gemini":
        return bool(os.getenv("GEMINI_API_KEY"))
    if prov in {"nvidia", "nim", "nvidia_openai"}:
        return bool(os.getenv("NVIDIA_API_KEY") or os.getenv("NVIDIA_NGC_API_KEY"))
    if prov == "ollama":
        return True
    if prov in {"deepseek", "deepseek_v3", "deepseek-r1", "deepseek_v1", "ds"}:
        return bool(os.getenv("DEEPSEEK_API_KEY"))
    return False


def _default_model_for_provider(provider: str) -> str:
    prov = provider.strip().lower()
    if prov == "openai":
        return os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if prov == "gemini":
        return os.getenv("GEMINI_MODEL", os.getenv("LLM_MODEL", "gemini-2.5-flash-lite"))
    if prov in {"nvidia", "nim", "nvidia_openai"}:
        return os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-r1")
    if prov == "ollama":
        return os.getenv("OLLAMA_MODEL", "qwen3.5:4b")
    if prov in {"deepseek", "deepseek_v3", "deepseek-r1", "deepseek_v1", "ds"}:
        return os.getenv("DEEPSEEK_MODEL", "deepseek-v3")
    return os.getenv("LLM_MODEL", "gpt-4o-mini")


def _select_provider_model(
    requested_provider: Optional[str],
    requested_model: Optional[str],
    *,
    need_vision: bool,
) -> Tuple[str, str]:
    # Prioritize: 1. Requested explicitly, 2. Env variable LLM_PROVIDER, 3. Hardcoded fallback logic
    req_provider = (requested_provider or os.getenv("LLM_PROVIDER") or "").strip().lower() or None
    req_model = (requested_model or os.getenv("LLM_MODEL") or "").strip() or None

    if req_provider and _provider_is_configured(req_provider):
        if (not need_vision) or _is_provider_vision_capable(req_provider):
            return req_provider, (req_model or _default_model_for_provider(req_provider))

    if need_vision:
        fallback_order = [
            os.getenv("AUTOSTEP_VISION_PROVIDER", "").strip().lower(),
            "ollama",
            "openai",
            "gemini",
            "nvidia",
        ]
    else:
        fallback_order = [
            os.getenv("AUTOSTEP_TEXT_PROVIDER", "").strip().lower(),
            req_provider or "",
            "deepseek",
            "openai",
            "gemini",
            "nvidia",
            "ollama",
        ]

    for prov in fallback_order:
        if not prov:
            continue
        if need_vision and not _is_provider_vision_capable(prov):
            continue
        if _provider_is_configured(prov):
            env_model = (
                os.getenv("AUTOSTEP_VISION_MODEL")
                if need_vision
                else os.getenv("AUTOSTEP_TEXT_MODEL")
            )
            return prov, (req_model if prov == req_provider and req_model else env_model or _default_model_for_provider(prov))

    # Final safe fallback for local testing
    return "ollama", _default_model_for_provider("ollama")


def _extract_image_from_content_items(content_items: List[Dict[str, Any]]) -> Optional[Tuple[str, str]]:
    for item in content_items:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "image_url":
            continue
        image_url = item.get("image_url")
        if isinstance(image_url, dict):
            url = image_url.get("url")
        else:
            url = image_url
        if not isinstance(url, str):
            continue
        if url.startswith("data:image/") and ";base64," in url:
            header, b64 = url.split(",", 1)
            fmt = header.split(";")[0].split("/")[1]
            return b64, fmt
    return None


def _resolve_autostep_image(request: AutoStepRequest) -> Optional[Tuple[str, str]]:
    # Preferred contract
    if request.image and request.image.base64:
        b64 = request.image.base64
        if b64.startswith("data:image") and "," in b64:
            head, payload = b64.split(",", 1)
            fmt = head.split(";")[0].split("/")[1]
            return payload, fmt
        return b64, (request.image.format or "png")

    # Compatibility: top-level content
    if request.content:
        out = _extract_image_from_content_items(request.content)
        if out:
            return out

    # Compatibility: messages[].content[].image_url
    if request.messages:
        for msg in request.messages:
            content = msg.get("content")
            if isinstance(content, list):
                out = _extract_image_from_content_items(content)
                if out:
                    return out
    return None


def _canon_app_name(name: Optional[str]) -> str:
    s = str(name or "").strip().lower()
    if not s:
        return ""
    # Keep canonicalization simple and robust for common desktop app aliases.
    s = s.replace("google ", "").replace("microsoft ", "").replace(" app", "")
    s = s.replace("浏览器", "browser").replace("谷歌", "chrome").replace("微信", "wechat")
    return "".join(ch for ch in s if ch.isalnum())


def _same_app_name(a: Optional[str], b: Optional[str]) -> bool:
    ca = _canon_app_name(a)
    cb = _canon_app_name(b)
    if not ca or not cb:
        return True
    return ca == cb or ca in cb or cb in ca


def _extract_observation_apps(request: AutoStepRequest) -> Tuple[Optional[str], Optional[str]]:
    obs = request.observation if isinstance(request.observation, dict) else {}
    cap = obs.get("capture") if isinstance(obs.get("capture"), dict) else {}
    active = obs.get("active") if isinstance(obs.get("active"), dict) else {}
    owner_name = cap.get("owner_name")
    active_name = active.get("app_name")
    return (str(owner_name) if isinstance(owner_name, str) else None,
            str(active_name) if isinstance(active_name, str) else None)


def _build_autostep_prompt(request: AutoStepRequest, phase: str) -> List[Dict[str, Any]]:
    if phase == "planner_next":
        contract = (
            "Return JSON only. Choose one: "
            '{"done": true, "reason": "..."} '
            "OR "
            '{"tool_call":{"action":"...","params":{...}},"reason":"...","selected_id":"optional"}'
        )
        user_payload = {
            "goal": request.goal,
            "platform_id": request.platform_id,
            "sig_key": request.sig_key,
            "observation": request.observation or {},
            "blacklist": request.blacklist or [],
        }
    else:
        contract = (
            'Return JSON only: {"ok": true, "reason": "..."}'
        )
        user_payload = {
            "goal": request.goal,
            "platform_id": request.platform_id,
            "sig_key": request.sig_key,
            "tool_call": request.tool_call or {},
            "result": request.result or {},
            "observation_after": request.observation_after or {},
        }

    return [
        {"role": "user", "parts": [{"text": contract + "\n\nInput JSON:\n" + json.dumps(user_payload, ensure_ascii=False)}]}
    ]


_AUTOSTEP_TOOL_PLANNER_ACTIONS = {
    "keyboard.type_text",
    "keyboard.hotkey",
    "keyboard.press",
    "wait.sleep",
}


def _normalize_autostep_tool_call(raw: Any) -> Optional[Dict[str, Any]]:
    """Normalize planner tool calls to the action names nbclient can execute."""
    if not isinstance(raw, dict):
        return None
    action = raw.get("action")
    params = raw.get("params")
    if not isinstance(action, str):
        return None
    action_norm = action.strip()
    if action_norm in {"type_text", "keyboard.type"}:
        action_norm = "keyboard.type_text"
    elif action_norm in {"hotkey", "key_combo", "keyboard.key_combo"}:
        action_norm = "keyboard.hotkey"
    elif action_norm in {"press", "key", "keyboard.key"}:
        action_norm = "keyboard.press"
    elif action_norm in {"wait", "ui.wait"}:
        action_norm = "wait.sleep"
    if action_norm == "keyboard.type_text":
        p = params if isinstance(params, dict) else {}
        text = p.get("text")
        if not isinstance(text, str) or not text:
            return None
        return {
            "action": action_norm,
            "params": {
                "text": text,
                "interval": float(p.get("interval", 0.02) or 0.02),
                "enter_after": bool(p.get("enter_after", p.get("press_enter", False))),
            },
        }
    if action_norm == "keyboard.hotkey":
        p = params if isinstance(params, dict) else {}
        keys = p.get("keys")
        if isinstance(keys, str):
            keys = [part.strip() for part in keys.replace("+", ",").split(",") if part.strip()]
        if not isinstance(keys, list) or not keys:
            return None
        return {"action": action_norm, "params": {"keys": [str(k) for k in keys if str(k).strip()]}}
    if action_norm == "keyboard.press":
        p = params if isinstance(params, dict) else {}
        key = p.get("key")
        if not isinstance(key, str) or not key.strip():
            return None
        return {"action": action_norm, "params": {"key": key.strip()}}
    if action_norm == "wait.sleep":
        p = params if isinstance(params, dict) else {}
        ms = p.get("ms", p.get("duration_ms", 800))
        try:
            ms_int = max(50, min(10000, int(ms)))
        except Exception:
            ms_int = 800
        return {"action": action_norm, "params": {"ms": ms_int}}
    return None


def _build_autostep_tool_planner_prompt(request: AutoStepRequest) -> List[Dict[str, Any]]:
    """Ask LLM whether the next step is a safe keyboard/wait action before visual click picking."""
    obs = request.observation if isinstance(request.observation, dict) else {}
    browser = obs.get("browser") if isinstance(obs.get("browser"), dict) else {}
    payload = {
        "goal": request.goal,
        "platform_id": request.platform_id,
        "sig_key": request.sig_key,
        "active_tab": browser.get("active_tab") if isinstance(browser, dict) else None,
        "page_text_preview": (browser.get("text") or browser.get("page_text") or "")[:1200] if isinstance(browser, dict) else "",
        "recent_observation_keys": sorted(list(obs.keys()))[:30],
    }
    contract = (
        "Return JSON only. Decide whether the next action should be a keyboard/wait action. "
        "Allowed non-click tool calls are exactly: "
        "keyboard.type_text, keyboard.hotkey, keyboard.press, wait.sleep. "
        "Use keyboard.type_text when the goal says to input/type/search text and the input field is already focused, "
        "or when the goal explicitly asks for typing as this step. "
        "Set enter_after=true when the goal asks to search/submit after typing. "
        "If the next action should be a visual mouse click, return "
        "{\"delegate_to_visual_picker\":true,\"reason\":\"...\"}. "
        "Never return browser DOM write/inject actions. "
        "Examples: "
        "{\"tool_call\":{\"action\":\"keyboard.type_text\",\"params\":{\"text\":\"买车\",\"enter_after\":true}},\"reason\":\"type search text\"} "
        "{\"delegate_to_visual_picker\":true,\"reason\":\"need click target\"}."
    )
    return [
        {"role": "user", "parts": [{"text": contract + "\n\nInput JSON:\n" + json.dumps(payload, ensure_ascii=False)}]}
    ]


@app.post("/v1/autostep")
async def v1_autostep(http_request: Request, request: AutoStepRequest):
    """AutoStep planner endpoint supporting planner_next and planner_report."""
    phase = request.phase
    request_id = _get_trace_request_id(request)
    operation_id = _get_operation_id(request)
    started_at = time.perf_counter()
    autostep_debug_headers: Dict[str, str] = {
        "X-Autostep-Phase": str(phase or ""),
    }
    response_status_code = 500
    response_ok = False
    response_code = "UNSET"
    sem_acquired = False

    def _mark_response(status_code: int, ok: bool, code: str) -> None:
        nonlocal response_status_code, response_ok, response_code
        response_status_code = int(status_code)
        response_ok = bool(ok)
        response_code = str(code)

    _autostep_stage(
        http_request,
        stage="inbound",
        request_id=request_id,
        operation_id=operation_id,
        phase=phase,
        started_at=started_at,
    )
    _obs_event(
        "autostep.start",
        request=http_request,
        phase=phase,
        request_id=request_id,
        operation_id=operation_id,
        provider=request.provider,
        model=request.model,
    )

    try:
        queue_timeout_sec = max(0.1, float(AUTOSTEP_QUEUE_TIMEOUT_MS) / 1000.0)
        try:
            await asyncio.wait_for(_AUTOSTEP_SEM.acquire(), timeout=queue_timeout_sec)
            sem_acquired = True
        except asyncio.TimeoutError:
            _autostep_stage(
                http_request,
                stage="exception",
                request_id=request_id,
                operation_id=operation_id,
                phase=phase,
                started_at=started_at,
                error_type="queue_timeout",
                queue_timeout_ms=AUTOSTEP_QUEUE_TIMEOUT_MS,
            )
            _mark_response(503, False, "BUSY")
            return _autostep_error(
                503,
                "BUSY",
                "autostep overloaded",
                http_request=http_request,
                request_id=request_id,
                operation_id=operation_id,
                extra_headers=autostep_debug_headers,
            )

        if phase == "planner_report":
            provider, model = _select_provider_model(
                request.provider,
                request.model,
                need_vision=False,
            )
            # DEBUG TOKEN USAGE for planner_report
            obs_size = len(json.dumps(request.observation or {}))
            obs_after_size = len(json.dumps(request.observation_after or {}))
            logger.info(
                "DEBUG_TOKEN_REPORT req=%s op=%s obs=%d obs_after=%d provider=%s model=%s",
                request_id, operation_id, obs_size, obs_after_size, provider, model
            )
            
            logger.info(
                "autostep planner_report req=%s op=%s provider=%s model=%s",
                request_id,
                operation_id,
                provider,
                model,
            )
            # Idempotency: request_id + operation_id
            cache_key = f"{request_id}:{operation_id}"
            with _AUTOSTEP_REPORT_CACHE_LOCK:
                if cache_key in _AUTOSTEP_REPORT_CACHE:
                    _obs_event(
                        "autostep.planner_report.idempotent_hit",
                        request=http_request,
                        request_id=request_id,
                        operation_id=operation_id,
                        provider=provider,
                        model=model,
                    )
                    _mark_response(200, True, "OK")
                    return _autostep_json(
                        {
                            "ok": True,
                            "phase": "planner_report",
                            "operation_id": operation_id,
                            "request_id": request_id,
                            "idempotent": True,
                            "provider": provider,
                            "model": model,
                        },
                        http_request=http_request,
                        request_id=request_id,
                        operation_id=operation_id,
                        extra_headers=autostep_debug_headers,
                    )
                _AUTOSTEP_REPORT_CACHE[cache_key] = {
                    "ts": time.time(),
                    "tool_call": request.tool_call or {},
                    "result": request.result or {},
                    "provider": provider,
                    "model": model,
                }
            _obs_event(
                "autostep.planner_report.accepted",
                request=http_request,
                request_id=request_id,
                operation_id=operation_id,
                provider=provider,
                model=model,
            )
            _mark_response(200, True, "OK")
            return _autostep_json(
                {
                    "ok": True,
                    "phase": "planner_report",
                    "operation_id": operation_id,
                    "request_id": request_id,
                    "provider": provider,
                    "model": model,
                },
                http_request=http_request,
                request_id=request_id,
                operation_id=operation_id,
                extra_headers=autostep_debug_headers,
            )

        # planner_next: image is required, support both image.base64 and content[].image_url
        image_tuple = _resolve_autostep_image(request)
        if image_tuple is None:
            _obs_event(
                "autostep.bad_request",
                request=http_request,
                reason="missing_image",
                phase=phase,
            )
            _mark_response(400, False, "BAD_REQUEST")
            return _autostep_error(
                400,
                "BAD_REQUEST",
                "planner_next requires image.base64 or content[].image_url",
                http_request=http_request,
                request_id=request_id,
                operation_id=operation_id,
                extra_headers=autostep_debug_headers,
            )

        image_b64, image_format = image_tuple
        image_source = "image.base64" if (request.image and request.image.base64) else "content_or_messages.image_url"
        try:
            image_bytes = base64.b64decode(image_b64)
        except Exception:
            _obs_event(
                "autostep.bad_request",
                request=http_request,
                reason="invalid_base64_image",
                phase=phase,
            )
            _mark_response(400, False, "BAD_REQUEST")
            return _autostep_error(
                400,
                "BAD_REQUEST",
                "invalid base64 image payload",
                http_request=http_request,
                request_id=request_id,
                operation_id=operation_id,
                extra_headers=autostep_debug_headers,
            )
        image_sha1 = hashlib.sha1(image_bytes).hexdigest()
        autostep_debug_headers.update(
            {
                "X-Autostep-Image-Received": "1",
                "X-Autostep-Image-Bytes": str(len(image_bytes)),
                "X-Autostep-Image-Format": str(image_format or ""),
                "X-Autostep-Image-Sha1": image_sha1[:12],
            }
        )
        _obs_event(
            "autostep.image.received",
            request=http_request,
            request_id=request_id,
            operation_id=operation_id,
            image_source=image_source,
            image_format=image_format,
            image_bytes=len(image_bytes),
            image_sha1=image_sha1[:16],
        )
        _autostep_stage(
            http_request,
            stage="image_decode_done",
            request_id=request_id,
            operation_id=operation_id,
            phase=phase,
            started_at=started_at,
            image_source=image_source,
            image_format=image_format,
            image_bytes=len(image_bytes),
        )

        # Guard: if observation says frontmost app mismatches captured window owner,
        # avoid any click decision and ask client to stabilize focus first.
        enforce_app_consistency = os.getenv("AUTOSTEP_ENFORCE_APP_CONSISTENCY", "1").strip().lower() not in {"0", "false", "no", "off"}
        owner_name, active_name = _extract_observation_apps(request)
        if enforce_app_consistency and owner_name and active_name and (not _same_app_name(owner_name, active_name)):
            _obs_event(
                "autostep.guard.app_mismatch",
                request=http_request,
                request_id=request_id,
                operation_id=operation_id,
                owner_name=owner_name,
                active_name=active_name,
            )
            _mark_response(200, True, "OK")
            return _autostep_json(
                {
                    "ok": True,
                    "phase": "planner_next",
                    "done": False,
                    "operation_id": operation_id,
                    "request_id": request_id,
                    "tool_call": {"action": "wait.sleep", "params": {"ms": 500}},
                    "reason": f"app_mismatch: active={active_name}, capture_owner={owner_name}",
                    "selected_id": "APP_MISMATCH",
                    "engine": "guard",
                },
                http_request=http_request,
                request_id=request_id,
                operation_id=operation_id,
                extra_headers=autostep_debug_headers,
            )

        provider, model = _select_provider_model(
            request.provider,
            request.model,
            need_vision=True,
        )
        logger.info(
            "autostep planner_next req=%s op=%s provider=%s model=%s goal=%s",
            request_id,
            operation_id,
            provider,
            model,
            (request.goal or "")[:120],
        )

        # LLM tool planner: allow the model to choose safe keyboard/wait actions
        # before the legacy visual picker, which is intentionally click-only.
        use_tool_planner = os.getenv("AUTOSTEP_TOOL_PLANNER", "1").strip().lower() not in {"0", "false", "no", "off"}
        if use_tool_planner:
            try:
                from core.llm_client import call_llm, extract_text_generic
                from core.gemini_client import parse_first_json

                tool_messages = _build_autostep_tool_planner_prompt(request)
                _autostep_stage(
                    http_request,
                    stage="model_call_start",
                    request_id=request_id,
                    operation_id=operation_id,
                    phase=phase,
                    started_at=started_at,
                    model_path="tool_planner",
                    provider=provider,
                    model=model,
                )

                def _run_tool_planner() -> Dict[str, Any]:
                    raw_resp = call_llm(
                        provider=provider,
                        model=model,
                        messages=tool_messages,
                        image_path=None,
                        temperature=0.0,
                    )
                    parsed = raw_resp.get("parsed") if isinstance(raw_resp, dict) else None
                    if isinstance(parsed, dict):
                        return parsed
                    text = extract_text_generic(raw_resp)
                    if text:
                        try:
                            return json.loads(text)
                        except Exception:
                            parsed_text = parse_first_json(text)
                            if isinstance(parsed_text, dict):
                                return parsed_text
                    content = raw_resp.get("content") if isinstance(raw_resp, dict) else None
                    if isinstance(content, str) and content.strip():
                        parsed_content = parse_first_json(content)
                        if isinstance(parsed_content, dict):
                            return parsed_content
                    raise RuntimeError("tool planner returned no parseable JSON")

                tool_plan = await asyncio.wait_for(
                    asyncio.to_thread(_run_tool_planner),
                    timeout=max(3.0, min(float(AUTOSTEP_MODEL_TIMEOUT_SEC), float(os.getenv("AUTOSTEP_TOOL_PLANNER_TIMEOUT_SEC", "20")))),
                )
                tool_call_plan = _normalize_autostep_tool_call(tool_plan.get("tool_call"))
                _autostep_stage(
                    http_request,
                    stage="model_call_done",
                    request_id=request_id,
                    operation_id=operation_id,
                    phase=phase,
                    started_at=started_at,
                    model_path="tool_planner",
                    has_tool_call=isinstance(tool_call_plan, dict),
                    delegated=bool(tool_plan.get("delegate_to_visual_picker")),
                )
                if isinstance(tool_call_plan, dict) and tool_call_plan.get("action") in _AUTOSTEP_TOOL_PLANNER_ACTIONS:
                    response_tool: Dict[str, Any] = {
                        "ok": True,
                        "phase": "planner_next",
                        "done": False,
                        "operation_id": operation_id,
                        "request_id": request_id,
                        "tool_call": tool_call_plan,
                        "reason": str(tool_plan.get("reason") or "LLM tool planner selected safe non-click action"),
                        "provider": provider,
                        "model": model,
                        "selected_id": "TOOL_PLANNER",
                        "engine": "tool_planner",
                    }
                    _obs_event(
                        "autostep.tool_planner.done",
                        request=http_request,
                        request_id=request_id,
                        operation_id=operation_id,
                        action=tool_call_plan.get("action"),
                        provider=provider,
                        model=model,
                    )
                    _mark_response(200, True, "OK")
                    return _autostep_json(
                        response_tool,
                        http_request=http_request,
                        request_id=request_id,
                        operation_id=operation_id,
                        extra_headers=autostep_debug_headers,
                    )
            except asyncio.TimeoutError:
                _obs_event(
                    "autostep.tool_planner.timeout",
                    request=http_request,
                    request_id=request_id,
                    operation_id=operation_id,
                )
            except Exception as tool_err:
                _obs_event(
                    "autostep.tool_planner.error",
                    request=http_request,
                    request_id=request_id,
                    operation_id=operation_id,
                    error=str(tool_err),
                )

        # Preferred path: run server-side YOLO+LLM execution chain and return click target.
        use_server_executor = os.getenv("AUTOSTEP_SERVER_EXECUTOR", "1").strip().lower() not in {"0", "false", "no", "off"}
        if use_server_executor:
            try:
                _autostep_stage(
                    http_request,
                    stage="model_call_start",
                    request_id=request_id,
                    operation_id=operation_id,
                    phase=phase,
                    started_at=started_at,
                    model_path="executor_pick",
                    provider=provider,
                    model=model,
                )
                _obs_event(
                    "autostep.executor.pick.start",
                    request=http_request,
                    request_id=request_id,
                    operation_id=operation_id,
                    provider=provider,
                    model=model,
                )
                # Build PickRequest from autostep payload.
                from schemas import PickRequest, ImageSpec, CaptureSpec, ContextSpec, OptionsSpec
                from dependencies import get_orchestrator
                from PIL import Image as _PILImage
                import io as _io
                # Read image size for capture spec.
                with _PILImage.open(_io.BytesIO(image_bytes)) as _im:
                    iw, ih = _im.size
                pick_req = PickRequest(
                    image=ImageSpec(base64=image_b64, format=(image_format or "png")),
                    capture=CaptureSpec(mode="full", screen_size=[int(iw), int(ih)], dpr=1.0),
                    context=ContextSpec(
                        workflow_id=(request.trace or {}).get("workflow_id") if isinstance(request.trace, dict) else None,
                        step_id=(request.trace or {}).get("step_id") if isinstance(request.trace, dict) else None,
                        goal=str(request.goal or "continue task"),
                        intent=(request.observation or {}).get("intent") if isinstance(request.observation, dict) else None,
                        vars={"platform_id": request.platform_id, "sig_key": request.sig_key},
                        history=[],
                    ),
                    anchors_known=[],
                    options=OptionsSpec(
                        mode="pick",
                        llm_provider=provider,
                        llm_timeout_ms=int(os.getenv("AUTOSTEP_LLM_TIMEOUT_MS", "30000")),
                        pick_min_conf=float(os.getenv("AUTOSTEP_PICK_MIN_CONF", "0.45")),
                    ),
                    idempotency_key=f"{request_id}:{operation_id}",
                )
                orch = get_orchestrator()
                img_bgr = decode_image_to_bgr(pick_req.image)
                pick_result = await asyncio.wait_for(
                    asyncio.to_thread(orch.pick, img_bgr, pick_req),
                    timeout=AUTOSTEP_MODEL_TIMEOUT_SEC,
                )
                decision = (pick_result or {}).get("decision") if isinstance(pick_result, dict) else {}
                point = decision.get("point_in_capture") if isinstance(decision, dict) else None
                reason_pick = str(decision.get("reason") if isinstance(decision, dict) else "") or "server executor decision"
                conf_pick = decision.get("confidence") if isinstance(decision, dict) else None
                action_pick = str(decision.get("action") if isinstance(decision, dict) else "")
                selected_rank = decision.get("selected_rank") if isinstance(decision, dict) else None
                bbox_pick = decision.get("bbox_in_capture") if isinstance(decision, dict) else None
                llm_debug = decision.get("llm_debug") if isinstance(decision, dict) else None
                _autostep_stage(
                    http_request,
                    stage="model_call_done",
                    request_id=request_id,
                    operation_id=operation_id,
                    phase=phase,
                    started_at=started_at,
                    model_path="executor_pick",
                    action=action_pick,
                    confidence=conf_pick,
                )
                if isinstance(point, list) and len(point) >= 2 and action_pick == "click":
                    # Executor returns point in capture-pixel space.
                    # Convert to global UI coordinates (pyautogui points) when capture metadata exists.
                    x_cap = float(point[0])
                    y_cap = float(point[1])
                    x = int(round(x_cap))
                    y = int(round(y_cap))
                    coord_space = "capture_px"
                    try:
                        obs0 = request.observation if isinstance(request.observation, dict) else {}
                        cap0 = obs0.get("capture") if isinstance(obs0.get("capture"), dict) else {}
                        mode0 = str(cap0.get("mode") or "full").strip().lower()
                        dpr0 = float(cap0.get("dpr") or 1.0)
                        if dpr0 <= 0:
                            dpr0 = 1.0
                        off0 = cap0.get("window_offset")
                        ox = float(off0[0]) if isinstance(off0, list) and len(off0) >= 2 else 0.0
                        oy = float(off0[1]) if isinstance(off0, list) and len(off0) >= 2 else 0.0
                        if mode0 in {"active_window", "region"}:
                            x = int(round((x_cap + ox) / dpr0))
                            y = int(round((y_cap + oy) / dpr0))
                            coord_space = "global_ui"
                        elif mode0 == "full":
                            # Full-screen captures are typically pixel-space; normalize to UI points.
                            x = int(round(x_cap / dpr0))
                            y = int(round(y_cap / dpr0))
                            coord_space = "global_ui"
                    except Exception:
                        pass
                    response_exec: Dict[str, Any] = {
                        "ok": True,
                        "phase": "planner_next",
                        "done": False,
                        "operation_id": operation_id,
                        "request_id": request_id,
                        "tool_call": {"action": "mouse.click", "params": {"x": x, "y": y}},
                        "reason": reason_pick,
                        "provider": provider,
                        "model": model,
                        "selected_id": (f"cand_{int(selected_rank)}" if isinstance(selected_rank, int) and selected_rank > 0 else f"{x}_{y}"),
                        "engine": "server_executor",
                    }
                    if conf_pick is not None:
                        response_exec["confidence"] = conf_pick
                    if isinstance(selected_rank, int) and selected_rank > 0:
                        response_exec["selected_rank"] = int(selected_rank)
                    bbox_out: List[int]
                    if isinstance(bbox_pick, list) and len(bbox_pick) == 4:
                        bbox_out = [int(bbox_pick[0]), int(bbox_pick[1]), int(bbox_pick[2]), int(bbox_pick[3])]
                        response_exec["selected_bbox"] = bbox_out
                    else:
                        px = int(round(x_cap))
                        py = int(round(y_cap))
                        bbox_out = [px, py, px, py]
                        response_exec["selected_bbox"] = bbox_out
                    response_exec["selected_point"] = [x, y]
                    response_exec["selected_point_capture"] = [int(round(x_cap)), int(round(y_cap))]
                    response_exec["coord_space"] = coord_space
                    # Stable top1 target contract for upstream callers.
                    nx = max(0.0, min(1.0, float(x_cap) / max(1.0, float(iw))))
                    ny = max(0.0, min(1.0, float(y_cap) / max(1.0, float(ih))))
                    response_exec["detections"] = [
                        {
                            "id": str(response_exec.get("selected_id") or "top1"),
                            "bbox_xyxy": bbox_out,
                            "click_xy_norm": [nx, ny],
                            "point_xy": [int(round(x_cap)), int(round(y_cap))],
                            "top1": True,
                            "confidence": float(conf_pick) if conf_pick is not None else None,
                        }
                    ]
                    if isinstance(llm_debug, dict):
                        response_exec["llm_debug"] = {
                            "overlay_path": str(llm_debug.get("overlay_path") or ""),
                            "overlay_sha1": str(llm_debug.get("overlay_sha1") or ""),
                        }
                    _obs_event(
                        "autostep.executor.pick.done",
                        request=http_request,
                        request_id=request_id,
                        operation_id=operation_id,
                        action="mouse.click",
                        x=x,
                        y=y,
                        selected_rank=selected_rank,
                        bbox=bbox_pick,
                        llm_overlay_path=(llm_debug or {}).get("overlay_path") if isinstance(llm_debug, dict) else None,
                        llm_overlay_sha1=(llm_debug or {}).get("overlay_sha1") if isinstance(llm_debug, dict) else None,
                        confidence=conf_pick,
                    )
                    _mark_response(200, True, "OK")
                    return _autostep_json(
                        response_exec,
                        http_request=http_request,
                        request_id=request_id,
                        operation_id=operation_id,
                        extra_headers=autostep_debug_headers,
                    )
                # No click returned from executor: safe fallback action.
                _obs_event(
                    "autostep.executor.pick.no_click",
                    request=http_request,
                    request_id=request_id,
                    operation_id=operation_id,
                    decision=_obs_safe(decision),
                )
                _mark_response(404, False, "NOT_FOUND")
                return _autostep_json(
                    {
                        "ok": False,
                        "status": 404,
                        "code": "NOT_FOUND",
                        "phase": "planner_next",
                        "done": False,
                        "operation_id": operation_id,
                        "request_id": request_id,
                        "message": reason_pick or "no clickable target from executor",
                        "reason": reason_pick or "no clickable target from executor",
                        "provider": provider,
                        "model": model,
                        "selected_id": "NO_TARGET",
                        "engine": "server_executor",
                        "detections": [],
                    },
                    status=404,
                    http_request=http_request,
                    request_id=request_id,
                    operation_id=operation_id,
                    extra_headers=autostep_debug_headers,
                )
            except asyncio.TimeoutError:
                _autostep_stage(
                    http_request,
                    stage="exception",
                    request_id=request_id,
                    operation_id=operation_id,
                    phase=phase,
                    started_at=started_at,
                    error_type="model_timeout",
                    model_path="executor_pick",
                    timeout_sec=AUTOSTEP_MODEL_TIMEOUT_SEC,
                )
                _mark_response(504, False, "MODEL_TIMEOUT")
                return _autostep_error(
                    504,
                    "MODEL_TIMEOUT",
                    "planner_next timeout",
                    http_request=http_request,
                    request_id=request_id,
                    operation_id=operation_id,
                    extra_headers=autostep_debug_headers,
                )
            except Exception as exec_err:
                _obs_event(
                    "autostep.executor.pick.error",
                    request=http_request,
                    request_id=request_id,
                    operation_id=operation_id,
                    error=str(exec_err),
                )
                _autostep_stage(
                    http_request,
                    stage="exception",
                    request_id=request_id,
                    operation_id=operation_id,
                    phase=phase,
                    started_at=started_at,
                    error_type="executor_error",
                    detail=str(exec_err),
                )
                logger.warning(f"autostep executor path failed, fallback to planner llm: {exec_err}")

        llm_messages = _build_autostep_prompt(request, "planner_next")
        allow_fallbacks = os.getenv("AUTOSTEP_ALLOW_LLM_FALLBACKS", "0").strip() not in {"0", "false", "False", "no", ""}
        _obs_event(
            "autostep.planner_next.pre_llm",
            request=http_request,
            request_id=request_id,
            operation_id=operation_id,
            provider=provider,
            model=model,
            image_format=image_format,
            image_bytes=len(image_bytes),
            image_sha1=image_sha1[:16],
            allow_fallbacks=allow_fallbacks,
        )

        _autostep_stage(
            http_request,
            stage="model_call_start",
            request_id=request_id,
            operation_id=operation_id,
            phase=phase,
            started_at=started_at,
            model_path="planner_llm",
            provider=provider,
            model=model,
        )
        try:
            # Call LLM with a temporary image file
            from core.llm_client import generate_json

            def _run_generate_json() -> Dict[str, Any]:
                with tempfile.NamedTemporaryFile(suffix=f".{image_format or 'png'}", delete=True) as tmp:
                    tmp.write(image_bytes)
                    tmp.flush()
                    return generate_json(
                        messages=llm_messages,
                        image_path=tmp.name,
                        provider=provider,
                        model=model,
                        temperature=0.2,
                        allow_fallbacks=allow_fallbacks,
                    )

            llm_result = await asyncio.wait_for(
                asyncio.to_thread(_run_generate_json),
                timeout=AUTOSTEP_MODEL_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            _autostep_stage(
                http_request,
                stage="exception",
                request_id=request_id,
                operation_id=operation_id,
                phase=phase,
                started_at=started_at,
                error_type="model_timeout",
                model_path="planner_llm",
                timeout_sec=AUTOSTEP_MODEL_TIMEOUT_SEC,
            )
            _mark_response(504, False, "MODEL_TIMEOUT")
            return _autostep_error(
                504,
                "MODEL_TIMEOUT",
                "planner_next timeout",
                http_request=http_request,
                request_id=request_id,
                operation_id=operation_id,
                extra_headers=autostep_debug_headers,
            )
        _autostep_stage(
            http_request,
            stage="model_call_done",
            request_id=request_id,
            operation_id=operation_id,
            phase=phase,
            started_at=started_at,
            model_path="planner_llm",
            done=bool(llm_result.get("done") is True),
            has_tool_call=isinstance(llm_result.get("tool_call"), dict),
        )
        _obs_event(
            "autostep.planner_next.post_llm",
            request=http_request,
            request_id=request_id,
            operation_id=operation_id,
            done=bool(llm_result.get("done") is True),
            has_tool_call=isinstance(llm_result.get("tool_call"), dict),
            selected_id=llm_result.get("selected_id"),
        )

        reason = str(llm_result.get("reason") or "autostep decision")
        selected_id = llm_result.get("selected_id")

        if llm_result.get("done") is True:
            _obs_event(
                "autostep.done",
                request=http_request,
                request_id=request_id,
                operation_id=operation_id,
                provider=provider,
                model=model,
                done=True,
            )
            _mark_response(200, True, "OK")
            return _autostep_json(
                {
                    "ok": True,
                    "phase": "planner_next",
                    "operation_id": operation_id,
                    "request_id": request_id,
                    "done": True,
                    "reason": reason,
                    "provider": provider,
                    "model": model,
                },
                http_request=http_request,
                request_id=request_id,
                operation_id=operation_id,
                extra_headers=autostep_debug_headers,
            )

        tool_call = llm_result.get("tool_call")
        if not isinstance(tool_call, dict):
            action = llm_result.get("action")
            params = llm_result.get("params")
            if isinstance(action, str):
                tool_call = {"action": action, "params": params if isinstance(params, dict) else {}}

        if not isinstance(tool_call, dict) or not isinstance(tool_call.get("action"), str):
            # Defensive fallback: always return actionable response
            tool_call = {"action": "wait.sleep", "params": {"ms": 800}}
            reason = f"{reason}; fallback_action=wait.sleep"

        # Compatibility normalization: clients may not register ui.wait
        if isinstance(tool_call, dict) and str(tool_call.get("action") or "").strip() == "ui.wait":
            tool_call = {
                "action": "wait.sleep",
                "params": tool_call.get("params") if isinstance(tool_call.get("params"), dict) else {"ms": 800},
            }

        response: Dict[str, Any] = {
            "ok": True,
            "phase": "planner_next",
            "done": False,
            "operation_id": operation_id,
            "request_id": request_id,
            "tool_call": {
                "action": tool_call.get("action"),
                "params": tool_call.get("params") if isinstance(tool_call.get("params"), dict) else {},
            },
            "reason": reason,
            "provider": provider,
            "model": model,
        }
        if selected_id is not None:
            response["selected_id"] = selected_id
        elif (response.get("tool_call") or {}).get("action") == "wait.sleep":
            response["selected_id"] = "NO_TARGET"
        _obs_event(
            "autostep.done",
            request=http_request,
            request_id=request_id,
            operation_id=operation_id,
            provider=provider,
            model=model,
            done=False,
            tool_action=response.get("tool_call", {}).get("action"),
        )
        if (response.get("tool_call") or {}).get("action") == "wait.sleep":
            not_found_payload = {
                "ok": False,
                "status": 404,
                "code": "NOT_FOUND",
                "phase": "planner_next",
                "done": False,
                "operation_id": operation_id,
                "request_id": request_id,
                "message": reason,
                "reason": reason,
                "provider": provider,
                "model": model,
                "selected_id": "NO_TARGET",
                "engine": "planner_llm",
                "detections": [],
            }
            _mark_response(404, False, "NOT_FOUND")
            return _autostep_json(
                not_found_payload,
                status=404,
                http_request=http_request,
                request_id=request_id,
                operation_id=operation_id,
                extra_headers=autostep_debug_headers,
            )
        _mark_response(200, True, "OK")
        return _autostep_json(
            response,
            http_request=http_request,
            request_id=request_id,
            operation_id=operation_id,
            extra_headers=autostep_debug_headers,
        )

    except Exception as e:
        logger.error(f"/v1/autostep error req={request_id} op={operation_id}: {e}")
        _autostep_stage(
            http_request,
            stage="exception",
            request_id=request_id,
            operation_id=operation_id,
            phase=phase,
            started_at=started_at,
            error_type="exception",
            detail=str(e),
        )
        _obs_event(
            "autostep.error",
            request=http_request,
            request_id=request_id,
            operation_id=operation_id,
            error=str(e),
        )
        _mark_response(500, False, "AUTOSTEP_ERROR")
        return _autostep_error(
            500,
            "AUTOSTEP_ERROR",
            str(e),
            http_request=http_request,
            request_id=request_id,
            operation_id=operation_id,
            extra_headers=autostep_debug_headers,
        )
    finally:
        if sem_acquired:
            _AUTOSTEP_SEM.release()
        duration_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
        _autostep_stage(
            http_request,
            stage="response_sent",
            request_id=request_id,
            operation_id=operation_id,
            phase=phase,
            started_at=started_at,
            status_code=response_status_code,
            ok=response_ok,
            code=response_code,
            duration_ms=duration_ms,
        )
        _obs_event(
            "autostep.response_sent",
            request=http_request,
            request_id=request_id,
            operation_id=operation_id,
            phase=phase,
            status_code=response_status_code,
            ok=response_ok,
            code=response_code,
            duration_ms=duration_ms,
        )


@app.post("/autostep")
async def autostep_alias(http_request: Request, request: AutoStepRequest):
    """Backward-compatible alias for /v1/autostep."""
    _obs_event(
        "autostep.alias.forwarded",
        request=http_request,
        from_path="/autostep",
        to_path="/v1/autostep",
    )
    return await v1_autostep(http_request, request)


@app.get("/v1/observability/recent", response_model=UnifiedResponse)
async def v1_observability_recent(limit: int = Query(default=100, ge=1, le=1000)):
    """Return recent API observability events."""
    try:
        path_latest = os.path.join(API_OBS_DIR, "events.latest.jsonl")
        if not os.path.exists(path_latest):
            return UnifiedResponse(ok=True, data={"events": [], "count": 0, "path": path_latest})
        with open(path_latest, "r", encoding="utf-8") as f:
            lines = f.readlines()
        picked = lines[-limit:]
        events: List[Dict[str, Any]] = []
        for line in picked:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                events.append({"raw": _obs_clip_text(line, 2048)})
        return UnifiedResponse(
            ok=True,
            data={"events": events, "count": len(events), "path": path_latest},
        )
    except Exception as e:
        return UnifiedResponse(ok=False, error={"code": "OBSERVABILITY_READ_ERROR", "msg": str(e)})


@app.get("/v1/observability/request/{request_id}", response_model=UnifiedResponse)
async def v1_observability_by_request(request_id: str, limit: int = Query(default=200, ge=1, le=5000)):
    """Find observability events for a given request_id."""
    try:
        path_latest = os.path.join(API_OBS_DIR, "events.latest.jsonl")
        if not os.path.exists(path_latest):
            return UnifiedResponse(ok=True, data={"events": [], "count": 0, "path": path_latest, "request_id": request_id})
        hits: List[Dict[str, Any]] = []
        with open(path_latest, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except Exception:
                    continue
                # Match from event payload, raw request json, or response json.
                p = evt.get("payload") if isinstance(evt.get("payload"), dict) else {}
                req = evt.get("request") if isinstance(evt.get("request"), dict) else {}
                req_json = req.get("json") if isinstance(req.get("json"), dict) else {}
                resp = evt.get("response") if isinstance(evt.get("response"), dict) else {}
                resp_json = resp.get("json") if isinstance(resp.get("json"), dict) else {}
                if (
                    str(p.get("request_id", "")) == request_id
                    or str(req_json.get("request_id", "")) == request_id
                    or str(resp_json.get("request_id", "")) == request_id
                ):
                    hits.append(evt)
        if len(hits) > limit:
            hits = hits[-limit:]
        return UnifiedResponse(ok=True, data={"events": hits, "count": len(hits), "path": path_latest, "request_id": request_id})
    except Exception as e:
        return UnifiedResponse(ok=False, error={"code": "OBSERVABILITY_LOOKUP_ERROR", "msg": str(e)})


@app.post("/v1/pick", response_model=UnifiedResponse)
async def v1_pick(request: PickRequest):
    """
    V1 Pick API - End-to-end YOLO+LLM decision making

    Combines YOLO detection, anchor matching, and LLM decision making
    to provide click coordinates and learning anchors.
    """
    try:
        # Get orchestrator instance
        orchestrator = get_orchestrator()

        # Decode image
        img_bgr = decode_image_to_bgr(request.image)

        # Optimize image for token reduction AND compress for file size reduction
        try:
            from core.image_optimizer import LLMImageOptimizer
            from core.image_compress_coords import compress_for_vlm
            import tempfile
            import cv2

            print(f"🔧 API: Starting image optimization for token reduction")
            optimizer = LLMImageOptimizer()

            # Create temp file from BGR image
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                cv2.imwrite(tmp.name, img_bgr)
                temp_path = tmp.name

            # Step 1: Optimize the image for token reduction
            optimized_path, stats = optimizer.optimize_for_llm(temp_path)

            if stats.get('optimized', False):
                # DO NOT overwrite img_bgr with optimized image here.
                # YOLO must run on the original resolution to return accurate coordinates.
                # The orchestrator handles its own resizing for LLM-specific payloads.
                print(f"🚀 API: Image optimized: {stats['reduction_percent']}% token reduction "
                      f"({stats['original_tokens']} → {stats['final_tokens']} tokens)")
            else:
                print(f"📷 API: Image already optimal, no optimization needed")

            # Step 2: Compress the image for file size reduction (target 200KB)
            try:
                print(f"🗜️ API: Starting file compression (target 200KB)")

                # Use optimized image as input for compression
                current_image_path = optimized_path if stats.get('optimized', False) else temp_path
                print(f"🗜️ API: Compressing image: {current_image_path}")

                # Create temp file for compressed output
                with tempfile.NamedTemporaryFile(suffix='.webp', delete=False) as compressed_tmp:
                    compressed_path = compressed_tmp.name

                print(f"🗜️ API: Output path: {compressed_path}")

                # Compress with coordinate mapping
                transform = compress_for_vlm(current_image_path, compressed_path, target_kb=200)
                print(f"🗜️ API: Compression complete, checking results...")

                # Check file size after compression
                import os
                orig_size = os.path.getsize(current_image_path)
                compressed_size = os.path.getsize(compressed_path)
                reduction_percent = ((orig_size - compressed_size) / orig_size) * 100

                print(f"📦 API: File compressed: {reduction_percent:.1f}% size reduction "
                      f"({orig_size//1024}KB → {compressed_size//1024}KB)")
                print(f"🗺️ API: Transform scale: {transform.sx:.3f}x{transform.sy:.3f}")

                # For now, continue with optimized BGR image (compression used for overlay saving)
                # TODO: Integrate compressed images into YOLO pipeline

            except Exception as compress_error:
                print(f"❌ API: Compression failed: {compress_error}")
                import traceback
                traceback.print_exc()

            # Clean up temp files
            try:
                os.unlink(temp_path)
                if optimized_path != temp_path:
                    os.unlink(optimized_path)
                os.unlink(compressed_path)
            except:
                pass

        except Exception as e:
            print(f"⚠️ API: Image optimization/compression failed, using original: {e}")
            # Continue with original image

        # Save original input image to out/originals for comparison
        try:
            import cv2
            key = request.idempotency_key
            os.makedirs(os.path.join("out", "originals"), exist_ok=True)
            cv2.imwrite(os.path.join("out", "originals", f"{key}.png"), img_bgr)
        except Exception:
            pass

        # Process pick request
        try:
            # Log request summary (no image content)
            cap = request.capture
            ctx = request.context
            if cap is not None:
                w = (cap.window_size[0] if cap.window_size else cap.screen_size[0])
                h = (cap.window_size[1] if cap.window_size else cap.screen_size[1])
                screen_info = {"w": w, "h": h, "dpr": cap.dpr}
            else:
                # Capture will be inferred later by orchestrator
                screen_info = {"w": "unknown", "h": "unknown", "dpr": "unknown"}

            jsonlog.info(
                "pick.request",
                svc="yoloapi",
                event="pick.request",
                path="/v1/pick",
                req_id=request.idempotency_key,
                site=((ctx.vars or {}).get("site") if getattr(ctx, 'vars', None) else None),
                screen=screen_info,
                context={"goal": ctx.goal, "intent": getattr(ctx, 'intent', None)}
            )
        except Exception:
            pass

        result = orchestrator.pick(img_bgr, request)

        # Return unified response
        try:
            stage_ms = (result.get("telemetry", {}) or {}).get("stage_lat_ms", {})
            decision = result.get("decision", {}) or {}
            jsonlog.info(
                "pick.response",
                svc="yoloapi",
                event="pick.response",
                path="/v1/pick",
                req_id=request.idempotency_key,
                telemetry={
                    "stages": stage_ms,
                    "cache_hit": (result.get("telemetry", {}) or {}).get("cache_hit"),
                },
                decision={
                    "conf": decision.get("confidence"),
                    "method": ((decision.get("llm", {}) or {}).get("method")),
                }
            )
        except Exception:
            pass
        return UnifiedResponse(ok=True, data=result)

    except Exception as e:
        logger.error(f"V1 Pick API error: {e}")
        return UnifiedResponse(
            ok=False,
            error={
                "code": "PICK_ERROR",
                "message": str(e),
                "req_id": request.idempotency_key
            }
        )


@app.post("/v1/verify", response_model=UnifiedResponse)
async def v1_verify(request: VerifyRequest):
    """
    V1 Verify API - Post-action verification and anchor learning

    Verifies action results against expectations and locks successful anchors.
    """
    try:
        # Get orchestrator instance
        orchestrator = get_orchestrator()

        # Decode image
        img_bgr = decode_image_to_bgr(request.image)

        # Process verify request
        result = orchestrator.verify(img_bgr, request)

        # Return unified response
        return UnifiedResponse(ok=True, data=result)

    except Exception as e:
        logger.error(f"V1 Verify API error: {e}")
        return UnifiedResponse(
            ok=False,
            error={
                "code": "VERIFY_ERROR",
                "message": str(e)
            }
        )


@app.post("/v1/anchors/resolve", response_model=UnifiedResponse)
async def v1_anchors_resolve(request: AnchorResolveRequest):
    """
    V1 Anchors Resolve API - Fast anchor-only element location

    Attempts to locate elements using only anchor matching without YOLO+LLM.
    """
    try:
        # Get orchestrator instance
        orchestrator = get_orchestrator()

        # Decode image
        img_bgr = decode_image_to_bgr(request.image)

        # Process anchor resolve request
        result = orchestrator.resolve_anchors(img_bgr, request)

        # Return unified response
        return UnifiedResponse(ok=True, data=result)

    except Exception as e:
        logger.error(f"V1 Anchors Resolve API error: {e}")
        return UnifiedResponse(
            ok=False,
            error={
                "code": "ANCHOR_RESOLVE_ERROR",
                "message": str(e)
            }
        )


@app.post("/v1/autostep/patch-proposal", response_model=UnifiedResponse)
async def v1_autostep_patch_proposal(request: AutoStepPatchRequest):
    """
    V1 AutoStep Patch Proposal API - Failure recovery suggestions

    Analyzes failure patterns and suggests workflow patches for recovery.
    """
    try:
        # For now, return a placeholder response
        # In a full implementation, this would analyze failure patterns
        # and generate specific patch suggestions

        patches = []
        risk = "low"
        reason = "AutoStep patch generation not yet implemented"

        # Analyze failure context for basic suggestions
        goal = request.context.goal.lower() if request.context.goal else ""
        if "timeout" in goal or "wait" in goal:
            patches.append({
                "op": "insert_before",
                "state": request.context.step_id or "current",
                "action": {"do": "instr.wait", "ms": 1000}
            })
            reason = "Added wait action for timeout issue"

        elif "not found" in goal:
            patches.append({
                "op": "insert_before",
                "state": request.context.step_id or "current",
                "action": {"do": "instr.scroll", "dir": "down", "amount": 300}
            })
            reason = "Added scroll action for element not found"

        result = {
            "patches": patches,
            "risk": risk,
            "reason": reason
        }

        return UnifiedResponse(ok=True, data=result)

    except Exception as e:
        logger.error(f"V1 AutoStep Patch Proposal API error: {e}")
        return UnifiedResponse(
            ok=False,
            error={
                "code": "AUTOSTEP_ERROR",
                "message": str(e)
            }
        )


@app.get("/v1/health", response_model=UnifiedResponse)
async def v1_health():
    """
    V1 Health API - Service health and dependency status

    Returns health status of all service dependencies.
    """
    try:
        health_status = get_services_health()

        # Overall health determination
        overall_ok = health_status.get("dependencies_ok", False)

        return UnifiedResponse(
            ok=overall_ok,
            data={
                "status": "healthy" if overall_ok else "unhealthy",
                "services": health_status,
                "timestamp": time.time()
            }
        )

    except Exception as e:
        logger.error(f"V1 Health API error: {e}")
        return UnifiedResponse(
            ok=False,
            error={
                "code": "HEALTH_CHECK_ERROR",
                "message": str(e)
            }
        )


@app.get("/v1/stats", response_model=UnifiedResponse)
async def v1_stats():
    """
    V1 Stats API - Service statistics and metrics

    Returns operational statistics for monitoring and debugging.
    """
    try:
        # Get orchestrator instance
        orchestrator = get_orchestrator()

        # Get stats from orchestrator
        stats = orchestrator.get_stats()

        return UnifiedResponse(ok=True, data=stats)

    except Exception as e:
        logger.error(f"V1 Stats API error: {e}")
        return UnifiedResponse(
            ok=False,
            error={
                "code": "STATS_ERROR",
                "message": str(e)
            }
        )
