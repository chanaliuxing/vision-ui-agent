#!/usr/bin/env bash
set -euo pipefail

# /v1/verify using verification_plan from a prior /v1/pick on s2.png
# Usage: API=http://127.0.0.1:8000 ./tools/api_tests/verify_s2.sh [image]

API=${API:-http://127.0.0.1:8000}
IMG=${1:-s2.png}

if ! command -v jq >/dev/null 2>&1; then echo "jq is required" >&2; exit 1; fi
if [ ! -f "$IMG" ]; then echo "Image not found: $IMG" >&2; exit 1; fi

# First, call /v1/pick to obtain a verification_plan
W=2560; H=1440
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

PICK_PAYLOAD=$(jq -n \
  --arg img "$IMG_B64" \
  '{
    image: {base64: $img, format: "png"},
    capture: {mode: "full", screen_size: [2560,1440], dpr: 1.0},
    context: {goal: "点击页面上的搜索", vars: {site: "xiaohongshu"}},
    options: {max_candidates: 48},
    idempotency_key: "t7-pick"
  }')

curl -s -o /tmp/verify_pick.json -X POST "$API/v1/pick" -H 'Content-Type: application/json' --data "$PICK_PAYLOAD"
PLAN=$(jq '.data.verification_plan' /tmp/verify_pick.json)

if [ -z "$PLAN" ] || [ "$PLAN" = "null" ]; then
  echo "No verification_plan available from pick; aborting" >&2
  exit 1
fi

# Now call /v1/verify with the same image (simulated post-click)
VERIFY_PAYLOAD=$(jq -n \
  --arg img "$IMG_B64" \
  --argjson plan "$PLAN" \
  '{
    image: {base64: $img, format: "png"},
    capture: {mode: "full", screen_size: [2560,1440], dpr: 1.0},
    context: {goal: "点击页面上的搜索", vars: {site: "xiaohongshu"}},
    expected: $plan,
    clicked: {point_in_capture: [100,100], bbox_in_capture: [90,90,110,110], candidate_id: "cand-xx"}
  }')

echo "POST $API/v1/verify"
HTTP=$(curl -s -o /tmp/verify_s2.json -w "%{http_code}" -X POST "$API/v1/verify" -H 'Content-Type: application/json' --data "$VERIFY_PAYLOAD")
echo "HTTP $HTTP"
cat /tmp/verify_s2.json | jq '.'

