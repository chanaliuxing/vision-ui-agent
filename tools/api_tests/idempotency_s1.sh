#!/usr/bin/env bash
set -euo pipefail

# Send the same /v1/pick request twice with the same idempotency_key
# Usage: API=http://127.0.0.1:8000 ./tools/api_tests/idempotency_s1.sh [image]

API=${API:-http://127.0.0.1:8000}
IMG=${1:-s1.png}
GOAL=${GOAL:-"点击搜索按钮"}
IDEM=${IDEM:-"idem-$(date +%s%3N)"}

if ! command -v jq >/dev/null 2>&1; then echo "jq is required" >&2; exit 1; fi
if [ ! -f "$IMG" ]; then echo "Image not found: $IMG" >&2; exit 1; fi

W=1920; H=1080
if command -v identify >/dev/null 2>&1; then
  read W H < <(identify -format "%w %h" "$IMG")
elif command -v sips >/dev/null 2>&1; then
  W=$(sips -g pixelWidth  "$IMG" 2>/dev/null | awk '/pixelWidth/{print $2}')
  H=$(sips -g pixelHeight "$IMG" 2>/dev/null | awk '/pixelHeight/{print $2}')
fi

if base64 -h 2>&1 | grep -q "-i"; then
  IMG_B64=$(base64 -i "$IMG" | tr -d '\n')
else
  IMG_B64=$(base64 "$IMG" | tr -d '\n')
fi

PAYLOAD=$(jq -n \
  --arg img "$IMG_B64" \
  --arg goal "$GOAL" \
  --arg idem "$IDEM" \
  --argjson w "$W" \
  --argjson h "$H" \
  '{
    image: {base64: $img, format: "png"},
    capture: {mode: "full", screen_size: [$w,$h], dpr: 1.0},
    context: {goal: $goal},
    options: {max_candidates: 32, yolo: {conf: 0.35, iou: 0.45}},
    idempotency_key: $idem
  }')

echo "First POST $API/v1/pick idem=$IDEM"
curl -s -o /tmp/pick_idem_1.json -w "HTTP %{http_code}\n" -X POST "$API/v1/pick" -H 'Content-Type: application/json' --data "$PAYLOAD"
echo "Second POST $API/v1/pick idem=$IDEM"
curl -s -o /tmp/pick_idem_2.json -w "HTTP %{http_code}\n" -X POST "$API/v1/pick" -H 'Content-Type: application/json' --data "$PAYLOAD"

echo "Second response cache_hit:"
jq -r '.data.telemetry.cache_hit' /tmp/pick_idem_2.json

