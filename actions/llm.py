import asyncio, uuid, time, hashlib
from core.registry import register_action
from core.expr import resolve
from runtime.actions.llm import llm_submit as runtime_llm_submit, llm_plan as runtime_llm_plan

@register_action("llm.submit")
def llm_submit(step, ctx, **_):
    """
    Enhanced LLM submit action with quota management
    step:
      content: "text to submit to LLM"
      user_id: <optional, default "default">
      provider: "gemini" | "openai" | "deepseek" | "nvidia" | "auto"
      quality: "high_quality" | "balanced" | "cost_optimized"

      # Legacy support
      job: "wechat_reply"
      prompt_pack: "wechat.sales.reply.v1"
      schema: "WeChatReplyV1"
      provider_hint: "openai" | "deepseek" | "mock"
      inputs: <object or @var>
      device_target: <optional, default current device>
      idempotency_key: <optional>
    """

    # 新版本支持
    if "content" in step:
        content = resolve(step["content"], ctx)
        user_id = step.get("user_id", "default")
        provider = step.get("provider", "auto")
        quality = step.get("quality", "balanced")

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            runtime_llm_submit(content, user_id, provider, quality)
        )
        return result

    # 传统版本支持（保持向后兼容）
    device_target = step.get("device_target") or ctx.vars.get("device_id") or "demo"
    job = step["job"]
    job_id = str(uuid.uuid4())
    prompt_pack = step.get("prompt_pack")
    schema = step.get("schema")
    provider_hint = step.get("provider_hint")
    inputs = resolve(step.get("inputs", {}), ctx)

    idem = step.get("idempotency_key")
    if not idem:
        idem = f"{job}:{hashlib.md5(str(inputs).encode('utf-8')).hexdigest()}"

    payload = {
        "job": job,
        "job_id": job_id,
        "device_target": device_target,
        "prompt_pack": prompt_pack,
        "schema": schema,
        "provider_hint": provider_hint,
        "inputs": inputs,
        "idempotency_key": idem,
        "ts": int(time.time())
    }
    loop = asyncio.get_event_loop()
    loop.create_task(ctx.services.mq.publish("llm-request.fifo", payload))
    return {"ok": True, "enqueued": True, "job_id": job_id, "device_target": device_target}


@register_action("llm.plan")
def llm_plan(step, ctx, **_):
    """
    LLM planning action with quota management
    step:
      goal: "what to achieve"
      page_state: <optional, current page state or @var>
      user_id: <optional, default "default">
      provider: "gemini" | "openai" | "deepseek" | "nvidia" | "auto"
      quality: "high_quality" | "balanced" | "cost_optimized"
    """
    goal = resolve(step["goal"], ctx)
    page_state = resolve(step.get("page_state", {}), ctx)
    user_id = step.get("user_id", "default")
    provider = step.get("provider", "auto")
    quality = step.get("quality", "high_quality")  # 规划任务默认高质量

    # 如果没有提供page_state，尝试从ctx获取当前状态
    if not page_state and hasattr(ctx, 'current_state'):
        page_state = ctx.current_state
    elif not page_state:
        page_state = {"screen": "unknown", "timestamp": time.time()}

    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(
        runtime_llm_plan(goal, page_state, user_id, provider, quality)
    )
    return result