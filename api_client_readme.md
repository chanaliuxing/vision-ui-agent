通用（两种模式都一样）

  - Endpoint：POST http://localhost:8000/v1/pick，请求体是 JSON（最外层响应是 {ok,data,error}）
  - 关键字段：image.base64、capture.mode/screen_size/dpr、context.goal、options.*、idempotency_key

  准备图片 Base64（macOS / Linux）：

  IMG=s1.png
  # macOS
  IMG_B64=$(base64 -i "$IMG" | tr -d '\n')
  # Linux（择一）
  # IMG_B64=$(base64 -w 0 "$IMG")

  ———

  1) 默认模式（不使用 explain_all，等同 options.mode="pick"）

  API=http://localhost:8000
  GOAL="Find the search button"
  IDEM="pick-$(date +%s%3N)"

  # 按你的“逻辑屏幕尺寸”填；不确定就先用图片像素尺寸
  W=1920
  H=1080

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
    options: {
      max_candidates: 32,
      llm_timeout_ms: 300000,
      yolo: {conf: 0.1, iou: 0.45}
    },
    idempotency_key: $idem
  }')

  curl -sS -X POST "$API/v1/pick" \
    -H 'Content-Type: application/json' \
    --data "$PAYLOAD" | jq '.data.decision, .data.mapping_hint, .data.telemetry'

  你通常用这些字段：

  - 点击坐标：.data.decision.point_in_screen（推荐）或 .data.decision.point_in_capture
  - 框坐标：.data.decision.bbox_in_screen / .data.decision.bbox_in_capture

  ———

  2) explain_all 模式（返回每个编号元素的语义 + 坐标）

  API=http://localhost:8000
  GOAL="Explain what each numbered UI element is"
  IDEM="explain-$(date +%s%3N)"


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
    options: {
      mode: "explain_all",
      max_candidates: 16,
      llm_timeout_ms: 300000,
      yolo: {conf: 0.1, iou: 0.45}
    },
    idempotency_key: $idem
  }')

  curl -sS -X POST "$API/v1/pick" \
    -H 'Content-Type: application/json' \
    --data "$PAYLOAD" | jq '.data.explain, (.data.elements[:10] | map({id,label,description,point_in_screen,bbox_in_screen}))'

  explain_all 你关心的字段：

  - 语义列表：.data.elements[]（每项含 id/label/description + point_in_screen/bbox_in_screen）
  - LLM 元信息：.data.explain（ok/language/llm）

  ———

  3) 前端 API 集成变更（必读）

  目标：只改变“找不到可点击坐标”时的返回；正常可点击结果保持原样。

  兼容性结论：

  - 请求体不用改；前端不需要批量修改请求参数。
  - 响应外层仍是 `{ok,data,error}`，不变。
  - 正常命中时仍是 `action="click"` + 有效坐标，不变。
  - 新增/强化的是“不可点击”语义：`action="none"`。

  服务端默认行为（已启用）：

  - 默认阈值：`options.pick_min_conf = 0.6`（服务端默认值）。
  - 当候选置信度 `< 0.6`，返回：
    - `.data.decision.action = "none"`
    - `.data.decision.point_in_capture = [0,0]`
    - `.data.decision.reason = "Low confidence: ..."`
  - 这表示“本次没有可点击坐标”，客户端应跳过点击。

  前端最小改动（只改点击前判断）：

  - 以前：拿到 `point_in_capture` 就点击。
  - 现在：只有 `action === "click"` 才点击；否则走“未命中”分支。

  TypeScript 示例（推荐直接复用）：

  ```ts
  type PickResp = any;

  export function getClickablePoint(resp: PickResp): { ok: boolean; point?: [number, number]; reason?: string } {
    if (!resp?.ok) return { ok: false, reason: resp?.error?.message || "request_failed" };

    const decision = resp?.data?.decision;
    const action = decision?.action;
    const point = decision?.point_in_capture;

    if (action !== "click") {
      return { ok: false, reason: decision?.reason || `action_${String(action)}` };
    }
    if (!Array.isArray(point) || point.length !== 2) {
      return { ok: false, reason: "invalid_point" };
    }
    if (point[0] === 0 && point[1] === 0) {
      return { ok: false, reason: decision?.reason || "zero_point" };
    }
    return { ok: true, point: [point[0], point[1]] };
  }
  ```

  可选：覆盖默认阈值（单请求）

  ```json
  {
    "options": {
      "pick_min_conf": 0.75
    }
  }
  ```

  前端建议处理：

  - `action="none"`：不点击，走 `重试/滚动/展开菜单/人工接管`。
  - 记录 `decision.reason` + `decision.confidence` 到日志，便于定位“没坐标”的真实原因。
