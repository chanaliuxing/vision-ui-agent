# app.py — YOLO + Fused OCR (PaddleOCR preferred, EasyOCR fallback) + PNG direct response
import io, os, time, base64
from typing import Optional, List, Tuple, Dict
from inspect import signature

import numpy as np
import cv2
from PIL import Image

from fastapi import FastAPI, File, UploadFile, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from ultralytics import YOLO

# ---------------- Optional deps ----------------
HAS_REQUESTS = True
try:
    import requests
except Exception:
    HAS_REQUESTS = False

HAS_TORCH = True
try:
    import torch
except Exception:
    HAS_TORCH = False

HAS_PADDLE = True
try:
    # PaddleOCR supports Chinese + English together with lang="ch"
    from paddleocr import PaddleOCR
except Exception:
    HAS_PADDLE = False

HAS_EASYOCR = True
try:
    import easyocr
except Exception:
    HAS_EASYOCR = False

# ---------------- YOLO config ----------------
DEFAULT_WEIGHTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weights", "model.pt")
WEIGHTS = os.getenv("YOLO_WEIGHTS", DEFAULT_WEIGHTS)
DEFAULT_CONF  = float(os.getenv("YOLO_CONF",  "0.25"))
DEFAULT_IOU   = float(os.getenv("YOLO_IOU",   "0.45"))
DEFAULT_IMGSZ = int(os.getenv("YOLO_IMGSZ",  "1280"))

device = "mps"
if not HAS_TORCH:
    device = "cpu"
else:
    try:
        if not torch.backends.mps.is_available():
            device = "cpu"
    except Exception:
        device = "cpu"

det_model = YOLO(WEIGHTS)

# ---------------- Utils ----------------
def _np_to_base64_png(img_np: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", img_np)
    if not ok: return ""
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode("utf-8")

def _read_image_bytes(file: UploadFile = None, image_base64: str = None, image_url: str = None) -> bytes:
    if file is not None: return file.file.read()
    if image_base64: return base64.b64decode(image_base64)
    if image_url:
        if not HAS_REQUESTS: raise ValueError("requests not installed")
        r = requests.get(image_url, timeout=10); r.raise_for_status(); return r.content
    raise ValueError("No image provided")

def _pil_to_bgr(pil_im) -> np.ndarray:
    rgb = np.array(pil_im); return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

def _sort_indices_tl(xyxy: List[List[float]]) -> List[int]:
    return sorted(range(len(xyxy)), key=lambda i: (xyxy[i][1], xyxy[i][0]))

def _font_scale_from_px(desired_px: int, thickness: int = 1) -> float:
    font = cv2.FONT_HERSHEY_SIMPLEX
    lo, hi = 0.05, 5.0
    for _ in range(20):
        mid = (lo + hi) / 2.0
        (_, h), _ = cv2.getTextSize("Ag", font, mid, thickness)
        if h > desired_px: hi = mid
        else: lo = mid
    return lo

def _clip_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))

