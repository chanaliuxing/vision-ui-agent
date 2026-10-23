from core.registry import register_action

@register_action("demo.fake_red_dot")
def fake_red_dot(step, ctx, **_):
    # 简单：每次调用把计数 +1，偶数次返回 has_red=True
    tick = ctx.vars.get("tick", 0) + 1
    ctx.vars["tick"] = tick
    return {"has_red": (tick % 2 == 0)}