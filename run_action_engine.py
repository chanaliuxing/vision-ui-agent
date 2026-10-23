#!/usr/bin/env python3
"""
Run Action Engine workflow with mock adapters for testing

Example:
  python run_action_engine.py --workflow examples/demo_loop_posts.json
"""

import argparse
import json
import time
from datetime import datetime

from core import ENGINE_VERSION
from core.flags import load_flags
from core.logging_setup import setup_logger
from core.artifacts import run_dir, snapshot_note
from core.context import Ctx, Services
from core.runner import WorkflowRunner
from core.mock_adapters import MockDomAdapter, MockOsAdapter, MockLogger

# Import all actions to register them
import actions.vars
import actions.flow
import actions.wait_scroll
import actions.exec
import actions.ext

def load_workflow(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    ap = argparse.ArgumentParser(description="Run Action Engine workflow")
    ap.add_argument("--workflow", default="examples/demo_loop_posts.json")
    ap.add_argument("--flags", help="Path to feature flags JSON file")
    args = ap.parse_args()

    # Setup logging and load flags
    logger = setup_logger()
    flags = load_flags(args.flags)

    # Create run ID and artifacts directory
    run_id = datetime.now().strftime("%Y-%m-%dT%H%M%SZ") + f"-{int(time.time() % 1000)}"
    artifacts_base = "artifacts"
    artifacts_dir = run_dir(artifacts_base, run_id)

    logger.info("Action Engine boot", extra={"flags": flags})
    logger.info(f"artifacts={artifacts_dir}")

    # Record startup
    snapshot_note(artifacts_dir, f"Action Engine v{ENGINE_VERSION} started with workflow {args.workflow}")

    # Create mock services
    dom_adapter = MockDomAdapter()
    os_adapter = MockOsAdapter()
    os_adapter._dom_adapter = dom_adapter  # 让OS适配器能访问DOM状态

    services = Services(
        dom=dom_adapter,
        os=os_adapter,
        vision=None,
        logger=MockLogger()
    )

    # Create context
    ctx = Ctx(
        services=services,
        run_id=run_id,
        artifacts_dir=str(artifacts_dir)
    )

    # Load and run workflow
    wf = load_workflow(args.workflow)
    runner = WorkflowRunner(wf, ctx)

    try:
        runner.run()
        snapshot_note(artifacts_dir, "Workflow completed successfully")
        logger.info("workflow completed successfully")
    except Exception as e:
        snapshot_note(artifacts_dir, f"Workflow failed: {e}")
        logger.error(f"workflow failed: {e}")
        raise

if __name__ == "__main__":
    main()