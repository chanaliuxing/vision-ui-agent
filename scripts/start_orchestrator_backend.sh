#!/usr/bin/env bash
set -euo pipefail

# Start Backend API (8787) and Orchestrator (8788) for DOM executor stack.
# Usage: ./scripts/start_orchestrator_backend.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"

ORCH=${ORCH:-"node"}

echo "[+] Starting Backend API on :8787 ..."
(
  cd "$ROOT_DIR/getcontent/backend" &&
  ${ORCH} src/index.js
) &
PID_API=$!

sleep 0.5
echo "[+] Starting Orchestrator on :8788 ..."
(
  cd "$ROOT_DIR/getcontent/backend" &&
  ${ORCH} orchestrator.js
) &
PID_ORCH=$!

echo "[i] PIDs: backend=$PID_API orchestrator=$PID_ORCH"
echo "[i] Health checks:"
echo "    curl -s http://127.0.0.1:8787/health"
echo "    curl -s http://127.0.0.1:8788/health"
echo "[i] ENV for engine: export EXT_ORCH_BASE=http://127.0.0.1:8788"

wait

