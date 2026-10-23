from core.registry import register_action
from core.expr import eval_expr

@register_action("branch")
def branch(step, ctx, **_):
    cond = step["if"]
    v = eval_expr(cond, ctx)
    # 返回一个提示：runner 不强制跳转，这里仅给调试信息
    return {"ok": True, "cond": cond, "value": v, "then": step.get("then"), "else": step.get("else")}