def _draw_inside_label(img: np.ndarray, box: Tuple[int,int,int,int], text: str,
                       base_font_px: int, line_width: int, img_h: int,
                       min_band_px: int, min_band_px_ratio: float,
                       color_box=(255,0,0), color_text=(255,255,255), alpha_bg=0.45):
    x1, y1, x2, y2 = [int(v) for v in box]
    out = img
    pad = 4
    thickness_text = max(1, line_width-1)
    font_px = max(7, base_font_px)
    font = cv2.FONT_HERSHEY_SIMPLEX

    def draw_filled(rect):
        rx1, ry1, rx2, ry2 = rect
        overlay = out.copy()
        cv2.rectangle(overlay, (rx1, ry1), (rx2, ry2), color_box, -1)
        cv2.addWeighted(overlay, alpha_bg, out, 1-alpha_bg, 0, out)

    # try to fit inside corners
    while font_px >= 7:
        scale = _font_scale_from_px(font_px, thickness=thickness_text)
        (tw, th), _ = cv2.getTextSize(text, font, scale, thickness_text)
        bw, bh = tw + 2*pad, th + 2*pad
        cands = [
            (x1+line_width, y1+line_width),
            (x2-line_width-bw, y1+line_width),
            (x1+line_width, y2-line_width-bh),
            (x2-line_width-bw, y2-line_width-bh),
        ]
        for (lx, ly) in cands:
            if lx>=x1 and ly>=y1 and (lx+bw)<=x2 and (ly+bh)<=y2:
                rect = (int(lx), int(ly), int(lx+bw), int(ly+bh))
                draw_filled(rect)
                cv2.putText(out, text, (rect[0]+pad, rect[3]-pad-1),
                            font, scale, color_text, thickness_text, cv2.LINE_AA)
                return out, rect, 0
        font_px = int(font_px*0.9)

    # fallback: top band
    min_band = max(min_band_px, int(min_band_px_ratio*img_h))
    band_h = max(min_band, int((y2-y1)*0.20))
    rx1, ry1, rx2, ry2 = x1+line_width, y1+line_width, x2-line_width, y1+band_h
    rect = (_clip_int(rx1,0,img.shape[1]-1), _clip_int(ry1,0,img.shape[0]-1),
            _clip_int(rx2,0,img.shape[1]-1), _clip_int(ry2,0,img.shape[0]-1))
    scale = _font_scale_from_px(max(9, band_h-6), thickness=thickness_text)
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness_text)
    tries=0
    while tw+8 > (rect[2]-rect[0]) and tries<8:
        scale *= 0.9
        (tw, th), _ = cv2.getTextSize(text, font, scale, thickness_text); tries+=1
    overlay = out.copy()
    cv2.rectangle(overlay, (rect[0], rect[1]), (rect[2], rect[3]), color_box, -1)
    cv2.addWeighted(overlay, 0.45, out, 0.55, 0, out)
    cx = int((rect[0]+rect[2]-tw)/2); cy = int((rect[1]+rect[3]+th)/2)-2
    cv2.putText(out, text, (cx, cy), font, scale, color_text, thickness_text, cv2.LINE_AA)
    return out, rect, 1

def _draw_scene_ids(base_bgr: np.ndarray, xyxy, ids,
                    line_width: int, font_px: int, min_band_px: int,
                    min_band_px_ratio: float, draw_center: bool):
    H, W = base_bgr.shape[:2]
    out = base_bgr.copy()
    color_box = (255,0,0)
    for (x1,y1,x2,y2) in xyxy:
        cv2.rectangle(out, (int(x1), int(y1)), (int(x2), int(y2)), color_box, line_width)

    label_rects=[]
    for (x1,y1,x2,y2), uid in zip(xyxy, ids):
        text = str(uid)
        out, label_rect, _ = _draw_inside_label(out, (int(x1),int(y1),int(x2),int(y2)), text,
                                                base_font_px=font_px, line_width=line_width,
                                                img_h=H, min_band_px=min_band_px,
                                                min_band_px_ratio=min_band_px_ratio)
        label_rects.append(label_rect)
        if draw_center:
            cx=int((x1+x2)/2); cy=int((y1+y2)/2)
            cv2.circle(out, (cx,cy), radius=3, color=color_box, thickness=-1)
    return out, label_rects

