import os
import time
from typing import Optional

_RUN_ID: Optional[str] = None
_OUT_DIR: str = "out"
_PER_RUN_PATH: Optional[str] = None
_LATEST_PATH: Optional[str] = None


def init(out_dir: str = "out", run_id: Optional[str] = None) -> None:
    global _RUN_ID, _OUT_DIR, _PER_RUN_PATH, _LATEST_PATH
    _OUT_DIR = out_dir
    if run_id is None:
        run_id = os.getenv("TIMELINE_RUN_ID") or time.strftime("%Y%m%d_%H%M%S")
    _RUN_ID = run_id
    timelines_dir = os.path.join(out_dir, "timelines")
    os.makedirs(timelines_dir, exist_ok=True)
    _PER_RUN_PATH = os.path.join(timelines_dir, f"timeline_{run_id}.log")
    _LATEST_PATH = os.path.join(out_dir, "timeline.log")
    # Start files with a header
    hdr = (
        "# Timeline (streaming)\n"
        f"run_id: {_RUN_ID}\n"
        f"started_at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    try:
        with open(_PER_RUN_PATH, "w", encoding="utf-8") as f:
            f.write(hdr)
        with open(_LATEST_PATH, "w", encoding="utf-8") as f:
            f.write(hdr)
    except Exception:
        pass


def _ts_line(src: str, msg: str, ts_ms: Optional[float] = None) -> str:
    if ts_ms is None:
        ts_ms = time.time() * 1000.0
    lt = time.localtime(ts_ms / 1000.0)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", lt) + f".{int(ts_ms % 1000):03d}"
    return f"{stamp} - [{src}] {msg}\n"


def event(src: str, msg: str, ts_ms: Optional[float] = None) -> None:
    """Append a timeline event line to the per-run file and latest file.
    Safe to call anytime; if init() hasn't run, will auto-init with defaults.
    """
    global _PER_RUN_PATH, _LATEST_PATH
    if _PER_RUN_PATH is None or _LATEST_PATH is None:
        init(_OUT_DIR)
    line = _ts_line(src, msg, ts_ms)
    try:
        with open(_PER_RUN_PATH, "a", encoding="utf-8") as f:
            f.write(line)
        with open(_LATEST_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
