import json, os
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / "config" / "feature_flags.default.json"

def load_flags(override_path: str | None = None) -> dict:
    with open(DEFAULT, "r", encoding="utf-8") as f:
        flags = json.load(f)
    if override_path and os.path.exists(override_path):
        with open(override_path, "r", encoding="utf-8") as f:
            user = json.load(f)
        flags.update(user)
    # 支持环境变量覆盖（FLAG_async_engine=true）
    for k in list(flags.keys()):
        env = os.getenv(f"FLAG_{k}")
        if env is not None:
            flags[k] = env.lower() in ("1","true","yes","on")
    return flags