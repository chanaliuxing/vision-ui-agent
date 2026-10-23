#!/usr/bin/env python3
"""
Minimal JSON logging setup for YOLO API (Y1).
Outputs JSON to stdout using structlog. Provides a small Timer helper
and a redact() utility for clipping large strings.
"""

import logging
import sys
import time
from typing import Any

try:
    import structlog
except Exception:  # fallback: no structlog installed
    structlog = None  # type: ignore


def setup_json_logging(level: str = None) -> None:
    lvl = (level or _env("YOLO_LOG_LEVEL", "INFO")).upper()
    if structlog is None:
        # Fallback to basic logging to stdout
        logging.basicConfig(stream=sys.stdout, level=getattr(logging, lvl, logging.INFO))
        return

    logging.basicConfig(stream=sys.stdout, level=getattr(logging, lvl, logging.INFO))
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, lvl, logging.INFO)),
    )


def get_logger():
    if structlog is None:
        return logging.getLogger("yolojson")
    return structlog.get_logger()


def redact(s: Any, maxlen: int = None) -> Any:
    if not isinstance(s, str):
        return s
    limit = int(_env("YOLO_LOG_REDACT_LEN", "300")) if maxlen is None else maxlen
    if len(s) <= limit:
        return s
    return s[:limit] + "..."


class Timer:
    def __enter__(self):
        self._t0 = time.perf_counter()
        self.ms = 0
        return self

    def __exit__(self, *exc):
        self.ms = int((time.perf_counter() - self._t0) * 1000)


def _env(key: str, default: str) -> str:
    try:
        import os
        return os.getenv(key, default)
    except Exception:
        return default

