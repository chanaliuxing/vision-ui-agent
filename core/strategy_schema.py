# core/strategy_schema.py - JSON白名单校验和输入清理
from typing import Dict, Any, List, Optional, Set
import json
import re

# 策略ID白名单 - 只允许已实现的策略
ALLOWED_STRATEGY_IDS = {
    "LIST_TOPMOST_WITH_ATTR",
    "NEAREST_BELOW", 
    "NTH_IN_CONTAINER",
    "TEXT_MATCH_NEAREST",
    "GRID_BY_ROWCOL",
    "FORM_FIELD_BY_LABEL",
    "TAB_SWITCH_BY_TITLE",
    "ACTION_IN_ROW",
    "FIRST_RESULT_BELOW_SEARCH",
    "LATEST_ITEM_BY_TIME"
}

# 参数白名单 - 每个策略允许的参数键
STRATEGY_PARAM_WHITELIST = {
    "LIST_TOPMOST_WITH_ATTR": {"container", "attr", "ordinal"},
    "NEAREST_BELOW": {"landmark", "container", "margin_px"},
    "NTH_IN_CONTAINER": {"container", "n", "sort_by"},
    "TEXT_MATCH_NEAREST": {"text", "landmark", "case_sensitive"},
    "GRID_BY_ROWCOL": {"container", "row", "col"},
    "FORM_FIELD_BY_LABEL": {"label_text", "field_type", "direction"},
    "TAB_SWITCH_BY_TITLE": {"title", "container"},
    "ACTION_IN_ROW": {"row_text", "action_type", "container"},
    "FIRST_RESULT_BELOW_SEARCH": {"search_landmark", "result_container"},
    "LATEST_ITEM_BY_TIME": {"container", "time_attr", "max_items"}
}

# 地标白名单
ALLOWED_LANDMARKS = {
    "search_bar", "chat_sidebar", "results_container", "tabs", "top_bar"
}

# 属性白名单
ALLOWED_ATTRS = {
    "unread", "badge", "selected", "active", "disabled", "highlighted"
}

def sanitize_string(s: str, max_len: int = 100) -> str:
    """清理字符串，移除危险字符"""
    if not isinstance(s, str):
        return ""
    
    # 移除控制字符和潜在危险字符
    s = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', s)
    s = re.sub(r'[<>"\']', '', s)
    
    # 限制长度
    return s[:max_len].strip()

def sanitize_strategy_json(raw_json: str) -> Optional[Dict[str, Any]]:
    """
    清理和验证Strategy LLM返回的JSON
    返回None表示无效输入
    """
    if not raw_json or not isinstance(raw_json, str):
        return None
    
    # 移除markdown代码块标记
    raw_json = re.sub(r'```json\s*', '', raw_json)
    raw_json = re.sub(r'```\s*$', '', raw_json)
    raw_json = raw_json.strip()
    
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    
    if not isinstance(data, dict):
        return None
    
    # 验证必需字段
    strategy_id = data.get("strategy_id")
    if not strategy_id or strategy_id not in ALLOWED_STRATEGY_IDS:
        return None
    
    params = data.get("params", {})
    if not isinstance(params, dict):
        return None
    
    # 验证参数白名单
    allowed_params = STRATEGY_PARAM_WHITELIST.get(strategy_id, set())
    sanitized_params = {}
    
    for key, value in params.items():
        if key not in allowed_params:
            continue
            
        # 清理参数值
        if isinstance(value, str):
            # 特殊验证
            if key in ["container", "landmark"] and value not in ALLOWED_LANDMARKS:
                continue
            if key == "attr" and value not in ALLOWED_ATTRS:
                continue
            sanitized_params[key] = sanitize_string(value)
        elif isinstance(value, (int, float)):
            # 数值范围检查
            if key in ["n", "ordinal", "row", "col"] and (value < 1 or value > 100):
                continue
            if key == "margin_px" and (value < 0 or value > 200):
                continue
            sanitized_params[key] = value
        elif isinstance(value, bool):
            sanitized_params[key] = value
    
    # 构造清理后的结果
    result = {
        "strategy_id": strategy_id,
        "params": sanitized_params
    }
    
    # 可选字段
    if "confidence" in data:
        conf = data["confidence"]
        if isinstance(conf, (int, float)) and 0 <= conf <= 1:
            result["confidence"] = conf
    
    if "fallback" in data:
        fallback = data["fallback"]
        if isinstance(fallback, str) and fallback in ALLOWED_STRATEGY_IDS:
            result["fallback"] = fallback
    
    if "reasoning" in data:
        reasoning = data["reasoning"]
        if isinstance(reasoning, str):
            result["reasoning"] = sanitize_string(reasoning, 500)
    
    return result

def validate_strategy_spec(spec_dict: Dict[str, Any]) -> bool:
    """验证策略规范是否完整有效"""
    if not isinstance(spec_dict, dict):
        return False
    
    strategy_id = spec_dict.get("strategy_id")
    if strategy_id not in ALLOWED_STRATEGY_IDS:
        return False
    
    params = spec_dict.get("params", {})
    if not isinstance(params, dict):
        return False
    
    # 检查必需参数（根据策略类型）
    required_params = {
        "LIST_TOPMOST_WITH_ATTR": {"container", "attr"},
        "NEAREST_BELOW": {"landmark"},
        "NTH_IN_CONTAINER": {"container", "n"},
        "TEXT_MATCH_NEAREST": {"text"},
        "GRID_BY_ROWCOL": {"container", "row", "col"},
        "FORM_FIELD_BY_LABEL": {"label_text"},
        "TAB_SWITCH_BY_TITLE": {"title"},
        "ACTION_IN_ROW": {"row_text"},
        "FIRST_RESULT_BELOW_SEARCH": {"search_landmark"},
        "LATEST_ITEM_BY_TIME": {"container"}
    }
    
    required = required_params.get(strategy_id, set())
    for param in required:
        if param not in params:
            return False
    
    return True

def extract_json_from_llm_response(response: str) -> Optional[str]:
    """从LLM响应中提取JSON部分"""
    if not response:
        return None
    
    # 尝试提取JSON代码块
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
    if json_match:
        return json_match.group(1)
    
    # 尝试提取花括号内容
    brace_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
    if brace_match:
        return brace_match.group(0)
    
    return None

def log_schema_violation(raw_input: str, violation_type: str, details: str = ""):
    """记录schema违规，用于调试和监控"""
    print(f"[schema_violation] type={violation_type} details={details} input_preview={raw_input[:100]}...")