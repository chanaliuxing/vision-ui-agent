# core/landmarks.py - 通用地标检测（YOLO+OCR+模板融合）
from typing import Dict, List, Optional
import numpy as np

try:
    from .types import Item, Landmark
except ImportError:
    from .ops_new import Item, Landmark

# YOLO类别到地标角色的映射
YOLO2ROLE = {
    "search_input": "search_bar",
    "magnifier": "search_bar", 
    "search": "search_bar",
    "side_list": "chat_sidebar",
    "sidebar": "chat_sidebar",
    "results_container": "results_container",
    "results": "results_container",
    "tab_bar": "tabs",
    "tabs": "tabs",
    "top_bar": "top_bar",
    "header": "top_bar",
    "navbar": "top_bar"
}

# OCR关键词提示
OCR_HINTS = {
    "search_bar": ["搜索", "search", "find", "查找", "Search"],
    "chat_sidebar": ["联系人", "会话", "聊天", "contacts", "chats"],
    "results_container": ["结果", "results", "条结果", "个结果"], 
    "tabs": ["推荐", "发现", "关注", "热门", "tab", "首页", "home"],
    "top_bar": ["返回", "back", "关闭", "close", "菜单", "menu"]
}

# 地标位置启发式规则
POSITION_RULES = {
    "search_bar": {"y_ratio_max": 0.3, "width_min": 100},  # 通常在页面上部
    "top_bar": {"y_ratio_max": 0.15, "width_min": 200},    # 页面最上方
    "tabs": {"y_ratio_max": 0.4, "width_min": 150},        # 上部或中上部
    "chat_sidebar": {"x_ratio_max": 0.3, "height_min": 300}, # 通常在左侧
    "results_container": {"y_ratio_min": 0.2}              # 通常在中下部
}

def _score_candidate(item: Item, role: str, ocr_lines: List[str], 
                     screen_w: int = 1920, screen_h: int = 1080, tpl_score: float = 0.0) -> float:
    """为候选地标打分"""
    score = 0.0
    x, y, w, h = item.bbox
    
    # 1. YOLO类别匹配
    for cls, r in YOLO2ROLE.items():
        if r == role and item.class_name == cls:
            score += 0.6
            break
    
    # 2. OCR关键词匹配
    if item.ocr_text:
        for hint in OCR_HINTS.get(role, []):
            if hint.lower() in item.ocr_text.lower():
                score += 0.25
                break
    
    # 3. 位置启发式规则
    rules = POSITION_RULES.get(role, {})
    if rules:
        x_ratio = x / max(screen_w, 1)
        y_ratio = y / max(screen_h, 1)
        
        # Y位置规则
        if "y_ratio_max" in rules and y_ratio <= rules["y_ratio_max"]:
            score += 0.1
        if "y_ratio_min" in rules and y_ratio >= rules["y_ratio_min"]:
            score += 0.1
            
        # X位置规则  
        if "x_ratio_max" in rules and x_ratio <= rules["x_ratio_max"]:
            score += 0.1
            
        # 尺寸规则
        if "width_min" in rules and w >= rules["width_min"]:
            score += 0.05
        if "height_min" in rules and h >= rules["height_min"]:
            score += 0.05
    
    # 4. 模板匹配加分
    if tpl_score > 0:
        score += min(tpl_score, 0.15)
    
    # 5. 类别名通用匹配
    if role in item.class_name.lower():
        score += 0.1
    
    return score

def _template_match_score(item: Item, role: str, img: np.ndarray = None) -> float:
    """模板匹配得分（占位实现）"""
    # TODO: 实现具体的模板匹配
    # 这里可以集成现有的模板匹配逻辑
    # 如放大镜图标、输入框端帽、分割线等
    return 0.0

def detect_landmarks(all_items: List[Item], ocr_lines: List[str] = None, 
                     img: np.ndarray = None) -> Dict[str, Landmark]:
    """检测页面中的通用地标"""
    if ocr_lines is None:
        ocr_lines = []
    
    screen_w = img.shape[1] if img is not None else 1920
    screen_h = img.shape[0] if img is not None else 1080
    
    roles = ["search_bar", "chat_sidebar", "results_container", "tabs", "top_bar"]
    landmarks: Dict[str, Landmark] = {}
    
    for role in roles:
        candidates = []
        
        for item in all_items:
            # 计算模板匹配得分
            tpl_score = _template_match_score(item, role, img)
            
            # 综合评分
            score = _score_candidate(item, role, ocr_lines, screen_w, screen_h, tpl_score)
            
            # 过滤低分候选
            if score >= 0.4:  # 最低置信度阈值
                # 创建Landmark
                landmark = Landmark(
                    id=item.id,
                    bbox=item.bbox,
                    class_name=item.class_name,
                    ocr_text=item.ocr_text,
                    attrs=item.attrs.copy(),
                    image_thumb=item.image_thumb,
                    meta=item.meta.copy(),
                    role=role
                )
                landmark.meta["lm_score"] = score
                candidates.append(landmark)
        
        # 选择最高分的候选作为该角色的地标
        if candidates:
            candidates.sort(key=lambda x: x.meta.get("lm_score", 0), reverse=True)
            landmarks[role] = candidates[0]
    
    return landmarks

def get_landmark_cache_key(all_items: List[Item], ocr_lines: List[str] = None) -> str:
    """生成地标缓存键"""
    import hashlib
    
    # 基于items的id和类别生成简单的缓存键
    items_sig = "|".join(f"{item.id}:{item.class_name}" for item in all_items[:50])  # 限制长度
    ocr_sig = "|".join(ocr_lines[:10]) if ocr_lines else ""
    
    combined = f"{items_sig}#{ocr_sig}"
    return hashlib.md5(combined.encode('utf-8')).hexdigest()

# 地标缓存（简单的内存缓存）
_landmark_cache = {}
_cache_ttl = {}

def detect_landmarks_cached(all_items: List[Item], ocr_lines: List[str] = None, 
                           img: np.ndarray = None, cache_ttl_s: int = 300) -> Dict[str, Landmark]:
    """带缓存的地标检测"""
    import time
    
    cache_key = get_landmark_cache_key(all_items, ocr_lines)
    now = time.time()
    
    # 检查缓存
    if cache_key in _landmark_cache and cache_key in _cache_ttl:
        if now - _cache_ttl[cache_key] < cache_ttl_s:
            return _landmark_cache[cache_key]
    
    # 重新检测
    landmarks = detect_landmarks(all_items, ocr_lines, img)
    
    # 更新缓存
    _landmark_cache[cache_key] = landmarks
    _cache_ttl[cache_key] = now
    
    # 简单的缓存清理（保留最近100个）
    if len(_landmark_cache) > 100:
        oldest_keys = sorted(_cache_ttl.items(), key=lambda x: x[1])[:20]
        for k, _ in oldest_keys:
            _landmark_cache.pop(k, None)
            _cache_ttl.pop(k, None)
    
    return landmarks