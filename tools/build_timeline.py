#!/usr/bin/env python3
"""
Build a concise chronological timeline from the out/logs folder.

Outputs to: out/timeline.log

Events aggregated (with timestamps when available):
- Route clicks and anchors (from routes.jsonl)
- Memory outcomes (from memory.jsonl)
- LLM picker/cross-confirm req/resp and final picks (from gemini_* and picker_* files)
- YOLO detections (from yolo_step_*.json and yolo_*.json)
- Denylist additions (searched heuristically; logged if found)

Notes:
- NDJSON files (routes.jsonl, memory.jsonl) provide absolute timestamps in ms.
- Other JSON files lack timestamps, so we use file modification time (mtime).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from glob import glob
from typing import Any, Dict, List, Optional, Tuple


LOG_ROOT = os.path.join("out", "logs")
# We will always write a per-run file into out/timelines with a timestamped name,
# and also refresh a convenience latest file at out/timeline.log
LATEST_OUT_FILE = os.path.join("out", "timeline.log")


def fmt_ts(ts_ms: float) -> str:
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000.0)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    except Exception:
        return f"{ts_ms:.0f}ms"


def file_mtime_ms(path: str) -> float:
    try:
        return os.path.getmtime(path) * 1000.0
    except FileNotFoundError:
        return 0.0


@dataclass
class Event:
    ts_ms: float
    src: str
    msg: str

    def line(self) -> str:
        return f"{fmt_ts(self.ts_ms)} - [{self.src}] {self.msg}"


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def add_routes_events(events: List[Event]) -> Tuple[int, int]:
    routes_path = os.path.join(LOG_ROOT, "routes.jsonl")
    anchors_count = 0
    clicks_count = 0
    if not os.path.exists(routes_path):
        return anchors_count, clicks_count
    with open(routes_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = float(obj.get("ts", 0))
            click_id = obj.get("click_id")
            goal = obj.get("goal")
            bbox = obj.get("bbox")
            verifier = obj.get("verifier")
            next_hint = obj.get("next_sig_hint", {})
            hint_url = next_hint.get("url")

            # anchors
            anchors = obj.get("anchors") or {}
            if anchors:
                anchors_count += 1
                a_type = anchors.get("type")
                method = anchors.get("method")
                th = anchors.get("th")
                roi = anchors.get("roi")
                events.append(
                    Event(
                        ts_ms=ts,
                        src="anchor",
                        msg=(
                            f"template_used type={a_type} method={method} th={th} "
                            f"roi={roi}"
                        ),
                    )
                )

            # click
            if click_id:
                clicks_count += 1
                events.append(
                    Event(
                        ts_ms=ts + 1e-3,  # ensure ordering after anchor at same ts
                        src="route/click",
                        msg=(
                            f"goal={goal} click_id={click_id} bbox={bbox} "
                            f"verifier={verifier} next_url_hint={hint_url}"
                        ),
                    )
                )
    return anchors_count, clicks_count


def add_memory_events(events: List[Event]) -> int:
    mem_path = os.path.join(LOG_ROOT, "memory.jsonl")
    if not os.path.exists(mem_path):
        return 0
    count = 0
    with open(mem_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = float(obj.get("ts", 0))
            click_id = obj.get("click_id")
            outcome = obj.get("outcome")
            reason = obj.get("reason")
            sig_key = obj.get("sig_key", "")
            url = None
            try:
                sk_obj = json.loads(sig_key)
                url = sk_obj.get("url")
            except Exception:
                # sig_key may be JSON-encoded string; if not parseable, skip url
                pass
            msg = f"memory: click_id={click_id} outcome={outcome} reason={reason}"
            if url:
                msg += f" url={url}"
            events.append(Event(ts_ms=ts, src="memory", msg=msg))
            count += 1
    return count


STEP_RE = re.compile(r"step_(\d+)")


def find_step_num(path: str) -> Optional[int]:
    m = STEP_RE.search(os.path.basename(path))
    return int(m.group(1)) if m else None


def add_llm_events(events: List[Event]) -> Tuple[int, int]:
    # picker req/resp
    picker_req = sorted(glob(os.path.join(LOG_ROOT, "gemini_*_picker_req_step_*.json")))
    picker_resp = sorted(glob(os.path.join(LOG_ROOT, "gemini_*_picker_resp_step_*.json")))
    xreq = sorted(glob(os.path.join(LOG_ROOT, "gemini_*_cross_confirm_req_step_*.json")))
    xresp = sorted(glob(os.path.join(LOG_ROOT, "gemini_*_cross_confirm_resp_step_*.json")))
    final_picks = sorted(glob(os.path.join(LOG_ROOT, "picker_final_step_*.json")))

    llm_calls = 0
    final_count = 0

    for path in picker_req:
        meta = load_json(path)
        step = find_step_num(path)
        model = f"{meta.get('provider')}/{meta.get('model')}"
        image = None
        # Picker req sometimes includes an image path
        if isinstance(meta.get("image"), str):
            image = meta["image"]
        ts = file_mtime_ms(path)
        events.append(Event(ts_ms=ts, src="llm/picker_req", msg=f"step={step} model={model} image={image}"))
        llm_calls += 1

    for path in picker_resp:
        meta = load_json(path)
        step = find_step_num(path)
        ts = file_mtime_ms(path)
        # Try to extract id/why/confidence
        summary = None
        if isinstance(meta.get("extracted_text"), str):
            txt = meta["extracted_text"]
            # best-effort: look for id and confidence in JSON-like text
            mid = re.search(r'"id"\s*:\s*"?([a-zA-Z0-9_]+)"?', txt)
            mwhy = re.search(r'"why"\s*:\s*"([^"]{0,64})"', txt)
            mconf = re.search(r'"confidence"\s*:\s*([0-9.]+)', txt)
            parts = []
            if mid:
                parts.append(f"id={mid.group(1)}")
            if mwhy:
                parts.append(f"why={mwhy.group(1)}")
            if mconf:
                parts.append(f"conf={mconf.group(1)}")
            if parts:
                summary = " ".join(parts)
        if not summary:
            summary = "parsed picker response"
        events.append(Event(ts_ms=ts, src="llm/picker_resp", msg=f"step={step} {summary}"))
        llm_calls += 1

    for path in xreq:
        meta = load_json(path)
        step = find_step_num(path)
        model = f"{meta.get('provider')}/{meta.get('model')}"
        ts = file_mtime_ms(path)
        events.append(Event(ts_ms=ts, src="llm/confirm_req", msg=f"step={step} model={model}"))
        llm_calls += 1

    for path in xresp:
        meta = load_json(path)
        step = find_step_num(path)
        ts = file_mtime_ms(path)
        # Try to extract is_expected/prev_action_ok
        summary = None
        if isinstance(meta.get("extracted_text"), str):
            txt = meta["extracted_text"]
            mie = re.search(r'"is_expected"\s*:\s*(true|false)', txt)
            mpok = re.search(r'"prev_action_ok"\s*:\s*(true|false)', txt)
            mwhy = re.search(r'"why"\s*:\s*"([^"]{0,64})"', txt)
            parts = []
            if mie:
                parts.append(f"is_expected={mie.group(1)}")
            if mpok:
                parts.append(f"prev_action_ok={mpok.group(1)}")
            if mwhy:
                parts.append(f"why={mwhy.group(1)}")
            if parts:
                summary = " ".join(parts)
        if not summary:
            summary = "parsed confirm response"
        events.append(Event(ts_ms=ts, src="llm/confirm_resp", msg=f"step={step} {summary}"))
        llm_calls += 1

    for path in final_picks:
        meta = load_json(path)
        step = find_step_num(path)
        ts = file_mtime_ms(path)
        parsed = meta.get("parsed") or {}
        fid = parsed.get("id")
        why = parsed.get("why")
        conf = parsed.get("confidence")
        events.append(Event(ts_ms=ts, src="picker_final", msg=f"step={step} id={fid} why={why} conf={conf}"))
        final_count += 1

    return llm_calls, final_count


def add_yolo_events(events: List[Event]) -> int:
    count = 0
    for path in sorted(glob(os.path.join(LOG_ROOT, "yolo_step_*.json")) + glob(os.path.join(LOG_ROOT, "yolo_*.json"))):
        try:
            meta = load_json(path)
        except Exception:
            continue
        step = find_step_num(path)
        t = file_mtime_ms(path)
        time_ms = meta.get("time_ms")
        detections = meta.get("detections") or []
        events.append(
            Event(
                ts_ms=t,
                src="yolo",
                msg=f"step={step} time_ms={time_ms} detections={len(detections)} file={os.path.basename(path)}",
            )
        )
        count += 1
    return count


def scan_denylist(events: List[Event]) -> int:
    # Heuristic: search for files/lines mentioning denylist-like keywords
    keywords = ("denylist", "deny_list", "blacklist", "blocked")
    found = 0
    for path in glob(os.path.join(LOG_ROOT, "**", "*"), recursive=True):
        if not os.path.isfile(path):
            continue
        base = os.path.basename(path).lower()
        if any(k in base for k in keywords):
            t = file_mtime_ms(path)
            events.append(Event(ts_ms=t, src="denylist", msg=f"file={os.path.relpath(path)}"))
            found += 1
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f):
                    low = line.lower()
                    if any(k in low for k in keywords):
                        t = file_mtime_ms(path)
                        events.append(
                            Event(
                                ts_ms=t,
                                src="denylist",
                                msg=f"mention in {os.path.relpath(path)} line {i+1}: {line.strip()[:120]}",
                            )
                        )
                        found += 1
                        break  # one hit per file is enough
        except Exception:
            pass
    return found


def write_timeline(per_run_path: str,
                   latest_path: str,
                   events: List[Event],
                   anchors_count: int,
                   clicks_count: int,
                   mem_count: int,
                   llm_calls: int,
                   final_count: int,
                   yolo_count: int,
                   deny_hits: int) -> None:
    os.makedirs(os.path.dirname(per_run_path), exist_ok=True)
    with open(per_run_path, "w", encoding="utf-8") as out:
        out.write("# Timeline summary\n")
        out.write(f"anchors_used: {anchors_count}\n")
        out.write(f"clicks: {clicks_count}\n")
        out.write(f"memory_events: {mem_count}\n")
        out.write(f"llm_events: {llm_calls} (picker/cross-confirm req+resp)\n")
        out.write(f"picker_final_steps: {final_count}\n")
        out.write(f"yolo_runs: {yolo_count}\n")
        out.write(f"denylist_mentions: {deny_hits}\n")
        out.write(f"generated_at: {datetime.now().isoformat(timespec='seconds')}\n")
        out.write("\n# Chronological events\n")
        for ev in events:
            out.write(ev.line() + "\n")

    # Also refresh latest
    os.makedirs(os.path.dirname(latest_path), exist_ok=True)
    with open(latest_path, "w", encoding="utf-8") as out:
        with open(per_run_path, "r", encoding="utf-8") as src:
            out.write(src.read())


def main() -> None:
    events: List[Event] = []

    anchors_count, clicks_count = add_routes_events(events)
    mem_count = add_memory_events(events)
    llm_calls, final_count = add_llm_events(events)
    yolo_count = add_yolo_events(events)
    deny_hits = scan_denylist(events)

    # sort by timestamp, then by src to stabilize ordering
    events.sort(key=lambda e: (e.ts_ms, e.src))

    # Prepare output paths
    from argparse import ArgumentParser
    ap = ArgumentParser(description="Build a chronological timeline log from out/logs")
    ap.add_argument("--outdir", default=os.path.join("out", "timelines"), help="Directory for per-run timeline files")
    ap.add_argument("--prefix", default="timeline_", help="Filename prefix inside outdir")
    ap.add_argument("--run-id", default=None, help="Use a stable run id for per-run filename (default: start timestamp)")
    ap.add_argument("--watch", type=float, default=None, help="Seconds interval to continuously refresh timeline (Ctrl-C to stop)")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    per_run_path = os.path.join(args.outdir, f"{args.prefix}{run_id}.log")

    def once():
        # Re-scan logs each time in case files updated during watch
        evs: List[Event] = []
        a_count, c_count = add_routes_events(evs)
        m_count = add_memory_events(evs)
        l_calls, f_count = add_llm_events(evs)
        y_count = add_yolo_events(evs)
        d_hits = scan_denylist(evs)
        evs.sort(key=lambda e: (e.ts_ms, e.src))
        write_timeline(per_run_path, LATEST_OUT_FILE, evs, a_count, c_count, m_count, l_calls, f_count, y_count, d_hits)

    if args.watch and args.watch > 0:
        try:
            while True:
                once()
                print(f"Refreshed {per_run_path} -> {LATEST_OUT_FILE}")
                import time
                time.sleep(args.watch)
        except KeyboardInterrupt:
            # Final write on interrupt
            once()
            print(f"Finalized {per_run_path} and {LATEST_OUT_FILE}")
    else:
        once()
        print(f"Wrote {per_run_path} and updated {LATEST_OUT_FILE}")


if __name__ == "__main__":
    main()
