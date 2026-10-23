import json
import os
import time
from typing import Any, Dict, List, Optional


class MemoryStore:
    """Lightweight page-level memory persisted as JSONL under out/logs.

    Keyed by a signature key (string). Stores recent decisions and outcomes,
    enabling simple blacklists and a short history hint for prompts.
    """

    def __init__(self, logs_dir: str, filename: str = "memory.jsonl", max_keep: int = 2000) -> None:
        self.logs_dir = logs_dir
        os.makedirs(self.logs_dir, exist_ok=True)
        self.path = os.path.join(self.logs_dir, filename)
        self.max_keep = max_keep
        self._cache: Dict[str, List[Dict[str, Any]]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        if not os.path.exists(self.path):
            self._loaded = True
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                        key = rec.get("sig_key")
                        if not key:
                            continue
                        self._cache.setdefault(key, []).append(rec)
                    except Exception:
                        continue
        except Exception:
            pass
        self._loaded = True

    def _append(self, rec: Dict[str, Any]) -> None:
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def record(self, sig_key: str, click_id: Optional[str], outcome: str, reason: str = "") -> None:
        """Record a decision outcome for this page signature.
        outcome: success|fail|need_input
        """
        self._load()
        rec = {
            "ts": int(time.time() * 1000),
            "sig_key": sig_key,
            "click_id": click_id,
            "outcome": outcome,
            "reason": reason,
        }
        self._cache.setdefault(sig_key, []).append(rec)
        # trim
        if len(self._cache[sig_key]) > self.max_keep:
            self._cache[sig_key] = self._cache[sig_key][-self.max_keep :]
        self._append(rec)
        # timeline event
        try:
            from . import timeline as _t
            msg = f"memory: click_id={click_id} outcome={outcome} reason={reason}"
            _t.event("memory", msg, ts_ms=rec.get("ts"))
            if outcome == "fail" and click_id:
                _t.event("denylist", f"add {click_id}", ts_ms=rec.get("ts"))
        except Exception:
            pass

    def get_blacklist(self, sig_key: str, k: int = 5, ttl_minutes: Optional[int] = None) -> List[str]:
        """Return up to k most recent failed click_ids for this signature.
        If ttl_minutes is provided, only include records within that window.
        """
        self._load()
        out: List[str] = []
        now_ms = int(time.time() * 1000)
        ttl_ms = None
        if ttl_minutes is not None:
            try:
                ttl_ms = int(ttl_minutes) * 60_000
            except Exception:
                ttl_ms = None
        for rec in reversed(self._cache.get(sig_key, [])):
            if ttl_ms is not None and isinstance(rec.get("ts"), int):
                if now_ms - int(rec.get("ts")) > ttl_ms:
                    continue
            if rec.get("outcome") == "fail" and rec.get("click_id") and rec["click_id"] not in out:
                out.append(rec["click_id"])
            if len(out) >= k:
                break
        return out

    def summarize(self, sig_key: str, limit: int = 2) -> Optional[str]:
        """Return a short one-liner hint for prompts, e.g.,
        "avoid: c12,c27; last: fail verify"
        """
        self._load()
        recent = list(reversed(self._cache.get(sig_key, [])))
        if not recent:
            return None
        avoids = [r["click_id"] for r in recent if r.get("outcome") == "fail" and r.get("click_id")]  # type: ignore
        avoids_uniq: List[str] = []
        for x in avoids:
            if x not in avoids_uniq:
                avoids_uniq.append(x)
            if len(avoids_uniq) >= limit:
                break
        last = recent[0]
        parts: List[str] = []
        if avoids_uniq:
            parts.append(f"avoid: {','.join(avoids_uniq)}")
        if last:
            lr = last.get("outcome")
            if lr:
                parts.append(f"last: {lr}")
        return "; ".join(parts) if parts else None
