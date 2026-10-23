from dataclasses import dataclass
from typing import Tuple


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


@dataclass
class CaptureMeta:
    cap_w: int
    cap_h: int
    win_offset_x: int = 0
    win_offset_y: int = 0
    dpr: float = 1.0


@dataclass
class PreprocMeta:
    frame_w: int
    frame_h: int
    imgsz: int
    letterbox: bool = True
    normalized: bool = False


def to_capture_coords(bbox, pre: PreprocMeta, cap: CaptureMeta) -> Tuple[float, float, float, float]:
    x1, y1, x2, y2 = bbox

    # 1) un-normalize if needed
    if pre.normalized:
        x1 *= pre.frame_w; x2 *= pre.frame_w
        y1 *= pre.frame_h; y2 *= pre.frame_h

    # 2) de-letterbox or scale back
    if pre.letterbox and pre.frame_w == pre.frame_h:
        imgsz = pre.frame_w
        r = min(imgsz / cap.cap_w, imgsz / cap.cap_h)
        new_w, new_h = cap.cap_w * r, cap.cap_h * r
        dw = (imgsz - new_w) / 2.0
        dh = (imgsz - new_h) / 2.0

        def inv_map(x, y):
            return (x - dw) / r, (y - dh) / r

        x1, y1 = inv_map(x1, y1)
        x2, y2 = inv_map(x2, y2)
    else:
        sx = cap.cap_w / float(pre.frame_w)
        sy = cap.cap_h / float(pre.frame_h)
        x1, x2 = x1 * sx, x2 * sx
        y1, y2 = y1 * sy, y2 * sy

    # Clamp inside capture image
    x1 = _clamp(x1, 0, cap.cap_w - 1); x2 = _clamp(x2, 0, cap.cap_w - 1)
    y1 = _clamp(y1, 0, cap.cap_h - 1); y2 = _clamp(y2, 0, cap.cap_h - 1)
    if x2 < x1: x1, x2 = x2, x1
    if y2 < y1: y1, y2 = y2, y1
    return x1, y1, x2, y2


def click_point_from_box(x1: float, y1: float, x2: float, y2: float, cls: str | None = None) -> Tuple[int, int]:
    w, h = x2 - x1, y2 - y1
    pad = max(3, int(0.05 * min(w, h)))
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    if cls in {"text_field", "search_bar", "caption_field", "input"}:
        cx = x1 + min(24, int(0.2 * w))
    cx = _clamp(cx, x1 + pad, x2 - pad)
    cy = _clamp(cy, y1 + pad, y2 - pad)
    return int(round(cx)), int(round(cy))


def map_id_to_screen_point(bbox, cls: str | None, pre: PreprocMeta, cap: CaptureMeta) -> Tuple[int, int]:
    x1, y1, x2, y2 = to_capture_coords(bbox, pre, cap)
    cx, cy = click_point_from_box(x1, y1, x2, y2, cls=cls)
    screen_x = cap.win_offset_x + int(cx)
    screen_y = cap.win_offset_y + int(cy)
    return screen_x, screen_y

