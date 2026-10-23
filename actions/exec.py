from core.registry import register_action
from core.expr import resolve

@register_action("click_coordinates")
def click_coordinates(step, ctx, **_):
    bbox = resolve(step["bbox"], ctx)  # {x,y,w,h}
    x = int(bbox["x"] + bbox["w"]/2)
    y = int(bbox["y"] + bbox["h"]/2)
    ctx.services.os.move_to(x, y)
    ctx.services.os.click()
    return {"ok": True, "x": x, "y": y}