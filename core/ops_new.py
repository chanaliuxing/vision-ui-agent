# core/ops_new.py - Enhanced structural operators for strategy execution
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple, Set
import cv2
import numpy as np
import math
import os

# Import new types
try:
    from .types import Item, Landmark, BBox
except ImportError:
    # Fallback for standalone usage
    from dataclasses import dataclass, field
    BBox = Tuple[int, int, int, int]
    
    @dataclass
    class Item:
        id: str
        bbox: BBox
        class_name: str
        ocr_text: Optional[str] = None
        attrs: Set[str] = field(default_factory=set)
        meta: Dict = field(default_factory=dict)

# ===== ITEM-BASED OPERATORS =====

IOU_MIN_CONTAIN = float(os.getenv("OPS_IOU_CONTAIN", "0.7"))

def _center(b: BBox) -> Tuple[float, float]:
    """Get bbox center coordinates"""
    x,y,w,h = b
    return (x+w/2, y+h/2)

def _iou(a: BBox, b: BBox) -> float:
    """Calculate Intersection over Union"""
    ax,ay,aw,ah = a
    bx,by,bw,bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax+aw, bx+bw), min(ay+ah, by+bh)
    inter = max(0,x2-x1)*max(0,y2-y1)
    union = aw*ah + bw*bh - inter
    return inter/union if union>0 else 0.0

def within(items: List[Item], container: Item, iou_thr: float = None) -> List[Item]:
    """Return items with bbox largely within container"""
    if not container or not items:
        return items
    
    if iou_thr is None:
        iou_thr = IOU_MIN_CONTAIN
        
    cx,cy,cw,ch = container.bbox
    res = []
    for it in items:
        if _iou(it.bbox, container.bbox) >= iou_thr:
            res.append(it)
    return res

def below(items: List[Item], landmark: Item, margin_px: int = 4) -> List[Item]:
    """Return items below landmark"""
    if not landmark or not items:
        return items
    _, ly, _, lh = landmark.bbox
    lyb = ly + lh + margin_px
    return [it for it in items if it.bbox[1] >= lyb]

def right_of(items: List[Item], landmark: Item, margin_px: int = 4) -> List[Item]:
    """Return items to the right of landmark"""
    if not landmark or not items:
        return items
    lx, _, lw, _ = landmark.bbox
    r = lx + lw + margin_px
    return [it for it in items if it.bbox[0] >= r]

def nearest_to(items: List[Item], landmark: Item, metric: str = "center") -> Optional[Item]:
    """Return item nearest to landmark"""
    if not items or not landmark:
        return None
    cx, cy = _center(landmark.bbox)
    items_sorted = sorted(items, key=lambda it: math.dist(_center(it.bbox), (cx,cy)))
    return items_sorted[0]

def sort_by_y(items: List[Item], reverse: bool = False) -> List[Item]:
    """Sort items by y coordinate"""
    return sorted(items, key=lambda it: it.bbox[1], reverse=reverse)

def topmost(items: List[Item]) -> Optional[Item]:
    """Return topmost (minimum y) item"""
    if not items:
        return None
    return sort_by_y(items)[0]

def nth(items: List[Item], n: int) -> Optional[Item]:
    """Return nth item (1-indexed)"""
    if not items or n<=0 or n>len(items):
        return None
    return sort_by_y(items)[n-1]

def cluster_list(items: List[Item], axis: str = "y", gap_ratio: float = None) -> List[List[Item]]:
    """Cluster items into rows by y proximity"""
    if not items:
        return []
    
    if gap_ratio is None:
        gap_ratio = float(os.getenv("OPS_ROW_GAP_RATIO", "0.25"))
        
    items_sorted = sorted(items, key=lambda it: it.bbox[1] + it.bbox[3]/2)
    avg_h = sum([it.bbox[3] for it in items_sorted])/len(items_sorted)
    rows, cur = [], [items_sorted[0]]
    
    for a,b in zip(items_sorted, items_sorted[1:]):
        ay = a.bbox[1]+a.bbox[3]/2
        by = b.bbox[1]+b.bbox[3]/2
        if abs(by - ay) > avg_h*gap_ratio:
            rows.append(cur)
            cur=[b]
        else:
            cur.append(b)
    rows.append(cur)
    return rows

def gridize(container_items: List[Item]) -> List[List[Item]]:
    """Organize items into grid (rows then columns)"""
    if not container_items:
        return []
    rows = cluster_list(container_items)
    # Sort each row by x coordinate  
    grid = []
    for row in rows:
        row_sorted = sorted(row, key=lambda it: it.bbox[0])
        grid.append(row_sorted)
    return grid

def has_attr(items: List[Item], attr: str) -> List[Item]:
    """Filter items that have the specified attribute"""
    return [it for it in items if attr in it.attrs]

def text_match(items: List[Item], text: str, case_sensitive: bool = False) -> List[Item]:
    """Filter items whose OCR text contains the given text"""
    if not text:
        return items
        
    if case_sensitive:
        return [it for it in items if it.ocr_text and text in it.ocr_text]
    else:
        text_lower = text.lower()
        return [it for it in items if it.ocr_text and text_lower in it.ocr_text.lower()]

def click_region(target: Item, role: str = "action", bgr: np.ndarray = None) -> Optional[Tuple[int, int]]:
    """Return optimal click coordinates for target item"""
    if not target:
        return None
    
    # Try to get action point from existing anchor system
    try:
        from .strategy_adapter import locate_action_point
        if bgr is not None:
            pt = locate_action_point(target, bgr)
            if pt:
                return pt
    except (ImportError, AttributeError) as e:
        print(f"[click_region] Anchor system not available: {e}")
    
    # Fallback to bbox-based positioning
    x,y,w,h = target.bbox
    click_bias = float(os.getenv("OPS_CLICK_BIAS_X", "0.7"))
    
    if role == "action":
        # Click towards right side for action buttons
        return (int(x + click_bias*w), int(y + 0.5*h))
    else:
        # Default center click
        return (int(x + 0.5*w), int(y + 0.5*h))

# ===== LEGACY COMPATIBILITY =====
# Import existing functions from original ops.py
try:
    from . import ops as legacy_ops
    # Preserve any existing functions that don't conflict
    has_attr_unread_by_ocr = getattr(legacy_ops, 'has_attr_unread_by_ocr', None)
    has_attr_unread_by_color = getattr(legacy_ops, 'has_attr_unread_by_color', None)  
    has_attr_unread_by_hough = getattr(legacy_ops, 'has_attr_unread_by_hough', None)
except ImportError:
    pass