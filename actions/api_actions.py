# actions/api_actions.py
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from core.registry import register_action

@register_action("api.upsert_chats")
def api_upsert_chats(step, ctx, **_):
    """上报聊天记录到云端API"""
    rows = step.get("rows", [])
    if hasattr(ctx.services, 'api') and ctx.services.api:
        ctx.services.api.post_async("/api/chats/upsert", {"rows": rows})
        return {"ok": True, "n": len(rows)}
    return {"ok": False, "error": "API client not available"}

@register_action("api.ingest_event")
def api_ingest_event(step, ctx, **_):
    """上报事件到云端API"""
    evt = step.get("event", "")
    payload = step.get("payload", {})
    if hasattr(ctx.services, 'api') and ctx.services.api:
        ctx.services.api.post_async("/api/events/ingest", {"event": evt, "payload": payload})
        return {"ok": True}
    return {"ok": False, "error": "API client not available"}

@register_action("api.upsert_contacts")
def api_upsert_contacts(step, ctx, **_):
    """上报联系人信息到云端API"""
    contacts = step.get("contacts", [])
    if hasattr(ctx.services, 'api') and ctx.services.api:
        ctx.services.api.post_async("/api/contacts/upsert", {"contacts": contacts})
        return {"ok": True, "n": len(contacts)}
    return {"ok": False, "error": "API client not available"}