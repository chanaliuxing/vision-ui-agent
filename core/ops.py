from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple
import cv2
import numpy as np


# NOTE: This module provides structural operator stubs for strategy execution.
# Implementations are intentionally minimal for initial integration and can be
# progressively completed per-strategy.


BBox = Tuple[int, int, int, int]


def within(b: BBox, container: BBox) -> bool:
    x1, y1, x2, y2 = b; X1, Y1, X2, Y2 = container
    return x1 >= X1 and y1 >= Y1 and x2 <= X2 and y2 <= Y2


def below(b: BBox, landmark: BBox, tol: int = 4) -> bool:
    _, y1, _, _ = b
    _, ly1, _, ly2 = landmark
    return y1 >= (ly2 - tol)


def right_of(b: BBox, landmark: BBox, tol: int = 4) -> bool:
    x1, _, _, _ = b
    lx1, _, lx2, _ = landmark
    return x1 >= (lx2 - tol)


def nearest_to(target: BBox, boxes: List[BBox]) -> Optional[BBox]:
    if not boxes:
        return None
    def center(b):
        x1, y1, x2, y2 = b
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    cx, cy = center(target)
    best = None; best_d = 1e18
    for b in boxes:
        bx, by = center(b)
        d = (bx - cx) ** 2 + (by - cy) ** 2
        if d < best_d:
            best = b; best_d = d
    return best


def sort_by_y(boxes: List[BBox]) -> List[BBox]:
    return sorted(boxes, key=lambda b: (b[1], b[0]))


def nth(boxes: List[BBox], n: int) -> Optional[BBox]:
    if n <= 0 or n > len(boxes):
        return None
    return boxes[n - 1]


def cluster_list(items: List[BBox]) -> List[List[BBox]]:
    # Very naive row clustering by y proximity; placeholder for a better grouping.
    if not items:
        return []
    items2 = sort_by_y(items)
    rows: List[List[BBox]] = []
    th = 24
    cur: List[BBox] = []
    for b in items2:
        if not cur:
            cur = [b]
            continue
        _, y1, _, y2 = b
        _, cy1, _, cy2 = cur[-1]
        if abs(y1 - cy1) < th or abs(y2 - cy2) < th:
            cur.append(b)
        else:
            rows.append(cur); cur = [b]
    if cur:
        rows.append(cur)
    return rows


def has_attr_unread_by_ocr(b: BBox, ocr_lines: Optional[List[dict]]) -> bool:
    """Very rough heuristic: if any OCR line inside bbox is a small integer (1-999), treat as badge-like."""
    if not ocr_lines:
        return False
    x1, y1, x2, y2 = b
    for ln in ocr_lines:
        poly = ln.get("polygon") or []
        txt = (ln.get("text") or "").strip()
        if not poly or not txt:
            continue
        try:
            val = int(txt)
        except Exception:
            continue
        # filter out large numbers (timestamps) by bounding value
        if 0 < val <= 999:
            # use polygon centroid
            xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
            cx = sum(xs) / max(1, len(xs)); cy = sum(ys) / max(1, len(ys))
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                return True
    return False


def has_attr_unread_by_color(bgr: np.ndarray, b: BBox) -> bool:
    """Heuristic red-badge detection inside bbox via HSV threshold.
    Returns True if small red-ish region ratio exceeds a tiny threshold.
    """
    try:
        x1, y1, x2, y2 = b
        x1 = max(0, x1); y1 = max(0, y1); x2 = min(bgr.shape[1] - 1, x2); y2 = min(bgr.shape[0] - 1, y2)
        if x2 <= x1 or y2 <= y1:
            return False
        roi = bgr[y1:y2, x1:x2]
        if roi.size == 0:
            return False
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        # red can wrap around 0 and 180 in HSV; check two ranges
        lower1 = np.array([0, 100, 100], dtype=np.uint8)
        upper1 = np.array([10, 255, 255], dtype=np.uint8)
        lower2 = np.array([170, 100, 100], dtype=np.uint8)
        upper2 = np.array([180, 255, 255], dtype=np.uint8)
        m1 = cv2.inRange(hsv, lower1, upper1)
        m2 = cv2.inRange(hsv, lower2, upper2)
        mask = cv2.bitwise_or(m1, m2)
        ratio = float(np.count_nonzero(mask)) / float(mask.size)
        if ratio < 0.001:
            return False
        # shape heuristic: connected component with moderate area and near-circular
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            area = cv2.contourArea(c)
            if area < max(6, 0.0002 * mask.size):
                continue
            per = cv2.arcLength(c, True)
            if per <= 0:
                continue
            circ = 4 * np.pi * (area / (per * per))  # 1.0 for circle
            if circ >= 0.4:
                return True
        return False
    except Exception:
        return False


