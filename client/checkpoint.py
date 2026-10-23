# client/checkpoint.py
import json, time
from pathlib import Path
from typing import Dict, Any

def _sanitize_vars(vars: Dict[str, Any]) -> Dict[str, Any]:
    """清理变量，只保留可序列化的内容"""
    def ok(v):
        return isinstance(v, (str, int, float, bool, list, dict, type(None)))
    out = {}
    for k, v in vars.items():
        if ok(v):
            out[k] = v
        else:
            out[k] = str(v)  # 不可序列化的转字符串（日志用途）
    return out

class Checkpointer:
    def __init__(self, artifacts_dir="artifacts", api=None, logger=None):
        self.artifacts_dir = Path(artifacts_dir)
        self.api = api  # APIClient
        self.logger = logger

    def save(self, run_id: str, workflow_name: str, engine_version: str, state: str,
             vars: Dict[str, Any], step_idx: int, resource_locks: list[str], inflight: Dict[str, Any]):
        """保存快照到本地和云端"""
        snap = {
            "run_id": run_id,
            "workflow_name": workflow_name,
            "engine_version": engine_version,
            "state": state,
            "vars": _sanitize_vars(vars),
            "step_idx": step_idx,
            "resource_locks": resource_locks,
            "inflight": inflight,
            "ts": int(time.time())
        }

        # 本地保存
        d = self.artifacts_dir / run_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "checkpoint.json").write_text(
            json.dumps(snap, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        # 云端上报（异步）
        if self.api:
            self.api.post_async("/api/runs/checkpoint", snap)

        if self.logger:
            self.logger.info(f"checkpoint saved state={state} step={step_idx}")

        return snap

    def load_local(self, run_id: str) -> Dict[str, Any] | None:
        """从本地加载快照"""
        p = self.artifacts_dir / run_id / "checkpoint.json"
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None