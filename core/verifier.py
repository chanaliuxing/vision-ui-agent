from typing import List, Optional, Dict, Any


def _has_any(yolo_after: Dict[str, Any], classes: List[str]) -> bool:
    dets = (yolo_after or {}).get("detections", []) or []
    names = {str(d.get("class_name", "")) for d in dets if isinstance(d, dict)}
    return any(c in names for c in classes)


def step_gate_verify(verify_rules: List[str], yolo_after: Dict[str, Any], ocr_lines: Optional[List[str]] = None) -> bool:
    """Lightweight per-step gate. Only allow transition when rules pass.

    - verify_rules: list of short tokens or phrases, e.g., ["page_change"],
      or logical signals we can map to YOLO/OCR hints like "出现搜索结果".
    - yolo_after: YOLO detections dict (expects key "detections").
    - ocr_lines: optional OCR text lines to search.
    """
    if not verify_rules:
        return True
    token_map = {
        "光标闪烁": "cursor_blink",
        "标题框被高亮": "text_field_focus",
        "出现搜索结果": "search_results",
    }
    expect = [token_map.get(r, r) for r in verify_rules]
    if _has_any(yolo_after, expect):
        return True
    if ocr_lines:
        joined = " ".join(ocr_lines).lower()
        for r in verify_rules:
            try:
                if str(r).lower() in joined:
                    return True
            except Exception:
                continue
    return False


def is_wrong_page_signature(yolo_after: Dict[str, Any], goal_text: str) -> bool:
    """Heuristic: if we see detail-page hints while goal is a home/search operation."""
    dets = (yolo_after or {}).get("detections", []) or []
    names = {str(d.get("class_name", "")) for d in dets if isinstance(d, dict)}
    goal_l = (goal_text or "").lower()
    detail_signals = {"post_detail_header", "comment_panel", "detail_toolbar"}
    if names & detail_signals:
        if any(k in goal_l for k in ("搜索", "search", "选择", "点击第一排", "点击第一")):
            return True
    return False

