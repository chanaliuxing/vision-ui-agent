#!/usr/bin/env bash
# One-click starter for the coordinate API stack.
# Starts the FastAPI YOLO service (and optional OCR) so you can call the API and get coordinates.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/myenv}"
PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/out/logs}"
PID_DIR="${PID_DIR:-$PROJECT_ROOT/out/pids}"

START_OCR=0

usage() {
    echo "Usage: $0 [--with-ocr|--no-ocr]"
    echo "  --with-ocr   start app_ocr.py on port 8001 (requires OCR deps)"
    echo "  --no-ocr     skip OCR service (default)"
}

for arg in "$@"; do
    case "$arg" in
        --with-ocr) START_OCR=1 ;;
        --no-ocr) START_OCR=0 ;;
        -h|--help) usage; exit 0 ;;
        *) usage; exit 1 ;;
    esac
done

info() { printf "ℹ️  %s\n" "$*"; }
ok() { printf "✅ %s\n" "$*"; }
warn() { printf "⚠️  %s\n" "$*"; }
err() { printf "❌ %s\n" "$*"; }

ensure_paths() {
    mkdir -p "$LOG_DIR" "$PID_DIR" "$PROJECT_ROOT/out"
}

ensure_weights() {
    local weights_path="$PROJECT_ROOT/weights/model.pt"
    if [ ! -f "$weights_path" ]; then
        err "YOLO weights not found at $weights_path"
        err "Place your model at weights/model.pt (or update WEIGHTS in app.py) before starting."
        exit 1
    fi
}

ensure_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        info "Creating virtualenv at $VENV_DIR"
        python3 -m venv "$VENV_DIR"
    fi

    # shellcheck disable=SC1090
    source "$VENV_DIR/bin/activate"

    if ! "$PYTHON_BIN" -c "import uvicorn, fastapi" >/dev/null 2>&1; then
        info "Installing Python dependencies..."
        "$PIP_BIN" install -r "$PROJECT_ROOT/requirements.txt"
    fi
}

start_uvicorn_service() {
    local name="$1" module="$2" port="$3"
    local pid_file="$PID_DIR/${name}.pid"
    local log_file="$LOG_DIR/${name}.log"

    if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        ok "$name already running (PID $(cat "$pid_file")), skipping"
        return
    fi

    info "Starting $name on :$port"
    nohup "$PYTHON_BIN" -m uvicorn "$module" --host 0.0.0.0 --port "$port" --log-level info > "$log_file" 2>&1 &
    echo $! > "$pid_file"
    ok "$name started (PID $(cat "$pid_file")), logs: $log_file"
}

wait_for_health() {
    local name="$1" url="$2"
    for i in {1..20}; do
        if curl -fs "$url" >/dev/null 2>&1; then
            ok "$name healthy at $url"
            return
        fi
        sleep 0.5
    done
    warn "$name did not report healthy (last tried $url); check logs."
}

main() {
    cd "$PROJECT_ROOT"
    ensure_paths
    ensure_weights
    ensure_venv

    start_uvicorn_service "yolo_api" "app:app" 8000

    if [ "$START_OCR" -eq 1 ]; then
        start_uvicorn_service "ocr_api" "app_ocr:app" 8001
    else
        warn "OCR service skipped (pass --with-ocr to start it)"
    fi

    wait_for_health "YOLO API" "http://127.0.0.1:8000/health"
    if [ "$START_OCR" -eq 1 ]; then
        wait_for_health "OCR API" "http://127.0.0.1:8001/health"
    fi

    cat <<EOF

📡 Services are up:
  - YOLO API:   http://127.0.0.1:8000 (health at /health)
  - OCR API:    http://127.0.0.1:8001 (if started)

Call the coordinate picker:
  curl -X POST http://127.0.0.1:8000/v1/pick \\
    -H "Content-Type: application/json" \\
    -d @your_request.json

Call the basic detector:
  curl -F image=@sample.png "http://127.0.0.1:8000/predict?return_image=false"

PID files are in $PID_DIR. Stop with: kill \$(cat $PID_DIR/yolo_api.pid) [and ocr_api.pid if used].
EOF
}

main "$@"
