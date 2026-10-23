from core.registry import register_action
import time

@register_action("wait_until")
def wait_until(step, ctx, **_):
    chk = step["check"]; timeout = step.get("timeout_ms", 8000)/1000; poll = step.get("poll_ms", 300)/1000
    t0 = time.time()
    while time.time()-t0 < timeout:
        if chk["type"] == "dom" and ctx.services.dom.exists(chk["selector"]):
            return {"ok": True}
        time.sleep(poll)
    raise TimeoutError("wait_until timeout")

@register_action("scroll_until")
def scroll_until(step, ctx, **_):
    anchor = step["anchor"]; max_sc = step.get("max_scrolls", 30); step_px = step.get("step_px", 800)
    for _ in range(max_sc):
        if anchor["type"]=="dom" and ctx.services.dom.exists(anchor["selector"]):
            return {"ok": True}
        ctx.services.os.scroll(step_px)
    raise TimeoutError("scroll_until anchor not reached")