import os
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


_CACHE: Dict[str, List[Tuple[str, np.ndarray]]] = {}


def _load_templates(kind: str, dir_env: str) -> List[Tuple[str, np.ndarray]]:
    if kind in _CACHE:
        return _CACHE[kind]
    d = os.getenv(dir_env, "")
    out: List[Tuple[str, np.ndarray]] = []
    if d and os.path.isdir(d):
        for name in os.listdir(d):
            p = os.path.join(d, name)
            if not os.path.isfile(p):
                continue
            try:
                img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
                if img is None or img.size == 0:
                    continue
                out.append((name, img))
            except Exception:
                continue
    _CACHE[kind] = out
    return out


def _multi_scale_match(gray: np.ndarray, tpl: np.ndarray, scales: List[float]) -> float:
    best = 0.0
    for s in scales:
        try:
            if abs(s - 1.0) > 1e-3:
                t2 = cv2.resize(tpl, (max(1, int(tpl.shape[1] * s)), max(1, int(tpl.shape[0] * s))), interpolation=cv2.INTER_AREA)
            else:
                t2 = tpl
            if gray.shape[0] < t2.shape[0] or gray.shape[1] < t2.shape[1]:
                continue
            res = cv2.matchTemplate(gray, t2, cv2.TM_CCOEFF_NORMED)
            _, maxv, _, _ = cv2.minMaxLoc(res)
            if maxv > best:
                best = float(maxv)
        except Exception:
            continue
    return best


def _crop_roi(bgr: np.ndarray, roi_norm: Tuple[float, float, float, float]) -> np.ndarray:
    """Crop a normalized ROI (x1,y1,x2,y2) in 0..1.
    Returns BGR subimage (may be empty if invalid).
    """
    H, W = bgr.shape[:2]
    x1 = max(0, min(W - 1, int(roi_norm[0] * W)))
    y1 = max(0, min(H - 1, int(roi_norm[1] * H)))
    x2 = max(0, min(W, int(roi_norm[2] * W)))
    y2 = max(0, min(H, int(roi_norm[3] * H)))
    if x2 <= x1 or y2 <= y1:
        return bgr[0:0, 0:0]
    return bgr[y1:y2, x1:x2]


def _detect_by_templates(bgr: np.ndarray, kind: str, dir_env: str, th_env: str, default_th: float = 0.82) -> Tuple[bool, str, float]:
    tpls = _load_templates(kind, dir_env)
    if not tpls:
        return False, "", 0.0
    try:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    except Exception:
        return False, "", 0.0
    # edges can help for line art
    try:
        edges = cv2.Canny(gray, 60, 120)
    except Exception:
        edges = None
    scales = [1.0, 0.85, 1.15]
    best_name = ""
    best_score = 0.0
    for name, tpl in tpls:
        s1 = _multi_scale_match(gray, tpl, scales)
        s2 = 0.0
        if edges is not None:
            try:
                etpl = cv2.Canny(tpl, 60, 120)
                s2 = _multi_scale_match(edges, etpl, scales)
            except Exception:
                s2 = 0.0
        scr = max(s1, s2)
        if scr > best_score:
            best_score = scr
            best_name = name
    th = float(os.getenv(th_env, str(default_th)))
    return (best_score >= th), best_name, best_score


def detect_loading(bgr: np.ndarray) -> Dict[str, object]:
    ok, name, score = _detect_by_templates(bgr, "loading", "LOADING_TPL_DIR", "LOADING_TPL_TH", 0.82)
    return {"matched": ok, "name": name, "score": score}


def detect_toast(bgr: np.ndarray) -> Dict[str, object]:
    ok, name, score = _detect_by_templates(bgr, "toast", "TOAST_TPL_DIR", "TOAST_TPL_TH", 0.82)
    return {"matched": ok, "name": name, "score": score}


def detect_close(bgr: np.ndarray, roi_norm: Tuple[float, float, float, float] = (0.7, 0.0, 1.0, 0.3)) -> Dict[str, object]:
    """Detect a close control (X) in a normalized ROI (default: top-right quadrant).
    Uses templates under CLOSE_TPL_DIR with CLOSE_TPL_TH threshold.
    """
    sub = _crop_roi(bgr, roi_norm)
    if sub.size == 0:
        return {"matched": False, "name": "", "score": 0.0}
    ok, name, score = _detect_by_templates(sub, "close", "CLOSE_TPL_DIR", "CLOSE_TPL_TH", 0.82)
    return {"matched": ok, "name": name, "score": score}


def detect_modal(bgr: np.ndarray) -> Dict[str, object]:
    """Heuristic + shape-based modal detector.
    - Detects dark overlay area ratio (0.1..0.7) and centered edge rectangle.
    Returns: {matched, score, overlay_ratio, edge_density}
    """
    H, W = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # overlay darkness ratio
    dark = (gray < 50).astype(np.uint8)
    overlay_ratio = float(dark.sum()) / float(max(1, H * W))
    # centered edge density
    edges = cv2.Canny(gray, 80, 160)
    cx1, cy1 = int(W * 0.2), int(H * 0.2)
    cx2, cy2 = int(W * 0.8), int(H * 0.8)
    cen = edges[cy1:cy2, cx1:cx2]
    edge_density = float(cen.mean()) / 255.0
    # simple score
    score = 0.0
    if 0.08 <= overlay_ratio <= 0.7:
        score += 0.5
    if edge_density >= 0.06:
        score += 0.5
    clos = detect_close(bgr)
    if clos.get("matched"):
        score = min(1.0, score + 0.2)
    return {
        "matched": score >= 0.7,
        "score": score,
        "overlay_ratio": overlay_ratio,
        "edge_density": edge_density,
        "closable": bool(clos.get("matched")),
        "close_name": clos.get("name"),
        "close_score": clos.get("score"),
    }
