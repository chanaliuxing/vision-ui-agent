#!/usr/bin/env bash
set -euo pipefail

# Usage: tools/run_with_timeline.sh <your-workflow-command...>
# Guarantees a timeline is continuously refreshed while your workflow runs
# and finalizes one on exit (success, failure, or interruption).

RUN_ID=$(date +%Y%m%d_%H%M%S)
WATCH_INTERVAL=${TIMELINE_INTERVAL:-5}

# Start watcher in background
python3 tools/build_timeline.py --watch "$WATCH_INTERVAL" --run-id "$RUN_ID" &
WATCH_PID=$!

cleanup() {
  # Stop watcher and do a final one-shot refresh to ensure the latest state
  if kill -0 "$WATCH_PID" 2>/dev/null; then
    kill "$WATCH_PID" 2>/dev/null || true
    wait "$WATCH_PID" 2>/dev/null || true
  fi
  python3 tools/build_timeline.py --run-id "$RUN_ID" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

# Run the actual workflow command
if [[ $# -eq 0 ]]; then
  echo "No workflow command provided. Watcher is running; press Ctrl-C to stop." >&2
  # If no command, just run watcher until interrupted
  wait "$WATCH_PID"
else
  "$@"
fi
