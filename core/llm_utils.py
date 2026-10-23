#!/usr/bin/env python3
"""
LLM utilities: robust parsing of decision outputs from mixed providers.
"""
from typing import Dict, Any, Optional
import json
import re


JSON_BLOCK = re.compile(r"\{[\s\S]*\}", re.M)
PICK_PATTS = [
    re.compile(r"(?i)\b(candidate|item|id|pick|choice|click[_\s-]?id)\s*[:=]?\s*(\d+)"),
    re.compile(r"(?i)\bselect(?:ed)?\s+(?:candidate|option)\s*(\d+)"),
    re.compile(r"(?i)\b#?(\d+)\b\s*(?:is|->|:)\s*(?:best|chosen|match)"),
]


def _extract_int(val: Any) -> Optional[int]:
    if isinstance(val, int):
        return val
    if isinstance(val, float) and float(val).is_integer():
        return int(val)
    if isinstance(val, str):
        m = re.search(r"\d+", val)
        if m:
            try:
                return int(m.group(0))
            except Exception:
                return None
    return None


def _extract_float(val: Any) -> Optional[float]:
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", val.strip())
        if m:
            try:
                return float(m.group(0))
            except Exception:
                return None
    return None


def _extract_json(s: str) -> Optional[Dict[str, Any]]:
    # fenced ```json
    m = re.search(r"```json\s*([\s\S]*?)```", s, re.M)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # first object
    m = JSON_BLOCK.search(s)
    if m:
        txt = m.group(0)
        try:
            return json.loads(txt)
        except Exception:
            pass
    # last try: whole string
    try:
        return json.loads(s)
    except Exception:
        return None


def _get_first(d: Dict[str, Any], keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
    return default


def _dig_decision_dict(js: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for k in ("decision", "result", "output", "action", "response"):
        v = js.get(k)
        if isinstance(v, dict):
            return v
    return None


def safe_parse_decision(text: str):
    """
    返回统一结构：{"candidate_id": int|None, "reason": str|None, "confidence": float|None}
    兼容：
      - 顶层: candidate_id/id/pick/choice/click_id/index
      - 嵌套: decision.click_id / decision.candidate_id / decision.id / decision.pick / decision.choice / decision.index
      - reason / confidence 同顶层与嵌套键名
      - 纯文本启发式
    """
    out = {"candidate_id": None, "reason": None, "confidence": None}
    if not text:
        return out

    # 1) JSON 优先
    js = _extract_json(text)
    if isinstance(js, dict):
        dec = _dig_decision_dict(js) or {}

        id_keys = ("click_id", "candidate_id", "id", "pick", "choice", "index")
        reason_keys = ("reason", "why", "explanation", "note", "because")
        conf_keys = ("confidence", "score", "prob", "p", "certainty")

        cid = _extract_int(_get_first(dec, id_keys))
        if cid is None:
            cid = _extract_int(_get_first(js, id_keys))

        reason = _get_first(dec, reason_keys)
        if not isinstance(reason, str):
            reason = _get_first(js, reason_keys)
        if isinstance(reason, (int, float)):
            reason = str(reason)

        conf = _extract_float(_get_first(dec, conf_keys))
        if conf is None:
            conf = _extract_float(_get_first(js, conf_keys))

        # OpenAI tool_calls 兼容
        if cid is None and "tool_calls" in js:
            try:
                tc = js["tool_calls"][0]["function"]["arguments"]
                if isinstance(tc, str):
                    tc = json.loads(tc)
                if isinstance(tc, dict):
                    cid = _extract_int(_get_first(tc, id_keys))
                    if not reason:
                        reason = _get_first(tc, reason_keys)
                    if conf is None:
                        conf = _extract_float(_get_first(tc, conf_keys))
            except Exception:
                pass

        if cid is not None:
            out["candidate_id"] = cid
            out["reason"] = (reason or (json.dumps(js, ensure_ascii=False)[:300]))
            out["confidence"] = conf
            return out

        # 没有 id 也保留已提取的 reason/conf
        if reason and not out["reason"]:
            out["reason"] = reason
        if conf is not None and out["confidence"] is None:
            out["confidence"] = conf

    # 2) 纯文本启发式
    for p in PICK_PATTS:
        m = p.search(text)
        if m:
            try:
                out["candidate_id"] = int(m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1))
                break
            except Exception:
                pass

    if not out["reason"]:
        out["reason"] = text.strip()[:300]
    return out
