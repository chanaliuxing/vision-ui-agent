#!/usr/bin/env bash
set -euo pipefail

# Simple /v1/pick test against a remote API using s1.png
# Usage: API=http://127.0.0.1:8000 ./tools/api_tests/pick_s1.sh [image]

API=${API:-http://127.0.0.1:8000}
IMG=${1:-s1.png}
GOAL=${GOAL:-"点击搜索按钮"}
IDEM=${IDEM:-"pick-$(date +%s%3N)"}
MODE=${MODE:-"pick"}

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required" >&2; exit 1
fi
if [ ! -f "$IMG" ]; then
  echo "Image not found: $IMG" >&2; exit 1
fi

# Determine image size (best-effort)
W=1920; H=1080
if command -v identify >/dev/null 2>&1; then
  read W H < <(identify -format "%w %h" "$IMG")
elif command -v sips >/dev/null 2>&1; then
  W=$(sips -g pixelWidth  "$IMG" 2>/dev/null | awk '/pixelWidth/{print $2}')
  H=$(sips -g pixelHeight "$IMG" 2>/dev/null | awk '/pixelHeight/{print $2}')
fi

# Base64 the image (no newlines)
if base64 -h 2>&1 | grep -q "-i"; then
  IMG_B64=$(base64 -i "$IMG" | tr -d '\n')
else
  IMG_B64=$(base64 "$IMG" | tr -d '\n')
fi

PAYLOAD=$(jq -n \
  --arg img "$IMG_B64" \
  --arg goal "$GOAL" \
  --arg idem "$IDEM" \
  --arg mode "$MODE" \
  --argjson w "$W" \
  --argjson h "$H" \
  '{
    image: {base64: $img, format: "png"},
    capture: {mode: "full", screen_size: [$w,$h], dpr: 1.0},
    context: {goal: $goal},
    options: {mode: $mode, max_candidates: 32, yolo: {conf: 0.35, iou: 0.45}},
    idempotency_key: $idem
  }')

echo "POST $API/v1/pick"
HTTP=$(curl -s -o /tmp/pick_s1.json -w "%{http_code}" -X POST "$API/v1/pick" \
  -H 'Content-Type: application/json' \
  --data "$PAYLOAD")
echo "HTTP $HTTP"

cat /tmp/pick_s1.json | jq '.data.decision, .data.mapping_hint, .data.telemetry'

# Save anchor proposal if present
ANCHOR=$(jq -e '.data.anchor_proposal' /tmp/pick_s1.json || true)
if [ -n "$ANCHOR" ] && [ "$ANCHOR" != "null" ]; then
  mkdir -p out
  echo "$ANCHOR" | jq '.' > out/anchor_from_pick.json
  echo "Saved anchor -> out/anchor_from_pick.json"
fi
