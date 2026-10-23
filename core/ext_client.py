import json
import os
import urllib.request as _u
import urllib.error as _ue
from typing import Any, Dict, Optional


class ExtClient:
    """HTTP client for orchestrator integration.

    Supports two modes:
      1) Run-scoped dispatch: /actions/dispatch and /runs/wait_quiet (preferred)
      2) Legacy direct: /ws/action with {header:{device_id,tab_id}}

    Configure via env (legacy only): EXT_DEVICE_ID, EXT_TAB_ID.
    Base URL: EXT_ORCH_BASE (default http://127.0.0.1:8788)
    """

    def __init__(self, base: Optional[str] = None) -> None:
        self.base = (base or os.getenv("EXT_ORCH_BASE") or "http://127.0.0.1:8788").rstrip("/")
        self.device_id = os.getenv("EXT_DEVICE_ID") or None
        self.tab_id = None
        try:
            self.tab_id = int(os.getenv("EXT_TAB_ID")) if os.getenv("EXT_TAB_ID") else None
        except Exception:
            self.tab_id = None

    def _header(self) -> Dict[str, Any]:
        return {"device_id": self.device_id, "tab_id": self.tab_id}

    def action_legacy(
        self,
        action: str,
        args: Optional[Dict[str, Any]] = None,
        await_result: bool = True,
        timeout_ms: int = 10000,
        exec_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base}/ws/action"
        payload = {
            "header": self._header(),
            "action": action,
            "args": args or {},
            "await_result": await_result,
            "timeout_ms": timeout_ms,
        }
        if exec_id:
            payload["exec_id"] = exec_id
        data = json.dumps(payload).encode("utf-8")
        req = _u.Request(url, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with _u.urlopen(req, data=data, timeout=max(2.0, timeout_ms / 1000.0 + 1.0)) as r:  # type: ignore
                txt = r.read().decode("utf-8", errors="ignore")
        except _ue.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"ext.action_legacy HTTP {e.code}: {body[:160]}")
        except Exception as e:
            raise RuntimeError(f"ext.action_legacy error: {e}")
        try:
            obj = json.loads(txt)
        except Exception:
            obj = {"ok": False, "error": f"bad_json:{txt[:160]}"}
        return obj

    def dispatch_run(
        self,
        run_id: str,
        action: str,
        args: Optional[Dict[str, Any]] = None,
        await_result: bool = True,
        timeout_ms: int = 10000,
        exec_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base}/actions/dispatch"
        payload = {
            "run_id": run_id,
            "action": action,
            "args": args or {},
            "await_result": await_result,
            "timeout_ms": timeout_ms,
        }
        if exec_id:
            payload["exec_id"] = exec_id
        data = json.dumps(payload).encode("utf-8")
        req = _u.Request(url, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with _u.urlopen(req, data=data, timeout=max(2.0, timeout_ms / 1000.0 + 1.0)) as r:  # type: ignore
                txt = r.read().decode("utf-8", errors="ignore")
        except _ue.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"dispatch_run HTTP {e.code}: {body[:160]}")
        except Exception as e:
            raise RuntimeError(f"dispatch_run error: {e}")
        try:
            return json.loads(txt)
        except Exception:
            return {"ok": False, "error": f"bad_json:{txt[:160]}"}

    def wait_quiet_run(self, run_id: str, timeout_ms: int = 8000) -> Dict[str, Any]:
        url = f"{self.base}/runs/wait_quiet"
        payload = {"run_id": run_id, "timeout_ms": timeout_ms}
        data = json.dumps(payload).encode("utf-8")
        req = _u.Request(url, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with _u.urlopen(req, data=data, timeout=max(2.0, timeout_ms / 1000.0 + 1.0)) as r:
                txt = r.read().decode("utf-8", errors="ignore")
        except _ue.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"wait_quiet_run HTTP {e.code}: {body[:160]}")
        except Exception as e:
            raise RuntimeError(f"wait_quiet_run error: {e}")
        try:
            return json.loads(txt)
        except Exception:
            return {"ok": False, "error": f"bad_json:{txt[:160]}"}

    def rebind_run(
        self,
        run_id: str,
        policy: str = "active_or_new",
        domain: Optional[str] = None,
        start_url: Optional[str] = None,
        prefer_active: bool = True,
        timeout_ms: int = 8000,
    ) -> Dict[str, Any]:
        """Request orchestrator to (re)bind run_id to a valid tab (CS_READY).

        Returns: { ok, device_id?, tab_id? } | { ok:false, error }
        """
        url = f"{self.base}/runs/rebind"
        payload = {
            "run_id": run_id,
            "policy": policy,
            "domain": domain,
            "start_url": start_url,
            "prefer_active": prefer_active,
            "timeout_ms": timeout_ms,
        }
        data = json.dumps(payload).encode("utf-8")
        req = _u.Request(url, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with _u.urlopen(req, data=data, timeout=max(2.0, timeout_ms / 1000.0 + 1.0)) as r:  # type: ignore
                txt = r.read().decode("utf-8", errors="ignore")
        except _ue.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            return {"ok": False, "error": f"rebind HTTP {e.code}: {body[:160]}"}
        except Exception as e:
            return {"ok": False, "error": f"rebind error: {e}"}
        try:
            return json.loads(txt)
        except Exception:
            return {"ok": False, "error": f"bad_json:{txt[:160]}"}
