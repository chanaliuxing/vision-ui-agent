from __future__ import annotations
import json
from typing import Any, Dict, List, Set
from pathlib import Path

try:
    import jsonschema  # type: ignore
    from jsonschema import Draft7Validator  # type: ignore
except Exception:
    jsonschema = None
    Draft7Validator = None


def _collect_vars(doc: Dict[str, Any]) -> Set[str]:
    out: Set[str] = set((doc.get("vars") or {}).keys())
    return out


def _find_var_refs(obj: Any) -> Set[str]:
    refs: Set[str] = set()
    if isinstance(obj, str) and obj.startswith("@") and len(obj) > 1:
        refs.add(obj[1:])
    elif isinstance(obj, dict):
        for v in obj.values():
            refs |= _find_var_refs(v)
    elif isinstance(obj, list):
        for v in obj:
            refs |= _find_var_refs(v)
    return refs


def validate_schema(doc: Dict[str, Any], schema_path: str = "schema/workflow.schema.json") -> List[str]:
    if not jsonschema:
        return ["jsonschema not available; install jsonschema to enable schema validation"]
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    validator = Draft7Validator(schema)
    errors = list(validator.iter_errors(doc))
    return [e.message for e in errors]


def validate_semantic(doc: Dict[str, Any]) -> List[str]:
    errs: List[str] = []
    states = doc.get("states") or {}
    start = doc.get("start")
    if not isinstance(states, dict) or not states:
        errs.append("states must be a non-empty object")
        return errs
    if not start or start not in states:
        errs.append("start must be a key in states")

    # actions non-empty
    for sid, st in states.items():
        acts = (st or {}).get("actions")
        if not isinstance(acts, list) or len(acts) == 0:
            errs.append(f"state '{sid}' must have non-empty actions")

    # reachability (simple BFS)
    g: Dict[str, List[str]] = {k: [] for k in states.keys()}
    for sid, st in states.items():
        nx = []
        ons = st.get("on_success")
        if isinstance(ons, str):
            nx.append(ons)
        for tr in st.get("transitions") or []:
            tgt = tr.get("go_to") or tr.get("else_go_to")
            if isinstance(tgt, str):
                nx.append(tgt)
        g[sid] = [x for x in nx if x in states]
    if start in g:
        seen: Set[str] = set()
        stack: List[str] = [start]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            stack.extend(g.get(u, []))
        dangling = [k for k in states.keys() if k not in seen]
        if dangling:
            errs.append(f"unreachable states: {', '.join(dangling)}")

    # variable existence (basic): any @var must be defined in vars
    declared = _collect_vars(doc)
    used = _find_var_refs(doc)
    missing = sorted([v for v in used if v not in declared])
    if missing:
        errs.append("undefined vars: " + ", ".join(missing))

    return errs


def validate_all(doc: Dict[str, Any]) -> Dict[str, Any]:
    schema_errs = validate_schema(doc)
    sem_errs = validate_semantic(doc) if not schema_errs else []
    ok = (len(schema_errs) == 0 and len(sem_errs) == 0)
    return {"ok": ok, "schema_errors": schema_errs, "semantic_errors": sem_errs}

