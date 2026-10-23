import json
from typing import Any, Dict, List, Optional

from .llm_client import call_llm, extract_text_generic
from .gemini_client import parse_first_json


def _trim_text(s: Optional[str], n: int = 160) -> str:
    s = (s or "").strip()
    if len(s) > n:
        return s[: n - 3] + "..."
    return s


def _prepare_items(dom: Dict[str, Any], limit: int = 200) -> List[Dict[str, Any]]:
    """Prepare a compact item list for LLM:
    - Drop entries without a stable id (id is required for CSS by #id)
    - Keep only semantic fields: id, role, text, href (if meaningful)
    - Remove geometry fields (bbox, center, region, visible, z) to reduce token cost
    """
    out: List[Dict[str, Any]] = []
    src = (dom or {}).get("items", []) or []
    for it in src:
        iid = it.get("id")
        if not iid:
            continue

        # Build minimal semantic item
        item = {
            "id": str(iid),
            "role": it.get("role"),
            "text": _trim_text(it.get("text")),
        }

        # Only include href if it's meaningful (not empty/null)
        href = it.get("href")
        if href and href.strip():
            item["href"] = href

        out.append(item)
        if len(out) >= int(limit):
            break
    return out


def pick_selector_from_dom(
    goal: str,
    dom: Dict[str, Any],
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Use LLM to pick a CSS selector from extension-provided DOM snapshot.

    Returns: { sel: str|None, confidence: float|None, why: str|None }
    """
    provider = provider or "gemini"
    model = model or "gemini-1.5-flash"
    items = _prepare_items(dom)
    prompt = (
        "You are a DOM action planner. Given a goal and a compact DOM list (id/role/text only),\n"
        "choose ONE precise CSS selector to click that best progresses the goal.\n"
        "Rules:\n"
        "- Input is minimal: items have only {id, role, text}; no geometry is provided.\n"
        "- Prefer interactive controls (role in input/button/a/textarea/combobox).\n"
        "- If goal is to focus a search input, pick an input-like element.\n"
        "- Use id-based CSS when possible: return '#<id>' (e.g., '#search-input').\n"
        "- If nothing reasonable, return null.\n"
        "Output STRICT JSON only:\n"
        "{\"sel\": string|null, \"confidence\": number|null, \"why\": string|null}"
    )
    user = {
        "goal": (goal or "").strip(),
        "items": items,
    }
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]
    resp = call_llm(provider=provider, model=model, messages=messages, image_path=None)
    text = extract_text_generic(resp)
    out = parse_first_json(text or "") or {}
    if not isinstance(out, dict):
        out = {}

    sel = out.get("sel")
    conf = out.get("confidence")
    why = out.get("why")

    # Fallback: if LLM didn't return a selector, pick a simple heuristic (first input-like element)
    if not sel:
        for it in items:
            role = (it.get("role") or "").lower()
            txt = (it.get("text") or "").lower()
            if role in ("input", "textarea", "combobox") or "search" in txt:
                candidate_id = it.get("id")
                if candidate_id:
                    sel = f"#{candidate_id}"
                    conf = conf or 0.15
                    why = why or "fallback: first input-like element"
                    break
        # If still nothing, pick the first item with an id
        if not sel and items:
            candidate_id = items[0].get("id")
            if candidate_id:
                sel = f"#{candidate_id}"
                conf = conf or 0.1
                why = why or "fallback: first item id"

    return {
        "sel": sel,
        "confidence": conf,
        "why": why,
    }
