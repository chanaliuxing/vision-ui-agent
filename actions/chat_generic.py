# actions/chat_generic.py
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from core.registry import register_action
from client.adapters.registry import get_adapter
from client.ocr.service import OCRService
import numpy as np
import time

_OCR = None

def _ocr():
    global _OCR
    if _OCR is None:
        _OCR = OCRService()
    return _OCR

@register_action("chat.find_unread")
def chat_find_unread(step, ctx, **_):
    """查找未读消息标记"""
    app = step.get("app") or ctx.vars.get("app", "wechat")
    ad = get_adapter(app)
    if not ad or not ad.detect():
        return {"has_unread": False}
    items = ad.find_unread_badges()
    return {"has_unread": len(items) > 0, "items": items}

@register_action("chat.open_latest_unread")
def chat_open_latest_unread(step, ctx, **_):
    """打开最新的未读会话"""
    app = step.get("app") or ctx.vars.get("app", "wechat")
    ad = get_adapter(app)
    if not ad:
        return {"ok": False}
    ok = ad.open_conversation()
    return {"ok": ok}

@register_action("chat.capture_visible")
def chat_capture_visible(step, ctx, **_):
    """捕获可见消息并提交OCR"""
    app = step.get("app") or ctx.vars.get("app", "wechat")
    ad = get_adapter(app)
    if not ad:
        return {"ocr_job": None}
    img = ad.capture_visible_messages()
    jid = _ocr().submit(img)
    return {"ocr_job": jid}

@register_action("chat.ocr_fetch")
def chat_ocr_fetch(step, ctx, **_):
    """获取OCR结果"""
    jid = step.get("job") or ctx.vars.get("ocr_job")
    if not jid:
        return {"done": False, "text": ""}

    txt = _ocr().fetch(jid)
    return {"done": txt is not None, "text": txt or ""}

@register_action("chat.send_text")
def chat_send_text(step, ctx, **_):
    """发送文本到当前会话"""
    app = step.get("app") or ctx.vars.get("app", "wechat")
    text = step.get("text", "")
    ad = get_adapter(app)
    if not ad or not text:
        return {"ok": False}
    ok = ad.send_text(text)
    return {"ok": ok}

@register_action("chat.focus_contact")
def chat_focus_contact(step, ctx, **_):
    """聚焦指定联系人"""
    app = step.get("app") or ctx.vars.get("app", "wechat")
    name = step.get("name", "")
    ad = get_adapter(app)
    if not ad or not name:
        return {"ok": False}
    ok = ad.focus_contact_by_name(name)
    return {"ok": ok}