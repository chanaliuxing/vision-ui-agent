from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

import math

from .yolo_client import Detection


@dataclass
class LocateResult:
    chosen: Optional[Detection]
    candidates: List[Detection]
    score: float


def _center_bias(cx: float, cy: float, w: float, h: float) -> float:
    # Prefer center-ish targets: 1.0 at center, smaller near edges.
    nx = abs((cx - w / 2) / (w / 2))
    ny = abs((cy - h / 2) / (h / 2))
    dist = math.sqrt(nx * nx + ny * ny)
    return max(0.5, 1.2 - dist)  # 1.2 at center -> ~0.5 at corners


def select_best(
    detections: Iterable[Detection],
    target_classes: Iterable[str],
    screen_w: int,
    screen_h: int,
    conf_min: float = 0.5,
) -> LocateResult:
    tset = {c.strip() for c in target_classes}
    cands: List[Detection] = [d for d in detections if d.class_name in tset and d.conf >= conf_min]

    best: Optional[Detection] = None
    best_score = -1.0
    for d in cands:
        x1, y1, x2, y2 = d.bbox_xyxy
        w = max(1.0, x2 - x1)
        h = max(1.0, y2 - y1)
        area = (w * h) / float(screen_w * screen_h)
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        score = d.conf * area * _center_bias(cx, cy, screen_w, screen_h)
        if score > best_score:
            best, best_score = d, score
    return LocateResult(chosen=best, candidates=cands, score=best_score if best else 0.0)


def bbox_center(bbox_xyxy: List[float], padding_px: float = 0.0) -> Tuple[int, int]:
    x1, y1, x2, y2 = bbox_xyxy
    if padding_px:
        x1 += padding_px
        y1 += padding_px
        x2 -= padding_px
        y2 -= padding_px
    return int((x1 + x2) / 2.0), int((y1 + y2) / 2.0)