# ---------------- OCR backends ----------------
class OCRBackend:
    """
    Unified wrapper for PaddleOCR (preferred) and EasyOCR (fallback).
    - prefer: 'paddle' | 'easyocr' | 'auto'
    - langs:
        * PaddleOCR: 'ch' recommended (covers CN + EN)
        * EasyOCR  : use 'en,ch_sim' (we auto-map 'ch' -> 'ch_sim')
    """

    def __init__(self, prefer: str, langs: str, use_gpu: bool = False):
        self.backend = None
        self.kind = None

        def _norm_easyocr_langs(s: str) -> List[str]:
            # map common aliases to EasyOCR codes
            raw = [x.strip().lower() for x in (s or "").split(",") if x.strip()]
            if not raw:
                raw = ["en"]
            out = []
            for x in raw:
                if x in ("ch", "zh", "zh-cn", "zh_cn", "cn", "zh-hans", "zh_hans"):
                    out.append("ch_sim")
                elif x in ("zh-tw", "zh_tw", "zh-hant", "zh_hant", "tw", "cht"):
                    out.append("ch_tra")
                else:
                    out.append(x)
            if "en" not in out:
                out.append("en")
            return out

        # Try Paddle first (if requested or auto + available)
        if prefer in ("paddle", "auto"):
            if HAS_PADDLE and ("PaddleOCR" in globals() or "PaddleOCR" in locals()):
                try:
                    # Some versions don't accept use_gpu/show_log; create kwargs by signature.
                    lang = "ch" if not langs or "ch" in langs else "ch"
                    kwargs = dict(lang=lang, use_angle_cls=True)
                    try:
                        sig_params = signature(PaddleOCR.__init__).parameters
                        if "show_log" in sig_params:
                            kwargs["show_log"] = False
                        if "use_gpu" in sig_params:
                            kwargs["use_gpu"] = use_gpu
                    except Exception:
                        pass
                    self.backend = PaddleOCR(**kwargs)
                    self.kind = "paddle"
                except Exception as e:
                    print("⚠️ PaddleOCR init failed:", e)
                    self.backend = None
                    self.kind = None

        # If no paddle, try EasyOCR
        if self.backend is None and (prefer in ("easyocr", "auto")):
            if not HAS_EASYOCR:
                print("⚠️ EasyOCR not installed; OCR disabled.")
            else:
                try:
                    lang_list = _norm_easyocr_langs(langs or "en,ch_sim")
                    self.backend = easyocr.Reader(lang_list, gpu=use_gpu)
                    self.kind = "easyocr"
                except Exception as e:
                    print(f"⚠️ EasyOCR init failed: {e}")
                    self.backend = None
                    self.kind = None

        if self.backend is None:
            # No exception here — we want the API to respond 200 without OCR.
            print("⚠️ No OCR backend available (Paddle/Easy both unavailable). OCR will be skipped.")

    def read(self, img_bgr: np.ndarray, min_conf: float = 0.5) -> List[Dict]:
        """Return [{'polygon':[[x,y]x4], 'text': str, 'conf': float}, ...] in *global coords* of 'img_bgr'."""
        if self.backend is None:
            return []

        if self.kind == "paddle":
            # Paddle expects RGB or BGR? Official examples use img_path; with ndarray use RGB is ok.
            # We pass BGR directly and set 'rec' robust enough; convert to RGB to match EasyOCR path.
            rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            res = self.backend.ocr(rgb, cls=True)
            lines = []
            # Paddle returns: [ [ [poly], (text, conf) ], ... ]
            for block in res:
                for poly, (txt, conf) in block:
                    if not txt:
                        continue
                    if conf is not None and conf < min_conf:
                        continue
                    lines.append({
                        "polygon": [[float(p[0]), float(p[1])] for p in poly],
                        "text": str(txt),
                        "conf": float(conf if conf is not None else 1.0)
                    })
            return lines

        # EasyOCR
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        raw = self.backend.readtext(
            rgb,
            detail=1,
            paragraph=False,
            contrast_ths=0.05,
            adjust_contrast=0.5,
            text_threshold=0.6,
            low_text=0.3,
            link_threshold=0.3,
            width_ths=0.7,
            decoder="greedy",
            beamWidth=5,
        )
        out = []
        for poly, txt, conf in raw:
            if not txt or conf < min_conf:
                continue
            out.append({
                "polygon": [[float(p[0]), float(p[1])] for p in poly],
                "text": str(txt),
                "conf": float(conf),
            })
        return out

