import json
import os
import time
import hashlib
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import ast

import cv2
import numpy as np
from PIL import Image
import platform
import subprocess
import webbrowser
import base64
import uuid

from .capture import ScreenCapture
from .executor import Executor
from .locator import bbox_center, select_best
from .reporter import Reporter, StepLog
from .yolo_client import YoloClient
from .prompt_builder import (
    PromptSpec,
    SYSTEM_TEMPLATE_UI_OUTLINE,
    build_messages,
    build_user_payload,
    build_id_only_messages,
    build_min_picker_messages,
    build_planner_messages,
    build_picker_messages_unified,
    PickerCtx,
)
from .llm_client import call_llm, extract_text_generic
from .gemini_client import parse_first_json
from types import SimpleNamespace
from .mapping import CaptureMeta, PreprocMeta, map_id_to_screen_point
from .candidates import yolo_to_geom_candidates
from .memory import MemoryStore
from .detectors import detect_loading, detect_toast, detect_modal
from .ocr_client import OcrClient
from .anchors import (
    RoutesStore,
    anchors_from,
    anchors_match,
    auto_select_anchors,
    locate_instance,
    state_anchors_from,
    state_anchors_vote,
    adjust_template_anchor,
    adjust_orb_anchor,
    adjust_relation,
    adjust_state_anchors,
)
from .strategy_selector import StrategySelector
from .landmarks import detect_landmarks  # summarize_page temporarily commented out
from .ops import has_attr_unread_by_ocr, has_attr_unread_by_color, group_by_rows, union_bbox, filter_in_region, has_attr_unread
from .strategy_store import StrategyStore
from .ext_client import ExtClient
from .dom_picker import pick_selector_from_dom
from .observability.run_events import RunEventRecorder, EventType


# ---- Configuration helpers (global) ----
def _get_wf(self):
    try:
        return self.workflow if isinstance(self.workflow, dict) else {}
    except Exception:
        return {}

def _wf_var(self, key, default=None):
    try:
        return (_get_wf(self).get("vars") or {}).get(key, default)
    except Exception:
        return default

def _wf_list(self, key, default=None):
    v = _wf_var(self, key, None)
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        xs = [x.strip() for x in v.split(",") if x.strip()]
        return xs or (default or [])
    return default or []

def _env_list(name, default=None):
    s = os.getenv(name)
    if not s:
        return default or []
    xs = [x.strip() for x in s.split(",") if x.strip()]
    return xs or (default or [])

def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

def _env_float(name, default):
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default

def _env_bool(name, default=False):
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1","true","yes","y","on")


@dataclass
class WFConfig:
    conf_min: float = 0.5
    poll_interval_s: float = 0.6
    wait_timeout_s: float = 8.0
    click_padding_px: int = -6
    imgsz: int = 1280
    screenshot_wait_s: float = float(os.getenv("SCREENSHOT_WAIT_S", "6.0"))
    max_retries_per_step: int = int(os.getenv("WF_MAX_RETRIES_PER_STEP", "1"))


