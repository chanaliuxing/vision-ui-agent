# app.py
import io
import os
import time
import base64
from typing import Optional, List, Tuple

import numpy as np
from fastapi import FastAPI, File, UploadFile, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ultralytics import YOLO

# Optional: URL input support
try:
    import requests
    HAS_REQUESTS = True
except Exception:
    HAS_REQUESTS = False

# ---------- Config ----------
DEFAULT_WEIGHTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weights", "model.pt")
WEIGHTS = os.getenv("YOLO_WEIGHTS", DEFAULT_WEIGHTS)
DEFAULT_CONF  = float(os.getenv("YOLO_CONF",  "0.25"))
DEFAULT_IOU   = float(os.getenv("YOLO_IOU",   "0.45"))
DEFAULT_IMGSZ = int(os.getenv("YOLO_IMGSZ",  "1280"))

# Prefer Apple Metal (MPS) on M1 if available
device = "mps"
try:
    import torch
    if not torch.backends.mps.is_available():
        device = "cpu"
except Exception:
    device = "cpu"

# Load once
model = YOLO(WEIGHTS)

app = FastAPI(title="YOLO FastAPI Server", version="2.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ---------- Schemas ----------
class PredictResponse(BaseModel):
    model: str
    device: str
    time_ms: float
    detections: List[dict]
    image_base64: Optional[str] = None  # only when requested

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

    return payload
