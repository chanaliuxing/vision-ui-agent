from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional


class StrategyStore:
    """Persistent store for selected strategies keyed by (sig_key, goal).

    Records events with EMA success and TTL aging, similar to RoutesStore.
    """

    def __init__(self, logs_dir: str, filename: str = "strategies.jsonl") -> None:
        self.path = os.path.join(logs_dir, filename)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.cache = []  # type: ignore[list-item]
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            self.cache.append(json.loads(line))
                        except Exception:
                            continue
            except Exception:
                pass

    def append(self, rec: Dict[str, Any]) -> None:
        self.cache.append(rec)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def record(self, sig_key: str, goal: str, strategy: Dict[str, Any], success: bool,
               landmark_hash: Optional[str] = None, yhist_hash: Optional[str] = None,
               source: Optional[str] = None) -> None:
        ema_prev = 0.5
        for rec in reversed(self.cache):
            if rec.get("sig_key") == sig_key and rec.get("goal") == goal:
                ema_prev = float(rec.get("ema_success", 0.5))
                break
        alpha = float(os.getenv("STRATEGY_EMA_ALPHA", "0.25"))
        ema_new = (1 - alpha) * ema_prev + alpha * (1.0 if success else 0.0)
        self.append({
            "ts": int(time.time() * 1000),
            "sig_key": sig_key,
            "goal": goal,
            "strategy": strategy,
            "event": "success" if success else "fail",
            "ema_success": ema_new,
            "landmark_hash": landmark_hash,
            "yhist_hash": yhist_hash,
            "source": source or "",
        })

    def lookup(self, sig_key: str, goal: str,
               landmark_hash: Optional[str] = None,
               yhist_hash: Optional[str] = None) -> Optional[Dict[str, Any]]:
        ttl_min = int(os.getenv("STRATEGY_TTL_MIN", "1440"))
        ema_min = float(os.getenv("STRATEGY_EMA_MIN", "0.4"))
        now_ms = int(time.time() * 1000)
        for rec in reversed(self.cache):
            if rec.get("sig_key") != sig_key or rec.get("goal") != goal:
                continue
            if float(rec.get("ema_success", 0.0)) < ema_min:
                continue
            ts = int(rec.get("ts", 0))
            if ttl_min > 0 and ts:
                age_min = (now_ms - ts) / 60000.0
                if age_min > ttl_min:
                    continue
            # Optional strict matching on landmark/yhist hashes
            if os.getenv("STRATEGY_MATCH_LANDMARK", "0") == "1" and landmark_hash is not None:
                if rec.get("landmark_hash") and rec.get("landmark_hash") != landmark_hash:
                    continue
            if os.getenv("STRATEGY_MATCH_YHIST", "0") == "1" and yhist_hash is not None:
                if rec.get("yhist_hash") and rec.get("yhist_hash") != yhist_hash:
                    continue
            strat = rec.get("strategy")
            if isinstance(strat, dict) and strat.get("strategy_id"):
                return strat
        return None
