#!/usr/bin/env python3
"""
Run a JSON-defined workflow using the minimal engine.

Example:
  python run_workflow.py --workflow flows/xhs_workflow.json --endpoint http://127.0.0.1:8000
"""

import argparse
import os
import time
from datetime import datetime

try:
    # Load .env so LLM/endpoint settings are picked up when running locally
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from core import ENGINE_VERSION
from core.flags import load_flags
from core.logging_setup import setup_logger
from core.artifacts import run_dir, snapshot_note
from core.workflow import WFConfig, WorkflowRunner, load_workflow


def main():
    ap = argparse.ArgumentParser(description="Run JSON workflow")
    ap.add_argument("--workflow", default=os.getenv("WORKFLOW", "flows/xhs_workflow.json"))
    ap.add_argument("--endpoint", default=os.getenv("YOLO_ENDPOINT", "http://127.0.0.1:8000"))
    ap.add_argument("--conf", type=float, default=float(os.getenv("CONF_MIN", 0.5)))
    ap.add_argument("--imgsz", type=int, default=int(os.getenv("YOLO_IMGSZ", 1280)))
    ap.add_argument("--timeout", type=float, default=float(os.getenv("WAIT_TIMEOUT_S", 8)))
    ap.add_argument("--shot-wait", dest="shot_wait", type=float, default=float(os.getenv("SCREENSHOT_WAIT_S", 6.0)))
    ap.add_argument("--poll", type=float, default=float(os.getenv("POLL_INTERVAL_S", 0.6)))
    ap.add_argument("--flags", help="Path to feature flags JSON file")
    args = ap.parse_args()

    # Setup logging and load flags
    logger = setup_logger()
    flags = load_flags(args.flags)

    # Create run ID and artifacts directory
    run_id = datetime.now().strftime("%Y-%m-%dT%H%M%SZ") + f"-{int(time.time() % 1000)}"
    artifacts_base = "artifacts"
    artifacts_dir = run_dir(artifacts_base, run_id)

    logger.info("engine boot", extra={"flags": flags})
    logger.info(f"artifacts={artifacts_dir}")

    # Record startup
    snapshot_note(artifacts_dir, f"Engine v{ENGINE_VERSION} started with workflow {args.workflow}")

    wf = load_workflow(args.workflow)
    cfg = WFConfig(conf_min=args.conf, poll_interval_s=args.poll, wait_timeout_s=args.timeout, imgsz=args.imgsz, screenshot_wait_s=args.shot_wait)
    runner = WorkflowRunner(workflow=wf, endpoint=args.endpoint, cfg=cfg)

    start = wf.get("start") or wf.get("workflow", {}).get("start") or "home"
    if "states" not in wf and "workflow" in wf:
        # if provided in nested schema, unwrap
        wf2 = wf.get("workflow")
        wf_flat = {"start": wf2.get("start"), "states": wf2.get("states")}
        runner.workflow = wf_flat
        start = wf_flat.get("start", start)

    try:
        runner.run(start_state=start)
        snapshot_note(artifacts_dir, "Workflow completed successfully")
        logger.info("workflow completed successfully")
    except Exception as e:
        snapshot_note(artifacts_dir, f"Workflow failed: {e}")
        logger.error(f"workflow failed: {e}")
        raise


if __name__ == "__main__":
    main()
