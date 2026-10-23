import json
import os
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image
try:
    from .ocr_client import OcrClient  # type: ignore
except Exception:
    OcrClient = None  # type: ignore


def _clip_box(x1, y1, x2, y2, w, h):
    return max(0, x1), max(0, y1), min(w - 1, x2), min(h - 1, y2)


def anchors_from(bgr: np.ndarray, bbox: List[float], pad_ratio: float = 0.1) -> Dict[str, Any]:
    x1, y1, x2, y2 = map(int, bbox)
    H, W = bgr.shape[:2]
    w = max(1, x2 - x1)
    h = max(1, y2 - y1)
    padw = int(pad_ratio * w)
    padh = int(pad_ratio * h)
    rx1, ry1, rx2, ry2 = _clip_box(x1 - padw, y1 - padh, x2 + padw, y2 + padh, W, H)
    roi = bgr[ry1:ry2, rx1:rx2].copy()
    # Template: downscale for performance
    tpl = cv2.resize(roi, (min(roi.shape[1], 128), min(roi.shape[0], 128))) if roi.size > 0 else roi
    # Store as PNG bytes (base64 is overkill for local)
    _, buf = cv2.imencode('.png', tpl)
    return {
        "type": "template",
        "roi": [rx1, ry1, rx2, ry2],
        "template_png": buf.tobytes().hex(),
        "method": "TM_CCOEFF_NORMED",
        "th": float(os.getenv("ANCHOR_TM_TH", "0.82")),
    }


