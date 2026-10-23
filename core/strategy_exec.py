# core/strategy_exec.py - 策略执行映射（系统侧，不调LLM）
from typing import Optional, List, Dict, Any

try:
    from .types import Item, StrategySpec, Landmark
    from .ops_new import *
    from .landmarks import detect_landmarks_cached
except ImportError:
    # Fallback implementations for missing imports
    class Item:
        pass
    class StrategySpec:
        pass
    class Landmark:
        pass
    def detect_landmarks_cached(*args, **kwargs):
        return {}

def _resolve_landmark_or_container(lm_map: Dict[str, Landmark], name_or_item) -> Optional[Item]:
    """解析地标或容器引用"""
    if isinstance(name_or_item, (Item, Landmark)):
        return name_or_item
    if isinstance(name_or_item, str):
        return lm_map.get(name_or_item)
    return None

def exec_strategy(spec: StrategySpec, all_items: List[Item], 
                  lm_map: Dict[str, Landmark] = None) -> Optional[Item]:
    """执行策略并返回目标Item"""
    if not spec or not all_items:
        return None
        
    if lm_map is None:
        lm_map = {}
    
    sid = spec.strategy_id
    p = spec.params or {}
    
    # 解析通用参数
    container = _resolve_landmark_or_container(lm_map, p.get("container"))
    landmark = _resolve_landmark_or_container(lm_map, p.get("landmark"))
    attr = p.get("attr")
    text = p.get("text")
    n = p.get("n") or p.get("ordinal", 1)
    r = p.get("r", 1)
    c = p.get("c", 1)
    
    try:
        # === 策略实现 ===
        
        if sid == "LIST_TOPMOST_WITH_ATTR":
            # 容器内具有属性attr的最上方项
            items = within(all_items, container) if container else all_items
            candidates = has_attr(items, attr) if attr else items
            return topmost(candidates)
        
        elif sid == "NEAREST_BELOW":
            # 地标下方最近的项
            if not landmark:
                return topmost(all_items) if all_items else None
            below_items = below(all_items, landmark)
            return nearest_to(below_items, landmark)
        
        elif sid == "NTH_IN_CONTAINER":
            # 容器内第n个项
            items = within(all_items, container) if container else all_items
            return nth(items, n)
        
        elif sid == "TEXT_MATCH_NEAREST":
            # OCR文本匹配且最接近地标的项
            if not text:
                return None
            candidates = text_match(all_items, text)
            if not candidates:
                return None
            if landmark:
                return nearest_to(candidates, landmark)
            else:
                return topmost(candidates)
        
        elif sid == "GRID_BY_ROWCOL":
            # 栅格中第r行第c列的项
            items = within(all_items, container) if container else all_items
            grid = gridize(items)
            if not grid or r <= 0 or c <= 0 or r > len(grid):
                return None
            row = grid[r-1]
            if c > len(row):
                return None
            return row[c-1]
        
        elif sid == "FORM_FIELD_BY_LABEL":
            # 根据标签找对应的表单字段
            if not text:
                return None
            # 先找标签
            label_items = text_match(all_items, text)
            if not label_items:
                return None
            label = label_items[0]  # 取第一个匹配的标签
            
            # 在标签右侧和下方找输入控件
            right_items = right_of(all_items, label)
            below_items = below(all_items, label)
            field_candidates = right_items + below_items
            
            # 过滤出输入控件类型
            input_types = {"input", "select", "checkbox", "radio", "upload", "textarea"}
            field_items = [it for it in field_candidates if it.class_name in input_types]
            
            if field_items:
                return nearest_to(field_items, label)
            return None
        
        elif sid == "TAB_SWITCH_BY_TITLE":
            # 根据标题切换Tab
            if not text:
                return None
            tabs_container = container or landmark
            if tabs_container:
                tab_items = within(all_items, tabs_container)
            else:
                tab_items = all_items
            
            # 文本匹配
            candidates = text_match(tab_items, text)
            if candidates:
                return nearest_to(candidates, tabs_container) if tabs_container else candidates[0]
            return None
        
        elif sid == "ACTION_IN_ROW":
            # 行内动作按钮
            row_attr = p.get("row_attr")
            action_role = p.get("action_role", "button")
            
            if not row_attr:
                return None
                
            items = within(all_items, container) if container else all_items
            rows = cluster_list(items)
            
            # 找到包含row_attr的行
            target_row = None
            for row in rows:
                for item in row:
                    # 检查OCR文本或属性
                    if ((item.ocr_text and row_attr in item.ocr_text) or 
                        (row_attr in item.attrs)):
                        target_row = row
                        break
                if target_row:
                    break
            
            if not target_row:
                return None
                
            # 在该行内找指定类型的按钮
            for item in target_row:
                if item.class_name == action_role or action_role in item.class_name:
                    return item
            
            # 如果没找到精确匹配，返回行中第一个button类
            buttons = [it for it in target_row if "button" in it.class_name.lower()]
            return buttons[0] if buttons else None
        
        elif sid == "FIRST_RESULT_BELOW_SEARCH":
            # 搜索框下方第一个结果
            search_landmark = landmark or lm_map.get("search_bar")
            if not search_landmark:
                # 没有搜索框地标，使用容器内第一个
                items = within(all_items, container) if container else all_items
                return topmost(items)
            
            below_items = below(all_items, search_landmark)
            if container:
                below_items = within(below_items, container)
            return topmost(below_items)
        
        elif sid == "LATEST_ITEM_BY_TIME":
            # 时间排序最新项（需要时间信息）
            items = within(all_items, container) if container else all_items
            
            # 检查meta中是否有时间戳
            time_items = [it for it in items if "ts" in it.meta or "timestamp" in it.meta]
            if time_items:
                # 按时间戳降序排序
                time_items.sort(key=lambda it: it.meta.get("ts", it.meta.get("timestamp", 0)), reverse=True)
                return time_items[0]
            
            # 如果没有时间戳，简单返回最上方的项（通常最新）
            return topmost(items)
        
        else:
            # 未知策略ID
            print(f"[strategy_exec] Unknown strategy_id: {sid}")
            return None
            
    except Exception as e:
        print(f"[strategy_exec] Error executing strategy {sid}: {e}")
        return None

def exec_strategy_with_fallback(spec: StrategySpec, all_items: List[Item], 
                                lm_map: Dict[str, Landmark] = None) -> Optional[Item]:
    """执行策略，失败时尝试fallback"""
    # 尝试主策略
    result = exec_strategy(spec, all_items, lm_map)
    if result:
        return result
    
    # 尝试fallback策略
    if spec.fallback:
        fallback_spec = StrategySpec(
            strategy_id=spec.fallback.get("strategy_id", ""),
            params=spec.fallback.get("params", {}),
            confidence=spec.fallback.get("confidence", 0.5),
            why="fallback"
        )
        result = exec_strategy(fallback_spec, all_items, lm_map)
        if result:
            print(f"[strategy_exec] Fallback strategy {fallback_spec.strategy_id} succeeded")
            return result
    
    return None