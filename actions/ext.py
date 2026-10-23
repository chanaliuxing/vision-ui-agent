from core.registry import register_action

@register_action("ext.open_url")
def ext_open_url(step, ctx, **_):
    return ctx.services.dom.open(step["url"])

@register_action("ext.exists")
def ext_exists(step, ctx, **_):
    sel = step["selector"]
    return {"exists": ctx.services.dom.exists(sel)}

@register_action("ext.extract")
def ext_extract(step, ctx, **_):
    return ctx.services.dom.extract(step.get("query", {}))

@register_action("ext.go_back")
def ext_go_back(step, ctx, **_):
    return ctx.services.dom.go_back()