# ---------------- Geometry helpers ----------------
def _poly_center(poly):
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    return (sum(xs)/len(xs), sum(ys)/len(ys))

def _rect_intersects_poly(rect, poly, iou_th=0.0):
    # quick test: center inside OR IoU of rect with poly's bbox
    rx1, ry1, rx2, ry2 = rect
    cx, cy = _poly_center(poly)
    if (rx1 <= cx <= rx2) and (ry1 <= cy <= ry2):
        return True
    pxs=[p[0] for p in poly]; pys=[p[1] for p in poly]
    bx1, by1, bx2, by2 = min(pxs), min(pys), max(pxs), max(pys)
    inter_x1, inter_y1 = max(rx1,bx1), max(ry1,by1)
    inter_x2, inter_y2 = min(rx2,bx2), min(ry2,by2)
    iw, ih = max(0.0, inter_x2-inter_x1), max(0.0, inter_y2-inter_y1)
    inter = iw*ih
    ra = (rx2-rx1)*(ry2-ry1)
    pa = (bx2-bx1)*(by2-by1)
    union = ra + pa - inter + 1e-6
    iou = inter / union
    return iou >= iou_th

def _expand_box(box, W, H, ratio=0.06):
    x1,y1,x2,y2 = box
    dw = (x2-x1)*ratio; dh=(y2-y1)*ratio
    nx1 = max(0, int(round(x1-dw))); ny1=max(0, int(round(y1-dh)))
    nx2 = min(W-1, int(round(x2+dw))); ny2=min(H-1, int(round(y2+dh)))
    return [nx1,ny1,nx2,ny2]

def _dedup_lines(lines: List[Dict]) -> List[Dict]:
    merged={}
    def _sig(l):
        poly=l["polygon"]; txt=l["text"].strip().lower()
        xs=[p[0] for p in poly]; ys=[p[1] for p in poly]
        a=round((max(xs)-min(xs))*(max(ys)-min(ys)),1)
        return (txt,a)
    for r in lines:
        key=_sig(r)
        if (key not in merged) or (r["conf"]>merged[key]["conf"]):
            merged[key]=r
    return list(merged.values())

