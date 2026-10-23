import json
import time
import os
from typing import Dict, Any


def _ts_ms() -> int:
    return int(time.time() * 1000)


def log_event(event: str, kv: Dict[str, Any]) -> None:
    try:
        print(json.dumps({"ts": _ts_ms(), "event": event, **kv}, ensure_ascii=False))
    except Exception:
        pass


_STEPS_LOG = os.environ.get("STEPS_LOG_PATH", os.path.join("out", "steps_log.jsonl"))


def append_steps_log(entry: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STEPS_LOG), exist_ok=True)
        with open(_STEPS_LOG, "a", encoding="utf-8") as f:
            entry2 = {"ts": _ts_ms(), **entry}
            f.write(json.dumps(entry2, ensure_ascii=False) + "\n")
    except Exception:
        pass