class WorkflowRunner:
    """Minimal JSON-driven workflow engine.

    Supported actions: screenshot, detect, locate, click, type_text, wait_for, scroll, sleep_ms.
    wait_for types: {"type":"yolo_appear", "any_of":[...]} | {"type":"spinner_disappear","yolo_class":"..."} | {"type":"sleep_ms","value":500}
    """

    def __init__(
        self,
        workflow: Dict[str, Any],
        endpoint: str = "http://127.0.0.1:8000",
        out_dir: str = "out",
        cfg: Optional[WFConfig] = None,
        event_recorder: Optional[RunEventRecorder] = None,
    ) -> None:
        self.workflow = workflow
        self.endpoint = endpoint.rstrip("/")
        self.cfg = cfg or WFConfig()

        self.cap = ScreenCapture()
        self.exec = Executor()
        self.yolo = YoloClient(endpoint=self.endpoint)
        self.reporter = Reporter(out_dir=out_dir)
        self.memory = MemoryStore(logs_dir=self.reporter.logs_dir)
        self.routes = RoutesStore(logs_dir=self.reporter.logs_dir)
        self.ocr = OcrClient(endpoint=os.getenv("OCR_ENDPOINT"))
        self.strategy = StrategySelector(logs_dir=self.reporter.logs_dir)
        self.event_recorder = event_recorder or RunEventRecorder()
        self.strategy_store = StrategyStore(logs_dir=self.reporter.logs_dir)
        # Extension/orchestrator client for DOM executor (Plan A)
        try:
            self.ext = ExtClient(base=os.getenv("EXT_ORCH_BASE") or "http://127.0.0.1:8788")
        except Exception:
            self.ext = None
        
        # M3 Cost control and reporting
        from .costs import CostGuard, Budget
        from .llm_router import LLMRouter
        from .report_events import emit_run_begin
        
        self.cost_guard = CostGuard(Budget.from_env())
        self.llm_router = LLMRouter(self.cost_guard)

        # transient context
        self.ctx: Dict[str, Any] = {
            "last_pil": None,
            "last_bgr": None,
            "detections": [],
            "chosen": None,
            "dpr": 1.0,
            "step_n": 1,
            "next_state_id": None,
            "last_sig_key": None,
            "sig_repeat_count": 0,
            "planner_calls": 0,
            "plan_queue": [],
        }

        # simple in-memory graph
        self.graph: Dict[str, Any] = {"nodes": {}, "edges": []}
        # run context for orchestrator integration
        self.ctx_run: Dict[str, Any] = {}
        # hot-patch counters
        self.ctx.setdefault("hot_patch_used", 0)

        # clipboard stack for safety
        self._clip_stack = []

    # ------ configuration helpers ------
    def _mouse_cap(self):
        # Return (has_exec, fallback)
        try:
            import pyautogui as _p
        except Exception:
            _p = None
        return (
            hasattr(self.exec, "mouse_down") and hasattr(self.exec, "mouse_up") and
            hasattr(self.exec, "drag_to") and hasattr(self.exec, "move_to"),
            _p
        )

    def _click_btn(self, x, y, button="left", dpr=None):
        # Unified click entry point
        if hasattr(self.exec, "click"):
            self.exec.click(x, y, dpr=float(dpr or self.ctx.get("dpr", 1.0)), button=button)
        else:
            # fallback
            _, _p = self._mouse_cap()
            if not _p:
                raise RuntimeError("click fallback requires pyautogui")
            _p.click(x, y, button=button)

    def _button_norm(self, b):
        b = (b or "left").lower()
        return b if b in ("left","right","middle") else "left"

    # ------ capture config helpers ------
    def _capture_cfg(self) -> Dict[str, Any]:
        try:
            return (self.workflow.get("vars", {}) or {}).get("capture", {}) or {}
        except Exception:
            return {}

    def _cap_meta(self) -> CaptureMeta:
        cap_h, cap_w = self.ctx.get("last_bgr").shape[:2] if self.ctx.get("last_bgr") is not None else (0, 0)
        cfg = self._capture_cfg()
        win_off = cfg.get("window_offset_px") or [0, 0]
        apply_off = bool(cfg.get("apply_offset", False))
        wx = int(win_off[0]) if (isinstance(win_off, (list, tuple)) and len(win_off) >= 2 and apply_off) else 0
        wy = int(win_off[1]) if (isinstance(win_off, (list, tuple)) and len(win_off) >= 2 and apply_off) else 0
        return CaptureMeta(cap_w=int(cap_w), cap_h=int(cap_h), win_offset_x=wx, win_offset_y=wy, dpr=float(self.ctx.get("dpr", 1.0)))

    # ------ condition evaluation ------
    def _eval_condition(self, expr: str) -> bool:
        """Evaluate a limited condition expression against workflow vars and runtime ctx.

        Supports patterns: @var, @obj['key'], @arr[0], booleans, comparisons, and/or/not.
        """
        if not isinstance(expr, str) or not expr.strip():
            return False

        # Build variable source
        try:
            wf_vars = (self.workflow.get("vars") or {}) if isinstance(self.workflow, dict) else {}
        except Exception:
            wf_vars = {}
        ctx_vars = dict(self.ctx) if isinstance(self.ctx, dict) else {}

        def __get(name: str):
            if name in wf_vars:
                return wf_vars.get(name)
            return ctx_vars.get(name)

        # Replace @name with __get("name")
        import re
        code = re.sub(r"@([A-Za-z_][A-Za-z0-9_]*)", r'__get("\\1")', expr)

        # Safe eval: allow only basic ops
        allowed_names = {"__get": __get, "True": True, "False": False, "None": None}
        try:
            # Parse first to screen nodes (very light check)
            tree = ast.parse(code, mode="eval")
            # Optional: could walk the AST to restrict nodes; keep minimal here
            return bool(eval(compile(tree, filename="<cond>", mode="eval"), {"__builtins": {}}, allowed_names))
        except Exception:
            return False

    # ------ helpers for generic names/arrays ------
    @staticmethod
    def _to_name_list(name_or_list: Any) -> List[str]:
        if name_or_list is None:
            return []
        if isinstance(name_or_list, (list, tuple)):
            return [str(x).strip() for x in name_or_list if str(x).strip()]
        return [str(name_or_list).strip()]

    @staticmethod
    def _any_true(fn, names: List[str]) -> Tuple[bool, Optional[str]]:
        for nm in names:
            try:
                if fn(nm):
                    return True, nm
            except Exception:
                pass
        return False, None

    # ------ core helpers ------
    def _grab(self) -> None:
        g = self.cap.screenshot()
        pil = g.image.convert("RGB")
        bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        self.ctx.update({"last_pil": pil, "last_bgr": bgr, "dpr": float(getattr(g, "dpr", 1.0))})
        # New: a fresh screenshot invalidates any prior detection cache
        try:
            self.ctx["vision_ready"] = False
        except Exception:
            pass

    def _detect(self) -> None:
        pil: Image.Image = self.ctx["last_pil"]
        resp = self.yolo.infer(pil, return_image=False, imgsz=self.cfg.imgsz)
        dets = self.yolo.to_detections(resp)
        self.ctx["detections"] = dets
        self.ctx["last_api_resp"] = resp
        # Mark current vision as ready for subsequent autostep
        try:
            self.ctx["vision_ready"] = True
        except Exception:
            pass

    # ------ signatures & graph ------
    @staticmethod
    def _tile_hashes(bgr: np.ndarray, tiles: int = 4) -> List[str]:
        # downscale and split into N tiles, hash bytes
        try:
            small = cv2.resize(bgr, (128, 128))
        except Exception:
            small = bgr
        hlist: List[str] = []
        t = int(math.sqrt(tiles))
        t = max(1, t)
        th, tw = small.shape[0] // t, small.shape[1] // t
        for i in range(t):
            for j in range(t):
                tile = small[i * th : (i + 1) * th, j * tw : (j + 1) * tw]
                h = hashlib.sha1(tile.tobytes()).hexdigest()
                hlist.append(h)
        return hlist[:tiles]

    @staticmethod
    def _phash(bgr: np.ndarray) -> str:
        try:
            g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(g, (16, 16), interpolation=cv2.INTER_AREA)
            avg = float(small.mean())
            bits = (small > avg).astype(np.uint8).flatten()
            out = []
            val = 0
            for i, b in enumerate(bits):
                val = (val << 1) | int(b)
                if (i + 1) % 4 == 0:
                    out.append(format(val, 'x'))
                    val = 0
            return ''.join(out)
        except Exception:
            return ""

    @staticmethod
    def _yolo_hist(dets: List[Any]) -> Dict[str, int]:
        hist: Dict[str, int] = {}
        for d in dets:
            cls = getattr(d, "class_name", None) or d.get("class_name")  # type: ignore
            hist[cls] = hist.get(cls, 0) + 1
        return hist

    # ------ lightweight detectors ------
    def _ocr_tokens_current(self) -> List[str]:
        toks: List[str] = []
        try:
            if hasattr(self, "ocr") and self.ocr:
                got = self.ocr.read_texts(self.ctx.get("last_pil")) or []
                for t in got:
                    s = (t or "").strip()
                    if 2 <= len(s) <= 16:
                        toks.append(s)
        except Exception:
            pass
        return toks

    def _detect_loading_toast(self) -> Dict[str, object]:
        """Composite detector: try small templates first, fallback to heuristics."""
        bgr = self.ctx.get("last_bgr")
        res: Dict[str, object] = {"loading": False, "toast": False, "detail": {}}
        if bgr is None:
            return res
        # 1) template-based
        try:
            d1 = detect_loading(bgr)
            if d1.get("matched"):
                res["loading"] = True
                res.setdefault("detail", {})["loading"] = {"name": d1.get("name"), "score": d1.get("score")}
        except Exception:
            pass
        try:
            d2 = detect_toast(bgr)
            if d2.get("matched"):
                res["toast"] = True
                res.setdefault("detail", {})["toast"] = {"name": d2.get("name"), "score": d2.get("score")}
        except Exception:
            pass
        toks = self._ocr_tokens_current()
        toks_join = " ".join(toks)
        loading_words = ["加载", "loading", "处理中", "正在", "刷新"]
        toast_words = ["成功", "已发布", "完成", "保存", "已复制"]
        if not res.get("loading"):
            if any(w in toks_join.lower() for w in ["loading", "processing"]) or any(w in toks_join for w in loading_words):
                res["loading"] = True
                res.setdefault("detail", {})["loading_text"] = True
        if not res.get("toast"):
            if any(w in toks_join for w in toast_words):
                res["toast"] = True
                res.setdefault("detail", {})["toast_text"] = True
        # bottom dark band heuristic (toast banner)
        try:
            H, W = bgr.shape[:2]
            band = bgr[int(H*0.8):H, :]
            gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
            if gray.mean() < 110 and gray.std() < 35:
                if not res.get("toast"):
                    res["toast"] = True
                    res.setdefault("detail", {})["toast_band"] = True
        except Exception:
            pass
        return res

    def _signature(self, bgr: np.ndarray, dets: List[Any]) -> Dict[str, Any]:
        sig = {"phash": self._phash(bgr), "phash_tiles": self._tile_hashes(bgr, 4), "yolo_hist": self._yolo_hist(dets)}
        # add a coarse layout grid hash (8x8 mean bins -> ints string)
        try:
            g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(g, (16, 16), interpolation=cv2.INTER_AREA)
            blocks = (small.reshape(16, 16) > small.mean()).astype(np.uint8).flatten()
            sig["layout"] = ''.join('1' if x else '0' for x in blocks.tolist())
        except Exception:
            pass
        # Optional URL hint on macOS (Chrome/Safari)
        try:
            url = self._get_url_hint()
            if url:
                sig["url"] = url
        except Exception:
            pass
        # Optional top OCR token hash
        try:
            if hasattr(self, "ocr") and self.ocr:
                toks = self.ocr.read_texts(self.ctx.get("last_pil")) or []
                toks = [t.strip() for t in toks if t and 2 <= len(t.strip()) <= 12]
                toks = sorted(set(toks))[:8]
                sig["ocr_top"] = '|'.join(toks)
        except Exception:
            pass
        return sig

    @staticmethod
    def _sig_sim(a: Dict[str, Any], b: Dict[str, Any]) -> float:
        # tile equality ratio + cosine over yolo_hist + layout hamming bonus
        ph_a = a.get("phash_tiles", []); ph_b = b.get("phash_tiles", [])
        ph_len = max(1, min(len(ph_a), len(ph_b)))
        ph_eq = sum(1 for x, y in zip(ph_a, ph_b) if x == y) / ph_len
        keys = set(a.get("yolo_hist", {})) | set(b.get("yolo_hist", {}))
        va = [a.get("yolo_hist", {}).get(k, 0) for k in keys]
        vb = [b.get("yolo_hist", {}).get(k, 0) for k in keys]
        dot = sum(x * y for x, y in zip(va, vb))
        na = math.sqrt(sum(x * x for x in va))
        nb = math.sqrt(sum(x * x for x in vb))
        yo = (dot / (na * nb)) if na * nb else 0.0
        # layout grid hamming
        lay_a = a.get("layout"); lay_b = b.get("layout")
        if isinstance(lay_a, str) and isinstance(lay_b, str) and len(lay_a) == len(lay_b) and len(lay_a) > 0:
            h_eq = sum(1 for x, y in zip(lay_a, lay_b) if x == y) / len(lay_a)
        else:
            h_eq = 0.0
        return 0.4 * ph_eq + 0.4 * yo + 0.2 * h_eq

    def _resolve_or_create_state(self, sig: Dict[str, Any], thr: float = 0.78) -> str:
        for sid, node in self.graph["nodes"].items():
            if self._sig_sim(sig, node["signature"]) >= thr:
                node.setdefault("stats", {}).update({"visits": node.get("stats", {}).get("visits", 0) + 1})
                return sid
        sid = f"pg_{len(self.graph['nodes']):04d}"
        self.graph["nodes"][sid] = {"id": sid, "signature": sig, "stats": {"visits": 1}}
        return sid

    def _link_edge(self, src: str, dst: str, action: Dict[str, Any], verify: Dict[str, Any]):
        self.graph["edges"].append({"from": src, "to": dst, "action": action, "verify": verify, "metrics": {"success": 1}})

    def _save_graph_workflow(self, start_id: Optional[str] = None) -> str:
        wf = {"start": start_id or (next(iter(self.graph["nodes"])) if self.graph["nodes"] else "open_home"),
              "states": {nid: {"actions": [{"do": "autostep"}], "on_success": "autonext"} for nid in self.graph["nodes"]}}
        path = os.path.join("flows", "auto_workflow.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(wf, f, ensure_ascii=False, indent=2)
        return path

    def _locate(self, targets: List[str]) -> None:
        bgr = self.ctx["last_bgr"]
        dets = self.ctx["detections"]
        sel = select_best(dets, targets, bgr.shape[1], bgr.shape[0], conf_min=self.cfg.conf_min)
        self.ctx["chosen"] = sel

    def _draw_overlay(self, name: str) -> Dict[str, str]:
        bgr = self.ctx["last_bgr"]
        dets = self.ctx["detections"]
        boxes = [d.bbox_xyxy for d in dets]
        labels = [f"{d.class_name} {d.conf:.2f}" for d in dets]
        chosen = self.ctx.get("chosen")
        chosen_idx = None
        if chosen and chosen.chosen is not None and chosen.chosen in dets:
            chosen_idx = dets.index(chosen.chosen)
        over = self.reporter.draw_detections(bgr, boxes, labels, chosen_idx)
        before = self.reporter.save_image(bgr, f"{name}_before.png")
        overlay = self.reporter.save_image(over, f"{name}_overlay.png")
        return {"before": before, "overlay": overlay}

    # ------ action implementations ------
    def act_screenshot(self, save_as: Optional[str] = None) -> None:
        # Wait before capturing to allow page/content to stabilize
        try:
            wait_s = float(getattr(self.cfg, "screenshot_wait_s", 0.0) or 0.0)
        except Exception:
            wait_s = 0.0
        if wait_s > 0:
            try:
                time.sleep(wait_s)
            except Exception:
                pass
        # Capture mode selection (full | active_window | region)
        cap_cfg = self._capture_cfg()
        mode = str(cap_cfg.get("mode") or "full").lower()
        if mode == "active_window":
            try:
                g, off = self.cap.screenshot_active_window()
                pil = g.image.convert("RGB")
                bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
                self.ctx.update({"last_pil": pil, "last_bgr": bgr, "dpr": float(getattr(g, "dpr", 1.0))})
                if off is not None:
                    # Update runtime capture overrides for mapping offset
                    try:
                        cap_rt = dict(self.ctx.get("capture") or {})
                        cap_rt.update({"window_offset_px": [int(off[0]), int(off[1])], "apply_offset": True})
                        self.ctx["capture"] = cap_rt
                    except Exception:
                        pass
            except Exception:
                self._grab()
        elif mode == "region":
            # Use provided window_offset_px + window_size_px
            try:
                off = cap_cfg.get("window_offset_px") or [0, 0]
                size = cap_cfg.get("window_size_px") or [0, 0]
                if isinstance(off, (list, tuple)) and len(off) >= 2 and isinstance(size, (list, tuple)) and len(size) >= 2:
                    region = (int(off[0]), int(off[1]), int(size[0]), int(size[1]))
                    img = __import__("pyautogui").screenshot(region=region)  # type: ignore
                    pil = img.convert("RGB")
                    bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
                    self.ctx.update({"last_pil": pil, "last_bgr": bgr, "dpr": float(self.ctx.get("dpr", 1.0))})
                    try:
                        cap_rt = dict(self.ctx.get("capture") or {})
                        cap_rt.update({"window_offset_px": [int(off[0]), int(off[1])], "apply_offset": True})
                        self.ctx["capture"] = cap_rt
                    except Exception:
                        pass
                else:
                    self._grab()
            except Exception:
                self._grab()
        else:
            self._grab()
        if save_as:
            self.reporter.save_image(self.ctx["last_bgr"], save_as)

    def act_detect(self) -> None:
        self._detect()

    def act_locate(self, targets: List[str]) -> None:
        self._locate(targets)

    def act_click(self, button="left", times=1, interval_ms=120) -> None:
        sel = self.ctx["chosen"]
        if not sel or not sel.chosen:
            raise RuntimeError("click requested but no chosen candidate")
        cx, cy = bbox_center(sel.chosen.bbox_xyxy, padding_px=self.cfg.click_padding_px)
        dpr = float(self.ctx.get("dpr", 1.0))

        # Danger double-confirm (pre-click); if danger words detected, skip click and mark need_input
        try:
            if _env_bool("DANGER_DOUBLE_CONFIRM", True):
                # Priority: workflow.vars.danger_words, then env DANGER_WORDS, then default mixed lang words
                default_words = ["publish","delete","pay","submit","确认","发布","删除","支付","提交"]
                words = _wf_list(self, "danger_words") or _env_list("DANGER_WORDS", default_words)
                if words and hasattr(self, "ocr") and self.ocr:
                    txts = self.ocr.read_texts(self.ctx.get("last_pil")) or []
                    if any(any(w in (t or "") for w in words) for t in txts):
                        try:
                            sig_key = json.dumps(self._signature(self.ctx["last_bgr"], self.ctx["detections"]), sort_keys=True)
                            self.memory.record(sig_key, None, "need_input", reason="danger_confirm")
                        except Exception:
                            pass
                        return
        except Exception:
            pass

        # Support multi-click (double-click/triple-click)
        button = self._button_norm(button)
        times = max(1, int(times))
        interval_ms = max(0, int(interval_ms))

        for i in range(times):
            self._click_btn(cx, cy, button=button, dpr=dpr)
            if i < times - 1:
                time.sleep(interval_ms / 1000.0)

    def act_type_text(self, text: str) -> None:
        self.exec.type_text(text)

    def act_scroll(self, clicks: int = -400) -> None:
        self.exec.scroll(clicks)

    def act_sleep_ms(self, value: int) -> None:
        time.sleep(max(0, value) / 1000.0)

    def act_go_back(self) -> None:
        try:
            self.exec.go_back()
        except Exception:
            pass

    def act_wait_for(self, until: Dict[str, Any]) -> bool:
        t = until.get("type")
        if t == "sleep_ms":
            self.act_sleep_ms(int(until.get("value", 500)))
            return True

        # Extension-driven page stable check (optional integration)
        # Polls a local HTTP endpoint exposed by the Chrome extension/daemon
        # Env overrides:
        #   EXT_SIGNAL_URL: full URL to check (e.g., http://127.0.0.1:8789/page_stable)
        #   EXT_ORCH_BASE: base URL to compose /page_stable when EXT_SIGNAL_URL not provided
        if t in ("ext_page_stable", "ext.wait_quiet"):
            import json as _json
            import urllib.request as _u
            import urllib.error as _ue

            def _is_stable(resp_bytes: bytes) -> bool:
                try:
                    s = (resp_bytes or b"").decode("utf-8", errors="ignore").strip()
                except Exception:
                    s = ""
                # Accept simple ok/true signal
                if s.lower() in ("ok", "true", "ready", "stable"):
                    return True
                try:
                    obj = _json.loads(s)
                    if isinstance(obj, dict):
                        # Accept { ok: true, stable: true } or either key
                        if bool(obj.get("stable")) or bool(obj.get("ok")) or bool(obj.get("ready")):
                            return True
                except Exception:
                    pass
                return False

            # Prefer orchestrator run-scoped wait if run_id available
            run_id = self.ctx_run.get("run_id") if isinstance(self.ctx_run, dict) else None
            if run_id and getattr(self, "ext", None):
                try:
                    tout = int(until.get("timeout_ms", int(self.cfg.wait_timeout_s * 1000)))
                    out = self.ext.wait_quiet_run(str(run_id), timeout_ms=tout)
                    if bool(out.get("ok")):
                        try:
                            self.reporter.log_step(StepLog(name="wait_ext_page_stable", status="success", message=f"ok run_id={run_id}", exec_id=self.ctx.get("exec_id")))
                        except Exception:
                            pass
                        return True
                    else:
                        try:
                            self.reporter.log_step(StepLog(name="wait_ext_page_stable", status="info", message=f"timeout run_id={run_id}", exec_id=self.ctx.get("exec_id")))
                        except Exception:
                            pass
                        return False
                except Exception:
                    pass

            url = until.get("url") or os.getenv("EXT_SIGNAL_URL")
            if not url:
                base = os.getenv("EXT_ORCH_BASE") or "http://127.0.0.1:8789"
                url = base.rstrip("/") + "/page_stable"
            else:
                # Note when falling back to URL-based readiness (no run_id available)
                try:
                    self.reporter.log_step(StepLog(name="wait_ext_page_stable", status="info", message="fallback_url_mode", exec_id=self.ctx.get("exec_id")))
                except Exception:
                    pass

            deadline = time.time() + float(until.get("timeout_ms", int(self.cfg.wait_timeout_s * 1000))) / 1000.0
            poll = float(until.get("poll_ms", int(self.cfg.poll_interval_s * 1000))) / 1000.0
            last_err = None
            while time.time() < deadline:
                try:
                    req = _u.Request(url, method="GET")
                    with _u.urlopen(req, timeout=2.0) as r:  # type: ignore
                        data = r.read()
                    if _is_stable(data):
                        try:
                            self.reporter.log_step(
                                StepLog(
                                    name="wait_ext_page_stable",
                                    status="success",
                                    message=f"ok url={url}",
                                    exec_id=self.ctx.get("exec_id")
                                )
                            )
                        except Exception:
                            pass
                        return True
                except Exception as e:
                    last_err = e
                time.sleep(poll)
            # Optional: log last error for diagnostics
            try:
                self.reporter.log_step(StepLog(name=f"wait_ext_page_stable", status="info", message=f"timeout url={url} err={str(last_err)[:48] if last_err else ''}", exec_id=self.ctx.get("exec_id")))
            except Exception:
                pass
            return False

        deadline = time.time() + float(until.get("timeout_ms", int(self.cfg.wait_timeout_s * 1000))) / 1000.0
        poll = float(until.get("poll_ms", int(self.cfg.poll_interval_s * 1000))) / 1000.0

        while time.time() < deadline:
            self._grab()
            self._detect()
            dets = self.ctx["detections"]
            classes = [d.class_name for d in dets]
            ocr_texts = None

            if t == "yolo_appear":
                any_of = set(until.get("any_of") or [])
                if any_of.intersection(classes):
                    return True

            if t == "spinner_disappear":
                spinner = until.get("yolo_class")
                if spinner and (spinner not in classes):
                    return True

            # Optional OCR text rules and page_change/loading/toast rules
            rules = until.get("rules") or []
            if isinstance(rules, list) and rules:
                need_ocr = any(isinstance(r, str) and (r.startswith("appear:text=") or r.startswith("disappear:text=")) for r in rules)
                if need_ocr:
                    try:
                        ocr_texts = self.ocr.read_texts(self.ctx.get("last_pil")) if self.ocr else []
                    except Exception:
                        ocr_texts = []
                for r in rules:
                    if isinstance(r, str) and r.startswith("appear:text="):
                        key = r.split("=", 1)[1].strip()
                        if key and any((key in (t or "")) for t in (ocr_texts or [])):
                            return True
                    if isinstance(r, str) and r.startswith("disappear:text="):
                        key = r.split("=", 1)[1].strip()
                        if key and not any((key in (t or "")) for t in (ocr_texts or [])):
                            return True
                    if isinstance(r, str) and r == "page_change":
                        sig2 = self._signature(self.ctx["last_bgr"], dets)
                        if self._sig_sim(sig2, self._signature(self.ctx["last_bgr"], dets)) < 0.72:
                            return True
                    if isinstance(r, str) and (r.endswith(":loading") or r.endswith(":toast")):
                        det = self._detect_loading_toast()
                        key = r.split(":", 1)[1]
                        flag = bool(det.get(key, False))
                        if r.startswith("appear:") and flag:
                            try:
                                msg = f"{key}:tpl={det.get('detail',{}).get(key,{}).get('name','')} score={det.get('detail',{}).get(key,{}).get('score','')}"
                                self.reporter.log_step(StepLog(name=f"autostep_{int(self.ctx.get('step_n',0))}_det", status='info', message=msg))
                            except Exception:
                                pass
                            return True
                        if r.startswith("disappear:") and (not flag):
                            return True

            time.sleep(poll)
        return False

    def act_open_url(self, url: str, app: Optional[str] = "Google Chrome") -> None:
        # Priority: workflow.vars.default_browser → env DEFAULT_BROWSER → parameter
        app2 = _wf_var(self, "default_browser") or os.getenv("DEFAULT_BROWSER") or app or "Google Chrome"
        sysname = platform.system()
        try:
            if sysname == "Darwin" and app2:
                subprocess.run(["open", "-a", app2, url], check=False)
                return
            if sysname == "Windows":
                os.startfile(url)  # type: ignore[attr-defined]
                return
        except Exception:
            pass
        # Fallback to default browser
        webbrowser.open(url)

    # ------ Instruction (instr.*) utilities ------
    def _get_var_value(self, name: str) -> Any:
        try:
            if not name:
                return None
            # strip optional leading '@'
            key = name[1:] if isinstance(name, str) and name.startswith("@") else name
            # 1) transient ctx
            if isinstance(self.ctx, dict) and key in self.ctx:
                return self.ctx.get(key)
            # 2) workflow-level vars
            if isinstance(self.workflow, dict):
                wf_vars = self.workflow.get("vars") or {}
                if key in wf_vars:
                    return wf_vars.get(key)
        except Exception:
            pass
        return None

    def _instr_resolve_target(self, target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        target = target or {}
        run_id = None
        try:
            if isinstance(self.ctx_run, dict):
                run_id = self.ctx_run.get("run_id")
        except Exception:
            run_id = None
        if run_id and getattr(self, "ext", None):
            # Try orchestrator resolve; accept either {selector} or {bbox}
            try:
                out = self.ext.dispatch_run(str(run_id), "ext.resolve", args={"target": target}, await_result=True, timeout_ms=8000, exec_id=str(uuid.uuid4()))
                if isinstance(out, dict) and out.get("ok"):
                    sel = out.get("selector") or (out.get("data") or {}).get("selector")
                    bbox = out.get("bbox") or (out.get("data") or {}).get("bbox")
                    return {"selector": sel, "bbox": bbox}
            except Exception:
                pass
        # No DOM resolution available
        return {"selector": None, "bbox": None}

    def _run_instr(self, act: Dict[str, Any]) -> None:
        op = act.get("do")
        tgt = act.get("target") or {}
        res = self._instr_resolve_target(tgt)
        sel = res.get("selector")
        bbox = res.get("bbox")
        run_id = self.ctx_run.get("run_id") if isinstance(self.ctx_run, dict) else None
        exec_id = self.ctx.get("exec_id")

        # Helper: coordinate click/scroll fallback via existing primitives
        def _click_fallback_from_target() -> bool:
            bv = (tgt or {}).get("bbox_var")
            ref = None
            if isinstance(bv, str) and bv:
                ref = self._get_var_value(bv)
            if not ref:
                ref = bbox
            if isinstance(ref, dict):
                # Supports dict form {x,y,w,h}
                try:
                    x = int(ref.get("x", 0) + ref.get("w", 0) / 2)
                    y = int(ref.get("y", 0) + ref.get("h", 0) / 2)
                    self.exec.click(x, y, dpr=float(self.ctx.get("dpr", 1.0)))
                    return True
                except Exception:
                    return False
            if isinstance(ref, (list, tuple)) and len(ref) >= 4:
                try:
                    # [x1,y1,x2,y2]
                    x1, y1, x2, y2 = ref[:4]
                    cx = int((float(x1) + float(x2)) / 2.0)
                    cy = int((float(y1) + float(y2)) / 2.0)
                    self.exec.click(cx, cy, dpr=float(self.ctx.get("dpr", 1.0)))
                    return True
                except Exception:
                    return False
            return False

        # Mapping
        if op == "instr.click":
            if sel and run_id and getattr(self, "ext", None):
                out = self.ext.dispatch_run(str(run_id), "ext.click_selector", args={"sel": sel}, await_result=True, timeout_ms=10000, exec_id=exec_id)
                if not out or not out.get("ok"):
                    # Suggest patch: wait/scroll
                    try:
                        self._suggest_patch("wait_quiet_insert", {"reason": "ext.click_selector not ok", "op": op, "sel": sel})
                    except Exception:
                        pass
                    # Hot patch retry once if enabled
                    if self._hot_patch_enabled():
                        tried = False
                        try:
                            self._hot_patch_use()
                            # wait quiet then retry
                            _ = self.ext.dispatch_run(str(run_id), "ext.wait_quiet", args={"timeout_ms": 3000}, await_result=True, timeout_ms=5000, exec_id=str(uuid.uuid4()))
                            out2 = self.ext.dispatch_run(str(run_id), "ext.click_selector", args={"sel": sel}, await_result=True, timeout_ms=8000, exec_id=str(uuid.uuid4()))
                            tried = True
                            if out2 and out2.get("ok"):
                                return
                        except Exception:
                            pass
                        try:
                            # small scroll then retry
                            self._hot_patch_use()
                            _ = self.ext.dispatch_run(str(run_id), "ext.scroll", args={"dir": "down", "amount": 300}, await_result=True, timeout_ms=4000, exec_id=str(uuid.uuid4()))
                            out3 = self.ext.dispatch_run(str(run_id), "ext.click_selector", args={"sel": sel}, await_result=True, timeout_ms=8000, exec_id=str(uuid.uuid4()))
                            if out3 and out3.get("ok"):
                                return
                        except Exception:
                            pass
                    if not _click_fallback_from_target():
                        raise RuntimeError(f"instr.click failed: {out}")
            else:
                if not _click_fallback_from_target():
                    try:
                        self._suggest_patch("scroll_then_retry", {"reason": "no selector/bbox", "op": op})
                    except Exception:
                        pass
                    raise RuntimeError("instr.click: no selector and no bbox fallback")
            return

        if op == "instr.type_text":
            text = act.get("text", "")
            replace = bool(act.get("clear", False))
            if sel and run_id and getattr(self, "ext", None):
                out = self.ext.dispatch_run(str(run_id), "ext.type_text", args={"sel": sel, "text": text, "replace": replace}, await_result=True, timeout_ms=12000, exec_id=exec_id)
                if not out or not out.get("ok"):
                    try:
                        self._suggest_patch("wait_quiet_insert", {"reason": "ext.type_text not ok", "sel": sel})
                    except Exception:
                        pass
                    if self._hot_patch_enabled():
                        try:
                            self._hot_patch_use()
                            _ = self.ext.dispatch_run(str(run_id), "ext.wait_quiet", args={"timeout_ms": 3000}, await_result=True, timeout_ms=5000, exec_id=str(uuid.uuid4()))
                            out2 = self.ext.dispatch_run(str(run_id), "ext.type_text", args={"sel": sel, "text": text, "replace": True}, await_result=True, timeout_ms=8000, exec_id=str(uuid.uuid4()))
                            if out2 and out2.get("ok"):
                                return
                        except Exception:
                            pass
                    raise RuntimeError(f"instr.type_text failed: {out}")
                return
            # Fallback: focus then type via OS
            if _click_fallback_from_target():
                self.exec.type_text(text, mode="type")
                return
            raise RuntimeError("instr.type_text: target not resolvable")

        if op == "instr.select_option":
            value = act.get("value")
            if sel and run_id and getattr(self, "ext", None):
                out = self.ext.dispatch_run(str(run_id), "ext.select_option", args={"sel": sel, "value": value}, await_result=True, timeout_ms=10000, exec_id=exec_id)
                if not out or not out.get("ok"):
                    raise RuntimeError(f"instr.select_option failed: {out}")
                return
            try:
                self._suggest_patch("selector_role_text", {"reason": "select_option needs DOM", "hint": "ensure <select>"})
            except Exception:
                pass
            raise RuntimeError("instr.select_option requires DOM selector (no fallback)")

        if op == "instr.scroll":
            dirv = (act.get("dir") or "down").lower()
            amount = int(act.get("amount", 600))
            amt = -abs(amount) if dirv == "down" else abs(amount)
            if sel and run_id and getattr(self, "ext", None):
                _ = self.ext.dispatch_run(str(run_id), "ext.scroll", args={"dir": ("down" if amt < 0 else "up"), "amount": abs(amt), "sel": sel}, await_result=True, timeout_ms=8000, exec_id=exec_id)
                return
            # window scroll fallback
            self.act_scroll(clicks=amt)
            return

        if op == "instr.navigate":
            url = act.get("url") or ""
            if run_id and getattr(self, "ext", None):
                _ = self.ext.dispatch_run(str(run_id), "ext.open_url", args={"url": url, "active": True}, await_result=True, timeout_ms=12000, exec_id=exec_id)
                # hot patch: wait quiet after navigate
                if self._hot_patch_enabled():
                    try:
                        self._hot_patch_use()
                        _ = self.ext.dispatch_run(str(run_id), "ext.wait_quiet", args={"timeout_ms": 4000}, await_result=True, timeout_ms=6000, exec_id=str(uuid.uuid4()))
                    except Exception:
                        pass
                return
            self.act_open_url(url)
            try:
                self._suggest_patch("wait_quiet_insert", {"reason": "after navigate", "hint": "WaitQuiet"})
            except Exception:
                pass
            return

        if op == "instr.history":
            op2 = (act.get("op") or "back").lower()
            if run_id and getattr(self, "ext", None):
                _ = self.ext.dispatch_run(str(run_id), "ext.history", args={"op": op2}, await_result=True, timeout_ms=8000, exec_id=exec_id)
                return
            if op2 == "back":
                self.act_go_back()
            return

        if op == "instr.hover":
            if sel and run_id and getattr(self, "ext", None):
                _ = self.ext.dispatch_run(str(run_id), "ext.hover", args={"sel": sel}, await_result=True, timeout_ms=8000, exec_id=exec_id)
                return
            # coords hover: move only
            if bbox:
                try:
                    x = int(bbox.get("x", 0) + bbox.get("w", 0) / 2)
                    y = int(bbox.get("y", 0) + bbox.get("h", 0) / 2)
                    self.exec.move_to(x, y, duration=0.2)
                    return
                except Exception:
                    pass
            raise RuntimeError("instr.hover: target not resolvable")

        if op == "instr.key":
            key = act.get("key")
            if key == "WaitQuiet":
                # map to ext.wait_quiet if possible
                if run_id and getattr(self, "ext", None):
                    _ = self.ext.dispatch_run(str(run_id), "ext.wait_quiet", args={}, await_result=True, timeout_ms=10000, exec_id=exec_id)
                    return
                time.sleep(self.cfg.poll_interval_s)
                return
            if run_id and getattr(self, "ext", None):
                _ = self.ext.dispatch_run(str(run_id), "ext.key", args={"key": key}, await_result=True, timeout_ms=6000, exec_id=exec_id)
                return
            # Fallback: limited keys unsupported here; ignore
            return

        if op == "instr.upload":
            if not sel:
                raise RuntimeError("instr.upload requires DOM selector for file input")
            file_path = act.get("file")
            if run_id and getattr(self, "ext", None):
                out = self.ext.dispatch_run(str(run_id), "ext.upload_file", args={"sel": sel, "file": file_path}, await_result=True, timeout_ms=15000, exec_id=exec_id)
                if not out or not out.get("ok"):
                    raise RuntimeError(f"instr.upload failed: {out}")
                return
            try:
                self._suggest_patch("timeout_increase_small", {"reason": "upload requires ext", "hint": "enable orchestrator"})
            except Exception:
                pass
            raise RuntimeError("instr.upload: no orchestrator ext available")

        if op == "instr.wait":
            ms = int(act.get("ms", 400))
            self.act_sleep_ms(ms)
            return

        if op == "instr.read":
            # Basic: try ext.extract; store into ctx['last_read']
            fields = act.get("fields") or []
            data = None
            if run_id and getattr(self, "ext", None):
                out = self.ext.dispatch_run(str(run_id), "ext.extract", args={"want": "default", "limit": 280}, await_result=True, timeout_ms=8000, exec_id=str(uuid.uuid4()))
                if isinstance(out, dict) and out.get("ok"):
                    data = out.get("data") or out
            self.ctx["last_read"] = data
            return

        if op == "instr.task_complete":
            try:
                self.reporter.log_step(StepLog(name="task_complete", status="success", message=str(act.get("message") or ""), exec_id=self.ctx.get("exec_id")))
            except Exception:
                pass
            self.ctx["task_completed"] = True
            return

        if op == "instr.answer_user":
            txt = act.get("text") or ""
            self.ctx["final_answer"] = txt
            try:
                self.reporter.log_step(StepLog(name="answer_user", status="success", message=f"len={len(txt)}", exec_id=self.ctx.get("exec_id")))
            except Exception:
                pass
            return

        # Unknown instr.*: ignore gracefully
        return

    def _suggest_patch(self, kind: str, payload: Dict[str, Any]) -> None:
        """Record a patch proposal to logs when autofix is enabled or default."""
        mode = None
        try:
            mode = (self.workflow or {}).get("autofix", {}).get("mode")
        except Exception:
            mode = None
        # In suggest_only (default) or auto_promote/hot_patch, we always log suggestions
        try:
            # enrich with current state/index if known
            st = None
            idx = None
            try:
                st = str(self.ctx.get("cur_state_name")) if self.ctx.get("cur_state_name") else None
            except Exception:
                st = None
            try:
                idx = int(self.ctx.get("cur_action_idx")) if self.ctx.get("cur_action_idx") is not None else None
            except Exception:
                idx = None
            if st is not None:
                payload = dict(payload)
                payload.setdefault("state", st)
            if idx is not None:
                payload = dict(payload)
                payload.setdefault("index", idx)
            path = os.path.join(self.reporter.logs_dir, "patch_proposals.jsonl")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            rec = {"kind": kind, "payload": payload, "ts": int(time.time() * 1000), "mode": mode or "suggest_only"}
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _hot_patch_enabled(self) -> bool:
        """Whether we should attempt an immediate one-off recovery patch within the same run."""
        try:
            mode = (self.workflow or {}).get("autofix", {}).get("mode")
            return str(mode) in ("hot_patch_session", "auto_promote_on_success") and self._hot_patch_left() > 0
        except Exception:
            return False

    def _hot_patch_left(self) -> int:
        try:
            lim = (self.workflow or {}).get("autofix", {}).get("limits", {}).get("max_patches_per_run", 2)
            used = int(self.ctx.get("hot_patch_used") or 0)
            return int(lim) - used
        except Exception:
            return 0

    def _hot_patch_use(self) -> None:
        try:
            self.ctx["hot_patch_used"] = int(self.ctx.get("hot_patch_used") or 0) + 1
        except Exception:
            self.ctx["hot_patch_used"] = 1

    def run_actions(self, actions: List[Dict[str, Any]]) -> None:
        for _i, act in enumerate(actions):
            try:
                self.ctx["cur_action_idx"] = int(_i)
            except Exception:
                pass
            # 记录步骤开始
            run_id = getattr(self, '_current_run_id', None)
            if run_id:
                self.event_recorder.record_event(run_id, EventType.STEP_START, {
                    "action": act.get("do"),
                    "args": act.get("args", {}),
                    "description": act.get("description", "")
                })
            # Flatten nested args for compatibility with {"do": ..., "args": {...}} schemas
            if isinstance(act, dict) and isinstance(act.get("args"), dict):
                flat = dict(act)
                flat.update(act.get("args") or {})
                act = flat
            op = act.get("do")
            if not op:
                continue
            # semantic instruction path
            if isinstance(op, str) and op.startswith("instr."):
                self._run_instr(act)
                continue
            # Run-scoped extension actions (explicit ext.* in workflow)
            if isinstance(op, str) and op.startswith("ext."):
                run_id = None
                try:
                    if isinstance(self.ctx_run, dict):
                        run_id = self.ctx_run.get("run_id")
                except Exception:
                    run_id = None
                if not (run_id and getattr(self, "ext", None)):
                    raise RuntimeError("ext.* action requested but run_id/ext client not available")
                # Build args from act minus 'do' and common meta keys
                args = {k: v for k, v in act.items() if k not in ("do", "description")}
                # Normalize keys for known actions
                if op == "ext.key" and "key" not in args and "text" in args:
                    args["key"] = str(args.get("text"))
                timeout_ms = int(args.pop("timeout_ms", 10000)) if isinstance(args.get("timeout_ms"), int) else 10000
                exec_id = str(uuid.uuid4())
                # Map ext.open_url -> 'open_url' action for the extension
                action_name = 'open_url' if op == 'ext.open_url' else op
                out = None
                try:
                    out = self.ext.dispatch_run(str(run_id), action_name, args=args, await_result=True, timeout_ms=timeout_ms, exec_id=exec_id)
                except Exception as e:
                    out = { 'ok': False, 'error': str(e) }
                # Bootstrap fallback: if open_url via extension failed due to not_bound/CS not ready and it's the first step, launch via OS
                if op == 'ext.open_url' and (not out or not out.get('ok', False)):
                    err_msg = str((out or {}).get('error') or '').lower()
                    # broaden matching for missing binding/tab cases
                    if ('not_bound' in err_msg) or ('cs_not_ready' in err_msg) or ('no_tab' in err_msg) or ('no tab' in err_msg) or ('cannot' in err_msg):
                        try:
                            url_bo = args.get('url') or ''
                            app_bo = args.get('app') or 'Google Chrome'
                            # Launch via OS to ensure Chrome is running and tab visible
                            self.act_open_url(url_bo, app=app_bo)
                            time.sleep(2.0)
                            # Try run-scoped quiet wait if possible
                            try:
                                self.ext.wait_quiet_run(str(run_id), timeout_ms=min(8000, timeout_ms))
                            except Exception:
                                pass
                            out = { 'ok': True, 'result': { 'bootstrap': True } }
                        except Exception:
                            pass
                # Rebind and retry on binding-related failures
                def _is_not_bound(o: dict) -> bool:
                    try:
                        msg = (o.get('result') or {}).get('error') or o.get('error') or ''
                        s = str(msg).lower()
                        return any(k in s for k in ['not_bound','no tab','no_tab','receiving end does not exist','cs_not_ready','no receiver'])
                    except Exception:
                        return False
                if (not out or not out.get("ok", False)) and _is_not_bound(out or {}):
                    try:
                        from urllib.parse import urlparse
                        dom_host = None
                        try:
                            # derive domain from url arg if present
                            u = str(args.get('url') or '')
                            if u:
                                dom_host = urlparse(u).hostname
                        except Exception:
                            dom_host = None
                        r = self.ext.rebind_run(str(run_id), policy='active_or_new', domain=dom_host, start_url=args.get('url'))
                        try:
                            self.reporter.log_step(StepLog(name='ext_rebind', status='info', message=f"{r}", exec_id=exec_id))
                        except Exception:
                            pass
                        if r and r.get('ok'):
                            # Retry original action once with same exec_id (idempotent)
                            out = self.ext.dispatch_run(str(run_id), action_name, args=args, await_result=True, timeout_ms=timeout_ms, exec_id=exec_id)
                    except Exception:
                        pass

                # Fallback: if element not found, try DomBrain selector pick
                def _element_not_found(o: dict) -> bool:
                    try:
                        msg = (o.get('result') or {}).get('error') or o.get('error') or ''
                        return isinstance(msg, str) and 'Element not found' in msg
                    except Exception:
                        return False
                if (not out or not out.get("ok", False)) and _element_not_found(out or {}):
                    # Verbose diagnostics for DOM LLM fallback path
                    try:
                        step_n_dbg = int(self.ctx.get("step_n", 0) or 0)
                    except Exception:
                        step_n_dbg = 0
                    try:
                        # Persist the original failure that triggered fallback
                        import json as _j, os as _os
                        trig_path = _os.path.join(self.reporter.logs_dir, f"dom_fallback_trigger_step_{step_n_dbg}.json")
                        with open(trig_path, "w", encoding="utf-8") as f:
                            _j.dump({"ext_action": op, "args": args, "result": out}, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                    try:
                        # Extract DOM and let LLM choose a selector based on goal
                        goal_text = str(act.get('goal') or '').strip() or 'focus search input'
                        ex = self.ext.dispatch_run(str(run_id), 'ext.extract', args={'want':'universal','limit':200}, await_result=True, timeout_ms=8000, exec_id=str(uuid.uuid4()))
                        # Save raw extract output for diagnostics
                        try:
                            import json as _j, os as _os
                            ex_path = _os.path.join(self.reporter.logs_dir, f"dom_extract_step_{step_n_dbg}.json")
                            with open(ex_path, "w", encoding="utf-8") as f:
                                _j.dump(ex, f, ensure_ascii=False, indent=2)
                        except Exception:
                            pass
                        dom = None
                        if ex and ex.get('ok'):
                            dom = ex.get('dom') or (ex.get('result') or {}).get('dom')
                        # Log extract outcome
                        try:
                            n_items = len((dom or {}).get('items', []) if isinstance(dom, dict) else [])
                            self.reporter.log_step(StepLog(name='dom_fallback', status='info', message=f'ext.extract ok; items={n_items}', exec_id=self.ctx.get('exec_id')))
                        except Exception:
                            pass
                        if isinstance(dom, dict):
                            sel_pick = pick_selector_from_dom(goal_text, dom, provider=os.getenv('LLM_PROVIDER'), model=os.getenv('LLM_MODEL'))
                            # Persist LLM pick result (without full prompt)
                            try:
                                import json as _j, os as _os
                                pick_path = _os.path.join(self.reporter.logs_dir, f"dom_llm_pick_step_{step_n_dbg}.json")
                                with open(pick_path, "w", encoding="utf-8") as f:
                                    _j.dump({"goal": goal_text, "pick": sel_pick}, f, ensure_ascii=False, indent=2)
                            except Exception:
                                pass
                            sel = sel_pick.get('sel') if isinstance(sel_pick, dict) else None
                            if sel:
                                if op == 'ext.click_selector':
                                    out2 = self.ext.dispatch_run(str(run_id), op, args={'sel': sel}, await_result=True, timeout_ms=timeout_ms, exec_id=str(uuid.uuid4()))
                                    if out2 and out2.get('ok'):
                                        self.ctx['last_sel'] = sel
                                        try:
                                            self.reporter.log_step(StepLog(name='dom_exec', status='success', message=f'llm_sel {sel}', exec_id=self.ctx.get('exec_id')))
                                        except Exception:
                                            pass
                                        out = out2
                                    else:
                                        # Click via DOM pick failed; persist for diagnostics
                                        try:
                                            import json as _j, os as _os
                                            errp = _os.path.join(self.reporter.logs_dir, f"dom_click_err_step_{step_n_dbg}.json")
                                            with open(errp, "w", encoding="utf-8") as f:
                                                _j.dump({"sel": sel, "result": out2}, f, ensure_ascii=False, indent=2)
                                        except Exception:
                                            pass
                                elif op == 'ext.type_text':
                                    text = str(args.get('text') or '')
                                    out2 = self.ext.dispatch_run(str(run_id), op, args={'sel': sel, 'text': text, 'replace': True}, await_result=True, timeout_ms=timeout_ms, exec_id=str(uuid.uuid4()))
                                    if out2 and out2.get('ok'):
                                        self.ctx['last_sel'] = sel
                                        try:
                                            self.reporter.log_step(StepLog(name='dom_exec', status='success', message=f'llm_sel {sel}', exec_id=self.ctx.get('exec_id')))
                                        except Exception:
                                            pass
                                        out = out2
                                    else:
                                        try:
                                            import json as _j, os as _os
                                            errp = _os.path.join(self.reporter.logs_dir, f"dom_type_err_step_{step_n_dbg}.json")
                                            with open(errp, "w", encoding="utf-8") as f:
                                                _j.dump({"sel": sel, "text": text, "result": out2}, f, ensure_ascii=False, indent=2)
                                        except Exception:
                                            pass
                            # If no selector produced by LLM, try heuristic selectors based on goal
                            try:
                                g = (goal_text or '').lower()
                                heur_sels: List[str] = []
                                if any(k in g for k in ['搜索', 'search', '输入框', 'input']):
                                    heur_sels = [
                                        "[role=search] input",
                                        "input[type=search]",
                                        "input[placeholder*=\\u641c\\u7d22 i]"
                                    ]
                                elif any(k in g for k in ['first post', '第一', '首贴', 'open first']):
                                    heur_sels = [
                                        "a[href*=/explore/]:not([rel=nofollow])"
                                    ]
                                if heur_sels:
                                    for hs in heur_sels:
                                        if op == 'ext.click_selector':
                                            h_out = self.ext.dispatch_run(str(run_id), 'ext.click_selector', args={'sel': hs}, await_result=True, timeout_ms=timeout_ms, exec_id=str(uuid.uuid4()))
                                            try:
                                                import json as _j, os as _os
                                                hlog = _os.path.join(self.reporter.logs_dir, f"dom_heuristic_try_step_{step_n_dbg}.json")
                                                with open(hlog, 'w', encoding='utf-8') as f:
                                                    _j.dump({"sel": hs, "result": h_out}, f, ensure_ascii=False, indent=2)
                                            except Exception:
                                                pass
                                            if h_out and h_out.get('ok'):
                                                self.ctx['last_sel'] = hs
                                                try:
                                                    self.reporter.log_step(StepLog(name='dom_exec', status='success', message=f'heuristic_sel {hs}', exec_id=self.ctx.get('exec_id')))
                                                except Exception:
                                                    pass
                                                out = h_out
                                                break
                                        elif op == 'ext.type_text':
                                            text = str(args.get('text') or '')
                                            h_out = self.ext.dispatch_run(str(run_id), 'ext.type_text', args={'sel': hs, 'text': text, 'replace': True}, await_result=True, timeout_ms=timeout_ms, exec_id=str(uuid.uuid4()))
                                            try:
                                                import json as _j, os as _os
                                                hlog = _os.path.join(self.reporter.logs_dir, f"dom_heuristic_try_step_{step_n_dbg}.json")
                                                with open(hlog, 'w', encoding='utf-8') as f:
                                                    _j.dump({"sel": hs, "text": text, "result": h_out}, f, ensure_ascii=False, indent=2)
                                            except Exception:
                                                pass
                                            if h_out and h_out.get('ok'):
                                                self.ctx['last_sel'] = hs
                                                try:
                                                    self.reporter.log_step(StepLog(name='dom_exec', status='success', message=f'heuristic_sel {hs}', exec_id=self.ctx.get('exec_id')))
                                                except Exception:
                                                    pass
                                                out = h_out
                                                break
                            except Exception:
                                pass
                        else:
                            # ext.extract did not return usable DOM
                            try:
                                self.reporter.log_step(StepLog(name='dom_fallback', status='fail', message='ext.extract returned no DOM', exec_id=self.ctx.get('exec_id')))
                            except Exception:
                                pass
                    except Exception as _fb_exc:
                        # Persist unexpected fallback exception
                        try:
                            import traceback, os as _os, json as _j
                            errp = _os.path.join(self.reporter.logs_dir, f"dom_fallback_err_step_{step_n_dbg}.json")
                            with open(errp, "w", encoding="utf-8") as f:
                                _j.dump({"error": str(_fb_exc), "trace": traceback.format_exc()}, f, ensure_ascii=False, indent=2)
                        except Exception:
                            pass
                if not out or not out.get("ok", False):
                    raise RuntimeError(f"ext action failed: {op} -> {out}")
                # Log success for traceability
                try:
                    self.reporter.log_step(StepLog(name=f"ext_action", status="success", message=f"{op} ok", exec_id=exec_id))
                except Exception:
                    pass
                continue
            if op == "open_url":
                self.act_open_url(act.get("url", ""), app=act.get("app"))
            elif op == "sleep_ms":
                self.act_sleep_ms(int(act.get("value", 500)))
            elif op == "screenshot":
                self.act_screenshot(save_as=act.get("save_as"))
            elif op == "wait_for":
                ok = self.act_wait_for(act.get("until", {}))
                if not ok:
                    raise RuntimeError("wait_for timeout or condition unmet")
            elif op == "detect":
                # run detection; optionally request server overlay and save payload/assets
                want_overlay = bool(act.get("return_image", False))
                pil: Image.Image = self.ctx.get("last_pil")
                if pil is None:
                    self.act_screenshot()
                    pil = self.ctx["last_pil"]
                resp = self.yolo.infer(pil, return_image=want_overlay, imgsz=self.cfg.imgsz)
                dets = self.yolo.to_detections(resp)
                self.ctx["detections"] = dets
                self.ctx["last_api_resp"] = resp

                # Save JSON payload if requested
                save_json = act.get("save_json")
                if save_json:
                    out_path = save_json
                    if not os.path.isabs(out_path):
                        out_path = os.path.join(self.reporter.logs_dir, save_json)
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump(resp, f, ensure_ascii=False, indent=2)

                # Always save base screenshot with step index for comparison
                try:
                    cur_step = int(self.ctx.get("step_n", 0))
                    self.reporter.save_image(self.ctx["last_bgr"], f"step_{cur_step}.png")
                except Exception:
                    pass

                # Save server overlay if requested
                save_server = act.get("save_server_image") or act.get("save_server_image_as")
                if want_overlay and resp.get("image_base64"):
                    data_url = resp["image_base64"]
                    b64 = data_url.split(",", 1)[1] if "," in data_url else data_url
                    img_bytes = base64.b64decode(b64)
                    # default naming aligned with autostep overlay
                    default_name = f"overlay_step_{int(self.ctx.get('step_n', 0))}.png"
                    out_name = save_server or default_name
                    out_path = out_name
                    if not os.path.isabs(out_path):
                        out_path = os.path.join(self.reporter.screens_dir, out_name)
                    with open(out_path, "wb") as f:
                        f.write(img_bytes)

                # Save local overlay if requested
                save_overlay = act.get("save_overlay")
                if save_overlay:
                    bgr = self.ctx["last_bgr"]
                    boxes = [d.bbox_xyxy for d in dets]
                    labels = [f"{d.class_name} {d.conf:.2f}" for d in dets]
                    over = self.reporter.draw_detections(bgr, boxes, labels, None)
                    out_path = save_overlay
                    if not os.path.isabs(out_path):
                        out_path = os.path.join(self.reporter.screens_dir, save_overlay)
                    cv2.imwrite(out_path, over)
            elif op == "locate":
                targets = act.get("targets") or act.get("candidates") or []
                self.act_locate(targets)
            elif op == "click":
                # Support multi-click (double-click/triple-click) and button selection
                button = act.get("button", "left")
                times = int(act.get("times") or act.get("clicks") or 1)
                interval_ms = int(act.get("interval_ms", 120))
                self.act_click(button=button, times=times, interval_ms=interval_ms)
            elif op == "type_text":
                self.exec.type_text(act.get("text", ""), mode=act.get("mode") or act.get("input_mode"))
            elif op == "scroll":
                self.act_scroll(int(act.get("clicks", -400)))
            elif op == "go_back":
                self.act_go_back()
            elif op == "os.activate_app":
                # Cross-platform bring app window to front
                name = act.get("name") or act.get("app") or "WeChat"
                ok = False
                try:
                    if platform.system() == "Darwin":
                        subprocess.run(["osascript", "-e", f'tell application "{name}" to activate'], check=True)
                        ok = True
                    elif platform.system() == "Windows":
                        ps = rf'''
                        $ErrorActionPreference = 'SilentlyContinue'
                        $p = Get-Process -Name "{name}" | Select-Object -First 1
                        if ($p -and $p.MainWindowHandle -ne 0) {{
                          $sig = '[DllImport("user32.dll")]public static extern bool SetForegroundWindow(IntPtr hWnd);'
                          Add-Type -MemberDefinition $sig -Name WinAPI -Namespace Win32 | Out-Null
                          [Win32.WinAPI]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
                          Write-Output 'OK'
                        }} else {{
                          Write-Output 'NOHWND'
                        }}
                        '''
                        out = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps], stderr=subprocess.DEVNULL, timeout=5)
                        s = (out or b"").decode("utf-8", errors="ignore").strip()
                        ok = s.startswith("OK")
                except Exception:
                    ok = False
                # expose result for transitions
                try:
                    sv = act.get("save")
                    if isinstance(sv, str) and sv:
                        self.ctx[sv] = bool(ok)
                except Exception:
                    pass
                if not ok:
                    # soft mode: don't crash the state, continue to next action
                    if bool(act.get("soft")):
                        try:
                            self.reporter.log_step(StepLog(name="os.activate_app", status="info", message=f"soft_fail {name}", exec_id=self.ctx.get("exec_id")))
                        except Exception:
                            pass
                    else:
                        raise RuntimeError(f"os.activate_app failed for {name}")
            elif op == "os.launch_app":
                name = act.get("name") or "WeChat"
                path = act.get("path")
                ok = False
                try:
                    if platform.system() == "Darwin":
                        if path:
                            subprocess.run(["open", path], check=True)
                        else:
                            subprocess.run(["open", "-a", name], check=True)
                        ok = True
                    elif platform.system() == "Windows":
                        if path:
                            cmd = ["powershell", "-NoProfile", "-Command", f"Start-Process -FilePath '{path}'"]
                        else:
                            cmd = ["powershell", "-NoProfile", "-Command", f"Start-Process '{name}'"]
                        subprocess.run(cmd, check=True)
                        ok = True
                except Exception:
                    ok = False
                # expose result for transitions
                try:
                    sv = act.get("save")
                    if isinstance(sv, str) and sv:
                        self.ctx[sv] = bool(ok)
                except Exception:
                    pass
                if not ok:
                    if bool(act.get("soft")):
                        try:
                            self.reporter.log_step(StepLog(name="os.launch_app", status="info", message=f"soft_fail {name} {path or ''}", exec_id=self.ctx.get("exec_id")))
                        except Exception:
                            pass
                    else:
                        raise RuntimeError(f"os.launch_app failed for {name} {path or ''}")

            # ========= Enhanced Mouse Operations =========
            elif op == "mouse.down":
                button = self._button_norm(act.get("button"))
                has_exec, _p = self._mouse_cap()
                if has_exec:
                    self.exec.mouse_down(button=button)
                else:
                    if not _p:
                        raise RuntimeError("mouse_down requires pyautogui")
                    _p.mouseDown(button=button)

            elif op == "mouse.up":
                button = self._button_norm(act.get("button"))
                has_exec, _p = self._mouse_cap()
                if has_exec:
                    self.exec.mouse_up(button=button)
                else:
                    if not _p:
                        raise RuntimeError("mouse_up requires pyautogui")
                    _p.mouseUp(button=button)

            elif op == "mouse.move":
                duration = int(act.get("duration_ms", 0))
                to = act.get("to")
                by = act.get("by")
                has_exec, _p = self._mouse_cap()
                if to:
                    x, y = int(to[0]), int(to[1])
                    if has_exec:
                        self.exec.move_to(x, y, duration=duration/1000.0 if duration>0 else 0.0)
                    else:
                        if not _p:
                            raise RuntimeError("mouse_move requires pyautogui")
                        _p.moveTo(x, y, duration=duration/1000.0 if duration>0 else 0.0)
                elif by:
                    dx, dy = int(by[0]), int(by[1])
                    if has_exec:
                        self.exec.move_by(dx, dy, duration=duration/1000.0 if duration>0 else 0.0)
                    else:
                        if not _p:
                            raise RuntimeError("mouse_move requires pyautogui")
                        _p.moveRel(dx, dy, duration=duration/1000.0 if duration>0 else 0.0)
                else:
                    raise RuntimeError("mouse.move needs 'to' or 'by'")

            elif op == "mouse.drag":
                button = self._button_norm(act.get("button"))
                duration = int(act.get("duration_ms", 120))
                to = act.get("to")
                by = act.get("by")
                has_exec, _p = self._mouse_cap()
                if to:
                    x, y = int(to[0]), int(to[1])
                    if has_exec:
                        self.exec.drag_to(x, y, duration=duration/1000.0, button=button)
                    else:
                        if not _p:
                            raise RuntimeError("mouse.drag requires pyautogui")
                        _p.dragTo(x, y, duration=duration/1000.0, button=button)
                elif by:
                    dx, dy = int(by[0]), int(by[1])
                    if has_exec:
                        self.exec.drag_by(dx, dy, duration=duration/1000.0, button=button)
                    else:
                        if not _p:
                            raise RuntimeError("mouse.drag requires pyautogui")
                        _p.dragRel(dx, dy, duration=duration/1000.0, button=button)
                else:
                    raise RuntimeError("mouse.drag needs 'to' or 'by'")

            elif op == "wheel":
                # Compatible with existing scroll; priority delta_y, unit pixels; else use clicks
                if "delta_y" in act:
                    dy = int(act.get("delta_y", 0))
                    if hasattr(self.exec, "scroll"):
                        self.exec.scroll(dy)
                else:
                    clicks = int(act.get("clicks", -400))
                    self.act_scroll(clicks)

            # ========= Enhanced Keyboard Operations =========
            elif op == "keyboard.key":
                key = act.get("key")
                if hasattr(self.exec, "key"):
                    self.exec.key(key)

            elif op == "keyboard.key_down":
                key = act.get("key")
                if hasattr(self.exec, "key_down"):
                    self.exec.key_down(key)

            elif op == "keyboard.key_up":
                key = act.get("key")
                if hasattr(self.exec, "key_up"):
                    self.exec.key_up(key)

            elif op == "keyboard.sequence":
                seq = act.get("keys") or []  # e.g., ["ctrl","shift","p"] or ["enter","tab","tab"]
                interval_ms = int(act.get("interval_ms", 50))
                for k in seq:
                    if hasattr(self.exec, "key"):
                        self.exec.key(k)
                    time.sleep(max(0, interval_ms)/1000.0)

            elif op == "keyboard.select_all":
                if platform.system() == "Darwin":
                    self.exec.key_combo("command", "a")
                else:
                    self.exec.key_combo("ctrl", "a")

            elif op == "keyboard.copy":
                if platform.system() == "Darwin":
                    self.exec.key_combo("command", "c")
                else:
                    self.exec.key_combo("ctrl", "c")

            elif op == "keyboard.cut":
                if platform.system() == "Darwin":
                    self.exec.key_combo("command", "x")
                else:
                    self.exec.key_combo("ctrl", "x")

            elif op == "keyboard.paste":
                if platform.system() == "Darwin":
                    self.exec.key_combo("command", "v")
                else:
                    self.exec.key_combo("ctrl", "v")

            elif op == "keyboard.toggle_ime":
                # Default mac: Ctrl+Space; Windows: Shift+Alt (can be overridden via vars)
                kseq = _wf_var(self, "toggle_ime_keys")
                if not kseq:
                    kseq = ["ctrl","space"] if platform.system() == "Darwin" else ["shift","alt"]
                if hasattr(self.exec, "key_combo"):
                    self.exec.key_combo(*kseq)

            # ========= Clipboard Operations =========
            elif op == "clipboard.push":
                try:
                    cur = self.exec.clipboard_get() if hasattr(self.exec, "clipboard_get") else ""
                except Exception:
                    cur = ""
                self._clip_stack.append(cur)

            elif op == "clipboard.pop":
                prev = self._clip_stack.pop() if self._clip_stack else ""
                try:
                    if hasattr(self.exec, "clipboard_set"):
                        self.exec.clipboard_set(prev)
                except Exception:
                    pass

            elif op == "clipboard.clear":
                try:
                    if hasattr(self.exec, "clipboard_clear"):
                        self.exec.clipboard_clear()
                except Exception:
                    pass

            elif op == "clipboard.copy_from_selection":
                pre_clear = bool(act.get("pre_clear", True))
                trim = bool(act.get("trim", True))
                max_len = int(act.get("max_len", 0))  # 0=unlimited
                regex = act.get("regex")
                save = act.get("save", "copied_text")
                restore_on_fail = bool(act.get("restore_on_fail", True))

                prev = ""
                if restore_on_fail:
                    try:
                        prev = self.exec.clipboard_get() if hasattr(self.exec, "clipboard_get") else ""
                    except:
                        prev = ""
                if pre_clear:
                    try:
                        if hasattr(self.exec, "clipboard_clear"):
                            self.exec.clipboard_clear()
                    except:
                        pass

                # Combo key copy
                if platform.system() == "Darwin":
                    self.exec.key_combo("command", "c")
                else:
                    self.exec.key_combo("ctrl", "c")
                time.sleep(max(0, int(act.get("wait_ms", 80)))/1000.0)

                val = self.exec.clipboard_get() if hasattr(self.exec, "clipboard_get") else ""
                if trim:
                    val = (val or "").strip()
                if regex:
                    import re
                    m = re.search(regex, val or "")
                    val = m.group(1) if (m and m.groups()) else (m.group(0) if m else "")
                if max_len and len(val) > max_len:
                    val = val[:max_len]

                if not val and restore_on_fail:
                    try:
                        if hasattr(self.exec, "clipboard_set"):
                            self.exec.clipboard_set(prev)
                    except:
                        pass
                self.ctx[save] = val

            # ========= Basic File/System Operations =========
            elif op == "os.shell":
                cmd = act.get("cmd")
                shell = bool(act.get("shell", True))
                timeout = int(act.get("timeout_s", 20))
                save = act.get("save", "shell")
                import subprocess, shlex
                if isinstance(cmd, str) and not shell:
                    cmd = shlex.split(cmd)
                try:
                    p = subprocess.run(cmd, capture_output=True, text=True, shell=shell, timeout=timeout)
                    self.ctx[save] = {"code": p.returncode, "out": p.stdout, "err": p.stderr}
                except Exception as e:
                    self.ctx[save] = {"code": -1, "out": "", "err": str(e)}

            elif op == "os.mkdir":
                path = act.get("path")
                if path:
                    os.makedirs(path, exist_ok=True)

            elif op == "os.remove":
                path = act.get("path")
                if path and os.path.exists(path):
                    os.remove(path)

            elif op == "os.copy":
                src = act.get("src")
                dst = act.get("dst")
                if src and dst:
                    import shutil
                    shutil.copy2(src, dst)

            elif op == "os.move":
                src = act.get("src")
                dst = act.get("dst")
                if src and dst:
                    import shutil
                    shutil.move(src, dst)

            elif op == "os.listdir":
                path = act.get("path", ".")
                save = act.get("save", "file_list")
                pattern = act.get("pattern")
                try:
                    files = os.listdir(path)
                    if pattern:
                        import fnmatch
                        files = [f for f in files if fnmatch.fnmatch(f, pattern)]
                    self.ctx[save] = files
                except Exception:
                    self.ctx[save] = []

            elif op == "os.read_text_file":
                path = act.get("path")
                save = act.get("save", "file_content")
                encoding = act.get("encoding", "utf-8")
                try:
                    with open(path, "r", encoding=encoding) as f:
                        self.ctx[save] = f.read()
                except Exception:
                    self.ctx[save] = ""

            elif op == "os.write_text_file":
                path = act.get("path")
                content = act.get("content", "")
                encoding = act.get("encoding", "utf-8")
                mkdirs = bool(act.get("mkdirs", False))
                if path:
                    if mkdirs:
                        os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w", encoding=encoding) as f:
                        f.write(str(content))

            elif op == "os.read_json":
                path = act.get("path")
                save = act.get("save", "json_data")
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        self.ctx[save] = json.load(f)
                except Exception:
                    self.ctx[save] = {}

            elif op == "os.write_json":
                path = act.get("path")
                data = act.get("data", {})
                mkdirs = bool(act.get("mkdirs", False))
                if path:
                    if mkdirs:
                        os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)

            elif op == "decide_with_gemini":
                # Minimal analysis: send only the goal text + overlay image (no heavy payload)
                from .prompt_builder import build_analysis_messages_min
                img_path = act.get("image")
                if img_path and not os.path.isabs(img_path):
                    img_path = os.path.join(self.reporter.screens_dir, img_path)
                if not img_path:
                    # wait a little for page to settle before using the latest overlay
                    try:
                        time.sleep(float(self.cfg.screenshot_wait_s))
                    except Exception:
                        pass
                    img_path = self.ctx.get("last_overlay_path")
                    if not img_path:
                        # Ensure we have some screenshot if no overlay
                        self.act_screenshot()
                        img_path = os.path.join(self.reporter.screens_dir, f"step_{int(self.ctx.get('step_n',0))}.png")

                # Support both goal and intent fields
                goal_text = act.get("goal") or act.get("intent") or ""
                # Build minimal context for decision to reduce hallucination
                ctx_context = {}
                try:
                    if self.ctx.get("last_click"):
                        lc = self.ctx.get("last_click") or {}
                        ctx_context["last_click"] = {"id": lc.get("id"), "why": lc.get("why")}
                except Exception:
                    pass
                try:
                    if act.get("expect_page"):
                        ctx_context["expect_page"] = act.get("expect_page")
                except Exception:
                    pass
                try:
                    # include a short history summary if available
                    hist = self.memory.summarize(self.ctx.get("last_sig_key") or "")
                    if hist:
                        ctx_context["history"] = hist[:220]
                except Exception:
                    pass
                messages = build_analysis_messages_min(goal_text, context=ctx_context if ctx_context else None)
                payload = None
                prov = act.get("llm_provider") or os.getenv("LLM_PROVIDER")
                model = act.get("llm_model") or os.getenv("LLM_MODEL")
                # Always save request content (minimal)
                try:
                    ts = int(time.time() * 1000)
                    safe_prov = (prov or "").replace("/", "-")
                    safe_model = (model or "").replace("/", "-")
                    prefix = f"{safe_prov}_{safe_model}".strip("_") or "llm"
                    req_path = os.path.join(self.reporter.logs_dir, f"{prefix}_decide_req_{ts}.json")
                    with open(req_path, "w", encoding="utf-8") as f:
                        json.dump({"provider": prov, "model": model, "image": img_path, "messages": messages}, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                resp = call_llm(provider=prov, model=model, messages=messages, image_path=img_path)
                text = extract_text_generic(resp)
                try:
                    resp_path = os.path.join(self.reporter.logs_dir, f"{prefix}_decide_resp_{ts}.json")
                    with open(resp_path, "w", encoding="utf-8") as f:
                        json.dump({"raw": resp, "extracted_text": text}, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                parsed = parse_first_json(text) or {}

                # save result
                save_name = act.get("save", "gemini_result.json")
                out_path = save_name
                if not os.path.isabs(out_path):
                    out_path = os.path.join(self.reporter.logs_dir, save_name)
                with open(out_path, "w", encoding="utf-8") as f:
                    req = {"payload": payload} if payload is not None else {}
                    json.dump({"request": req, "raw_text": text, "parsed": parsed}, f, ensure_ascii=False, indent=2)

                # Map decision click_id -> chosen detection (kept for compatibility if goal expects a click id)
                click_id = (parsed.get("decision", {}) or {}).get("click_id") or parsed.get("click_id")
                chosen_det = None
                if isinstance(click_id, str):
                    try:
                        did = int(click_id[1:]) if click_id.startswith("c") else int(click_id)
                        for d in (yj.get("detections", []) or []):
                            if int(d.get("id", -1)) == did:
                                chosen_det = SimpleNamespace(
                                    id=did,
                                    class_name=str(d.get("class_name", "")),
                                    conf=float(d.get("conf", 0.0)),
                                    bbox_xyxy=[float(x) for x in d.get("bbox_xyxy", [0, 0, 0, 0])],
                                )
                                break
                    except Exception:
                        pass
                if chosen_det is not None:
                    # create a compatible selection
                    cands = []
                    for d in ((self.ctx.get("last_api_resp") or {}).get("detections", []) or []):
                        cands.append(
                            SimpleNamespace(
                                id=int(d.get("id", 0)),
                                class_name=str(d.get("class_name", "")),
                                conf=float(d.get("conf", 0.0)),
                                bbox_xyxy=[float(x) for x in d.get("bbox_xyxy", [0, 0, 0, 0])],
                            )
                        )
                    self.ctx["chosen"] = SimpleNamespace(chosen=chosen_det, candidates=cands, score=float(getattr(chosen_det, "conf", 0.0)))
                else:
                    # No decision; leave chosen unset; caller may handle NEED_INPUT/ABSTAIN
                    self.ctx["chosen"] = None
            elif op == "autostep":
                self._autostep(act)

    # ------ runner ------
    def run(self, start_state: str) -> None:
        print(f"DEBUG: Workflow run started with start_state: {start_state}")

        # 开始运行记录
        workflow_id = self.workflow.get("task", "unknown_workflow")
        run_id = self.event_recorder.start_run(workflow_id)
        self._current_run_id = run_id  # 保存当前运行ID以供子方法使用

        # Attempt to register run with orchestrator to obtain run_id and optional auto-binding
        try:
            import urllib.request as _u, json as _j, time as _t
            orch = os.getenv("EXT_ORCH_BASE") or "http://127.0.0.1:8788"
            # extract a preferred start_url from first state actions (prefer ext.open_url non-about:blank)
            start_url = None
            try:
                st = self.workflow.get("states", {}).get(start_state) or {}
                cand = []
                for a in st.get("actions", []) or []:
                    if not isinstance(a, dict):
                        continue
                    do = a.get("do"); url_a = a.get("url")
                    if do in ("open_url", "ext.open_url") and url_a:
                        cand.append((do, url_a))
                # Prefer ext.open_url with non about:blank, else any non about:blank, else first
                for do, u in cand:
                    if do == "ext.open_url" and str(u).strip().lower() != "about:blank":
                        start_url = u; break
                if start_url is None:
                    for do, u in cand:
                        if str(u).strip().lower() != "about:blank":
                            start_url = u; break
                if start_url is None and cand:
                    start_url = cand[0][1]
            except Exception:
                start_url = None
            body = {
                "workflow": {"name": self.workflow.get("name") or "wf", "start": start_state, "states": self.workflow.get("states", {})},
                "bind": {"strategy": "match_or_open", "domain": None, "prefer_active": True, "timeout_ms": 8000},
                "start_url": start_url
            }
            url = orch.rstrip("/") + "/runs/start"
            for attempt in range(3):
                try:
                    req = _u.Request(url, method="POST")
                    req.add_header("Content-Type", "application/json")
                    with _u.urlopen(req, data=_j.dumps(body).encode("utf-8"), timeout=6.0) as r:
                        txt = r.read().decode("utf-8", errors="ignore")
                    resp = _j.loads(txt)
                    # Persist response for diagnostics
                    try:
                        import os as _os
                        with open(_os.path.join(self.reporter.logs_dir, "run_start_resp.json"), "w", encoding="utf-8") as f:
                            f.write(txt)
                    except Exception:
                        pass
                    if isinstance(resp, dict) and resp.get("run_id"):
                        self.ctx_run["run_id"] = resp.get("run_id")
                        try:
                            from . import timeline as _tln
                            _tln.event("run_id", f"{self.ctx_run['run_id']}")
                        except Exception:
                            pass
                        break
                except Exception as ie:
                    if attempt == 2:
                        print(f"[run] /runs/start failed: {ie}")
                    _t.sleep(0.6)
        except Exception as e:
            print(f"[run] orchestrator /runs/start skipped or failed: {e}")
        states = self.workflow.get("states", {})
        cur = start_state
        visited = set()
        max_steps = int(os.getenv("WF_MAX_STEPS", "50"))
        steps_done = 0
        try:
            self.exec.move_to(1, 1, duration=0.12)
        except Exception:
            pass
        self.ctx["run_started_ts"] = int(time.time() * 1000)
        all_ok = True
        while cur and steps_done < max_steps:
            print(f"DEBUG: Entering state: {cur}, steps_done: {steps_done}")
            if (not str(cur).startswith("pg_")) and (cur in visited):
                raise RuntimeError(f"workflow loop detected at state '{cur}'")
            visited.add(cur)
            steps_done += 1
            node = states.get(cur)
            if not node:
                node = {"actions": [{"do": "autostep", "picker": "vision"}], "on_success": "autonext"}
                self.workflow.setdefault("states", {})[cur] = node

            name = cur
            msg = ""
            status = "info"
            before_after = {}
            chosen = None
            conf = None

            try:
                if node.get("actions"):
                    print(f"DEBUG: Running actions for state: {cur}")
                    try:
                        self.ctx["cur_state_name"] = str(cur)
                    except Exception:
                        pass
                    self.run_actions(node.get("actions"))
                    status = "success"
                    msg = "actions executed"
                else:
                    # 1) screenshot + detect
                    self.act_screenshot()
                    self.act_detect()

                    # 2) locate targets
                    targets = node.get("candidates") or []
                    if targets:
                        self.act_locate(targets)
                        chosen = self.ctx["chosen"].chosen if self.ctx.get("chosen") else None
                    before_after = self._draw_overlay(f"{cur}")

                    # 3) click if found
                    if chosen is None:
                        # optional: on_error policy
                        on_error = node.get("on_error")
                        if on_error == "scroll_and_retry":
                            self.act_scroll(-400)
                            self.act_screenshot()
                            self.act_detect()
                            self.act_locate(targets)
                            chosen = self.ctx["chosen"].chosen if self.ctx.get("chosen") else None
                            before_after = self._draw_overlay(f"{cur}_retry")
                    if chosen is None:
                        status = "fail"
                        seen = [d.class_name for d in (self.ctx.get("detections") or [])]
                        top = ",".join(sorted(set(seen))[:8])
                        msg = f"no candidate among {targets}; seen: [{top}]"
                    else:
                        conf = float(chosen.conf)
                        self.act_click()
                        # 4) wait_for next signature
                        verify = node.get("verify_next") or {}
                        ok = True
                        if verify:
                            if "any_of" in verify:
                                ok = self.act_wait_for({"type": "yolo_appear", "any_of": verify.get("any_of"), "timeout_ms": int(self.cfg.wait_timeout_s * 1000)})
                            else:
                                ok = self.act_wait_for(verify)
                        status = "success" if ok else "fail"
                        msg = "clicked and verified" if ok else "clicked but verify timeout"

            except Exception as e:  # pragma: no cover
                status = "fail"
                msg = f"exception: {e}"
                print(f"DEBUG: Exception caught in state {cur}: {e}")

            self.act_screenshot()
            after = self.reporter.save_image(self.ctx["last_bgr"], f"{cur}_after.png")

            self.reporter.log_step(
                StepLog(
                    name=name,
                    status=status,
                    message=msg,
                    conf=conf,
                    chosen_cls=(chosen.class_name if chosen else None),
                    before_img=before_after.get("before"),
                    overlay_img=before_after.get("overlay"),
                    after_img=after,
                    click_xy=None,
                )
            )
            print(f"DEBUG: State {cur} finished with status: {status}")

            if status != "success":
                # If state defines on_error, jump there; otherwise stop
                err_next = node.get("on_error") if isinstance(node, dict) else None
                if isinstance(err_next, str) and err_next:
                    print(f"DEBUG: Status not success; jumping to on_error: {err_next}")
                    cur = err_next
                    continue
                print(f"DEBUG: Status is not success, breaking loop.")
                all_ok = False
                break

            # Transitions (conditional) take precedence if present
            nxt = None
            trans = node.get("transitions") if isinstance(node, dict) else None
            if isinstance(trans, list) and trans:
                matched = False
                else_target = None
                for tr in trans:
                    if not isinstance(tr, dict):
                        continue
                    if "if" in tr and "go_to" in tr:
                        cond = str(tr.get("if"))
                        if self._eval_condition(cond):
                            nxt = tr.get("go_to")
                            matched = True
                            break
                    elif "go_to" in tr and "if" not in tr:
                        # unconditional go_to (less common)
                        nxt = tr.get("go_to")
                        matched = True
                        break
                    if "else_go_to" in tr:
                        else_target = tr.get("else_go_to")
                if not matched and else_target:
                    nxt = else_target
            # Fallback to legacy next/on_success
            if nxt is None:
                nxt = node.get("on_success") if ("on_success" in node) else node.get("next")
            print(f"DEBUG: Next state candidate (nxt): {nxt}")
            if nxt == "autonext" and self.ctx.get("next_state_id"):
                cur_next = self.ctx.get("next_state_id")
                print(f"DEBUG: autonext detected, cur_next: {cur_next}")
                if cur_next == cur and not str(cur).startswith("pg_"):
                    print(f"DEBUG: No progress on named state, stopping gracefully.")
                    cur = None
                else:
                    cur = cur_next
            else:
                cur = nxt
            print(f"DEBUG: 'cur' updated to: {cur}")

        print(f"DEBUG: Exiting main loop. Final 'cur': {cur}, steps_done: {steps_done}")
        self.reporter.flush_jsonl()
        report = self.reporter.write_html()
        print(f"Workflow report: {report}")
        try:
            self._maybe_auto_promote(all_ok)
        except Exception as _ap_err:
            print(f"[autofix] auto-promote skipped: {_ap_err}")

    def _maybe_auto_promote(self, run_ok: bool) -> None:
        """Apply simple, safe patches automatically when configured.

        Rules:
          - Only when workflow.autofix.mode == 'auto_promote_on_success'
          - Only consider proposals from this run window (ts >= run_started_ts)
          - Allowed kinds: wait_quiet_insert, scroll_then_retry
          - Save a patched copy to flows/<name>.autofix.json (and out/logs/patched_*.json)
        """
        mode = (self.workflow or {}).get("autofix", {}).get("mode")
        if str(mode) != "auto_promote_on_success":
            return
        if not run_ok:
            return
        logs_dir = self.reporter.logs_dir
        prop_path = os.path.join(logs_dir, "patch_proposals.jsonl")
        if not os.path.exists(prop_path):
            return
        try:
            run_ts = int(self.ctx.get("run_started_ts") or 0)
        except Exception:
            run_ts = 0
        proposals = []
        try:
            with open(prop_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                        if not isinstance(rec, dict):
                            continue
                        if int(rec.get("ts", 0)) >= run_ts:
                            proposals.append(rec)
                    except Exception:
                        continue
        except Exception:
            return
        if not proposals:
            return
        allowed = {"wait_quiet_insert", "scroll_then_retry"}
        wf = json.loads(json.dumps(self.workflow))  # deep copy
        states = wf.setdefault("states", {})
        changed = False
        for rec in proposals:
            kind = rec.get("kind")
            if kind not in allowed:
                continue
            payload = rec.get("payload") or {}
            st = payload.get("state")
            idx = payload.get("index")
            if not (isinstance(st, str) and st in states):
                continue
            acts = states[st].get("actions") or []
            if not isinstance(acts, list):
                continue
            insert_at = None
            val = None
            if kind == "wait_quiet_insert":
                insert_at = (idx + 1) if isinstance(idx, int) else len(acts)
                val = {"do": "instr.key", "key": "WaitQuiet"}
            elif kind == "scroll_then_retry":
                insert_at = idx if isinstance(idx, int) else 0
                val = {"do": "instr.scroll", "dir": "down", "amount": 300}
            if val is not None:
                try:
                    acts.insert(max(0, min(len(acts), insert_at)), val)
                    states[st]["actions"] = acts
                    changed = True
                except Exception:
                    pass
        if not changed:
            return
        ts = int(time.time() * 1000)
        patched1 = os.path.join(self.reporter.logs_dir, f"patched_workflow_{ts}.json")
        with open(patched1, "w", encoding="utf-8") as f:
            json.dump(wf, f, ensure_ascii=False, indent=2)
        try:
            name = (wf.get("name") or "workflow").replace("/", "-")
            flows_dir = os.path.join(os.getcwd(), "flows")
            os.makedirs(flows_dir, exist_ok=True)
            out2 = os.path.join(flows_dir, f"{name}.autofix.json")
            with open(out2, "w", encoding="utf-8") as f2:
                json.dump(wf, f2, ensure_ascii=False, indent=2)
            print(f"[autofix] auto-promoted patched workflow -> {out2}")
        except Exception as e:
            print(f"[autofix] patched saved to logs only: {e}")

    # ------ autostep ------
    def _autostep(self, cfg: Dict[str, Any]) -> None:
        # M3: Begin step cost tracking
        step_n = self.ctx.get("step_n", 1)
        self.cost_guard.begin_step()
        # Generate exec_id for this autostep (MVP idempotence)
        try:
            self.ctx["exec_id"] = str(uuid.uuid4())
        except Exception:
            self.ctx["exec_id"] = f"exec_{int(time.time()*1000)}"
        
        # Emit step begin event
        from .report_events import emit_step_begin
        # Support both goal and intent fields (intent as fallback)
        goal_text = cfg.get("goal") or cfg.get("intent") or ""
        
        # Perceive (reuse prior detect if available in this state)
        if not bool(self.ctx.get("vision_ready")):
            self.act_screenshot()
            self.act_detect()
        bgr = self.ctx["last_bgr"]
        dets = self.ctx["detections"]
        yj = self.ctx.get("last_api_resp", {})

        # Signature & state resolve
        sig = self._signature(bgr, dets)
        sig_key = json.dumps(sig, sort_keys=True)
        # Maintain a simple signature stack for modals (heuristic via OCR tokens)
        try:
            stack = self.ctx.setdefault("sig_stack", [])
            det = detect_modal(bgr)
            has_modal = bool(det.get("matched"))
            if has_modal:
                if (not stack) or self._sig_sim(stack[-1], sig) < 0.9:
                    stack.append(sig)
                    try:
                        msg = f"modal push; score={det.get('score',0)} closable={det.get('closable',False)}"
                        if det.get('closable'):
                            msg += f" close_tpl={det.get('close_name','')}:{det.get('close_score','')}"
                        msg += f" depth={len(stack)}"
                        self.reporter.log_step(StepLog(name=f"autostep_{step_n}_modal", status="info", message=msg))
                    except Exception:
                        pass
            else:
                if stack and self._sig_sim(stack[0], sig) >= 0.85:
                    stack.clear()
                    try:
                        self.reporter.log_step(StepLog(name=f"autostep_{step_n}_modal", status="info", message="modal stack cleared"))
                    except Exception:
                        pass
        except Exception:
            pass
        # Track repeats to detect stuck
        if self.ctx.get("last_sig_key") == sig_key:
            self.ctx["sig_repeat_count"] = int(self.ctx.get("sig_repeat_count", 0)) + 1
        else:
            self.ctx["sig_repeat_count"] = 1
            self.ctx["last_sig_key"] = sig_key
        cur_id = self._resolve_or_create_state(sig)

        # Save artifacts
        step_n = int(self.ctx.get("step_n", 1))
        save = cfg.get("save", {})
        # Always save base screenshot as step_{n}.png for debugging
        try:
            self.reporter.save_image(bgr, f"step_{step_n}.png")
        except Exception:
            pass
        if save:
            if save.get("shot"):
                name = save["shot"].format(n=step_n)
                self.reporter.save_image(bgr, name)
            if save.get("yolo"):
                name = save["yolo"].format(n=step_n)
                path = os.path.join(self.reporter.logs_dir, name)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(yj, f, ensure_ascii=False, indent=2)

        # Optionally generate and persist server-annotated overlay
        overlay_name = cfg.get("overlay") or f"overlay_step_{step_n}.png"
        if overlay_name:
            try:
                pil = self.ctx["last_pil"]
                resp_overlay = self.yolo.infer(pil, return_image=True, imgsz=self.cfg.imgsz)
                data_url = resp_overlay.get("image_base64")
                if data_url:
                    import base64
                    b64 = data_url.split(",", 1)[1] if "," in data_url else data_url
                    img_bytes = base64.b64decode(b64)
                    out_path = overlay_name
                    if not os.path.isabs(out_path):
                        out_path = os.path.join(self.reporter.screens_dir, overlay_name)
                    with open(out_path, "wb") as f:
                        f.write(img_bytes)
                    try:
                        # Store absolute path to avoid double-joining with screens_dir later
                        self.ctx["last_overlay_path"] = os.path.abspath(out_path)
                    except Exception:
                        self.ctx["last_overlay_path"] = out_path
            except Exception:
                pass

        # Persist YOLO JSON for debugging (always)
        try:
            yolo_dbg = os.path.join(self.reporter.logs_dir, f"yolo_step_{step_n}.json")
            with open(yolo_dbg, "w", encoding="utf-8") as f:
                json.dump(yj, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        # Persist global goal (first time) so autonext/pg_* can reuse it
        if "global_goal" not in self.ctx:
            gg = cfg.get("goal") or cfg.get("intent")
            if gg:
                self.ctx["global_goal"] = str(gg)

        # DOM executor fast-path (use extension for DOM-first actions)
        try:
            use_dom = bool(cfg.get("executor") == "dom" or os.getenv("WF_AUTOSTEP_EXECUTOR", "").lower() == "dom")
        except Exception:
            use_dom = False
        if use_dom and getattr(self, "ext", None):
            goal_text_dom = str(cfg.get("goal") or cfg.get("intent") or self.ctx.get("global_goal") or "").lower()
            try:
                run_id = self.ctx_run.get("run_id") if isinstance(self.ctx_run, dict) else None
                def _wait_quiet(ms: int = 8000) -> bool:
                    try:
                        if run_id:
                            out = self.ext.dispatch_run(run_id, "ext.wait_quiet", {"timeout_ms": ms}, await_result=True, timeout_ms=ms+2000, exec_id=self.ctx.get("exec_id"))
                        else:
                            out = self.ext.action_legacy("ext.wait_quiet", {"timeout_ms": ms}, await_result=True, timeout_ms=ms+2000, exec_id=self.ctx.get("exec_id"))
                        return bool(out.get("ok"))
                    except Exception:
                        return False

                def _click(sel: str) -> bool:
                    if run_id:
                        out = self.ext.dispatch_run(run_id, "ext.click_selector", {"sel": sel}, await_result=True, timeout_ms=8000, exec_id=self.ctx.get("exec_id"))
                    else:
                        out = self.ext.action_legacy("ext.click_selector", {"sel": sel}, await_result=True, timeout_ms=8000, exec_id=self.ctx.get("exec_id"))
                    return bool(out.get("ok"))

                acted = False
                # Heuristic: focus search input
                if any(k in goal_text_dom for k in ["搜索", "search", "输入框", "input"]):
                    sels = [
                        "input[placeholder*=\\u641c\\u7d22 i]",
                        "input[type=search]",
                        "[role=search] input"
                    ]
                    for s in sels:
                        if _click(s):
                            acted = True
                            break
                    if acted:
                        _wait_quiet(3000)
                        try:
                            self.reporter.log_step(StepLog(name=f"autostep_{step_n}", status="success", message="dom_exec: focused_search", exec_id=self.ctx.get("exec_id")))
                        except Exception:
                            pass
                        self.ctx["next_state_id"] = self._resolve_or_create_state(self._signature(self.ctx["last_bgr"], self.ctx["detections"]))
                        self.ctx["step_n"] = step_n + 1
                        return
                # Heuristic: open first post
                if any(k in goal_text_dom for k in ["first post", "第一", "首贴", "点击首贴", "open first"]):
                    sel_post = "a[href*=/explore/]:not([rel=nofollow])"
                    if _click(sel_post):
                        _wait_quiet(8000)
                        try:
                            self.reporter.log_step(StepLog(name=f"autostep_{step_n}", status="success", message="dom_exec: open_first_post", exec_id=self.ctx.get("exec_id")))
                        except Exception:
                            pass
                        self.ctx["next_state_id"] = self._resolve_or_create_state(self._signature(self.ctx["last_bgr"], self.ctx["detections"]))
                        self.ctx["step_n"] = step_n + 1
                        return
                # LLM DOM picker fallback: use ext.extract + LLM to select a CSS selector
                try:
                    if run_id:
                        out_ex = self.ext.dispatch_run(run_id, 'ext.extract', args={ 'want': 'default', 'limit': 280 }, await_result=True, timeout_ms=8000, exec_id=str(uuid.uuid4()))
                        dom = None
                        if out_ex and out_ex.get('ok'):
                            # result may be at top-level or under result.dom depending on SW
                            dom = out_ex.get('dom') or (out_ex.get('result') or {}).get('dom')
                        if isinstance(dom, dict):
                            sel_pick = pick_selector_from_dom(goal_text_dom, dom, provider=os.getenv('LLM_PROVIDER'), model=os.getenv('LLM_MODEL'))
                            sel = sel_pick.get('sel') if isinstance(sel_pick, dict) else None
                            if sel and _click(sel):
                                _wait_quiet(8000)
                                try:
                                    self.reporter.log_step(StepLog(name=f"autostep_{step_n}", status="success", message=f"dom_exec: llm_sel {sel}", exec_id=self.ctx.get("exec_id")))
                                except Exception:
                                    pass
                                self.ctx["next_state_id"] = self._resolve_or_create_state(self._signature(self.ctx["last_bgr"], self.ctx["detections"]))
                                self.ctx["step_n"] = step_n + 1
                                return
                except Exception:
                    pass
            except Exception:
                pass

        # If stuck or looping, call planner to get micro-goals
        try:
            repeats = int(self.ctx.get("sig_repeat_count", 1))
            deny_len = len(self.ctx.get("denylist", {}).get(sig_key, [])) if self.ctx.get("denylist") else 0
            tm_miss = int(self.ctx.get("template_miss", 0))
            # Count need_input in recent memory (last 5)
            need_recent = 0
            for rec in reversed(self.memory._cache.get(sig_key, []))[:5]:  # type: ignore[attr-defined]
                if rec.get("outcome") == "need_input":
                    need_recent += 1
            trig_repeat = repeats >= int(os.getenv("WF_PLANNER_REPEATS", "3"))
            trig_need = need_recent >= int(os.getenv("WF_PLANNER_NEED_INPUT", "2"))
            trig_deny = deny_len >= int(os.getenv("WF_PLANNER_DENY_THRESH", "3"))
            planner_cap = int(os.getenv("WF_MAX_PLANNER_CALLS", "2"))
            trig_tpl = tm_miss >= 2
            if (trig_repeat or trig_need or trig_deny or trig_tpl) and int(self.ctx.get("planner_calls", 0)) < planner_cap:
                goal_text = str(cfg.get("goal") or cfg.get("intent") or self.ctx.get("global_goal") or "continue task")
                recent = f"repeats={repeats}, need_input={need_recent}, deny={deny_len}"
                sig_hint = f"phash={sig.get('phash','')}"
                messages = build_planner_messages(goal_text, recent, sig_hint)
                prov = cfg.get("llm_provider") or os.getenv("LLM_PROVIDER") or "gemini"
                model = cfg.get("llm_model") or os.getenv("LLM_MODEL") or "gemini-1.5-flash"
                prefix = f"{(prov or '').replace('/', '-')}_{(model or '').replace('/', '-')}".strip('_') or 'llm'
                try:
                    reqp = os.path.join(self.reporter.logs_dir, f"{prefix}_planner_req_step_{step_n}.json")
                    with open(reqp, "w", encoding="utf-8") as f:
                        json.dump({"provider": prov, "model": model, "messages": messages}, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                try:
                    resp = call_llm(provider=prov, model=model, messages=messages, image_path=None)
                    text_pl = extract_text_generic(resp)
                    try:
                        respp = os.path.join(self.reporter.logs_dir, f"{prefix}_planner_resp_step_{step_n}.json")
                        with open(respp, "w", encoding="utf-8") as f:
                            json.dump({"raw": resp, "extracted_text": text_pl}, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                    plan = parse_first_json(text_pl) or {}
                    items = plan.get("plan") if isinstance(plan, dict) else None
                    if isinstance(items, list) and items:
                        self.ctx["plan_queue"] = items
                        self.ctx["planner_calls"] = int(self.ctx.get("planner_calls", 0)) + 1
                except Exception:
                    pass
        except Exception:
            pass

        # Decide click target: support minimal vision-first picker (default) or legacy id-only
        # Prepare ids for mapping and sanity checks
        ids = [f"c{int(d.id)}" for d in dets] if dets else []
        use_vision_picker = bool(cfg.get("picker") == "vision")
        if use_vision_picker:
            # Replay via anchors if we have a stable route for this signature/goal
            k = int(cfg.get("k", 12))
            # If planner provided a micro goal, use it
            plan_item = None
            if self.ctx.get("plan_queue"):
                try:
                    plan_item = (self.ctx.get("plan_queue") or []).pop(0)
                except Exception:
                    plan_item = None
            goal_text = str((plan_item or {}).get("goal") or cfg.get("goal") or cfg.get("intent") or self.ctx.get("global_goal") or "continue task")

            # Attempt anchor-based replay (no LLM)
            try:
                route = self.routes.lookup(sig_key, goal_text)
            except Exception:
                route = None
            if route:
                try:
                    # New: try compound anchors first (row+action+relation)
                    row_a = route.get("row_anchor")
                    act_a = route.get("action_anchor")
                    rel = route.get("relation") or {}
                    used_compound = False
                    if row_a and act_a:
                        bbox2 = locate_instance(self.ctx["last_bgr"], row_a, act_a, rel)
                        if bbox2 is not None:
                            cap_h, cap_w = self.ctx["last_bgr"].shape[:2]
                            cap_meta = self._cap_meta()
                            pre = PreprocMeta(frame_w=cap_w, frame_h=cap_h, imgsz=cap_w, letterbox=False, normalized=False)
                            x1, y1, x2, y2 = bbox2
                            sx, sy = map_id_to_screen_point([x1, y1, x2, y2], None, pre, cap_meta)
                            # Pre-hover probe (optional)
                            try:
                                hover_ms = int(os.getenv("PRE_HOVER_MS", "200"))
                                if hover_ms > 0:
                                    self.exec.move_to(sx, sy, duration=0.15)
                                    time.sleep(hover_ms / 1000.0)
                            except Exception:
                                pass
                            self.exec.click(sx, sy, dpr=cap_meta.dpr)
                            try:
                                # record last click for next step prompts
                                self.ctx["last_click"] = {"id": route.get("click_id"), "why": "replay_compound", "bbox": [x1, y1, x2, y2]}
                            except Exception:
                                pass
                            verify = cfg.get("verify", {"rules": ["page_change"], "timeout_ms": 8000, "poll_ms": 600})
                            # If we have state_anchors, use them for quick pass (and optional OCR text list)
                            ok = False
                            start = time.time()
                            while (time.time() - start) * 1000 < int(verify.get("timeout_ms", 8000)):
                                time.sleep(float(verify.get("poll_ms", 600)) / 1000.0)
                                self.act_screenshot(); self.act_detect()
                                try:
                                    ocr_got = self.ocr.read_texts(self.ctx.get("last_pil")) if self.ocr else []
                                    ocr_lines = self.ocr.read_lines(self.ctx.get("last_pil")) if self.ocr else []
                                except Exception:
                                    ocr_got = []
                                    ocr_lines = []
                                vote = 0.0
                                vote_tpl = vote_ocr = vote_url = 0.0
                                try:
                                    if route.get("state_anchors"):
                                        from .anchors import state_anchors_vote_detail
                                        det = state_anchors_vote_detail(
                                            self.ctx["last_bgr"],
                                            route.get("state_anchors") or {},
                                            ocr_texts=ocr_got,
                                            current_url=(self._get_url_hint() or None),
                                            expected_texts=(route.get("state_texts") or []),
                                            ocr_lines=ocr_lines,
                                        )
                                        vote = float(det.get("vote", 0.0))
                                        vote_tpl = float(det.get("tpl_ratio", 0.0))
                                        vote_ocr = float(det.get("ocr_ratio", 0.0))
                                        vote_url = float(det.get("url_match", 0.0))
                                except Exception:
                                    vote = 0.0
                                if vote >= float(os.getenv("STATE_ANCHOR_PASS_RATIO", "0.66")):
                                    try:
                                        self.reporter.log_step(StepLog(name=f"autostep_{step_n}_state_vote", status="info", message=f"state_vote={vote:.2f} (tpl={vote_tpl:.2f}, ocr={vote_ocr:.2f}, url={vote_url:.2f})"))
                                    except Exception:
                                        pass
                                    ok = True; break
                                # Fallback to signature change
                                if self._sig_sim(sig, self._signature(self.ctx["last_bgr"], self.ctx["detections"])) < 0.72:
                                    ok = True; break
                            if ok:
                                next_id = self._resolve_or_create_state(self._signature(self.ctx["last_bgr"], self.ctx["detections"]))
                                self._link_edge(cur_id, next_id, action={"replay": True, "bbox": [x1, y1, x2, y2]}, verify={"rules": verify.get("rules", [])})
                                # Adaptive: increment success and tighten thresholds a bit
                                try:
                                    sc_prev = int(route.get("success_count", 1))
                                    route2 = dict(route)
                                    route2["success_count"] = sc_prev + 1
                                    route2["ts"] = int(time.time() * 1000)
                                    # rolling EMA of success
                                    ema_prev = float(route.get("ema_success", 0.5))
                                    alpha = float(os.getenv("ROUTE_EMA_ALPHA", "0.2"))
                                    route2["ema_success"] = (1 - alpha) * ema_prev + alpha * 1.0
                                    route2["event"] = "success"
                                    # adjust anchors
                                    ra = route2.get("row_anchor"); aa = route2.get("action_anchor")
                                    if isinstance(aa, dict) and aa.get("type") == "template":
                                        route2["action_anchor"] = adjust_template_anchor(aa, True)
                                    if isinstance(aa, dict) and aa.get("type") == "orb":
                                        route2["action_anchor"] = adjust_orb_anchor(aa, True)
                                    if isinstance(ra, dict) and ra.get("type") == "template":
                                        route2["row_anchor"] = adjust_template_anchor(ra, True)
                                    route2["relation"] = adjust_relation(route2.get("relation") or {}, True)
                                    if route2.get("state_anchors"):
                                        route2["state_anchors"] = adjust_state_anchors(route2.get("state_anchors"), True)
                                    self.routes.append(route2)
                                    # windowed health check and optional replacement
                                    try:
                                        win = int(os.getenv("ROUTE_WIN_SIZE", "50"))
                                        thr = float(os.getenv("ROUTE_WIN_MIN", "0.6"))
                                        rate = self.routes.window_success_rate(sig_key, goal_text, window=win)
                                        if rate < thr:
                                            comp2 = auto_select_anchors(self.ctx["last_bgr"], [x1, y1, x2, y2])
                                            repl = dict(route2)
                                            repl.update({
                                                "row_anchor": comp2.get("row_anchor"),
                                                "action_anchor": comp2.get("action_anchor"),
                                                "relation": comp2.get("relation"),
                                                "replacement": True,
                                                "event": "success",
                                                "ts": int(time.time() * 1000),
                                            })
                                            self.routes.append(repl)
                                            try:
                                                self.reporter.log_step(StepLog(name=f"autostep_{step_n}_health", status="info", message=f"route health {rate:.2f} < {thr:.2f}; anchors replaced"))
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass
                                except Exception:
                                    pass
                                # Per-step log
                                try:
                                    msg = f"replay_compound ok; vote>={os.getenv('STATE_ANCHOR_PASS_RATIO','0.66')}"
                                    self.reporter.log_step(StepLog(name=f"autostep_{step_n}", status="success", message=msg, conf=None, chosen_cls=None, before_img=None, after_img=None, overlay_img=self.ctx.get("last_overlay_path")))
                                except Exception:
                                    pass
                                self._save_graph_workflow(start_id=cur_id)
                                self.ctx["next_state_id"] = next_id
                                self.ctx["step_n"] = step_n + 1
                                return
                            else:
                                try:
                                    # record a low state_vote hint for strategy gating
                                    self.ctx["state_vote_low"] = int(self.ctx.get("state_vote_low", 0)) + 1
                                except Exception:
                                    pass
                            used_compound = True
                # Legacy single anchor fallback
                    score_anchor = anchors_match(self.ctx["last_bgr"], route.get("anchors", {}))
                except Exception:
                    score_anchor = 0.0
                th_anchor = float(os.getenv("TH_ANCHOR", "0.82"))
                if score_anchor >= th_anchor:
                    # Click from stored bbox
                    try:
                        bbox = route.get("bbox", [])
                        cap_h, cap_w = self.ctx["last_bgr"].shape[:2]
                        cap_meta = self._cap_meta()
                        pre = PreprocMeta(frame_w=cap_w, frame_h=cap_h, imgsz=cap_w, letterbox=False, normalized=False)
                        x1, y1, x2, y2 = bbox
                        sx, sy = map_id_to_screen_point([x1, y1, x2, y2], None, pre, cap_meta)
                        self.exec.click(sx, sy, dpr=cap_meta.dpr)
                        try:
                            self.ctx["last_click"] = {"id": route.get("click_id"), "why": "replay_legacy", "bbox": bbox}
                        except Exception:
                            pass
                        # verify stored rules
                        verify = cfg.get("verify", {"rules": ["page_change"], "timeout_ms": 8000, "poll_ms": 600})
                        ver2 = route.get("verifier", [])
                        if ver2:
                            verify["rules"] = ver2
                        start = time.time()
                        ok = False
                        sig_prev = sig
                        while (time.time() - start) * 1000 < int(verify.get("timeout_ms", 8000)):
                            time.sleep(float(verify.get("poll_ms", 600)) / 1000.0)
                            self.act_screenshot(); self.act_detect()
                            sig2 = self._signature(self.ctx["last_bgr"], self.ctx["detections"])
                            if self._sig_sim(sig_prev, sig2) < 0.72:
                                ok = True; break
                        if ok:
                            # Route validated, skip to end of autostep
                            next_id = self._resolve_or_create_state(sig2)
                            self._link_edge(cur_id, next_id, action={"replay": True, "bbox": bbox}, verify={"rules": verify.get("rules", [])})
                            # Adaptive: increment success count and slightly tighten template threshold
                            try:
                                sc_prev = int(route.get("success_count", 1))
                                route2 = dict(route)
                                route2["success_count"] = sc_prev + 1
                                route2["ts"] = int(time.time() * 1000)
                                ema_prev = float(route.get("ema_success", 0.5))
                                alpha = float(os.getenv("ROUTE_EMA_ALPHA", "0.2"))
                                route2["ema_success"] = (1 - alpha) * ema_prev + alpha * 1.0
                                route2["event"] = "success"
                                if route2.get("anchors"):
                                    route2["anchors"] = adjust_template_anchor(route2.get("anchors"), True)
                                if route2.get("state_anchors"):
                                    route2["state_anchors"] = adjust_state_anchors(route2.get("state_anchors"), True)
                                self.routes.append(route2)
                                # windowed health check on legacy path
                                try:
                                    win = int(os.getenv("ROUTE_WIN_SIZE", "50"))
                                    thr = float(os.getenv("ROUTE_WIN_MIN", "0.6"))
                                    rate = self.routes.window_success_rate(sig_key, goal_text, window=win)
                                    if rate < thr:
                                        comp2 = auto_select_anchors(self.ctx["last_bgr"], bbox)
                                        repl = dict(route2)
                                        repl.update({
                                            "row_anchor": comp2.get("row_anchor"),
                                            "action_anchor": comp2.get("action_anchor"),
                                            "relation": comp2.get("relation"),
                                            "replacement": True,
                                            "event": "success",
                                            "ts": int(time.time() * 1000),
                                        })
                                        self.routes.append(repl)
                                        try:
                                            self.reporter.log_step(StepLog(name=f"autostep_{step_n}_health", status="info", message=f"route health {rate:.2f} < {thr:.2f}; anchors replaced"))
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                            except Exception:
                                pass
                            try:
                                self.reporter.log_step(StepLog(name=f"autostep_{step_n}", status="success", message="replay_legacy ok", overlay_img=self.ctx.get("last_overlay_path")))
                            except Exception:
                                pass
                            self._save_graph_workflow(start_id=cur_id)
                            self.ctx["next_state_id"] = next_id
                            self.ctx["step_n"] = step_n + 1
                            return
                    except Exception:
                        pass
                else:
                    # Adaptive: relax thresholds on route when both compound and legacy failed this round
                    try:
                        route2 = dict(route)
                        route2["fail_count"] = int(route2.get("fail_count", 0)) + 1
                        route2["ts"] = int(time.time() * 1000)
                        ema_prev = float(route.get("ema_success", 0.5))
                        alpha = float(os.getenv("ROUTE_EMA_ALPHA", "0.2"))
                        route2["ema_success"] = (1 - alpha) * ema_prev + alpha * 0.0
                        route2["event"] = "fail"
                        ra = route2.get("row_anchor"); aa = route2.get("action_anchor")
                        if isinstance(aa, dict) and aa.get("type") == "template":
                            route2["action_anchor"] = adjust_template_anchor(aa, False)
                        if isinstance(aa, dict) and aa.get("type") == "orb":
                            route2["action_anchor"] = adjust_orb_anchor(aa, False)
                        if isinstance(ra, dict) and ra.get("type") == "template":
                            route2["row_anchor"] = adjust_template_anchor(ra, False)
                        if route2.get("anchors"):
                            route2["anchors"] = adjust_template_anchor(route2.get("anchors"), False)
                        if route2.get("state_anchors"):
                            route2["state_anchors"] = adjust_state_anchors(route2.get("state_anchors"), False)
                        route2["relation"] = adjust_relation(route2.get("relation") or {}, False)
                        self.routes.append(route2)
                    except Exception:
                        pass
                    # flag for strategy trigger gates
                    try:
                        self.ctx["replay_failed"] = True
                    except Exception:
                        pass
                    # mark a template miss for planner trigger
                    try:
                        self.ctx["template_miss"] = int(self.ctx.get("template_miss", 0)) + 1
                        self.ctx["replay_failed_count"] = int(self.ctx.get("replay_failed_count", 0)) + 1
                    except Exception:
                        pass
            # Build a short history hint using page signature
            sig = self._signature(bgr, dets)
            import json as _json
            sig_key = _json.dumps(sig, sort_keys=True)
            try:
                history_hint = self.memory.summarize(sig_key)
            except Exception:
                history_hint = None

            # Denylist (session + persistent) and overlay masking
            deny_ids = set([f"c{int(d)}" for d in []])
            try:
                dl = self.ctx.get("denylist", {})
                for x in dl.get(sig_key, []):
                    deny_ids.add(x)
                for x in self.memory.get_blacklist(sig_key, k=5):
                    deny_ids.add(x)
            except Exception:
                pass

            # Build id->bbox mapping for masking
            id2bbox = {f"c{int(d.id)}": d.bbox_xyxy for d in dets}

            # Unified Picker (merged POP semantics into picker)
            try:
                hist = history_hint or ""
            except Exception:
                hist = ""
            try:
                verify_rules = []
                vr = cfg.get("verify")
                if isinstance(vr, dict):
                    verify_rules = vr.get("rules", []) or []
                elif isinstance(vr, list):
                    verify_rules = vr
            except Exception:
                verify_rules = []

            constraints_hint = ""
            try:
                hint_parts = []
                if cfg.get("hints"): hint_parts.append(",".join(cfg.get("hints") or []))
                if cfg.get("negative_classes"): hint_parts.append("avoid:" + ",".join(cfg.get("negative_classes") or []))
                constraints_hint = "; ".join(hint_parts) if hint_parts else ""
            except Exception:
                constraints_hint = ""

            pctx = PickerCtx(
                task=cfg.get("task_context", "") or goal_text,
                phase=cfg.get("phase", "general"),
                state=str(cur_id),
                goal=goal_text,
                plan_next=cfg.get("plan_next", ""),
                verify=verify_rules,
                constraints=constraints_hint,
                fallback=(cfg.get("fallback", {}) or {}).get("action", "scroll") if isinstance(cfg.get("fallback"), dict) else (cfg.get("fallback") or "scroll"),
                history_summary=str(hist)[:220],
            )
            messages = build_picker_messages_unified(pctx)
            base_overlay_path = self.ctx.get("last_overlay_path") or overlay_name
            if not os.path.isabs(base_overlay_path):
                base_overlay_path = os.path.join(self.reporter.screens_dir, str(base_overlay_path))
            # If denylist present, create a masked copy to downweight wrong targets visually
            img_path = base_overlay_path
            try:
                if deny_ids:
                    over = cv2.imread(base_overlay_path)
                    if over is not None:
                        for cid in deny_ids:
                            box = id2bbox.get(cid)
                            if box:
                                x1, y1, x2, y2 = map(int, box)
                                # semi-transparent gray mask
                                overlay = over.copy()
                                cv2.rectangle(overlay, (x1, y1), (x2, y2), (128, 128, 128), thickness=-1)
                                alpha = 0.5
                                over = cv2.addWeighted(overlay, alpha, over, 1 - alpha, 0)
                        masked_name = f"picker_overlay_step_{step_n}.png"
                        out_path = masked_name
                        if not os.path.isabs(out_path):
                            out_path = os.path.join(self.reporter.screens_dir, masked_name)
                        cv2.imwrite(out_path, over)
                        img_path = out_path
            except Exception:
                img_path = base_overlay_path
            if not os.path.isabs(img_path):
                img_path = os.path.join(self.reporter.screens_dir, str(img_path))
            prov = cfg.get("llm_provider") or os.getenv("LLM_PROVIDER") or "gemini"
            model = cfg.get("llm_model") or os.getenv("LLM_MODEL") or "gemini-1.5-flash"
            # If provider is NVIDIA and we need to send an image, fall back to a vision-capable provider
            eff_prov, eff_model = prov, model
            if eff_prov.strip().lower() in ("nvidia", "nim", "nvidia_openai"):
                # override to fallback for vision
                eff_prov = os.getenv("NV_VISION_FALLBACK_PROVIDER", os.getenv("LLM_VISION_PROVIDER", "gemini"))
                eff_model = os.getenv("NV_VISION_FALLBACK_MODEL", os.getenv("LLM_VISION_MODEL", "gemini-1.5-flash"))
            # Save LLM request (always)
            try:
                safe_prov = (eff_prov or "").replace("/", "-")
                safe_model = (eff_model or "").replace("/", "-")
                prefix = f"{safe_prov}_{safe_model}".strip("_") or "llm"
                # Include state id in filenames to avoid overwriting across states
                req_path = os.path.join(self.reporter.logs_dir, f"{prefix}_picker_req_{cur_id}_step_{step_n}.json")
                with open(req_path, "w", encoding="utf-8") as f:
                    json.dump({"provider": eff_prov, "model": eff_model, "image": img_path, "messages": messages}, f, ensure_ascii=False, indent=2)
                try:
                    from . import timeline as _t
                    _t.event("llm/picker_req", f"step={step_n} model={eff_prov}/{eff_model} image={img_path}")
                    # Log history fields passed to LLM for auditability
                    h = history_hint or ""
                    lc = self.ctx.get("last_click") or {}
                    lc_str = None
                    try:
                        lc_str = f"id={lc.get('id')}, why={lc.get('why')}"
                    except Exception:
                        lc_str = None
                    _t.event("llm/history", f"step={step_n} state={cur_id} last=({lc_str}) history={h}")
                except Exception:
                    pass
            except Exception:
                pass
            # M3: Use LLM router for cost-controlled picker calls
            parsed = {}
            fallback_result = {"need_input": True, "why": "budget_exceeded"}
            
            try:
                router_result = self.llm_router.maybe_call(
                    kind="picker",
                    messages=messages,
                    image_path=img_path,
                    provider=eff_prov,
                    model=eff_model,
                    fallback_result=fallback_result
                )
                
                if router_result:
                    parsed = router_result
                    # Emit picker decision event
                    from .report_events import emit_picker_decision
                    emit_picker_decision(
                        step_idx=step_n,
                        chosen_id=parsed.get("id", ""),
                        confidence=parsed.get("confidence", 0.0),
                        why=parsed.get("why", ""),
                        method="llm"
                    )
                else:
                    parsed = fallback_result
                
                # Keep existing logging for compatibility
                try:
                    resp_path = os.path.join(self.reporter.logs_dir, f"{prefix}_picker_resp_{cur_id}_step_{step_n}.json")
                    with open(resp_path, "w", encoding="utf-8") as f:
                        json.dump({"router_result": parsed}, f, ensure_ascii=False, indent=2)
                    try:
                        from . import timeline as _t
                        import re as _re
                        parsed_str = json.dumps(parsed)
                        mid = _re.search(r'"id"\s*:\s*"?([a-zA-Z0-9_]+)"?', parsed_str or "")
                        mconf = _re.search(r'"confidence"\s*:\s*([0-9.]+)', parsed_str or "")
                        parts = []
                        if mid: parts.append(f"id={mid.group(1)}")
                        if mconf: parts.append(f"conf={mconf.group(1)}")
                        _t.event("llm/picker_resp", f"step={step_n} {' '.join(parts) if parts else 'parsed'}")
                    except Exception:
                        pass
                except Exception:
                    pass
            except Exception as e:
                # Rate limits or network issues — mark need_input and continue with fallback
                try:
                    err_path = os.path.join(self.reporter.logs_dir, f"{prefix}_picker_err_{cur_id}_step_{step_n}.json")
                    with open(err_path, "w", encoding="utf-8") as f:
                        json.dump({"error": str(e)}, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                parsed = {"need_input": True, "why": "llm_error"}
                try:
                    from . import timeline as _t
                    _t.event("llm/picker_err", f"step={step_n} {str(e)[:80]}")
                except Exception:
                    pass
            # M2 Strategy Integration - Enhanced trigger logic and memory
            strategy_result = None
            try:
                if os.getenv("STRATEGY_LAYER", "0") == "1":
                    # Build workflow state for M2 trigger logic
                    workflow_state = {
                        "picker_consecutive_failures": int(self.ctx.get("picker_consecutive_failures", 0)),
                        "need_input_events": int(self.ctx.get("need_input_events", 0)),
                        "deny_hits": len(deny_ids),
                        "current_step": step_n,
                        "page_kind": "unknown"  # Will be determined by strategy_adapter
                    }
                    
                    # Try M2 strategy selection with enhanced logic
                    try:
                        from .strategy_adapter import create_strategy_context
                        from .strategy_exec import exec_strategy_with_fallback
                        
                        # Get OCR lines for strategy context
                        ocr_lines = []
                        try:
                            if self.ocr:
                                ocr_lines = self.ocr.read_lines(self.ctx.get("last_pil")) or []
                        except:
                            pass
                        
                        # Create strategy context
                        context = create_strategy_context(
                            dets, self.ctx["last_bgr"], ocr_lines, 
                            url_hint=sig.get("url", "")
                        )
                        workflow_state["page_kind"] = context.get("page_kind", "unknown")
                        
                        # Use enhanced strategy selector with M2 trigger logic
                        result = self.strategy.decide(
                            step_n, sig_key, goal_text, 
                            page_summary=context, 
                            workflow_state=workflow_state
                        )
                        
                        if result:
                            strategy_result = result
                            try:
                                from . import timeline as _t
                                _t.event("strategy/m2_selected", f"step={step_n} strategy={result.get('strategy_id')} source={result.get('source', 'llm')}")
                            except:
                                pass
                                
                            # If strategy came from memory or LLM, try to execute it
                            if result.get("strategy_id"):
                                try:
                                    from .types import StrategySpec
                                    spec = StrategySpec(
                                        strategy_id=result["strategy_id"],
                                        params=result.get("params", {}),
                                        confidence=result.get("confidence", 0.8),
                                        reasoning=result.get("why", "")
                                    )
                                    
                                    target_item = exec_strategy_with_fallback(
                                        spec, context["items"], context.get("landmarks", {})
                                    )
                                    
                                    if target_item:
                                        # Convert target_item back to detection format for workflow
                                        for d in dets:
                                            if str(d.id) == target_item.id:
                                                parsed = {
                                                    "id": f"c{int(d.id)}",
                                                    "confidence": result.get("confidence", 0.8),
                                                    "why": result.get("why", "strategy_selected")
                                                }
                                                try:
                                                    from . import timeline as _t
                                                    _t.event("strategy/m2_executed", f"step={step_n} target_id={parsed['id']} conf={parsed['confidence']}")
                                                except:
                                                    pass
                                                break
                                except Exception as e:
                                    print(f"[workflow] M2 strategy execution failed: {e}")
                    except Exception as e:
                        print(f"[workflow] M2 strategy selection failed: {e}")
            except Exception as e:
                print(f"[workflow] M2 strategy integration error: {e}")
            
            # Original Strategy layer (fallback if M2 didn't succeed)
            try:
                if os.getenv("STRATEGY_LAYER", "0") == "1" and not strategy_result:
                    # Build compact summary for strategy selection
                    try:
                        sig = self._signature(self.ctx["last_bgr"], dets)
                    except Exception:
                        sig = {"yolo_hist": {}}
                    url_hint = sig.get("url")
                    yhist = sig.get("yolo_hist", {})
                    top_ocr = (sig.get("ocr_top", "").split("|") if sig.get("ocr_top") else [])
                    page_summary = {"url": url_hint, "yolo_hist": yhist, "ocr_top": top_ocr}  # simplified page summary
                    page_summary.update({
                        "goal": goal_text,
                        "landmarks": [],
                        "history": self.memory.summarize(json.dumps(sig, sort_keys=True)) or "",
                    })
                    try:
                        # attach compact landmarks into summary (id + bbox)
                        lm_list = detect_landmarks(dets, self.ocr.read_lines(self.ctx.get("last_pil")) if self.ocr else [], (self.ctx["last_bgr"].shape[1], self.ctx["last_bgr"].shape[0]))
                        page_summary["landmarks"] = [{"id": lm.get("id"), "bbox": lm.get("bbox")} for lm in lm_list]
                    except Exception:
                        pass
                    from . import timeline as _t

                    # Trigger conditions: new signature (no memory), ambiguity, or route/verify failure hints
                    allow = False
                    try:
                        sig_key = json.dumps(sig, sort_keys=True)
                        # new signature: no cached strategy
                        if self.strategy_store.lookup(sig_key, goal_text) is None:
                            allow = True
                        # ambiguity: top two det confs close
                        confs = []
                        for d in dets:
                            try:
                                confs.append(float(getattr(d, "conf", 0.0)))
                            except Exception:
                                try:
                                    confs.append(float(d.get("conf", 0.0)))
                                except Exception:
                                    pass
                        confs.sort(reverse=True)
                        if len(confs) >= 2 and (confs[0] - confs[1]) <= float(os.getenv("STRATEGY_AMBIG_DELTA", "0.05")):
                            allow = True
                        # prior replay failure hint in this step
                        if self.ctx.get("replay_failed") is True:
                            allow = True
                        # repeated failures gate
                        fails_n = int(self.ctx.get("replay_failed_count", 0))
                        if fails_n >= int(os.getenv("STRATEGY_TRIG_FAILS", "1")):
                            allow = True
                        # low state_vote gate
                        low_sv = int(self.ctx.get("state_vote_low", 0))
                        if low_sv >= int(os.getenv("STRATEGY_TRIG_LOW_SV", "1")):
                            allow = True
                    except Exception:
                        allow = True

                    # Compute light hashes for cache scoping (optional)
                    import hashlib, json as _json
                    try:
                        lm = detect_landmarks(dets, self.ocr.read_lines(self.ctx.get("last_pil")) if self.ocr else [], (self.ctx["last_bgr"].shape[1], self.ctx["last_bgr"].shape[0]))
                    except Exception:
                        lm = []
                    lm_hash = hashlib.sha1(_json.dumps(lm, sort_keys=True).encode("utf-8")).hexdigest() if lm else None
                    yhist_hash = hashlib.sha1(_json.dumps(yhist, sort_keys=True).encode("utf-8")).hexdigest() if yhist else None

                    # Attempt memory hit first
                    mem_hit = None
                    try:
                        mem_hit = self.strategy_store.lookup(json.dumps(sig, sort_keys=True), goal_text, lm_hash, yhist_hash)
                        if mem_hit:
                            _t.event("strategy/memory_hit", f"step={step_n} id={mem_hit.get('strategy_id')}")
                            if self._execute_strategy(mem_hit, step_n, cur_id, goal_text):
                                self.strategy_store.record(json.dumps(sig, sort_keys=True), goal_text, mem_hit, True, lm_hash, yhist_hash, source="memory")
                                return
                            else:
                                self.strategy_store.record(json.dumps(sig, sort_keys=True), goal_text, mem_hit, False, lm_hash, yhist_hash, source="memory")
                                _t.event("strategy/fallback", f"step={step_n} to=picker")
                    except Exception:
                        pass

                    # Per-signature call budget: avoid repeated LLM calls on same sig in one run
                    already = False
                    try:
                        sig_calls = self.ctx.setdefault("strategy_sig_calls", {})
                        already = sig_calls.get(sig_key, 0) >= int(os.getenv("STRATEGY_MAX_CALLS_PER_SIG", "1"))
                    except Exception:
                        already = False
                    try:
                        glob_calls = int(self.ctx.get("strategy_global_calls", 0))
                        if glob_calls >= int(os.getenv("STRATEGY_MAX_CALLS", "3")):
                            already = True
                    except Exception:
                        pass

                    if allow and not mem_hit and not already:
                        _t.event("strategy/try", f"step={step_n} goal={goal_text}")
                        strat = self.strategy.decide(step_n, json.dumps(sig, sort_keys=True), goal_text, page_summary)
                        try:
                            sig_calls[sig_key] = sig_calls.get(sig_key, 0) + 1
                            self.ctx["strategy_global_calls"] = int(self.ctx.get("strategy_global_calls", 0)) + 1
                        except Exception:
                            pass
                    if strat and isinstance(strat, dict) and strat.get("strategy_id"):
                        _t.event("strategy/chosen", f"step={step_n} id={strat.get('strategy_id')}")
                        # Attempt to execute minimal subset of strategies
                        ok = self._execute_strategy(strat, step_n, cur_id, goal_text)
                        if ok:
                            try:
                                self.strategy_store.record(json.dumps(sig, sort_keys=True), goal_text, strat, True, lm_hash, yhist_hash, source="llm")
                            except Exception:
                                pass
                            return
                        else:
                            try:
                                self.strategy_store.record(json.dumps(sig, sort_keys=True), goal_text, strat, False, lm_hash, yhist_hash, source="llm")
                            except Exception:
                                pass
                            _t.event("strategy/fallback", f"step={step_n} to=picker")
            except Exception:
                pass

            # Confidence-based fallback
            conf_val = None
            try:
                conf_val = float(parsed.get("confidence") or parsed.get("conf"))
            except Exception:
                conf_val = None
            need_input_flag = parsed.get("need_input") is True
            if (parsed.get("click_id") in ("NEED_INPUT", "ABSTAIN") or need_input_flag or (conf_val is not None and conf_val < float(cfg.get("min_conf", 0.6)))):
                # Strict handling: do NOT guess a click; execute fallback only
                fb = cfg.get("fallback") or {"action": "scroll"}
                act = (fb or {}).get("action", "scroll")
                try:
                    if act == "scroll":
                        self.act_scroll(-400)
                    elif act == "open_menu":
                        self.act_scroll(-200)
                    elif act == "expand":
                        self.act_scroll(-150)
                except Exception:
                    pass
                # mark need_input for this step and stay on current state
                try:
                    self.memory.record(sig_key, None, "need_input", reason="picker")
                    self.ctx["need_input"] = True
                except Exception:
                    pass
                self.ctx["next_state_id"] = cur_id
                self.ctx["step_n"] = step_n + 1
                return
        else:
            # Legacy id-only flow
            messages = build_id_only_messages(goal=(cfg.get("goal") or cfg.get("intent") or ""), ids=ids, hints=cfg.get("hints") or [])
            img_path = overlay_name
            if not os.path.isabs(img_path):
                img_path = os.path.join(self.reporter.screens_dir, overlay_name)
            prov = cfg.get("llm_provider") or os.getenv("LLM_PROVIDER") or "gemini"
            model = cfg.get("llm_model") or os.getenv("LLM_MODEL") or "gemini-1.5-flash"
            eff_prov = prov
            eff_model = model
            try:
                safe_prov = (eff_prov or "").replace("/", "-")
                safe_model = (eff_model or "").replace("/", "-")
                prefix = f"{safe_prov}_{safe_model}".strip("_") or "llm"
                req_path = os.path.join(self.reporter.logs_dir, f"{prefix}_picker_req_step_{step_n}.json")
                with open(req_path, "w", encoding="utf-8") as f:
                    json.dump({"provider": eff_prov, "model": eff_model, "image": img_path, "messages": messages}, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            text = ""
            try:
                resp = call_llm(provider=eff_prov, model=eff_model, messages=messages, image_path=img_path)
                text = extract_text_generic(resp)
                try:
                    resp_path = os.path.join(self.reporter.logs_dir, f"{prefix}_picker_resp_step_{step_n}.json")
                    with open(resp_path, "w", encoding="utf-8") as f:
                        json.dump({"raw": resp, "extracted_text": text}, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                parsed = parse_first_json(text) or {}
            except Exception as e:
                try:
                    err_path = os.path.join(self.reporter.logs_dir, f"{prefix}_picker_err_step_{step_n}.json")
                    with open(err_path, "w", encoding="utf-8") as f:
                        json.dump({"error": str(e)}, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                parsed = {"need_input": True, "why": "llm_error"}

        # Always persist a compact final summary for the step
        try:
            final_path = os.path.join(self.reporter.logs_dir, f"picker_final_step_{step_n}.json")
            with open(final_path, "w", encoding="utf-8") as f:
                json.dump({
                    "provider": (eff_prov if 'eff_prov' in locals() else prov),
                    "model": (eff_model if 'eff_model' in locals() else model),
                    "parsed": parsed
                }, f, ensure_ascii=False, indent=2)
            try:
                from . import timeline as _t
                _t.event("picker_final", f"step={step_n} id={parsed.get('id')} why={parsed.get('why')} conf={parsed.get('confidence')}")
            except Exception:
                pass
        except Exception:
            pass
        # Per-step log (LLM path)
        try:
            pconf = None
            try:
                pconf = float(parsed.get("confidence") or parsed.get("conf"))
            except Exception:
                pconf = None
            msg = f"llm_picker; conf={pconf if pconf is not None else ''}"
            self.reporter.log_step(StepLog(name=f"autostep_{step_n}", status="info", message=msg, overlay_img=self.ctx.get("last_overlay_path")))
        except Exception:
            pass

        # Continue with vision picker click execution
        # Map id to detection and execute click
        click_id = parsed.get("id") or parsed.get("click_id") or (parsed.get("decision", {}) or {}).get("click_id")
        # If click_id is denied, try alt.id if provided  
        deny_ids = self.ctx.get("denylist", {}).get(sig_key, set())
        original_click_id = click_id
        if click_id and deny_ids and click_id in deny_ids:
            alt = parsed.get("alt") or {}
            alt_id = alt.get("id") if isinstance(alt, dict) else None
            if alt_id and alt_id not in deny_ids:
                click_id = alt_id
                print(f"[autostep] Using alternative element: {alt_id} (original {original_click_id} was denied)")
        
        if click_id in ("ABSTAIN", "NEED_INPUT", None) or not ids:
            # Strict: do not guess; try OCR fallback for search focus, else fallback
            try:
                self.memory.record(sig_key, None, "need_input", reason="picker")
            except Exception:
                pass

            def _is_search_focus_goal(text: str) -> bool:
                t = (text or "").lower()
                return ("search" in t) or ("搜索" in text) or ("查找" in text) or ("放大镜" in text)

            used_ocr = False
            if _is_search_focus_goal(goal_text):
                try:
                    # ensure we have a current frame saved
                    if self.ctx.get("last_bgr") is None:
                        self.act_screenshot()
                    tmp_name = f"ocr_step_{int(self.ctx.get('step_n',0))}.png"
                    img_path = os.path.join(self.reporter.screens_dir, tmp_name)
                    cv2.imwrite(img_path, self.ctx.get("last_bgr"))
                    lines = run_ocr(img_path)
                    H0, W0 = self.ctx["last_bgr"].shape[:2]
                    box = find_search_field_region(lines, (W0, H0))
                    if box:
                        dpr = float(self.ctx.get("dpr", 1.0))
                        cx = int((box[0] + box[2]) / 2)
                        cy = int((box[1] + box[3]) / 2)
                        self.exec.click(cx, cy, dpr=dpr)
                        # verify gate
                        self.act_screenshot(); self.act_detect()
                        dets2 = self.ctx["detections"]
                        yolo_after_dict = {"detections": [{"class_name": str(getattr(dd, "class_name", ""))} for dd in dets2]}
                        from .verifier import step_gate_verify as _sgv
                        rules = (cfg.get("verify") or {}).get("rules", []) if isinstance(cfg.get("verify"), dict) else []
                        if _sgv(rules, yolo_after_dict, None):
                            log_event("ocr_fallback_used", {"state": str(cur_id), "goal": goal_text})
                            append_steps_log({"event": "ocr_fallback_used", "state": str(cur_id), "goal": goal_text})
                            # mark success and move to next step
                            self.ctx["next_state_id"] = cur_id
                            self.ctx["step_n"] = step_n + 1
                            return
                        used_ocr = True
                except Exception:
                    pass
            # regular fallback if OCR not used or failed
            try:
                fb = cfg.get("fallback") or {"action": "scroll"}
                act = (fb or {}).get("action", "scroll")
                if act == "scroll":
                    self.act_scroll(-400)
                elif act == "open_menu":
                    self.act_scroll(-200)
                elif act == "expand":
                    self.act_scroll(-150)
            except Exception:
                pass
            self.ctx["next_state_id"] = cur_id
            return

        try:
            did = int(str(click_id)[1:]) if str(click_id).startswith("c") else int(click_id)
        except Exception:
            self.ctx["next_state_id"] = cur_id
            self.ctx["step_n"] = step_n + 1 
            return

        det = None
        for d in dets:
            if int(d.id) == did:
                det = d; break
        if det is None:
            # Try alternative element if available before giving up
            alt = parsed.get("alt") or {}
            alt_id = alt.get("id") if isinstance(alt, dict) else None
            if alt_id and alt_id != click_id:
                try:
                    alt_did = int(str(alt_id)[1:]) if str(alt_id).startswith("c") else int(alt_id)
                    for d in dets:
                        if int(d.id) == alt_did:
                            det = d
                            click_id = alt_id
                            did = alt_did
                            print(f"[autostep] Using alternative element: {alt_id} (original {original_click_id} not found)")
                            break
                except Exception:
                    pass
            if det is None:
                self.ctx["next_state_id"] = cur_id
                return

        # Execute click
        cap_h, cap_w = self.ctx["last_bgr"].shape[:2]
        cap_meta = self._cap_meta()
        pre = PreprocMeta(frame_w=cap_w, frame_h=cap_h, imgsz=cap_w, letterbox=False, normalized=False)
        sx, sy = map_id_to_screen_point(det.bbox_xyxy, det.class_name, pre, cap_meta)
        
        # Optional pre-hover
        try:
            hover_ms = int(os.getenv("PRE_HOVER_MS", "0"))
            if hover_ms > 0:
                self.exec.move_to(sx, sy, duration=0.15)
                time.sleep(hover_ms / 1000.0)
        except Exception:
            pass
        
        self.exec.click(sx, sy, dpr=cap_meta.dpr)
        
        # Record click for next step prompts
        try:
            self.ctx["last_click"] = {"id": click_id, "why": parsed.get("why", ""), "bbox": det.bbox_xyxy}
        except Exception:
            pass
        
        # Verify transition
        verify = cfg.get("verify", {"rules": ["page_change"], "timeout_ms": 8000, "poll_ms": 600})
        start = time.time()
        next_id = cur_id
        ok = False
        while (time.time() - start) * 1000 < int(verify.get("timeout_ms", 8000)):
            time.sleep(float(verify.get("poll_ms", 600)) / 1000.0)
            self.act_screenshot()
            self.act_detect()
            bgr2 = self.ctx["last_bgr"]  
            dets2 = self.ctx["detections"]
            sig2 = self._signature(bgr2, dets2)
            
            # Check if page changed
            if self._sig_sim(sig, sig2) < 0.85:
                next_id = self._resolve_or_create_state(sig2)
                ok = True
                break
        
        if ok:
            # Outcome verification for navigation-type goals (result-centric)
            try:
                def _is_navigation_goal(text: str) -> bool:
                    t = (text or "").lower()
                    keys = ["search", "回车", "enter", "打开", "进入", "跳转", "submit", "publish", "open", "go", "详情"]
                    return any(k in t for k in keys)
                if _is_navigation_goal(goal_text):
                    from .prompt_builder import VerifierCtx, build_verifier_messages_unified
                    vctx = VerifierCtx(
                        task=cfg.get("task_context", "") or goal_text,
                        phase=cfg.get("phase", "general"),
                        state=str(cur_id),
                        goal=goal_text,
                        action_summary=f"clicked {parsed.get('id') or parsed.get('click_id')}; waited for page change",
                        expect_page=str(cfg.get("expect_page", "search_results")),
                        history_summary=str(history_hint or "")[:220],
                    )
                    vmsgs = build_verifier_messages_unified(vctx)
                    prov_v = cfg.get("llm_provider") or os.getenv("LLM_PROVIDER") or "gemini"
                    model_v = cfg.get("llm_model") or os.getenv("LLM_MODEL") or "gemini-1.5-flash"
                    resp_v = call_llm(provider=prov_v, model=model_v, messages=vmsgs, image_path=self.ctx.get("last_overlay_path"))
                    text_v = extract_text_generic(resp_v)
                    parsed_v = parse_first_json(text_v) or {}
                    if not bool(parsed_v.get("ok")):
                        ok = False
                        try:
                            from . import timeline as _t
                            _t.event("verify/outcome_fail", f"step={step_n} reason={parsed_v.get('reason','')[:32]}")
                        except Exception:
                            pass
                    else:
                        try:
                            from . import timeline as _t
                            _t.event("verify/outcome_ok", f"step={step_n} to={parsed_v.get('state','')}")
                        except Exception:
                            pass
            except Exception:
                pass
            # Step gate: require verify rules to pass in addition to page change
            try:
                yolo_after_dict = {"detections": []}
                for dd in dets2:
                    try:
                        clsn = str(getattr(dd, "class_name", ""))
                    except Exception:
                        try:
                            clsn = str(dd.get("class_name", ""))
                        except Exception:
                            clsn = ""
                    yolo_after_dict["detections"].append({"class_name": clsn})
                rules = (verify or {}).get("rules", []) if isinstance(verify, dict) else []
                from .verifier import step_gate_verify as _sgv
                if not _sgv(rules, yolo_after_dict, None):
                    ok = False
            except Exception:
                pass

        if ok:
            try:
                self.memory.record(sig_key, f"c{did}", "success")
            except Exception:
                pass
            self._link_edge(
                cur_id,
                next_id, 
                action={"det_id": did, "cls": det.class_name, "bbox": det.bbox_xyxy, "click_point": [sx, sy]},
                verify={"rules": verify.get("rules", [])},
            )
            self.ctx["next_state_id"] = next_id
            self.ctx["step_n"] = step_n + 1  # Only increment on success
        else:
            # Wrong page guard: attempted navigation but reached an unexpected page (e.g., detail)
            try:
                from .verifier import is_wrong_page_signature as _iwps
                yolo_after_dict = {"detections": []}
                for dd in dets2:
                    try:
                        clsn = str(getattr(dd, "class_name", ""))
                    except Exception:
                        try:
                            clsn = str(dd.get("class_name", ""))
                        except Exception:
                            clsn = ""
                    yolo_after_dict["detections"].append({"class_name": clsn})
                if _iwps(yolo_after_dict, goal_text):
                    try:
                        self.act_go_back()
                        from . import timeline as _t
                        _t.event("guard/wrong_page", f"step={step_n} back")
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                self.memory.record(sig_key, f"c{did}", "fail", reason="verify")
            except Exception:
                pass
            self.ctx["next_state_id"] = cur_id

            # Check for retry attempts 
            retry_count = self.ctx.get("retry_count", 0)
            max_retries = int(cfg.get("max_retries", 2))  # Allow 2 retries by default
            
            if retry_count < max_retries:
                print(f"[autostep] Verification failed for step {step_n}, retrying (attempt {retry_count + 1}/{max_retries})")
                self.ctx["retry_count"] = retry_count + 1
                # Don't increment step_n, retry the same step
                return
            
            # Exhausted retries: log and try OCR fallback once more for search focus
            try:
                log_event("step_gate_failed", {"state": str(cur_id), "goal": goal_text})
                append_steps_log({"event": "step_gate_failed", "state": str(cur_id), "goal": goal_text})
            except Exception:
                pass
            try:
                def _is_search_focus_goal(text: str) -> bool:
                    t = (text or "").lower()
                    return ("search" in t) or ("搜索" in text) or ("查找" in text) or ("放大镜" in text)
                if _is_search_focus_goal(goal_text) and self.ctx.get("last_bgr") is not None:
                    tmp_name = f"ocr_step_{int(self.ctx.get('step_n',0))}_retry.png"
                    img_path = os.path.join(self.reporter.screens_dir, tmp_name)
                    cv2.imwrite(img_path, self.ctx.get("last_bgr"))
                    lines = run_ocr(img_path)
                    H2, W2 = self.ctx["last_bgr"].shape[:2]
                    box = find_search_field_region(lines, (W2, H2))
                    if box:
                        dpr = float(self.ctx.get("dpr", 1.0))
                        cx = int((box[0] + box[2]) / 2)
                        cy = int((box[1] + box[3]) / 2)
                        self.exec.click(cx, cy, dpr=dpr)
                        self.act_screenshot(); self.act_detect()
                        dets2b = self.ctx["detections"]
                        yolo_after_dict2 = {"detections": [{"class_name": str(getattr(dd, "class_name", ""))} for dd in dets2b]}
                        from .verifier import step_gate_verify as _sgv
                        rules2 = (verify or {}).get("rules", []) if isinstance(verify, dict) else []
                        if _sgv(rules2, yolo_after_dict2, None):
                            log_event("ocr_fallback_used", {"state": str(cur_id), "goal": goal_text})
                            append_steps_log({"event": "ocr_fallback_used", "state": str(cur_id), "goal": goal_text})
                            self.ctx["retry_count"] = 0
                            self.ctx["next_state_id"] = cur_id
                            self.ctx["step_n"] = step_n + 1
                            return
            except Exception:
                pass
            # Keep gate closed and retry on next outer loop iteration
            print(f"[autostep] Verification failed for step {step_n}, retries exhausted; staying on current step.")
            self.ctx["retry_count"] = 0

    def _execute_strategy(self, strat: Dict[str, Any], step_n: int, cur_id: str, goal_text: str) -> bool:
        """Execute a minimal subset of strategies: FIRST_RESULT_BELOW_SEARCH, NTH_IN_CONTAINER, LIST_TOPMOST_WITH_ATTR.
        Returns True on success (state progressed), False to fallback to picker.
        """
        from . import timeline as _t
        sid = str(strat.get("strategy_id"))
        params = strat.get("params") or {}
        bgr = self.ctx.get("last_bgr")
        if bgr is None:
            return False
        H, W = bgr.shape[:2]
        # Build candidate boxes and classes from detections (coarse proxy)
        dets = self.ctx.get("detections") or []
        det_infos = []
        boxes = []
        for d in dets:
            try:
                bbox = [int(x) for x in d.bbox_xyxy]
                cls = str(getattr(d, "class_name", ""))
            except Exception:
                try:
                    bbox = [int(x) for x in d.get("bbox_xyxy", [])]
                    cls = str(d.get("class_name", ""))
                except Exception:
                    continue
            det_infos.append({"bbox": bbox, "cls": cls})
            boxes.append(bbox)
        if not det_infos:
            return False

        target_bbox = None
        # Helper: OCR lines for landmarks
        ocr_lines = []
        try:
            if self.ocr and self.ctx.get("last_pil") is not None:
                ocr_lines = self.ocr.read_lines(self.ctx.get("last_pil")) or []
        except Exception:
            ocr_lines = []

        if sid == "FIRST_RESULT_BELOW_SEARCH":
            try:
                # Prefer detected landmarks
                landmarks = detect_landmarks(dets, ocr_lines, (W, H))
                search = None
                for lm in landmarks:
                    if lm.get("id") == "search_bar":
                        search = tuple(lm.get("bbox"))  # type: ignore
                        break
                if search is None:
                    from .landmarks import find_search_bar_bbox
                    search = find_search_bar_bbox(ocr_lines, (W, H))
                if search is None:
                    _t.event("strategy/info", f"step={step_n} no_search_bar_found")
                else:
                    sx1, sy1, sx2, sy2 = search
                    # pick the first box below search bar in central width
                    candidates = []
                    for b in boxes:
                        x1, y1, x2, y2 = b
                        if y1 >= (sy2 + 8) and (x1 >= int(0.10 * W)) and (x2 <= int(0.90 * W)):
                            candidates.append(b)
                    candidates.sort(key=lambda b: (b[1], b[0]))
                    if candidates:
                        target_bbox = candidates[0]
            except Exception:
                target_bbox = None

        elif sid == "NTH_IN_CONTAINER":
            try:
                n = int(params.get("n") or params.get("ordinal") or 1)
                # Container heuristic: prefer detected results_container
                cx1, cy1, cx2, cy2 = (int(0.05 * W), int(0.20 * H), int(0.95 * W), int(0.95 * H))
                try:
                    landmarks = detect_landmarks(dets, ocr_lines, (W, H))
                    for lm in landmarks:
                        if lm.get("id") == "results_container":
                            cx1, cy1, cx2, cy2 = lm.get("bbox")  # type: ignore
                            break
                except Exception:
                    pass
                # Filter boxes in container and group rows, then pick nth row's union box
                cands = filter_in_region(boxes, (cx1, cy1, cx2, cy2))
                rows = group_by_rows(cands)
                if 1 <= n <= len(rows):
                    ub = union_bbox(rows[n - 1])
                    if ub:
                        target_bbox = ub
            except Exception:
                target_bbox = None

        elif sid == "LIST_TOPMOST_WITH_ATTR":
            try:
                # Heuristic: choose top-most box within left sidebar region; prefer rows containing a 'badge' class when attr==unread
                try:
                    landmarks = detect_landmarks(dets, ocr_lines, (W, H))
                    side = next((lm.get("bbox") for lm in landmarks if lm.get("id") == "side_list"), None)
                    if side:
                        lx1, ly1, lx2, ly2 = side  # type: ignore
                    else:
                        lx1, ly1, lx2, ly2 = int(0.02 * W), int(0.12 * H), int(0.28 * W), int(0.95 * H)
                except Exception:
                    lx1, ly1, lx2, ly2 = int(0.02 * W), int(0.12 * H), int(0.28 * W), int(0.95 * H)
                # Group into rows within sidebar region
                bxs = [info["bbox"] for info in det_infos if (info["bbox"][0] >= lx1 and info["bbox"][1] >= ly1 and info["bbox"][2] <= lx2 and info["bbox"][3] <= ly2)]
                rows = group_by_rows(bxs)
                # Prefer rows which contain a nearby 'badge' detection (unread)
                attr = str(params.get("attr") or "").lower()
                def _overlap(a, b):
                    ax1, ay1, ax2, ay2 = a; bx1, by1, bx2, by2 = b
                    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
                    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
                    return (ix2 > ix1) and (iy2 > iy1)
                if attr in ("unread", "badge"):
                    badge_boxes = [i["bbox"] for i in det_infos if i["cls"].lower() in ("badge", "dot", "notif")]
                    scored: List[Tuple[int, BBox]] = []
                    for row in rows:
                        ub = union_bbox(row)
                        if not ub:
                            continue
                        score = has_attr_unread(bgr, ub, ocr_lines, badge_boxes)
                        if score > 0:
                            scored.append((score, ub))
                    if scored:
                        scored.sort(key=lambda t: (t[0] * -1, t[1][1], t[1][0]))
                        target_bbox = scored[0][1]
                if target_bbox is None:
                    # fallback: top-most row in sidebar
                    if rows:
                        ub = union_bbox(rows[0])
                        if ub:
                            target_bbox = ub
            except Exception:
                target_bbox = None

        if target_bbox is None:
            # try fallback if provided
            fb = strat.get("fallback")
            if isinstance(fb, dict) and fb.get("strategy_id"):
                _t.event("strategy/fallback_try", f"step={step_n} id={fb.get('strategy_id')}")
                if self._execute_strategy({"strategy_id": fb.get("strategy_id"), "params": fb.get("params") or {}}, step_n, cur_id, goal_text):
                    return True
            return False

        # Click target bbox center and verify by page change heuristics
        try:
            cap_h, cap_w = H, W
            cap_meta = self._cap_meta()
            pre = PreprocMeta(frame_w=cap_w, frame_h=cap_h, imgsz=cap_w, letterbox=False, normalized=False)
            x1, y1, x2, y2 = target_bbox
            sx, sy = map_id_to_screen_point([x1, y1, x2, y2], None, pre, cap_meta)
            self.exec.click(sx, sy, dpr=cap_meta.dpr)
            _t.event("strategy/click", f"step={step_n} bbox={[x1, y1, x2, y2]}")
            # verify: use signature delta (page_change) as light-weight verification
            verify = {"timeout_ms": 8000, "poll_ms": 600}
            ok = False
            start = time.time()
            sig_prev = self._signature(self.ctx["last_bgr"], dets)
            while (time.time() - start) * 1000 < int(verify.get("timeout_ms", 8000)):
                time.sleep(float(verify.get("poll_ms", 600)) / 1000.0)
                self.act_screenshot(); self.act_detect()
                sig2 = self._signature(self.ctx["last_bgr"], self.ctx["detections"])
                if self._sig_sim(sig_prev, sig2) < 0.72:
                    ok = True; break
            if ok:
                next_id = self._resolve_or_create_state(sig2)
                self._link_edge(cur_id, next_id, action={"strategy": sid, "bbox": target_bbox}, verify={"rules": ["page_change"]})
                self._save_graph_workflow(start_id=cur_id)
                self.ctx["next_state_id"] = next_id
                self.ctx["step_n"] = step_n + 1
                try:
                    # record last_click summary for next step prompt context
                    self.ctx["last_click"] = {"id": None, "why": f"strategy:{sid}", "bbox": target_bbox}
                except Exception:
                    pass
                try:
                    # per-step reporter entry to mark strategy path
                    self.reporter.log_step(StepLog(name=f"autostep_{step_n}", status="success", message=f"strategy_exec ok; id={sid}", overlay_img=self.ctx.get("last_overlay_path")))
                except Exception:
                    pass
                _t.event("strategy/exec_ok", f"step={step_n} id={sid}")
                return True
        except Exception:
            pass
        _t.event("strategy/exec_fail", f"step={step_n} id={sid}")
        return False

        if save and save.get("picker"):
            name = save["picker"].format(n=step_n)
            path = os.path.join(self.reporter.logs_dir, name)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"raw_text": text, "parsed": parsed}, f, ensure_ascii=False, indent=2)

        # Map id to detection
        click_id = parsed.get("id") or parsed.get("click_id") or (parsed.get("decision", {}) or {}).get("click_id")
        # If click_id is denied, try alt.id if provided
        if click_id and deny_ids and click_id in deny_ids:
            alt = parsed.get("alt") or {}
            alt_id = alt.get("id") if isinstance(alt, dict) else None
            if alt_id and alt_id not in deny_ids:
                click_id = alt_id
        if click_id in ("ABSTAIN", "NEED_INPUT", None) or not ids:
            # no-op, trace and stay on same state
            try:
                self.memory.record(sig_key, None, "need_input", reason="picker")
            except Exception:
                pass
            self.ctx["next_state_id"] = cur_id
            self.ctx["step_n"] = step_n + 1
            return

        try:
            did = int(str(click_id)[1:]) if str(click_id).startswith("c") else int(click_id)
        except Exception:
            self.ctx["next_state_id"] = cur_id
            self.ctx["step_n"] = step_n + 1
            return

        det = None
        for d in dets:
            if int(d.id) == did:
                det = d; break
        if det is None:
            self.ctx["next_state_id"] = cur_id
            self.ctx["step_n"] = step_n + 1
            return

        # Click
        # Map robustly from model frame to capture → screen
        cap_h, cap_w = self.ctx["last_bgr"].shape[:2]
        cap_meta = CaptureMeta(cap_w=cap_w, cap_h=cap_h, dpr=float(self.ctx.get("dpr", 1.0)))
        # Assume API returns original pixels; set letterbox False
        pre = PreprocMeta(frame_w=cap_w, frame_h=cap_h, imgsz=cap_w, letterbox=False, normalized=False)
        # capture pre-click ROI mean for visual delta verify
        try:
            x1, y1, x2, y2 = map(int, det.bbox_xyxy)
            x1 = max(0, min(cap_w - 1, x1)); x2 = max(0, min(cap_w - 1, x2))
            y1 = max(0, min(cap_h - 1, y1)); y2 = max(0, min(cap_h - 1, y2))
            roi0 = self.ctx["last_bgr"][y1:y2, x1:x2]
            roi0_mean = float(roi0.mean()) if roi0.size > 0 else None
        except Exception:
            roi0_mean = None
        sx, sy = map_id_to_screen_point(det.bbox_xyxy, det.class_name, pre, cap_meta)
        # Optional pre-hover
        try:
            hover_ms = int(os.getenv("PRE_HOVER_MS", "0"))
            if hover_ms > 0:
                self.exec.move_to(sx, sy, duration=0.15)
                time.sleep(hover_ms / 1000.0)
        except Exception:
            pass
        self.exec.click(sx, sy, dpr=cap_meta.dpr)

        # Verify transition
        verify = cfg.get("verify", {"rules": ["page_change"], "timeout_ms": 8000, "poll_ms": 600})
        # Planner override of verify rules/timeout
        try:
            if plan_item and isinstance(plan_item, dict):
                if isinstance(plan_item.get("verify"), list):
                    verify["rules"] = plan_item.get("verify")
                if plan_item.get("timeout_ms"):
                    verify["timeout_ms"] = int(plan_item.get("timeout_ms"))
        except Exception:
            pass
        start = time.time()
        next_id = cur_id
        ok = False
        while (time.time() - start) * 1000 < int(verify.get("timeout_ms", 8000)):
            time.sleep(float(verify.get("poll_ms", 600)) / 1000.0)
            self.act_screenshot()
            self.act_detect()
            bgr2 = self.ctx["last_bgr"]
            dets2 = self.ctx["detections"]
            sig2 = self._signature(bgr2, dets2)
            rules = verify.get("rules", [])
            rule_ok = False
            if rules:
                classes2 = [getattr(x, "class_name") for x in dets2]
                for r in rules:
                    if r == "page_change":
                        continue
                    if r.startswith("appear:"):
                        cl = r.split(":", 1)[1]
                        if cl in classes2: rule_ok = True
                    if r.startswith("disappear:"):
                        cl = r.split(":", 1)[1]
                        if cl not in classes2: rule_ok = True
            # visual delta on click region as additional weak signal
            if not rule_ok and roi0_mean is not None:
                try:
                    roi2 = bgr2[y1:y2, x1:x2]
                    if roi2.size > 0:
                        delta = abs(float(roi2.mean()) - roi0_mean)
                        if delta > 8.0:  # small threshold
                            rule_ok = True
                except Exception:
                    pass
            if rule_ok or self._sig_sim(sig, sig2) < 0.72:
                next_id = self._resolve_or_create_state(sig2)
                ok = True
                break

        if ok:
            # Cross-page confirmation LLM and S fusion
            try:
                from .prompt_builder import build_cross_confirm_messages
                prev_click = {"id": f"c{did}", "why": parsed.get("why"), "bbox": det.bbox_xyxy}
                goal_cc = goal_text
                msgs = build_cross_confirm_messages(goal_cc, prev_click, expected_state=goal_cc)
                prov_cc = cfg.get("llm_provider") or os.getenv("LLM_PROVIDER") or "gemini"
                model_cc = cfg.get("llm_model") or os.getenv("LLM_MODEL") or "gemini-1.5-flash"
                pref_cc = f"{(prov_cc or '').replace('/', '-')}_{(model_cc or '').replace('/', '-')}".strip('_') or 'llm'
                try:
                    with open(os.path.join(self.reporter.logs_dir, f"{pref_cc}_cross_confirm_req_step_{step_n}.json"), "w", encoding="utf-8") as f:
                        json.dump({"provider": prov_cc, "model": model_cc, "messages": msgs}, f, ensure_ascii=False, indent=2)
                    try:
                        from . import timeline as _t
                        _t.event("llm/confirm_req", f"step={step_n} model={prov_cc}/{model_cc}")
                    except Exception:
                        pass
                except Exception:
                    pass
                resp_cc = call_llm(provider=prov_cc, model=model_cc, messages=msgs, image_path=self.ctx.get("last_overlay_path"))
                text_cc = extract_text_generic(resp_cc)
                try:
                    with open(os.path.join(self.reporter.logs_dir, f"{pref_cc}_cross_confirm_resp_step_{step_n}.json"), "w", encoding="utf-8") as f:
                        json.dump({"raw": resp_cc, "extracted_text": text_cc}, f, ensure_ascii=False, indent=2)
                    try:
                        from . import timeline as _t
                        _t.event("llm/confirm_resp", f"step={step_n} parsed")
                    except Exception:
                        pass
                except Exception:
                    pass
                arb = parse_first_json(text_cc) or {}
                conf_llm = float(arb.get("confidence", 0.0)) if isinstance(arb, dict) else 0.0
            except Exception:
                conf_llm = 0.0

            # Compute S = w1*V1 + w2*V2 + w3*LLM
            # V1: page_change already true -> 1.0
            V1 = 1.0
            # V2: URL/path change hint (if available)
            try:
                url1 = sig.get("url"); url2 = sig2.get("url")
                if url1 and url2:
                    from urllib.parse import urlparse
                    p1 = urlparse(url1); p2 = urlparse(url2)
                    if (p1.netloc != p2.netloc) or (p1.path != p2.path):
                        V2 = 1.0
                    else:
                        V2 = 0.3
                else:
                    V2 = 1.0
            except Exception:
                V2 = 1.0
            W_RULE = float(os.getenv("W_RULE", "0.5"))
            W_HINT = float(os.getenv("W_HINT", "0.2"))
            W_LLM = float(os.getenv("W_LLM", "0.3"))
            TH_PASS = float(os.getenv("TH_PASS", "0.7"))
            S = W_RULE * V1 + W_HINT * V2 + W_LLM * conf_llm
            # Log S breakdown
            try:
                self.reporter.log_step(StepLog(
                    name=f"autostep_{step_n}_confirm",
                    status="info",
                    message=f"S={S:.2f} (V1={V1:.2f}, V2={V2:.2f}, LLM={conf_llm:.2f})",
                    overlay_img=self.ctx.get("last_overlay_path")
                ))
            except Exception:
                pass

            # Promote route + anchors if pass
            if S >= TH_PASS:
                try:
                    anchors = anchors_from(bgr, det.bbox_xyxy)
                    compound = auto_select_anchors(bgr, det.bbox_xyxy)
                    # Embed URL and OCR texts into state anchors
                    url_hint = None
                    try:
                        url_hint = self._get_url_hint()
                    except Exception:
                        url_hint = None
                    ocr_now = []
                    ocr_lines = []
                    try:
                        if hasattr(self, "ocr") and self.ocr:
                            ocr_now = self.ocr.read_texts(self.ctx.get("last_pil")) or []
                            ocr_lines = self.ocr.read_lines(self.ctx.get("last_pil")) or []
                    except Exception:
                        ocr_now = []
                        ocr_lines = []
                    state_anc = state_anchors_from(self.ctx["last_bgr"], url_hint=url_hint, ocr_texts=ocr_now, ocr_lines=ocr_lines)
                    # Optional: capture a few OCR tokens to help confirm next page
                    state_texts = []
                    try:
                        if hasattr(self, "ocr") and self.ocr:
                            got = self.ocr.read_texts(self.ctx.get("last_pil")) or []
                            for t in got:
                                s = (t or "").strip()
                                if 2 <= len(s) <= 12 and s not in state_texts:
                                    state_texts.append(s)
                                if len(state_texts) >= 5:
                                    break
                    except Exception:
                        state_texts = []
                    self.routes.append({
                        "ts": int(time.time() * 1000),
                        "sig_key": sig_key,
                        "goal": goal_text,
                        "click_id": f"c{did}",
                        "bbox": det.bbox_xyxy,
                        "verifier": verify.get("rules", []),
                        "next_sig_hint": self._signature(self.ctx["last_bgr"], self.ctx["detections"]),
                        "anchors": anchors,
                        "row_anchor": compound.get("row_anchor"),
                        "action_anchor": compound.get("action_anchor"),
                        "relation": compound.get("relation"),
                        "text_anchor": compound.get("text_anchor"),
                        "state_anchors": state_anc,
                        "state_texts": state_texts,
                        "success_count": 1,
                    })
                except Exception:
                    pass
            try:
                self.memory.record(sig_key, f"c{did}", "success")
            except Exception:
                pass
            self._link_edge(
                cur_id,
                next_id,
                action={"det_id": did, "cls": det.class_name, "bbox": det.bbox_xyxy, "click_point": [sx, sy]},
                verify={"rules": verify.get("rules", [])},
            )
            self._save_graph_workflow(start_id=cur_id)
            self.ctx["next_state_id"] = next_id
        else:
            try:
                self.memory.record(sig_key, f"c{did}", "fail", reason="verify")
                dl = self.ctx.setdefault("denylist", {})
                dset = set(dl.get(sig_key, []))
                dset.add(f"c{did}")
                dl[sig_key] = list(dset)
            except Exception:
                pass
            # Attempt to go back after a failed transition
            try:
                self.act_go_back()
            except Exception:
                pass
            self.ctx["next_state_id"] = cur_id
        
        # M3: End step cost tracking and emit events
        self.cost_guard.end_step()
        from .report_events import emit_step_end
        
        # Determine step status
        step_status = "success"  # Default to success
        chosen = self.ctx.get("chosen")
        if not chosen or not chosen.chosen:
            step_status = "failure"
        elif self.ctx.get("need_input"):
            step_status = "need_input"
        
        emit_step_end(
            step_idx=step_n,
            status=step_status,
            ms=int(self.cost_guard.u.step_durations_ms[-1]) if self.cost_guard.u.step_durations_ms else 0,
            chosen_id=chosen.chosen.id if chosen and chosen.chosen else None
        )
        
        self.ctx["step_n"] = step_n + 1

    # ------ platform helpers ------
    def _get_url_hint(self) -> Optional[str]:
        sysname = platform.system()
        if sysname != "Darwin":
            return None
        # Try Google Chrome
        try:
            out = subprocess.check_output(["osascript", "-e", 'tell application "Google Chrome" to get URL of active tab of front window'], timeout=1.0)
            u = out.decode("utf-8").strip()
            if u:
                return u
        except Exception:
            pass
        # Try Safari
        try:
            out = subprocess.check_output(["osascript", "-e", 'tell application "Safari" to get URL of front document'], timeout=1.0)
            u = out.decode("utf-8").strip()
            return u or None
        except Exception:
            return None


def load_workflow(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
