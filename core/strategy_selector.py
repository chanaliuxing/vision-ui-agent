from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Tuple

from .llm_client import call_llm, extract_text_generic
from .gemini_client import parse_first_json

# Import M2 components
try:
    from .strategy_schema import sanitize_strategy_json, validate_strategy_spec, extract_json_from_llm_response
    from .memory_strategy import get_memory_store, StrategyMemory
    from .strategy_adapter import create_strategy_context, infer_page_kind
    from .strategy_exec import exec_strategy_with_fallback
    from .types import StrategySpec, Item
except ImportError as e:
    print(f"[strategy_selector] M2 imports not available: {e}")


STRATEGY_SYSTEM = (
    "You are a UI strategy selector. Choose a generic selection STRATEGY for the current page.\n"
    "- DO NOT return pixel coordinates.\n"
    "- Only return a JSON with fields: strategy_id, params{...}, fallback?, confidence, why.\n"
    "- strategy_id must be one of: LIST_TOPMOST_WITH_ATTR, NEAREST_BELOW, NTH_IN_CONTAINER, TEXT_MATCH_NEAREST, "
    "GRID_BY_ROWCOL, FORM_FIELD_BY_LABEL, TAB_SWITCH_BY_TITLE, ACTION_IN_ROW, FIRST_RESULT_BELOW_SEARCH, LATEST_ITEM_BY_TIME.\n"
    "- params may include: container, landmark, attr, text, n, r, c, row_attr, action_role, ordinal.\n"
    "- Prefer invariant strategies (relative position, attributes, ordinals).\n"
    "- If ambiguous, include a conservative fallback.\n"
    "Return JSON only. No extra text."
)


def _build_messages(page_summary: Dict[str, Any]) -> list:
    return [{
        "role": "user",
        "parts": [
            {"text": STRATEGY_SYSTEM},
            {"text": json.dumps(page_summary, ensure_ascii=False)},
        ],
    }]


from dataclasses import dataclass

@dataclass
class TriggerCondition:
    """策略触发条件"""
    min_picker_failures: int = 2  # Picker连续失败次数
    min_need_input_count: int = 2  # need_input事件次数  
    min_deny_hits: int = 1  # deny词汇命中次数
    memory_health_threshold: float = 0.75  # 记忆健康度阈值