def has_attr_unread_by_hough(bgr: np.ndarray, b: BBox) -> bool:
    """Detect small circular badges using HoughCircles on a red-masked ROI."""
    try:
        x1, y1, x2, y2 = b
        x1 = max(0, x1); y1 = max(0, y1); x2 = min(bgr.shape[1] - 1, x2); y2 = min(bgr.shape[0] - 1, y2)
        if x2 <= x1 or y2 <= y1:
            return False
        roi = bgr[y1:y2, x1:x2]
        if roi.size == 0:
            return False
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        lower1 = np.array([0, 100, 80], dtype=np.uint8)
        upper1 = np.array([10, 255, 255], dtype=np.uint8)
        lower2 = np.array([170, 100, 80], dtype=np.uint8)
        upper2 = np.array([180, 255, 255], dtype=np.uint8)
        mask = cv2.bitwise_or(cv2.inRange(hsv, lower1, upper1), cv2.inRange(hsv, lower2, upper2))
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.bitwise_and(gray, gray, mask=mask)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        # radius range relative to ROI size
        min_r = max(3, int(min(roi.shape[:2]) * 0.01))
        max_r = max(min_r + 2, int(min(roi.shape[:2]) * 0.06))
        circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=8, param1=60, param2=12, minRadius=min_r, maxRadius=max_r)
        return circles is not None and len(circles) > 0
    except Exception:
        return False


def group_by_rows(items: List[BBox]) -> List[List[BBox]]:
    """Alias for row clustering; future hook for improved grouping."""
    return cluster_list(items)


def union_bbox(boxes: List[BBox]) -> Optional[BBox]:
    if not boxes:
        return None
    x1 = min(b[0] for b in boxes)
    y1 = min(b[1] for b in boxes)
    x2 = max(b[2] for b in boxes)
    y2 = max(b[3] for b in boxes)
    return (x1, y1, x2, y2)


def filter_in_region(boxes: List[BBox], region: BBox) -> List[BBox]:
    X1, Y1, X2, Y2 = region
    out: List[BBox] = []
    for b in boxes:
        x1, y1, x2, y2 = b
        if x1 >= X1 and y1 >= Y1 and x2 <= X2 and y2 <= Y2:
            out.append(b)
    return out


def has_attr_unread(bgr: np.ndarray, b: BBox, ocr_lines: Optional[List[dict]], badge_boxes: Optional[List[BBox]] = None) -> int:
    """Composite unread scoring (0..3): badge overlap + OCR small number + red-dot color.
    Returns an integer score to allow weighted selection.
    """
    score = 0
    # badge overlap
    if badge_boxes:
        x1, y1, x2, y2 = b
        for bb in badge_boxes:
            bx1, by1, bx2, by2 = bb
            ix1, iy1 = max(x1, bx1), max(y1, by1)
            ix2, iy2 = min(x2, bx2), min(y2, by2)
            if ix2 > ix1 and iy2 > iy1:
                score += 1
                break
    # OCR small number
    if has_attr_unread_by_ocr(b, ocr_lines):
        score += 1
    # Red badge color / circle
    try:
        if has_attr_unread_by_color(bgr, b):
            score += 1
        elif has_attr_unread_by_hough(bgr, b):
            score += 1
    except Exception:
        pass
    return score
