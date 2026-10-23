import asyncio
from core.registry import register_action

@register_action("mq.publish")
def mq_publish(step, ctx, **_):
    topic = step["topic"]; payload = step.get("payload", {})
    loop = asyncio.get_event_loop()
    loop.create_task(ctx.services.mq.publish(topic, payload))
    return {"ok": True, "enqueued": True, "topic": topic}

@register_action("mq.consume")
def mq_consume(step, ctx, **_):
    topic = step["topic"]
    save_var = step.get("save", "msg")

    # 简化版本：如果有消息直接返回，否则返回None
    if ctx.services.mq.qsize(topic) == 0:
        ctx.vars[save_var] = None
        return None

    # 有消息时，启动协程获取
    loop = asyncio.get_event_loop()

    # 检查是否已有待处理的消息在变量中
    if save_var in ctx.vars and ctx.vars[save_var] not in [None, "pending"]:
        # 如果已经有消息，清空变量并返回消息
        msg = ctx.vars[save_var]
        ctx.vars[save_var] = None
        return msg

    # 标记为pending并启动获取任务
    async def _get_and_store():
        try:
            msg = await ctx.services.mq.consume(topic, timeout_ms=10)
            if msg is not None:
                ctx.vars[save_var] = msg
        except:
            ctx.vars[save_var] = None

    # 立即安排获取任务
    loop.create_task(_get_and_store())
    ctx.vars[save_var] = "pending"
    return "pending"