#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1090
source ".venv/bin/activate"

pip install -r requirements.txt

export YOLO_WEIGHTS=${YOLO_WEIGHTS:-weights/model.pt}

echo "Starting API on http://0.0.0.0:8000 (weights: $YOLO_WEIGHTS)"
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
