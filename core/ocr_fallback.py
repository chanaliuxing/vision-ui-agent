from typing import List, Dict, Any, Optional, Tuple

SEARCH_KEYWORDS = [
    "搜索", "搜素", "查找", "搜索一下", "🔍", "Search", "search", "Find", "find", "Search here"
]


def _merge_boxes(boxes: List[List[int]], margin: int = 8) -> Optional[List[int]]:
    if not boxes:
        return None
    x1 = min(b[0] for b in boxes) - margin
    y1 = min(b[1] for b in boxes) - margin
    x2 = max(b[2] for b in boxes) + margin
    y2 = max(b[3] for b in boxes) + margin
    return [max(0, x1), max(0, y1), max(0, x2), max(0, y2)]


def find_search_field_region(ocr_lines: List[Dict[str, Any]], viewport_wh: Tuple[int, int]) -> Optional[List[int]]:
    """Return coarse bbox [x1,y1,x2,y2] for search field region.

    Heuristics:
    - keyword hit → collect nearby lines and merge
    - prefer upper 40% (topbar bias)
    - reasonable min width/height
    """
    W, H = viewport_wh
    hits: List[List[int]] = []
    for ln in ocr_lines:
        try:
            txt = (ln.get("text") or "").strip()
            if not txt:
                continue
            if any(k.lower() in txt.lower() for k in SEARCH_KEYWORDS):
                b = ln.get("bbox")
                if isinstance(b, (list, tuple)) and len(b) >= 4:
                    hits.append([int(b[0]), int(b[1]), int(b[2]), int(b[3])])
        except Exception:
            continue
    if not hits:
        return None
    merged = _merge_boxes(hits, margin=12)
    if not merged:
        return None
    # topbar bias
    cx = (merged[0] + merged[2]) // 2
    cy = (merged[1] + merged[3]) // 2
    if cy > int(0.45 * H):
        merged[3] = max(merged[1] + 24, int(0.4 * H))
    if (merged[2] - merged[0] < max(60, int(0.08 * W))) or (merged[3] - merged[1] < max(24, int(0.03 * H))):
        return None
    return merged
