from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
    x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
    iw = max(0.0, x2 - x1); ih = max(0.0, y2 - y1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, (a[2] - a[0])) * max(0.0, (a[3] - a[1]))
    area_b = max(0.0, (b[2] - b[0])) * max(0.0, (b[3] - b[1]))
    union = area_a + area_b - inter + 1e-6
    return float(inter / union) if union > 0 else 0.0


def box_to_geom(bbox: Sequence[float], page_w: int, page_h: int) -> Dict[str, float]:
    x1, y1, x2, y2 = map(float, bbox)
    w = max(1.0, x2 - x1)
    h = max(1.0, y2 - y1)
    cx = (x1 + x2) / 2.0 / float(page_w)
    cy = (y1 + y2) / 2.0 / float(page_h)
    return {
        "cx": round(cx, 4),
        "cy": round(cy, 4),
        "w": round(w / float(page_w), 4),
        "h": round(h / float(page_h), 4),
        "area": round((w * h) / float(page_w * page_h), 6),
        "aspect": round(w / h, 3),
    }


def region_tag(cx: float, cy: float) -> str:
    # cx, cy are normalized (0..1)
    if cy < 0.12:
        return "topbar"
    if cy < 0.25:
        return "toolbar"
    if cy > 0.88:
        return "bottombar"
    return "content"


def is_overlap_modal(bbox: Sequence[float], modal_bbox_list: Optional[Sequence[Sequence[float]]] = None, thr: float = 0.2) -> int:
    if not modal_bbox_list:
        return 0
    return 1 if any(iou(bbox, m) > thr for m in modal_bbox_list) else 0


def yolo_to_geom_candidates(
    yolo_json: Dict[str, Any],
    page_w: int,
    page_h: int,
    modal_bbox_list: Optional[Sequence[Sequence[float]]] = None,
    k: int = 8,
) -> Dict[str, Any]:
    """Convert YOLO API JSON to a compact geometry-only candidate set for the vision-first picker.

    Returns: {"k": int, "candidates": [...], "meta": {"page_w":..., "page_h":...}}
    Each candidate: {id, cx, cy, w, h, area, aspect, region, overlap_modal}
    """
    dets = list(yolo_json.get("detections", []) or [])
    # Sort by confidence desc then area desc
    def _area(d: Dict[str, Any]) -> float:
        x1, y1, x2, y2 = d.get("bbox_xyxy", [0, 0, 0, 0])
        return max(0.0, (x2 - x1) * (y2 - y1))

    dets.sort(key=lambda d: (float(d.get("conf", 0.0)), _area(d)), reverse=True)
    dets = dets[: max(1, int(k))]

    cands: List[Dict[str, Any]] = []
    for d in dets:
        bid = int(d.get("id", 0))
        box = d.get("bbox_xyxy", [0, 0, 0, 0])
        g = box_to_geom(box, page_w, page_h)
        rg = region_tag(g["cx"], g["cy"])
        ov = is_overlap_modal(box, modal_bbox_list)
        cands.append({
            "id": f"c{bid}",
            **g,
            "region": rg,
            "overlap_modal": ov,
        })

    return {"k": len(cands), "candidates": cands, "meta": {"page_w": page_w, "page_h": page_h}}

