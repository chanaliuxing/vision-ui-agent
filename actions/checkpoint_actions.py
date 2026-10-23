# actions/checkpoint_actions.py
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from core.registry import register_action

@register_action("checkpoint.save")
def cp_save(step, ctx, **_):
    """显式在工作流关键点保存快照"""
    rm = getattr(ctx.services, 'run_manager', None)
    if not rm:
        return {"ok": False, "error": "run_manager not available"}

    # 从上下文获取基本信息
    run_id = getattr(ctx, 'run_id', 'unknown')
    workflow_name = ctx.vars.get("_workflow_name", "")
    engine_version = ctx.vars.get("_engine_version", "0.4.0")
    state = ctx.vars.get("_state", "")
    step_idx = ctx.vars.get("_step_idx", 0)
    resource_locks = [ctx.vars.get("_lock")] if ctx.vars.get("_lock") else []

    try:
        rm.checkpointer.save(
            run_id=run_id,
            workflow_name=workflow_name,
            engine_version=engine_version,
            state=state,
            vars=ctx.vars,
            step_idx=step_idx,
            resource_locks=resource_locks,
            inflight={}
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}