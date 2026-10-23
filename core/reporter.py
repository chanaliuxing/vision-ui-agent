import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import cv2
import numpy as np


@dataclass
class StepLog:
    name: str
    status: str  # success|fail|info
    message: str
    exec_id: Optional[str] = None
    conf: Optional[float] = None
    chosen_cls: Optional[str] = None
    before_img: Optional[str] = None
    after_img: Optional[str] = None
    overlay_img: Optional[str] = None
    click_xy: Optional[List[int]] = None
    time_ms: Optional[float] = None


class Reporter:
    def __init__(self, out_dir: str = "out"):
        self.out_dir = out_dir
        self.screens_dir = os.path.join(out_dir, "screens")
        self.reports_dir = os.path.join(out_dir, "reports")
        self.logs_dir = os.path.join(out_dir, "logs")
        for d in [self.out_dir, self.screens_dir, self.reports_dir, self.logs_dir]:
            os.makedirs(d, exist_ok=True)
        self.steps: List[StepLog] = []
        self._t0 = time.time()
        # Initialize streaming timeline per run
        try:
            from . import timeline as _t
            _t.init(out_dir=self.out_dir)
            _t.event("report", "reporter_init")
        except Exception:
            pass

    def save_image(self, bgr: np.ndarray, name: str) -> str:
        path = os.path.join(self.screens_dir, name)
        cv2.imwrite(path, bgr)
        return path

    @staticmethod
    def draw_detections(
        bgr: np.ndarray,
        boxes: List[List[float]],
        labels: List[str],
        chosen_idx: Optional[int] = None,
    ) -> np.ndarray:
        out = bgr.copy()
        for i, (box, label) in enumerate(zip(boxes, labels)):
            x1, y1, x2, y2 = map(int, box)
            color = (0, 255, 0) if i == chosen_idx else (255, 0, 0)
            thickness = 3 if i == chosen_idx else 2
            cv2.rectangle(out, (x1, y1), (x2, y2), color, thickness)
            cv2.putText(out, label, (x1 + 4, max(12, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
        return out

    def log_step(self, step: StepLog):
        self.steps.append(step)

    def flush_jsonl(self) -> str:
        path = os.path.join(self.logs_dir, "steps_log.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for s in self.steps:
                f.write(json.dumps(asdict(s), ensure_ascii=False) + "\n")
        return path

    def write_html(self, filename: Optional[str] = None) -> str:
        if filename is None:
            ts = time.strftime("%Y%m%d_%H%M%S")
            filename = f"run_report_{ts}.html"
        path = os.path.join(self.reports_dir, filename)

        total_ms = int((time.time() - self._t0) * 1000)
        ok = sum(1 for s in self.steps if s.status == "success")
        fail = sum(1 for s in self.steps if s.status == "fail")

        def img_tag(p: Optional[str]) -> str:
            if not p:
                return ""
            rel = os.path.relpath(p, os.path.dirname(path))
            return f'<img src="{rel}" style="max-width:320px;border:1px solid #ddd;margin:4px" />'

        # Aggregate optional self-heal metrics from routes.jsonl
        routes_path = os.path.join(self.logs_dir, "routes.jsonl")
        strategies_path = os.path.join(self.logs_dir, "strategies.jsonl")
        r_total = r_succ = r_fail = r_tight = r_relax = 0
        top_goals: Dict[str, int] = {}
        # windowed health per (sig_key,goal)
        health: Dict[str, Dict[str, Any]] = {}
        if os.path.exists(routes_path):
            try:
                with open(routes_path, "r", encoding="utf-8") as rf:
                    for line in rf:
                        try:
                            rec = json.loads(line)
                        except Exception:
                            continue
                        r_total += 1
                        if int(rec.get("success_count", 0)) > 1:
                            r_succ += 1
                        if int(rec.get("fail_count", 0)) >= 1:
                            r_fail += 1
                        g = rec.get("goal") or ""
                        if g:
                            top_goals[g] = top_goals.get(g, 0) + 1
                        a = rec.get("action_anchor") or {}
                        if isinstance(a, dict) and a.get("type") == "template":
                            try:
                                th = float(a.get("th", 0.82))
                                if th > 0.84:
                                    r_tight += 1
                                if th < 0.80:
                                    r_relax += 1
                            except Exception:
                                pass
            except Exception:
                pass
            # populate health from routes.jsonl
            if os.path.exists(routes_path):
                try:
                    with open(routes_path, 'r', encoding='utf-8') as rf:
                        for line in rf:
                            try:
                                rec = json.loads(line)
                            except Exception:
                                continue
                            key = f"{rec.get('sig_key','')}|{rec.get('goal','')}"
                            if key.strip('|'):
                                ent = health.setdefault(key, {'events': []})
                                ev = rec.get('event')
                                if ev in ('success','fail'):
                                    ent['events'].append(ev)
                except Exception:
                    pass

        html = [
            "<html><head><meta charset='utf-8'><title>MVP Run Report</title>",
            "<style>body{font-family:system-ui,Arial;margin:16px} .card{border:1px solid #eee;padding:10px;margin:10px 0;} .hdr{display:flex;gap:20px;align-items:center}</style>",
            "</head><body>",
            f"<h2>Run Report</h2><div class='hdr'><div><b>Steps:</b> {len(self.steps)}</div><div><b>OK:</b> {ok}</div><div><b>Fail:</b> {fail}</div><div><b>Total:</b> {total_ms} ms</div></div>",
        ]
        # Self-heal metrics block
        if r_total > 0:
            html.append("<div class='card'>")
            html.append("<div><b>Self-Heal Metrics</b></div>")
            html.append(f"<div>routes total: {r_total}; replay successes: {r_succ}; replay failures: {r_fail}; tightened: {r_tight}; relaxed: {r_relax}</div>")
            if top_goals:
                html.append("<div>top goals: ")
                items = sorted(top_goals.items(), key=lambda x: x[1], reverse=True)[:6]
                html.append(", ".join([f"{k}={v}" for k,v in items]))
                html.append("</div>")
            html.append("</div>")

        # Strategy metrics (minimal)
        if os.path.exists(strategies_path):
            s_total = s_succ = s_fail = 0
            s_src_mem = s_src_llm = 0
            try:
                with open(strategies_path, 'r', encoding='utf-8') as sf:
                    for line in sf:
                        try:
                            rec = json.loads(line)
                        except Exception:
                            continue
                        s_total += 1
                        ev = rec.get('event')
                        if ev == 'success':
                            s_succ += 1
                        elif ev == 'fail':
                            s_fail += 1
                        if (rec.get('source') or '').startswith('memory'):
                            s_src_mem += 1
                        elif (rec.get('source') or '').startswith('llm'):
                            s_src_llm += 1
            except Exception:
                pass
            if s_total > 0:
                html.append("<div class='card'>")
                html.append("<div><b>Strategy Layer</b></div>")
                rate = (s_succ / max(1, s_total)) * 100.0
                html.append(f"<div>records: {s_total}; success: {s_succ}; fail: {s_fail}; hit_rate={rate:.1f}%</div>")
                html.append(f"<div>source: memory={s_src_mem} ({(s_src_mem/max(1,s_total)*100):.1f}%), llm={s_src_llm} ({(s_src_llm/max(1,s_total)*100):.1f}%)</div>")
                html.append("</div>")
        # Run metrics (replay vs strategy vs LLM; autostep summaries)
        try:
            autosteps = [s for s in self.steps if isinstance(s.name, str) and s.name.startswith("autostep_")]
            n_auto = len(autosteps)
            n_comp = sum(1 for s in autosteps if isinstance(s.message, str) and "replay_compound ok" in s.message)
            n_legacy = sum(1 for s in autosteps if isinstance(s.message, str) and "replay_legacy ok" in s.message)
            n_strategy = sum(1 for s in autosteps if isinstance(s.message, str) and "strategy_exec ok" in s.message)
            n_llm = sum(1 for s in autosteps if isinstance(s.message, str) and "llm_picker" in s.message)
            n_fail = sum(1 for s in autosteps if s.status == "fail")
            direct_rate = (n_comp + n_legacy + n_strategy) / max(1, n_auto)
            downgrade_rate = n_llm / max(1, n_auto)
            html.append("<div class='card'>")
            html.append("<div><b>Run Metrics</b></div>")
            html.append(f"<div>autosteps={n_auto}; replay_compound={n_comp}; replay_legacy={n_legacy}; strategy_exec={n_strategy}; llm_picker={n_llm}; fails={n_fail}</div>")
            html.append(f"<div>direct_run_rate={(direct_rate*100):.1f}% &nbsp; downgrade_rate={(downgrade_rate*100):.1f}% &nbsp; error_click_rate={(n_fail/max(1,n_auto)*100):.1f}%</div>")
            html.append("</div>")
        except Exception:
            pass

        # Per-step S/Vote table rendering
        try:
            import re
            rows: Dict[int, Dict[str, str]] = {}
            for s in self.steps:
                if not isinstance(s.name, str):
                    continue
                m = re.match(r"autostep_(\d+)(?:_(.*))?", s.name)
                if not m:
                    # infer from message if it references autostep
                    continue
                idx = int(m.group(1))
                ent = rows.setdefault(idx, {"path": "", "S": "", "vote": "", "status": ""})
                msg = s.message or ""
                if "replay_compound ok" in msg:
                    ent["path"] = "compound"
                    ent["status"] = s.status or ent["status"]
                elif "replay_legacy ok" in msg:
                    ent["path"] = "legacy"
                    ent["status"] = s.status or ent["status"]
                elif "llm_picker" in msg:
                    ent["path"] = "llm"
                if s.name.endswith("_confirm") and msg.startswith("S="):
                    ent["S"] = msg
                if s.name.endswith("_state_vote") and "state_vote=" in msg:
                    ent["vote"] = msg
                # capture explicit success/fail
                if s.status in ("success", "fail"):
                    ent["status"] = s.status
            if rows:
                html.append("<div class='card'>")
                html.append("<div><b>Per-step Decisions</b></div>")
                html.append("<table style='border-collapse:collapse'>")
                html.append("<tr><th style='padding:4px 8px;border:1px solid #eee'>step</th><th style='padding:4px 8px;border:1px solid #eee'>path</th><th style='padding:4px 8px;border:1px solid #eee'>S(V1/V2/LLM)</th><th style='padding:4px 8px;border:1px solid #eee'>state_vote (tpl/ocr/url)</th><th style='padding:4px 8px;border:1px solid #eee'>status</th></tr>")
                for k in sorted(rows.keys()):
                    r = rows[k]
                    html.append(
                        f"<tr><td style='padding:4px 8px;border:1px solid #eee'>{k}</td>"
                        f"<td style='padding:4px 8px;border:1px solid #eee'>{r.get('path','')}</td>"
                        f"<td style='padding:4px 8px;border:1px solid #eee'>{(r.get('S',''))}</td>"
                        f"<td style='padding:4px 8px;border:1px solid #eee'>{(r.get('vote',''))}</td>"
                        f"<td style='padding:4px 8px;border:1px solid #eee'>{r.get('status','')}</td></tr>"
                    )
                html.append("</table>")
                html.append("</div>")
        except Exception:
            pass


        # Anchor Health (windowed)
        try:
            if health:
                html.append("<div class='card'>")
                html.append("<div><b>Anchor Health (recent)</b></div>")
                html.append("<table style='border-collapse:collapse'>")
                html.append("<tr><th style='padding:4px 8px;border:1px solid #eee'>route</th><th style='padding:4px 8px;border:1px solid #eee'>window</th><th style='padding:4px 8px;border:1px solid #eee'>success_rate</th></tr>")
                for k, ent in list(health.items())[:10]:
                    events = ent.get("events", [])[-50:]
                    total = len(events)
                    succ = sum(1 for e in events if e == "success")
                    rate = (succ / total) if total else 1.0
                    html.append(f"<tr><td style='padding:4px 8px;border:1px solid #eee'>{k}</td><td style='padding:4px 8px;border:1px solid #eee'>{total}</td><td style='padding:4px 8px;border:1px solid #eee'>{rate:.2f}</td></tr>")
                html.append("</table>")
                html.append("</div>")
        except Exception:
            pass
        for s in self.steps:
            html.append("<div class='card'>")
            html.append(f"<div><b>{s.name}</b> — <i>{s.status}</i> — {s.message}</div>")
            if s.chosen_cls or s.conf:
                html.append(f"<div>chosen: {s.chosen_cls or ''} conf={s.conf if s.conf is not None else ''}</div>")
            if s.click_xy:
                html.append(f"<div>click: {s.click_xy}</div>")
            imgs = "".join([img_tag(s.before_img), img_tag(s.overlay_img), img_tag(s.after_img)])
            if imgs:
                html.append(f"<div>{imgs}</div>")
            html.append("</div>")
        html.append("</body></html>")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(html))
        return path