def anchors_match(bgr: np.ndarray, anchors: Dict[str, Any]) -> float:
    """Backward-compatible matcher for legacy single template anchor dict."""
    if not isinstance(anchors, dict):
        return 0.0
    if anchors.get("type") not in (None, "template"):
        # Not a legacy template anchor, caller should use compound matchers
        return 0.0
    roi = anchors.get("roi", [0, 0, 0, 0])
    x1, y1, x2, y2 = map(int, roi)
    H, W = bgr.shape[:2]
    x1, y1, x2, y2 = _clip_box(x1, y1, x2, y2, W, H)
    crop = bgr[y1:y2, x1:x2]
    tpl_hex = anchors.get("template_png")
    if not tpl_hex:
        return 0.0
    tpl = np.frombuffer(bytes.fromhex(tpl_hex), dtype=np.uint8)
    tpl = cv2.imdecode(tpl, cv2.IMREAD_COLOR)
    try:
        if crop.shape[0] < tpl.shape[0] or crop.shape[1] < tpl.shape[1]:
            return 0.0
        res = cv2.matchTemplate(crop, tpl, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, _ = cv2.minMaxLoc(res)
        return float(maxv)
    except Exception:
        return 0.0


class RoutesStore:
    def __init__(self, logs_dir: str, filename: str = "routes.jsonl") -> None:
        self.path = os.path.join(logs_dir, filename)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.cache: List[Dict[str, Any]] = []
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            self.cache.append(json.loads(line))
                        except Exception:
                            continue
            except Exception:
                pass

    def append(self, rec: Dict[str, Any]) -> None:
        self.cache.append(rec)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass
        # timeline events for anchors and clicks
        try:
            from . import timeline as _t
            ts = float(rec.get("ts", 0))
            if rec.get("anchors"):
                a = rec.get("anchors") or {}
                _t.event(
                    "anchor",
                    f"template_used type={a.get('type')} method={a.get('method')} th={a.get('th')} roi={a.get('roi')}",
                    ts_ms=ts,
                )
            if rec.get("click_id"):
                _t.event(
                    "route/click",
                    f"goal={rec.get('goal')} click_id={rec.get('click_id')} bbox={rec.get('bbox')} verifier={rec.get('verifier')}",
                    ts_ms=(ts + 0.1),
                )
        except Exception:
            pass

    def lookup(self, sig_key: str, goal: str) -> Optional[Dict[str, Any]]:
        # Return the most recent healthy route for this signature and goal
        ttl_min = int(os.getenv("ROUTE_TTL_MIN", "1440"))
        ema_min = float(os.getenv("ROUTE_EMA_MIN", "0.3"))
        now_ms = int(os.getenv("_NOW_MS_OVERRIDE", "0")) or None
        for rec in reversed(self.cache):
            if rec.get("sig_key") != sig_key or rec.get("goal") != goal:
                continue
            if int(rec.get("success_count", 0)) < 2:
                continue
            try:
                ts = int(rec.get("ts", 0))
                age_min = ((now_ms - ts) / 60000.0) if (now_ms and ts) else 0.0
                ema = float(rec.get("ema_success", 0.5))
                if ema < ema_min:
                    continue
                if ttl_min > 0 and age_min and age_min > ttl_min:
                    continue
                return rec
            except Exception:
                return rec
        return None

    def window_success_rate(self, sig_key: str, goal: str, window: int = 50) -> float:
        """Compute recent success rate over the last `window` events for this route.
        Expects records to have an 'event' field of 'success' or 'fail'.
        """
        total = 0
        succ = 0
        for rec in reversed(self.cache):
            if rec.get("sig_key") != sig_key or rec.get("goal") != goal:
                continue
            ev = rec.get("event")
            if ev not in ("success", "fail"):
                continue
            total += 1
            if ev == "success":
                succ += 1
            if total >= window:
                break
        if total == 0:
            return 1.0
        return float(succ) / float(total)


# --------------- Adaptive threshold helpers ---------------

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def adjust_template_anchor(a: Dict[str, Any], success: bool) -> Dict[str, Any]:
    if not isinstance(a, dict):
        return a
    out = dict(a)
    if out.get("type") != "template":
        return out
    th = float(out.get("th", 0.82))
    if success:
        th = _clamp(th + 0.01, 0.70, 0.95)
    else:
        th = _clamp(th - 0.02, 0.65, 0.95)
    out["th"] = th
    return out


def adjust_orb_anchor(a: Dict[str, Any], success: bool) -> Dict[str, Any]:
    if not isinstance(a, dict):
        return a
    out = dict(a)
    if out.get("type") != "orb":
        return out
    ratio = float(out.get("ratio", 0.75))
    inl = int(out.get("min_inliers", 12))
    if success:
        ratio = _clamp(ratio - 0.02, 0.65, 0.85)
        inl = max(8, min(24, inl + 1))
    else:
        ratio = _clamp(ratio + 0.02, 0.65, 0.90)
        inl = max(6, min(24, inl - 1))
    out["ratio"] = ratio
    out["min_inliers"] = inl
    return out


def adjust_sift_anchor(a: Dict[str, Any], success: bool) -> Dict[str, Any]:
    if not isinstance(a, dict):
        return a
    out = dict(a)
    if out.get("type") != "sift":
        return out
    ratio = float(out.get("ratio", 0.75))
    inl = int(out.get("min_inliers", 8))
    if success:
        ratio = _clamp(ratio - 0.01, 0.65, 0.80)
        inl = max(6, min(20, inl + 1))
    else:
        ratio = _clamp(ratio + 0.02, 0.65, 0.85)
        inl = max(4, min(20, inl - 1))
    out["ratio"] = ratio
    out["min_inliers"] = inl
    return out


def adjust_relation(rel: Dict[str, Any], success: bool) -> Dict[str, Any]:
    out = dict(rel or {})
    tx = float(out.get("tol_x", 0.0))
    ty = float(out.get("tol_y", 0.0))
    if tx and ty:
        if success:
            tx *= 0.95; ty *= 0.95
        else:
            tx *= 1.07; ty *= 1.07
    out["tol_x"], out["tol_y"] = tx, ty
    return out


def adjust_state_anchors(state: Dict[str, Any], success: bool) -> Dict[str, Any]:
    if not isinstance(state, dict):
        return state
    out = dict(state)
    arr = []
    for a in (out.get("anchors") or []):
        if a.get("type") == "template":
            arr.append(adjust_template_anchor(a, success))
        else:
            arr.append(a)
    out["anchors"] = arr
    return out


# ---------------- New: Compound anchors (Row + Action + Relation) ----------------

def _encode_png(arr: np.ndarray) -> str:
    _, buf = cv2.imencode(".png", arr)
    return buf.tobytes().hex()


def _decode_png(hex_str: str) -> Optional[np.ndarray]:
    if not hex_str:
        return None
    data = np.frombuffer(bytes.fromhex(hex_str), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    return img


def _crop_pad(bgr: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
    H, W = bgr.shape[:2]
    x1, y1, x2, y2 = _clip_box(x1, y1, x2, y2, W, H)
    return bgr[y1:y2, x1:x2].copy()


def gen_templates(bgr: np.ndarray, bbox: List[float], k: int = 3) -> List[Dict[str, Any]]:
    x1, y1, x2, y2 = map(int, bbox)
    w = max(1, x2 - x1)
    h = max(1, y2 - y1)
    patches = []
    # sample around corners and center areas inside bbox pad
    pads = [(0.1, 0.1), (0.5, 0.2), (0.2, 0.5)]
    for px, py in pads[:k]:
        cx = int(x1 + px * w)
        cy = int(y1 + py * h)
        pw = max(8, int(0.35 * w)); ph = max(8, int(0.35 * h))
        rx1, ry1, rx2, ry2 = _clip_box(cx, cy, cx + pw, cy + ph, bgr.shape[1], bgr.shape[0])
        roi = _crop_pad(bgr, rx1, ry1, rx2, ry2)
        if roi.size == 0:
            continue
        tpl = cv2.resize(roi, (min(roi.shape[1], 128), min(roi.shape[0], 128)))
        patches.append({
            "type": "template",
            "roi": [rx1, ry1, rx2, ry2],
            "template_png": _encode_png(tpl),
            "method": "TM_CCOEFF_NORMED",
            "th": float(os.getenv("ANCHOR_TM_TH", "0.82")),
        })
    return patches


def gen_orb_features(bgr: np.ndarray, bbox: List[float], max_kpts: int = 512) -> Optional[Dict[str, Any]]:
    try:
        orb = cv2.ORB_create(nfeatures=max_kpts)
    except Exception:
        return None
    x1, y1, x2, y2 = map(int, bbox)
    roi = _crop_pad(bgr, x1, y1, x2, y2)
    if roi.size == 0:
        return None
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    kpts, desc = orb.detectAndCompute(gray, None)
    if desc is None or len(kpts) < 8:
        return None
    # encode descriptor matrix as png for compact storage
    return {
        "type": "orb",
        "roi": [x1, y1, x2, y2],
        "kpts": len(kpts),
        "desc_png": _encode_png(desc),
        "ratio": float(os.getenv("ANCHOR_ORB_RATIO", "0.75")),
        "min_inliers": int(os.getenv("ANCHOR_ORB_INLIERS", "12")),
    }


def match_template(crop: np.ndarray, tmpl_hex: str) -> float:
    tpl = _decode_png(tmpl_hex)
    if tpl is None or crop.size == 0:
        return 0.0
    try:
        if crop.shape[0] < tpl.shape[0] or crop.shape[1] < tpl.shape[1]:
            return 0.0
        res = cv2.matchTemplate(crop, tpl, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, _ = cv2.minMaxLoc(res)
        return float(maxv)
    except Exception:
        return 0.0


def match_template_bbox(crop: np.ndarray, tmpl_hex: str) -> Tuple[float, Optional[List[int]]]:
    tpl = _decode_png(tmpl_hex)
    if tpl is None or crop.size == 0:
        return 0.0, None
    try:
        h, w = tpl.shape[:2]
        if crop.shape[0] < h or crop.shape[1] < w:
            return 0.0, None
        res = cv2.matchTemplate(crop, tpl, cv2.TM_CCOEFF_NORMED)
        _, maxv, maxloc, _ = cv2.minMaxLoc(res)
        x, y = maxloc
        return float(maxv), [int(x), int(y), int(x + w), int(y + h)]
    except Exception:
        return 0.0, None


def match_orb(crop: np.ndarray, desc_hex: str, ratio: float = 0.75) -> Tuple[int, float]:
    try:
        orb = cv2.ORB_create()
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    except Exception:
        return 0, 0.0

    query = _decode_png(desc_hex)
    if query is None:
        return 0, 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    kpts2, desc2 = orb.detectAndCompute(gray, None)
    if desc2 is None or desc2.size == 0:
        return 0, 0.0
    try:
        matches = bf.knnMatch(query, desc2, k=2)
        good = []
        for m, n in matches:
            if m.distance < ratio * n.distance:
                good.append(m)
        # score: normalized by number of query descriptors
        score = float(len(good)) / max(1.0, float(query.shape[0]))
        return len(good), score
    except Exception:
        return 0, 0.0


def gen_sift_features(bgr: np.ndarray, bbox: List[float], max_kpts: int = 512) -> Optional[Dict[str, Any]]:
    """Generate SIFT features for more robust matching than ORB"""
    try:
        sift = cv2.SIFT_create(nfeatures=max_kpts)
    except Exception:
        return None
    x1, y1, x2, y2 = map(int, bbox)
    roi = _crop_pad(bgr, x1, y1, x2, y2)
    if roi.size == 0:
        return None
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    kpts, desc = sift.detectAndCompute(gray, None)
    if desc is None or len(kpts) < 8:
        return None
    # Convert float32 descriptors to uint8 for storage
    desc_uint8 = (desc * 255).astype(np.uint8)
    return {
        "type": "sift",
        "roi": [x1, y1, x2, y2],
        "kpts": len(kpts),
        "desc_png": _encode_png(desc_uint8),
        "ratio": float(os.getenv("ANCHOR_SIFT_RATIO", "0.75")),
        "min_inliers": int(os.getenv("ANCHOR_SIFT_INLIERS", "8")),
    }


def match_sift(crop: np.ndarray, desc_hex: str, ratio: float = 0.75) -> Tuple[int, float]:
    """Match SIFT features with ratio test"""
    try:
        sift = cv2.SIFT_create()
        bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
    except Exception:
        return 0, 0.0

    query_uint8 = _decode_png(desc_hex)
    if query_uint8 is None:
        return 0, 0.0
    # Convert back to float32
    query = query_uint8.astype(np.float32) / 255.0

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    kpts2, desc2 = sift.detectAndCompute(gray, None)
    if desc2 is None or desc2.size == 0:
        return 0, 0.0
    try:
        matches = bf.knnMatch(query, desc2, k=2)
        good = []
        for match_pair in matches:
            if len(match_pair) == 2:
                m, n = match_pair
                if m.distance < ratio * n.distance:
                    good.append(m)
        # score: normalized by number of query descriptors
        score = float(len(good)) / max(1.0, float(query.shape[0]))
        return len(good), score
    except Exception:
        return 0, 0.0


def _ocr_texts(bgr: np.ndarray) -> List[str]:
    if OcrClient is None:
        return []
    try:
        cli = OcrClient(endpoint=os.getenv("OCR_ENDPOINT"))
        if not cli or not getattr(cli, "endpoint", None):
            return []
        pil = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        return cli.read_texts(pil) or []
    except Exception:
        return []


def _tokenize_ocr(txts: List[str]) -> List[str]:
    out: List[str] = []
    for t in txts or []:
        t2 = (t or "").strip()
        if 2 <= len(t2) <= 12:
            out.append(t2)
    return out


def check_relation(row_bbox: List[int], act_bbox: List[int], relation: Dict[str, Any]) -> bool:
    x1r, y1r, x2r, y2r = map(int, row_bbox)
    x1a, y1a, x2a, y2a = map(int, act_bbox)
    dx = (x1a + x2a) / 2 - (x1r + x2r) / 2
    dy = (y1a + y2a) / 2 - (y1r + y2r) / 2
    tol_x = float(relation.get("tol_x", 0.15 * max(1, x2r - x1r)))
    tol_y = float(relation.get("tol_y", 0.15 * max(1, y2r - y1r)))
    return abs(dx - float(relation.get("dx", dx))) <= tol_x and abs(dy - float(relation.get("dy", dy))) <= tol_y


def locate_instance(bgr: np.ndarray, row_anchor: Dict[str, Any], action_anchor: Dict[str, Any], relation: Dict[str, Any]) -> Optional[List[int]]:
    # 1) match row on full image
    H, W = bgr.shape[:2]
    # row matching: scan full image using stored template
    if row_anchor.get("type") == "template":
        score, box = match_template_bbox(bgr, row_anchor.get("template_png", ""))
        if not box or score < float(row_anchor.get("th", 0.82)):
            return None
        x1, y1, x2, y2 = box
        row_bbox = [x1, y1, x2, y2]
    else:
        return None

    # 2) search action within a window around row (expand slightly)
    rx1, ry1, rx2, ry2 = map(int, row_bbox)
    padw = int(0.5 * (rx2 - rx1)); padh = int(0.5 * (ry2 - ry1))
    wx1, wy1, wx2, wy2 = _clip_box(rx1 - padw, ry1 - padh, rx2 + padw, ry2 + padh, W, H)
    win = bgr[wy1:wy2, wx1:wx2]
    act_bbox = None
    if action_anchor.get("type") == "template":
        sc, abox = match_template_bbox(win, action_anchor.get("template_png", ""))
        if sc is not None and abox is not None and sc >= float(action_anchor.get("th", 0.82)):
            ax1, ay1, ax2, ay2 = abox
            # map back to global
            act_bbox = [wx1 + ax1, wy1 + ay1, wx1 + ax2, wy1 + ay2]
    elif action_anchor.get("type") == "orb":
        inliers, score = match_orb(win, action_anchor.get("desc_png", ""), ratio=float(action_anchor.get("ratio", 0.75)))
        if inliers >= int(action_anchor.get("min_inliers", 12)):
            ax1, ay1, ax2, ay2 = map(int, action_anchor.get("roi", [0, 0, 0, 0]))
            act_bbox = [wx1 + ax1, wy1 + ay1, wx1 + ax2, wy1 + ay2]
    elif action_anchor.get("type") == "sift":
        # Lazy import of SIFT support above
        try:
            from .anchors import match_sift  # self import ok after function defined
        except Exception:
            match_sift = None  # type: ignore
        if match_sift is not None:
            inliers, score = match_sift(win, action_anchor.get("desc_png", ""), ratio=float(action_anchor.get("ratio", 0.75)))  # type: ignore[arg-type]
            if inliers >= int(action_anchor.get("min_inliers", 8)):
                ax1, ay1, ax2, ay2 = map(int, action_anchor.get("roi", [0, 0, 0, 0]))
                act_bbox = [wx1 + ax1, wy1 + ay1, wx1 + ax2, wy1 + ay2]
    if act_bbox is None:
        return None

    # 3) relation check
    if not check_relation(row_bbox, act_bbox, relation):
        return None
    return act_bbox


def auto_select_anchors(bgr: np.ndarray, bbox: List[float]) -> Dict[str, Any]:
    """Heuristic auto anchor selector around a clicked bbox.

    Returns a compound dict with row_anchor, action_anchor, relation.
    """
    x1, y1, x2, y2 = map(int, bbox)
    H, W = bgr.shape[:2]
    # Row: expand bbox to include likely row region to the left
    row_rx1 = max(0, x1 - int(0.5 * (x2 - x1)))
    row_ry1 = max(0, y1 - int(0.2 * (y2 - y1)))
    row_rx2 = min(W - 1, x2)
    row_ry2 = min(H - 1, y2 + int(0.2 * (y2 - y1)))
    row_tpl = anchors_from(bgr, [row_rx1, row_ry1, row_rx2, row_ry2], pad_ratio=0.05)

    # Compute row uniqueness U by counting template matches over the full page
    try:
        sc_full, _ = match_template_bbox(bgr, row_tpl.get("template_png", ""))
        # count peaks above (th-0.05)
        tpl = _decode_png(row_tpl.get("template_png", ""))
        res = cv2.matchTemplate(bgr, tpl, cv2.TM_CCOEFF_NORMED) if tpl is not None else None
        n_peaks = 1
        if res is not None:
            thr = max(0.0, float(row_tpl.get("th", 0.82)) - 0.05)
            n_peaks = int((res >= thr).sum()) // max(1, int(tpl.shape[0] * tpl.shape[1] // 256))
        row_unique_U = 1.0 / (1.0 + max(0, n_peaks - 1))
    except Exception:
        row_unique_U = 0.7

    # Action: the bbox region itself (template, ORB, and SIFT if available)
    action_tpl = anchors_from(bgr, [x1, y1, x2, y2], pad_ratio=0.05)
    action_orb = gen_orb_features(bgr, [x1, y1, x2, y2])
    action_sift = gen_sift_features(bgr, [x1, y1, x2, y2])
    action_anchor = action_sift or action_orb or action_tpl

    # OCR/Text candidates around bbox
    ocr_all = _tokenize_ocr(_ocr_texts(bgr))
    text_anchor: Optional[Dict[str, Any]] = None
    if ocr_all:
        # pick the rarest token near bbox by proximity heuristic (we don't have per-line boxes, so fallback by token freq)
        freq: Dict[str, int] = {}
        for t in ocr_all:
            freq[t] = freq.get(t, 0) + 1
        rare = sorted(ocr_all, key=lambda t: (freq.get(t, 0), len(t)))
        if rare:
            text_anchor = {"type": "ocr", "text": rare[0], "score_base": 0.0}

    # Scoring utilities
    def score_template(a: Dict[str, Any]) -> float:
        try:
            # uniqueness via peak count
            tpl = _decode_png(a.get("template_png", ""))
            res = cv2.matchTemplate(bgr, tpl, cv2.TM_CCOEFF_NORMED) if tpl is not None else None
            n_peaks = 1
            if res is not None:
                thr = max(0.0, float(a.get("th", 0.82)) - 0.05)
                n_peaks = int((res >= thr).sum()) // max(1, int(tpl.shape[0] * tpl.shape[1] // 256))
            U = 1.0 / (1.0 + max(0, n_peaks - 1))
            # stability under blur/scale
            roi = _decode_png(a.get("template_png", ""))
            hits = 0; tot = 0
            if roi is not None:
                aug = [cv2.GaussianBlur(roi, (3,3), 0), cv2.resize(roi, None, fx=0.9, fy=0.9), cv2.resize(roi, None, fx=1.1, fy=1.1)]
                for r in aug:
                    tot += 1
                    s = match_template(bgr, _encode_png(r))
                    if s >= float(a.get("th", 0.82)) - 0.04:
                        hits += 1
            S = (hits / tot) if tot else 0.6
            # distinctiveness by nearby max corr in a window
            D = 0.6
            return 0.5 * U + 0.3 * S + 0.2 * D
        except Exception:
            return 0.5

    def score_orb(a: Dict[str, Any]) -> float:
        U = 0.7  # ORB features have moderate uniqueness
        S = 0.7  # Good stability under moderate lighting changes
        D = 0.5  # Moderate distinctiveness
        return 0.5 * U + 0.3 * S + 0.2 * D

    def score_sift(a: Dict[str, Any]) -> float:
        U = 0.8  # SIFT features are more unique than ORB
        S = 0.9  # Excellent stability under scale/rotation changes
        D = 0.7  # Better distinctiveness than ORB
        return 0.5 * U + 0.3 * S + 0.2 * D

    def score_text(a: Dict[str, Any]) -> float:
        if not a or not a.get("text"):
            return 0.0
        t = a.get("text")
        cnt = sum(1 for x in ocr_all if x == t)
        U = 1.0 / (1.0 + max(0, cnt - 1))
        S = 0.8 if 2 <= len(t) <= 12 else 0.5
        D = 1.0 - min(0.9, (cnt - 1) * 0.2)
        return 0.5 * U + 0.3 * S + 0.2 * D

    # Pick complementary types for action (template/ORB/SIFT/text)
    action_scores: List[Tuple[float, Dict[str, Any]]] = []
    if action_tpl: action_scores.append((score_template(action_tpl), action_tpl))
    if action_orb: action_scores.append((score_orb(action_orb), action_orb))
    if action_sift: action_scores.append((score_sift(action_sift), action_sift))
    if text_anchor: action_scores.append((score_text(text_anchor), text_anchor))
    # sort and pick highest three with type diversity
    action_scores.sort(key=lambda x: x[0], reverse=True)
    chosen_action = None
    seen_types: set = set()
    for sc, a in action_scores:
        tp = a.get("type")
        if tp in seen_types:
            continue
        seen_types.add(tp)
        chosen_action = a
        chosen_action["score"] = sc
        break
    if chosen_action is None:
        chosen_action = action_tpl or action_orb or (text_anchor or {})

    # Relation: center offset and tolerances relative to row
    dx = (x1 + x2) / 2 - (row_rx1 + row_rx2) / 2
    dy = (y1 + y2) / 2 - (row_ry1 + row_ry2) / 2
    relation = {
        "dx": float(dx),
        "dy": float(dy),
        "tol_x": float(os.getenv("ANCHOR_REL_TOL_X", "0.15")) * max(1, (row_rx2 - row_rx1)),
        "tol_y": float(os.getenv("ANCHOR_REL_TOL_Y", "0.15")) * max(1, (row_ry2 - row_ry1)),
    }

    # If row is not unique (low U), tighten relation tolerances
    if row_unique_U < 0.7:
        relation["tol_x"] *= 0.8
        relation["tol_y"] *= 0.8

    return {
        "row_anchor": row_tpl,
        "action_anchor": chosen_action,
        "text_anchor": text_anchor if text_anchor else None,
        "relation": relation,
    }


def _poly_to_bbox(poly: List[List[float]]) -> List[int]:
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


def _iou(a: List[int], b: List[int]) -> float:
    ax1, ay1, ax2, ay2 = a; bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / max(1.0, float(area))


def state_anchors_from(bgr: np.ndarray, url_hint: Optional[str] = None, ocr_texts: Optional[List[str]] = None, ocr_lines: Optional[List[dict]] = None) -> Dict[str, Any]:
    """Create simple state anchors from prominent regions (top bar + logo-ish center).
    This is a heuristic placeholder to enable second-page verification without OCR.
    """
    H, W = bgr.shape[:2]
    # top bar area
    top = anchors_from(bgr, [int(0.05 * W), int(0.02 * H), int(0.95 * W), int(0.12 * H)], pad_ratio=0.0)
    # left top icon-ish
    left = anchors_from(bgr, [int(0.03 * W), int(0.15 * H), int(0.2 * W), int(0.25 * H)], pad_ratio=0.0)
    # right top icon-ish
    right = anchors_from(bgr, [int(0.8 * W), int(0.15 * H), int(0.97 * W), int(0.25 * H)], pad_ratio=0.0)
    st: Dict[str, Any] = {"anchors": [top, left, right], "vote_k": 2}
    if url_hint:
        st["url_hint"] = url_hint
    if ocr_texts:
        toks = _tokenize_ocr(ocr_texts)
        st["texts"] = toks[:6]
    if ocr_lines:
        # store up to 6 text boxes (polygon + text + conf)
        lines2 = []
        for ln in ocr_lines:
            try:
                poly = ln.get("polygon")
                txt = ln.get("text")
                cf = float(ln.get("conf", 0.0))
                if not poly or not txt:
                    continue
                if 2 <= len(str(txt).strip()) <= 16:
                    lines2.append({"bbox": _poly_to_bbox(poly), "text": txt, "conf": cf})
            except Exception:
                continue
        st["boxes"] = lines2[:6]
    return st


def state_anchors_vote_detail(
    bgr: np.ndarray,
    state: Dict[str, Any],
    ocr_texts: Optional[List[str]] = None,
    current_url: Optional[str] = None,
    expected_texts: Optional[List[str]] = None,
    ocr_lines: Optional[List[dict]] = None,
) -> Dict[str, float]:
    """Composite vote in [0..1] combining templates, OCR tokens, and URL hint.

    vote = tpl_ratio*(1-w_ocr-w_url) + ocr_ratio*w_ocr + url_match*w_url
    """
    w_ocr = float(os.getenv("STATE_W_OCR", "0.25"))
    w_url = float(os.getenv("STATE_W_URL", "0.15"))
    anchors = state.get("anchors", []) or []
    # template ratio
    hits = 0
    for a in anchors:
        if a.get("type") == "template":
            sc = anchors_match(bgr, a)
            if sc >= float(a.get("th", 0.82)):
                hits += 1
    tpl_ratio = (hits / max(1, len(anchors))) if anchors else 0.0
    # OCR ratio: prefer geometry boxes if available; fallback to text token match
    boxes_exp = state.get("boxes") or []
    ocr_ratio = 0.0
    if boxes_exp and ocr_lines:
        # build bboxes for current lines
        cur_boxes = []
        for ln in ocr_lines:
            try:
                poly = ln.get("polygon") or []
                cur_boxes.append(_poly_to_bbox(poly))
            except Exception:
                continue
        hits = 0
        for bx in boxes_exp:
            b = bx.get("bbox")
            if not b:
                continue
            best = 0.0
            for cb in cur_boxes:
                best = max(best, _iou(b, cb))
                if best >= 0.6:
                    break
            if best >= 0.6:
                hits += 1
        ocr_ratio = (hits / max(1, len(boxes_exp))) if boxes_exp else 0.0
    else:
        toks = expected_texts or state.get("texts") or []
        got = _tokenize_ocr(ocr_texts or [])
        ocr_hits = 0
        for t in toks:
            if any((t in (g or "")) for g in got):
                ocr_hits += 1
        ocr_ratio = (ocr_hits / max(1, len(toks))) if toks else 0.0
    # URL match
    url_expected = state.get("url_hint") or ""
    url_match = 0.0
    if url_expected and current_url:
        try:
            from urllib.parse import urlparse
            p1 = urlparse(url_expected); p2 = urlparse(current_url)
            url_match = 1.0 if (p1.netloc == p2.netloc and p1.path == p2.path) else 0.0
        except Exception:
            url_match = 0.0
    vote = max(0.0, min(1.0, tpl_ratio * (1.0 - w_ocr - w_url) + ocr_ratio * w_ocr + url_match * w_url))
    return {"vote": vote, "tpl_ratio": float(tpl_ratio), "ocr_ratio": float(ocr_ratio), "url_match": float(url_match)}


def state_anchors_vote(
    bgr: np.ndarray,
    state: Dict[str, Any],
    ocr_texts: Optional[List[str]] = None,
    current_url: Optional[str] = None,
    expected_texts: Optional[List[str]] = None,
    ocr_lines: Optional[List[dict]] = None,
) -> float:
    d = state_anchors_vote_detail(bgr, state, ocr_texts, current_url, expected_texts, ocr_lines)
    return float(d.get("vote", 0.0))
