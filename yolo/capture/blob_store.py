#!/usr/bin/env python3
"""
Simple blob store for full-fidelity capture.
Default is local filesystem under CAPTURE_DIR (./out).
"""
from __future__ import annotations
import os
import io
import json
import hashlib
import datetime as _dt
from typing import Any, Optional


class LocalBlobStore:
    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def _full(self, key: str) -> str:
        path = os.path.join(self.base_dir, key)
        d = os.path.dirname(path)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        return path

    def save_bytes(self, key: str, b: bytes) -> str:
        path = self._full(key)
        with open(path, "wb") as f:
            f.write(b)
        return key

    def save_json(self, key: str, obj: Any) -> str:
        path = self._full(key)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return key


def _env(name: str, default: str) -> str:
    try:
        return os.getenv(name, default)
    except Exception:
        return default


def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def make_prefix(wf_run_id: Optional[str], req_id: str) -> str:
    date = _dt.datetime.now().strftime("%Y-%m-%d")
    wf = wf_run_id or "no-wf"
    return f"runs/{date}/{wf}/{req_id}"


def init_store():
    backend = _env("CAPTURE_BACKEND", "local").lower()
    if backend == "local":
        return LocalBlobStore(_env("CAPTURE_DIR", "./out"))
    # Placeholder for S3/MinIO implementation
    return LocalBlobStore(_env("CAPTURE_DIR", "./out"))