class StrategySelector:
    """Enhanced LLM-backed strategy selector with M2 trigger logic and memory integration.

    Combines existing cache functionality with new M2 features:
    - Strict triggering conditions
    - Memory-based strategy recall
    - EMA health tracking
    """

    def __init__(self, logs_dir: str) -> None:
        self.logs_dir = logs_dir
        self.cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        
        # M2 enhancements
        self.max_llm_calls = int(os.getenv("STRATEGY_LLM_MAX_CALLS_PER_RUN", "3"))
        self.cache_ttl = int(os.getenv("STRATEGY_CACHE_TTL_S", "3600"))
        self.health_threshold = float(os.getenv("STRATEGY_HEALTH_TH", "0.75"))
        
        # Session state
        self.llm_calls_made = 0
        self.last_strategy_time = 0
        
        # Trigger conditions
        self.trigger = TriggerCondition()
        
        # Memory store (if available)
        try:
            self.memory_store = get_memory_store()
        except:
            self.memory_store = None

    def _cache_key(self, sig_key: str, goal: str) -> Tuple[str, str]:
        return (sig_key, goal)

    def get_cached(self, sig_key: str, goal: str) -> Optional[Dict[str, Any]]:
        return self.cache.get(self._cache_key(sig_key, goal))

    def put_cached(self, sig_key: str, goal: str, strat: Dict[str, Any]) -> None:
        self.cache[self._cache_key(sig_key, goal)] = strat
    
    def reset_session(self):
        """重置会话状态"""
        self.llm_calls_made = 0
        self.last_strategy_time = 0
    
    def should_trigger_strategy_llm(self, workflow_state: Dict[str, Any]) -> Tuple[bool, str]:
        """
        M2 触发逻辑：判断是否应该触发Strategy LLM
        返回 (should_trigger, reason)
        """
        # 检查LLM调用次数限制
        if self.llm_calls_made >= self.max_llm_calls:
            return False, f"llm_calls_exceeded_{self.max_llm_calls}"
        
        # 检查触发条件
        picker_failures = workflow_state.get("picker_consecutive_failures", 0)
        need_input_count = workflow_state.get("need_input_events", 0)
        deny_hits = workflow_state.get("deny_hits", 0)
        
        # 条件1: Picker连续失败
        if picker_failures >= self.trigger.min_picker_failures:
            return True, f"picker_failures_{picker_failures}"
        
        # 条件2: 需要人工输入事件
        if need_input_count >= self.trigger.min_need_input_count:
            return True, f"need_input_{need_input_count}"
        
        # 条件3: deny词汇命中（危险操作）
        if deny_hits >= self.trigger.min_deny_hits:
            return True, f"deny_hits_{deny_hits}"
        
        # 条件4: 当前页面有健康的策略记忆
        if self.memory_store:
            page_kind = workflow_state.get("page_kind", "")
            if page_kind:
                healthy_strategies = self.memory_store.get_healthy_strategies(page_kind)
                if healthy_strategies:
                    return True, f"healthy_memory_{len(healthy_strategies)}"
        
        return False, "no_trigger_condition"
    
    def select_from_memory(self, page_kind: str) -> Optional[Dict[str, Any]]:
        """从记忆中选择健康的策略"""
        if not self.memory_store:
            return None
            
        healthy_strategies = self.memory_store.get_healthy_strategies(page_kind)
        
        if not healthy_strategies:
            return None
        
        # 选择健康度最高的策略
        strategy_id, params, health = healthy_strategies[0]
        
        strategy = {
            "strategy_id": strategy_id,
            "params": params,
            "confidence": health,
            "why": f"Memory recall, health={health:.3f}",
            "source": "memory"
        }
        
        print(f"[strategy_selector] Memory recall: {strategy_id} health={health:.3f}")
        return strategy
    
    def record_strategy_outcome(self, strategy: Dict[str, Any], success: bool, 
                               page_kind: str = ""):
        """记录策略执行的最终结果"""
        if not self.memory_store:
            return
            
        strategy_id = strategy.get("strategy_id")
        params = strategy.get("params", {})
        
        if strategy_id and params:
            self.memory_store.record_outcome(
                strategy_id,
                params,
                success=success,
                page_context={
                    "page_kind": page_kind,
                    "last_params": params,
                    "confidence": strategy.get("confidence", 0.8)
                },
                page_kind=page_kind
            )

    def decide(self, step_n: int, sig_key: str, goal: str, page_summary: Dict[str, Any], 
               workflow_state: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        Enhanced decision method with M2 trigger logic and memory integration
        """
        # M2 trigger check
        if workflow_state:
            should_trigger, trigger_reason = self.should_trigger_strategy_llm(workflow_state)
            if not should_trigger:
                print(f"[strategy_selector] No trigger: {trigger_reason}")
                return None
            print(f"[strategy_selector] Triggered: {trigger_reason}")
            
            # Try memory first if available
            page_kind = workflow_state.get("page_kind", "")
            if page_kind and self.memory_store:
                memory_strategy = self.select_from_memory(page_kind)
                if memory_strategy:
                    return memory_strategy
        
        # Increment LLM call counter
        self.llm_calls_made += 1
        
        provider = os.getenv("STRATEGY_LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or "gemini"
        model = os.getenv("STRATEGY_LLM_MODEL") or os.getenv("LLM_MODEL") or "gemini-1.5-flash"
        msgs = _build_messages(page_summary)

        # log request
        try:
            safe_prov = provider.replace('/', '-'); safe_model = model.replace('/', '-')
            req_path = os.path.join(self.logs_dir, f"{safe_prov}_{safe_model}_strategy_req_step_{step_n}.json")
            with open(req_path, "w", encoding="utf-8") as f:
                json.dump({"provider": provider, "model": model, "messages": msgs}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        try:
            from . import timeline as _t
            _t.event("llm/strategy_req", f"step={step_n} model={provider}/{model}")
        except Exception:
            pass

        try:
            resp = call_llm(provider=provider, model=model, messages=msgs)
            text = extract_text_generic(resp)
            try:
                safe_prov = provider.replace('/', '-'); safe_model = model.replace('/', '-')
                resp_path = os.path.join(self.logs_dir, f"{safe_prov}_{safe_model}_strategy_resp_step_{step_n}.json")
                with open(resp_path, "w", encoding="utf-8") as f:
                    json.dump({"raw": resp, "extracted_text": text}, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            strat = parse_first_json(text) or {}
            if isinstance(strat, dict) and strat.get("strategy_id"):
                try:
                    self.put_cached(sig_key, goal, strat)
                except Exception:
                    pass
                try:
                    from . import timeline as _t
                    _t.event("llm/strategy_resp", f"step={step_n} id={strat.get('strategy_id')} conf={strat.get('confidence')}")
                except Exception:
                    pass
                return strat
        except Exception as e:
            try:
                from . import timeline as _t
                _t.event("llm/strategy_err", f"step={step_n} {str(e)[:80]}")
            except Exception:
                pass
        return None