# ---------------- FastAPI ----------------
app = FastAPI(title="YOLO + Fused OCR (IDs only)", version="2.2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

class OCRLine(BaseModel):
    polygon: List[List[float]]
    text: str
    conf: float

class PredictResponse(BaseModel):
    model: str
    device: str
    time_ms: float
    detections: List[dict]
    ocr_full_count: Optional[int] = None
    image_base64: Optional[str] = None

@app.get("/health")
def health():
    return {"status":"ok","model":WEIGHTS,"device":device,"paddleocr":HAS_PADDLE,"easyocr":HAS_EASYOCR}

@app.post("/predict", response_model=PredictResponse)
async def predict(
    image: UploadFile = File(default=None),
    image_base64: Optional[str] = Form(default=None),
    image_url: Optional[str] = Form(default=None),

    conf: float = Query(default=DEFAULT_CONF), iou: float = Query(default=DEFAULT_IOU),
    imgsz: int = Query(default=DEFAULT_IMGSZ), max_det: int = Query(default=300),

    # drawing
    return_image: bool = Query(default=True),
    return_image_format: str = Query(default="json"),   # "json" | "png"
    line_width: int = Query(default=2), font_px: int = Query(default=12),
    min_band_px: int = Query(default=14), min_band_px_ratio: float = Query(default=0.012),
    draw_center: bool = Query(default=True),

    # id strategy
    id_order: str = Query(default="tl"), label_prefix: str = Query(default="icon"),

    # OCR config
    ocr_backend: str = Query(default="auto"),   # 'auto' | 'paddle' | 'easyocr'
    ocr_langs: str = Query(default="ch"),       # 'ch' for Paddle; 'en,ch_sim' for EasyOCR (auto-mapped)
    ocr_min_conf: float = Query(default=0.5),
    box_expand_ratio: float = Query(default=0.06),  # enlarge each crop
    box_ocr_mode: str = Query(default="fused"),     # 'global' | 'crop' | 'fused'
    fuse_iou_th: float = Query(default=0.01),       # how strict to assign global lines to boxes

    # heuristics to speed up crop OCR
    crop_ocr_if_needed_only: bool = Query(default=True),     # only do crop OCR when global lines are empty or short
    crop_trigger_min_chars: int = Query(default=6),          # if fused text shorter than this, trigger crop OCR
    max_crops_ocr: int = Query(default=200)                  # safety cap for huge images
):
    """
    Pipeline:
      1) YOLO detect boxes (IDs only overlay).
      2) OCR back-end (PaddleOCR preferred) runs on:
         - full image once, and/or
         - each expanded crop (仅在需要时).
      3) For each box: fuse global + crop OCR lines, dedupe, return JSON.
      4) 可选直接返回 PNG（return_image_format=png），避免终端看到很长的 base64。
    """
    raw = _read_image_bytes(image, image_base64, image_url)
    pil_img = Image.open(io.BytesIO(raw)).convert("RGB")
    W, H = pil_img.size
    np_img = np.array(pil_img)
    bgr_full = cv2.cvtColor(np_img, cv2.COLOR_RGB2BGR)

    # detection
    t0 = time.time()
    res = det_model.predict(pil_img, conf=conf, iou=iou, imgsz=imgsz,
                            max_det=max_det, device=device, verbose=False)[0]
    det_ms = (time.time() - t0) * 1000.0

    dets=[]; xyxy=[]; confs=[]; clss=[]
    names = res.names if hasattr(res,"names") and res.names else det_model.names

    if res.boxes is not None and len(res.boxes)>0:
        xyxy = res.boxes.xyxy.cpu().tolist()
        confs= [float(x) for x in res.boxes.conf.cpu().tolist()]
        clss = [int(x) for x in res.boxes.cls.cpu().tolist()]

        order = _sort_indices_tl(xyxy) if id_order=="tl" else list(range(len(xyxy)))
        ids = [0]*len(xyxy)
        for n,i in enumerate(order, start=1): ids[i]=n
    else:
        ids=[]

    # OCR init (safe)
    ocr_lines_global = []
    ocr_backend_obj = None
    try:
        if (box_ocr_mode in ["global","fused"]) and (HAS_PADDLE or HAS_EASYOCR):
            ocr_backend_obj = OCRBackend(prefer=ocr_backend, langs=ocr_langs, use_gpu=False)
            ocr_lines_global = ocr_backend_obj.read(bgr_full, min_conf=ocr_min_conf)
    except Exception as e:
        print("⚠️ OCR init/read exception (continuing without OCR):", e)
        ocr_backend_obj = None
        ocr_lines_global = []
    ocr_full_count = len(ocr_lines_global)

    # For each box, do fused OCR
    crops_used = 0
    for (box, c, k, uid) in zip(xyxy, confs, clss, ids):
        x1,y1,x2,y2 = [int(round(v)) for v in box]
        x1 = max(0, min(x1, W-1)); x2 = max(0, min(x2, W-1))
        y1 = max(0, min(y1, H-1)); y2 = max(0, min(y2, H-1))
        rect = [x1,y1,x2,y2]

        # expand rect for crop OCR (helps tight boxes)
        ex = _expand_box(rect, W, H, ratio=box_expand_ratio)

        lines = []
        # a) use global OCR lines that fall inside (or intersect) the expanded box
        if box_ocr_mode in ["global","fused"]:
            for ln in ocr_lines_global:
                if _rect_intersects_poly(ex, ln["polygon"], iou_th=fuse_iou_th):
                    lines.append(ln)

        # 如果仅全局 OCR 不足（字数太少），再触发 crop OCR；否则跳过以提速
        need_crop_ocr = (box_ocr_mode in ["crop","fused"]) and (ocr_backend_obj is not None)
        if crop_ocr_if_needed_only and need_crop_ocr:
            current_txt = " ".join([l["text"] for l in lines])
            if len(current_txt.strip()) >= crop_trigger_min_chars:
                need_crop_ocr = False

        if need_crop_ocr and crops_used < max_crops_ocr:
            try:
                crop = bgr_full[ex[1]:ex[3], ex[0]:ex[2]].copy()
                # 轻微放大有时能提高小字识别率（最多放到 1.6x）
                h, w = crop.shape[:2]
                scale = 1.4 if max(h, w) < 512 else 1.0
                if scale > 1.0:
                    crop = cv2.resize(crop, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_CUBIC)

                crop_lines = ocr_backend_obj.read(crop, min_conf=ocr_min_conf)
                # bring crop polygons back to global coords（按 scale 回投）
                inv_s = (1.0/scale)
                for ln in crop_lines:
                    poly = [[p[0]*inv_s+ex[0], p[1]*inv_s+ex[1]] for p in ln["polygon"]]
                    lines.append({"polygon": poly, "text": ln["text"], "conf": ln["conf"]})
                crops_used += 1
            except Exception as e:
                print("⚠️ Crop OCR exception:", e)

        lines = _dedup_lines(lines)
        text_join = " ".join([l["text"] for l in lines]).strip()

        dets.append({
            "id": uid,
            "name": f"{label_prefix} {uid}",
            "label": f"{label_prefix} {uid}",
            "conf": c,
            "class_id": k,
            "class_name": names.get(k, str(k)) if isinstance(names, dict) else str(k),
            "bbox_xyxy": [float(box[0]), float(box[1]), float(box[2]), float(box[3])],
            "bbox_xyxy_norm": [box[0]/W, box[1]/H, box[2]/W, box[3]/H],
            "center_xy_norm": [((box[0]+box[2])/2)/W, ((box[1]+box[3])/2)/H],
            "size_wh_norm": [(box[2]-box[0])/W, (box[3]-box[1])/H],
            "click_xy_norm": [((box[0]+box[2])/2)/W, ((box[1]+box[3])/2)/H],
            "label_bbox_xyxy": None,
            "ocr": {
                "text": text_join,
                "lines": lines
            }
        })

    # draw IDs only
    payload = {"model": WEIGHTS, "device": device,
               "time_ms": round(det_ms,2), "detections": dets,
               "ocr_full_count": ocr_full_count}

    base_bgr = None
    annotated = None
    if return_image:
        base_bgr = _pil_to_bgr(pil_img)
        if dets:
            draw_xyxy = [d["bbox_xyxy"] for d in dets]
            draw_ids  = [d["id"] for d in dets]
            annotated, label_rects = _draw_scene_ids(base_bgr, draw_xyxy, draw_ids,
                                                     line_width=line_width, font_px=font_px,
                                                     min_band_px=min_band_px, min_band_px_ratio=min_band_px_ratio,
                                                     draw_center=draw_center)
            for d, lab_rect in zip(dets, label_rects):
                d["label_bbox_xyxy"] = [float(lab_rect[0]), float(lab_rect[1]),
                                        float(lab_rect[2]), float(lab_rect[3])]
            if return_image_format == "json":
                payload["image_base64"] = _np_to_base64_png(annotated)
            else:  # png
                ok, buf = cv2.imencode(".png", annotated)
                return Response(content=buf.tobytes(), media_type="image/png")
        else:
            if return_image_format == "json":
                payload["image_base64"] = _np_to_base64_png(base_bgr)
            else:
                ok, buf = cv2.imencode(".png", base_bgr)
                return Response(content=buf.tobytes(), media_type="image/png")

    return payload
