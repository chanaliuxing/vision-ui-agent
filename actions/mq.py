import asyncio, json
from core.registry import register_action

@register_action("mq.publish")
def mq_publish(step, ctx, **_):
    topic = step["topic"]
    payload = step.get("payload", {})
    asyncio.get_event_loop().create_task(ctx.services.mq.publish(topic, payload))
    return {"ok": True, "topic": topic}

@register_action("mq.consume")
def mq_consume(step, ctx, **_):
    topic = step["topic"]
    save = step.get("save", "msg")
    # 如果队列近似长度为 0，直接返回 None（非阻塞）
    if ctx.services.mq.qsize(topic) == 0:
        ctx.vars[save] = None
        return None

    async def _get():
        msg = await ctx.services.mq.consume(topic, timeout_ms=1)
        if msg is not None:
            ctx.vars[save] = msg

    asyncio.get_event_loop().create_task(_get())
    ctx.vars[save] = "pending"
    return "pending"

@register_action("mq.ack")
def mq_ack(step, ctx, **_):
    topic = step["topic"]
    receipt = step.get("receipt") or ctx.vars.get("_sqs_receipt") or \
              (ctx.vars.get(step.get("from_var","msg")) or {}).get("_sqs_receipt")
    if not receipt:
        return {"ok": False, "reason": "no receipt"}
    asyncio.get_event_loop().create_task(ctx.services.mq.ack(topic, receipt))
    return {"ok": True}

@register_action("mq.requeue_now")
def mq_requeue_now(step, ctx, **_):
    """立即让SQS消息重新可见（VisibilityTimeout=0）"""
    topic = step["topic"]
    receipt = step.get("receipt") or ctx.vars.get("_sqs_receipt")
    if not receipt:
        return {"ok": False, "reason": "no receipt"}

    async def _requeue():
        if hasattr(ctx.services.mq, 'requeue_now'):
            await ctx.services.mq.requeue_now(topic, receipt)

    asyncio.get_event_loop().create_task(_requeue())
    return {"ok": True}