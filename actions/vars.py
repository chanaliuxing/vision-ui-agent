from core.registry import register_action
from core.expr import resolve

@register_action("set_variable")
def set_variable(step, ctx, **_):
    ctx.vars[step["name"]] = resolve(step.get("value"), ctx)
    return {"ok": True, "value": ctx.vars[step["name"]]}

@register_action("increment_variable")
def increment_variable(step, ctx, **_):
    ctx.vars[step["name"]] = ctx.vars.get(step["name"], 0) + 1
    return {"ok": True, "value": ctx.vars[step["name"]]}

@register_action("get_list_length")
def get_list_length(step, ctx, **_):
    data = resolve(step["from"], ctx) or []
    return len(data)

@register_action("get_list_item")
def get_list_item(step, ctx, **_):
    data = resolve(step["from"], ctx) or []
    idx = resolve(step["index"], ctx)
    return data[idx]

@register_action("query_data")
def query_data(step, ctx, **_):
    obj = resolve(step["from"], ctx)
    path = step.get("query","")
    cur = obj
    for part in path.split("."):
        if part:
            cur = cur[part] if isinstance(cur, dict) else getattr(cur, part)
    return cur