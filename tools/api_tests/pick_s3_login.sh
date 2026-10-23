#!/usr/bin/env bash
set -euo pipefail

# /v1/pick on s3.png for login button
# Usage: API=http://127.0.0.1:8000 ./tools/api_tests/pick_s3_login.sh [image]

API=${API:-http://127.0.0.1:8000}
IMG=${1:-s3.png}
GOAL=${GOAL:-"点击登录按钮"}
SITE=${SITE:-"login_page"}
IDEM=${IDEM:-"t3-$(date +%s%3N)"}

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
  --arg site "$SITE" \
  --arg idem "$IDEM" \
  --argjson w "$W" \
  --argjson h "$H" \
  '{
    image: {base64: $img, format: "png"},
    capture: {mode: "full", screen_size: [$w,$h], dpr: 1.0},
    context: {goal: $goal, intent: "click", vars: {site: $site}},
    options: {max_candidates: 32},
    idempotency_key: $idem
  }')

echo "POST $API/v1/pick (s3 login)"
HTTP=$(curl -s -o /tmp/pick_s3_login.json -w "%{http_code}" -X POST "$API/v1/pick" -H 'Content-Type: application/json' --data "$PAYLOAD")
echo "HTTP $HTTP"
cat /tmp/pick_s3_login.json | jq '.data.decision, .data.telemetry'

