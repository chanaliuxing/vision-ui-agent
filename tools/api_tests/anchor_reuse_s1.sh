#!/usr/bin/env bash
set -euo pipefail

# Reuse saved anchor to hit fast path on /v1/pick
# Usage: API=http://127.0.0.1:8000 ./tools/api_tests/anchor_reuse_s1.sh [image]

API=${API:-http://127.0.0.1:8000}
IMG=${1:-s1.png}
GOAL=${GOAL:-"点击搜索按钮"}
IDEM=${IDEM:-"t5-anchor-$(date +%s%3N)"}
ANCHOR_FILE=${ANCHOR_FILE:-out/anchor_from_pick.json}

if ! command -v jq >/dev/null 2>&1; then echo "jq is required" >&2; exit 1; fi
if [ ! -f "$IMG" ]; then echo "Image not found: $IMG" >&2; exit 1; fi
if [ ! -f "$ANCHOR_FILE" ]; then echo "Anchor file not found: $ANCHOR_FILE" >&2; exit 1; fi

# Use anchor's norm_ref as screen size baseline
W=$(jq -r '.norm_ref.w' "$ANCHOR_FILE")
H=$(jq -r '.norm_ref.h' "$ANCHOR_FILE")
if [ -z "$W" ] || [ -z "$H" ] || [ "$W" = "null" ] || [ "$H" = "null" ]; then
  W=1920; H=1080
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
  --argfile anchor "$ANCHOR_FILE" \
  --argjson w "$W" \
  --argjson h "$H" \
  '{
    image: {base64: $img, format: "png"},
    capture: {mode: "full", screen_size: [$w,$h], dpr: 1.0},
    context: {goal: $goal},
    anchors_known: [$anchor],
    options: {max_candidates: 24},
    idempotency_key: $idem
  }')

echo "POST $API/v1/pick (anchor reuse)"
HTTP=$(curl -s -o /tmp/pick_s1_anchor.json -w "%{http_code}" -X POST "$API/v1/pick" \
  -H 'Content-Type: application/json' \
  --data "$PAYLOAD")
echo "HTTP $HTTP"

cat /tmp/pick_s1_anchor.json | jq '.data.decision, .data.telemetry'

