# core/strategy_adapter.py - 适配器，连接新策略系统与现有YOLO/锚点系统
from typing import Dict, List, Optional, Tuple
import numpy as np

try:
    from .types import Item, Landmark, BBox
    from .ops_new import *
    from .landmarks import detect_landmarks_cached
    from .strategy_exec import exec_strategy_with_fallback
    from .anchors import auto_select_anchors, locate_instance
except ImportError:
    print("[strategy_adapter] Warning: Some imports failed, check dependencies")

def yolo_detection_to_item(detection, attrs: set = None) -> Item:
    """将YOLO检测结果转换为Item对象"""
    if attrs is None:
        attrs = set()
    
    # 假设detection有这些字段，根据实际调整
    item_id = str(getattr(detection, 'id', 'unknown'))
    bbox = getattr(detection, 'bbox_xyxy', [0,0,0,0])
    # 转换为x,y,w,h格式
    if len(bbox) == 4:
        x1, y1, x2, y2 = bbox
        bbox = (x1, y1, x2-x1, y2-y1)
    
    class_name = getattr(detection, 'class_name', 'unknown')
    
    # 尝试获取OCR文本（如果有）
    ocr_text = getattr(detection, 'ocr_text', None)
    
    return Item(
        id=item_id,
        bbox=bbox,
        class_name=class_name,
        ocr_text=ocr_text,
        attrs=attrs.copy(),
        meta={
            'confidence': getattr(detection, 'conf', 0.0),
            'source': 'yolo'
        }
    )

def preprocess_items_with_attrs(items: List[Item], bgr: np.ndarray = None, 
                               ocr_lines: List[dict] = None) -> List[Item]:
    """为Items添加属性标注（unread/badge/selected等）"""
    if bgr is None or ocr_lines is None:
        return items
        
    processed = []
    for item in items:
        new_item = Item(
            id=item.id,
            bbox=item.bbox,
            class_name=item.class_name,
            ocr_text=item.ocr_text,
            attrs=item.attrs.copy(),
            image_thumb=item.image_thumb,
            meta=item.meta.copy()
        )
        
        # 使用现有的has_attr函数检测属性
        try:
            from .ops import has_attr_unread_by_ocr, has_attr_unread_by_color
            
            # 检测unread属性
            if has_attr_unread_by_ocr(item.bbox, ocr_lines):
                new_item.attrs.add('unread')
                new_item.attrs.add('badge')
            elif has_attr_unread_by_color(bgr, item.bbox):
                new_item.attrs.add('unread')  
                new_item.attrs.add('badge')
                
        except ImportError:
            pass
            
        processed.append(new_item)
    
    return processed

def locate_action_point(target_item: Item, bgr: np.ndarray = None) -> Optional[Tuple[int, int]]:
    """使用现有锚点系统定位Item的最佳点击点"""
    if not target_item or bgr is None:
        return None
        
    try:
        # 使用现有的auto_select_anchors系统
        x, y, w, h = target_item.bbox
        bbox_list = [x, y, x+w, y+h]  # 转换为x1,y1,x2,y2格式
        
        anchors = auto_select_anchors(bgr, bbox_list)
        if not anchors:
            return None
            
        # 尝试定位实例
        row_anchor = anchors.get('row_anchor')
        action_anchor = anchors.get('action_anchor')
        relation = anchors.get('relation')
        
        if row_anchor and action_anchor and relation:
            result = locate_instance(bgr, row_anchor, action_anchor, relation)
            if result and len(result) >= 2:
                return (int(result[0]), int(result[1]))
                
    except Exception as e:
        print(f"[strategy_adapter] locate_action_point failed: {e}")
        
    return None

def get_yolo_hist_from_items(items: List[Item]) -> Dict[str, int]:
    """从Items生成YOLO类别直方图"""
    hist = {}
    for item in items:
        cls = item.class_name
        hist[cls] = hist.get(cls, 0) + 1
    return hist

def extract_top_ocr_tokens(ocr_lines: List[dict], max_tokens: int = 10) -> List[str]:
    """从OCR结果提取顶部关键词"""
    if not ocr_lines:
        return []
        
    tokens = []
    for line in ocr_lines:
        text = line.get('text', '').strip()
        if text and len(text) > 1:  # 过滤单字符
            tokens.append(text)
            
    # 按y坐标排序，取前面的
    try:
        sorted_lines = sorted(ocr_lines, key=lambda x: x.get('polygon', [[0,0]])[0][1])
        top_tokens = []
        for line in sorted_lines[:max_tokens]:
            text = line.get('text', '').strip()
            if text:
                top_tokens.append(text)
        return top_tokens[:max_tokens]
    except:
        return tokens[:max_tokens]

def infer_page_kind(url_hint: str, yolo_hist: Dict[str, int], landmarks: Dict[str, Landmark]) -> str:
    """推断页面类型"""
    if not url_hint:
        url_hint = ""
        
    url_lower = url_hint.lower()
    
    # URL启发式
    if "search" in url_lower:
        return "search_results"
    elif "chat" in url_lower or "conversation" in url_lower:
        return "chat_detail"
    elif "explore" in url_lower or "feed" in url_lower:
        return "feed"
    elif "profile" in url_lower or "user" in url_lower:
        return "profile"
        
    # 地标启发式
    if "search_bar" in landmarks and "results_container" in landmarks:
        return "search_results"
    elif "chat_sidebar" in landmarks:
        return "sidebar_list" 
    elif "tabs" in landmarks:
        return "tabs"
        
    # YOLO类别启发式
    if yolo_hist.get("card", 0) > 5:
        return "feed" if yolo_hist.get("avatar", 0) > 3 else "search_results"
    elif yolo_hist.get("list_row", 0) > 5:
        return "sidebar_list"
        
    return "unknown"

# 主要的适配器函数
def create_strategy_context(yolo_detections, bgr: np.ndarray, ocr_lines: List[dict],
                           url_hint: str = "") -> dict:
    """创建策略选择所需的上下文"""
    # 转换检测结果为Items
    items = [yolo_detection_to_item(det) for det in yolo_detections]
    
    # 添加属性标注
    items = preprocess_items_with_attrs(items, bgr, ocr_lines)
    
    # 检测地标
    landmarks = detect_landmarks_cached(items, [line.get('text', '') for line in ocr_lines], bgr)
    
    # 生成统计信息
    yolo_hist = get_yolo_hist_from_items(items)
    top_ocr_tokens = extract_top_ocr_tokens(ocr_lines)
    page_kind = infer_page_kind(url_hint, yolo_hist, landmarks)
    
    return {
        'items': items,
        'landmarks': landmarks, 
        'yolo_hist': yolo_hist,
        'top_ocr_tokens': top_ocr_tokens,
        'page_kind': page_kind,
        'bgr': bgr,
        'ocr_lines': ocr_lines
    }