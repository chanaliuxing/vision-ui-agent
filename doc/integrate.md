我需要把目前的项目集成到legalchatbot，基于目前代码骨架（`app.py / action_engine.py / anchors.py / executor.py / llm_client.py / runner.py / workflow.py / services.py / prompt_builder.py`），我给你一份**可直接落地到 YOLO 端的 API 详细方案**。它把“YOLO+LLM+DOM 融合决策、锚点学习、点击后验证、AutoStep 补丁建议”都统一到一个服务里，同时和你现有模块对齐，尽量少改动、清晰分层、易扩展。

下面是完整落地设计（接口规范 + 代码落点 + 模块职责 + 误差/坐标处理 + 日志与计费钩子 + 测试清单）。你可以按章节一步步实现。

---

# 0. 设计目标（结合你的重构思路）

1. **客户端仅执行**（PyAutoGUI 点击/输入/滚动），截图与上下文发到 YOLO 端。
2. **YOLO 端**做识别→候选→LLM 决策→产出**点击点**与**锚点提案**，并负责**点击结果验证**与**锚点锁定**。
3. 命中锚点 → 快速返回；不命中 → YOLO+LLM；多次失败 → **AutoStep 补丁/改写建议**。
4. 接口**稳定**，请求/响应字段**可演进**；支持**窗口截图**坐标换算、**DPR**、**幂等**、**计费**、**风控**。

---

# 1. 顶层 API 形态（v1）

> 推荐挂在现有 `app.py` 的 FastAPI 里（保持你已有的 `/health`、`/predict` 等）。新加以下路由。

## 1.1 `/v1/pick`（端到端 YOLO+LLM 决策）

* **用途**：给定截图 + 目标意图（goal/intent/历史），直接返回**在该截图坐标系下**可点击点/框、锚点提案、验证计划。
* **方法**：`POST application/json` 或 `multipart/form-data`（图片大时选后者）。
* **请求体**（Pydantic 模型建议名：`PickRequest`）：

```json
{
  "image": {"base64": "<...>", "format": "png"},                 // 或 multipart file
  "capture": {
    "mode": "full | active_window | region",
    "screen_size": [2560, 1440],                                 // 屏幕逻辑尺寸（点）
    "window_offset": [100, 80],                                   // 仅 window/region 必填（逻辑坐标）
    "window_size": [1220, 900],                                   // 仅 window/region 必填
    "dpr": 2.0                                                    // 设备像素比
  },
  "context": {
    "workflow_id": "wf_123",
    "step_id": "step_login_submit",
    "goal": "登录账户",                                           // 任务目标（prompt 主轴）
    "intent": "click_submit",                                     // 动作意图（短语）
    "vars": {"site": "example.com"},
    "history": [{"t":"click","target":"username_input"}],
    "allow_rewrite": true,                                        // 是否允许 AutoStep 改写建议
    "dom_hints": { "css": ["button[type=submit]"], "text": ["登录","Sign in"] } // 可选（来自扩展/回放）
  },
  "anchors_known": [                                              // 可选：客户端已有的锚点（命中则快返）
    {"id":"login_submit_v1","fingerprint":"sha1:...","norm_ref":{"kind":"window","w":1220,"h":900}}
  ],
  "options": {
    "mode": "pick | explain_all",
    "timeout_ms": 3500,
    "max_candidates": 32,
    "yolo": {"conf": 0.35, "iou": 0.45},
    "llm_provider": "gemini",
    "return_overlay": false
  },
  "idempotency_key": "uuid-req-001"                               // 幂等键（计费/防重）
}
```

* **响应体**（`PickResponse`）：

```json
{
  "decision": {
    "action": "click",
    "bbox_in_capture": [x0, y0, x1, y1],
    "point_in_capture": [xc, yc],
    "confidence": 0.92,
    "reason": "LLM picked candidate#3 (text≈'登录')"
  },
  "mapping_hint": { "apply_window_offset": true, "expects_dpr": 2.0 },
  "anchor_proposal": {
    "id": "login_submit_v1",
    "type": "compound",
    "descriptors": {
      "template_hash": "sha1:...",
      "orb": {"kpts": 128, "desc_hash": "sha1:..."},
      "color_hist": "sha1:..."},
    "norm_ref": {"kind": "window","w":1220,"h":900},
    "norm_bbox": [0.42,0.78,0.56,0.84],
    "dom_hints": {"css":["button[type=submit]"],"text":["登录","Sign in"]}
  },
  "verification_plan": {
    "expect_text_any": ["登录成功","Dashboard"],
    "expect_absent": ["密码错误","try again"],
    "timeout_ms": 5000,
    "post_delay_ms": 300
  },
  "telemetry": {"req_id":"uuid-req-001","cache_hit": false, "stage_lat_ms": {"yolo":14,"llm":120}}
}
```

> **Explain All 模式**：当 `options.mode="explain_all"` 时，响应会额外包含 `elements[]`（每个元素包含 `id/label/description` 及其 `bbox/point` 坐标），用于“先识别所有元素 → LLM 逐个解释用途”的场景。

> **客户端坐标映射**（窗口截图 → 屏幕）：
> `P_screen = (ox + xc, oy + yc)`（如上传的是物理像素，需再除以 `dpr`；见第 4 章）

---

## 1.2 `/v1/verify`（点击后验证 + 锚点锁定）

* **用途**：客户端执行点击后上传**新截图**，YOLO 端判断是否达成预期（文本/结构/状态），并返回**可锁定锚点**（可用于长期复用）。
* **请求体**（`VerifyRequest`）：

```json
{
  "image": {"base64": "<post-shot>", "format": "png"},
  "capture": {"mode":"full","screen_size":[2560,1440],"dpr":2.0},
  "context": {"workflow_id":"wf_123","step_id":"step_login_submit"},
  "expected": {
    "anchor_id": "login_submit_v1",
    "verification_plan": {"expect_text_any":["Dashboard"],"timeout_ms":0}
  },
  "clicked": {"point_in_screen":[1334,1120], "from":"anchor_cache | pick_api"}
}
```

* **响应体**（`VerifyResponse`）：

```json
{
  "pass": true,
  "reason": "Detected 'Dashboard' and url_change",
  "lock_anchor": {
    "id": "login_submit_v1",
    "norm_bbox": [0.418,0.777,0.562,0.842],
    "descriptors_delta": {"orb_patch":"sha1:...","template_hash":"sha1:new..."},
    "version": 3
  },
  "telemetry": {"latency_ms": 210}
}
```

---

## 1.3 `/v1/anchors/resolve`（极速锚点解析）

* **用途**：仅用锚点进行定位（模板/ORB/关系），命中即返回点位；不命中 → 返回 `miss=true` 由客户端转 `/v1/pick`。
* **请求体**（`AnchorResolveRequest`）：

```json
{"image": {"base64":"<...>","format":"png"}, "anchors": [ { ... } ], "capture": {...} }
```

* **响应体**：

```json
{"hit": true, "point_in_capture": [x,y], "confidence": 0.88, "anchor_id": "login_submit_v1"}
```

---

## 1.4 `/v1/autostep/patch-proposal`（失败后改写建议）

* **用途**：多次 `/pick`+`/verify` 失败后，请求受限补丁建议（仅**白名单**类：插入 `WaitQuiet`、`scroll_then_retry`、**追加** selector/text 等）。
* **请求体**：包含近 N 步轨迹、最后失败截图、失败分类（`target_not_found`/`timing_issue` 等）、`allow_rewrite`。
* **响应体**：`{ "patches": [...], "risk": "low|medium|high", "reason": "..." }`

> 客户端/编排器只在 `allow_rewrite=true` 且 **step 未标记禁止** 时，调用 WAM/AutoFix 落盘；否则仅提示。

---

## 1.5 `/v1/anchors/lock`（可选，云端汇聚）

* 客户端把已验证通过的锚点上报云端（联邦学习/多设备复用），可加 `host/app/scope` 维度。

---

## 1.6 其他

* `/health`（已存在）：聚合各子服务状态（YOLO/LLM/Anchors/OCR）；返回 `{ok: true, deps: {...}}`
* `/metrics`（Prometheus 文本或 JSON）：QPS、命中率、p95/p99、各阶段耗时

---

# 2. 服务分层与代码落点

> 尽量复用你已有模块，新增最薄适配层。

## 2.1 Orchestrator（新增，YOLO 端主协调）

* **文件**：`orchestrator.py`（新）
* **职责**：

  1. 解码输入截图 → 调 `DetectorService`（YOLO）→ 候选
  2. 构建 prompt（`prompt_builder.PromptSpec`）+ 组织 candidate JSON
  3. 调 `LLMService`（`llm_client.LLMClient`）→ 产出 click\_id/score
  4. 生成 `decision`/`anchor_proposal`/`verification_plan`
  5. 命中**锚点缓存**时提前返回（`AnchorsService.quick_match`），不命中再走 YOLO+LLM
* **内部依赖**：

  * `anchors.py`：模板/ORB/关系匹配、锚点描述生成与校验
  * `prompt_builder.py`：构建候选 JSON + 规则/安全约束
  * `llm_client.py`：LLM 统一调用（Gemini/OpenAI）
  * `services.py`：可做依赖注入与上下文

> **实现提示**：
> 你已有 `prompt_builder.PromptSpec`、`llm_client.LLMClient`、`anchors.py` 的能力足够；Orchestrator 只需要拼装 I/O 和把候选规整为 LLM 输入（`prompt_builder` 的 OUTPUT\_SCHEMA 已经定义了返回字段，直接解析）。

## 2.2 DetectorService（封装 YOLO）

* **文件**：扩展现有 `app.py` 或新建 `detector_service.py`
* **职责**：

  * `run_yolo(image, conf, iou, imgsz) -> List[Candidate]`
  * 输出结构：`{"id":"cand_1","xyxy":[x0,y0,x1,y1],"cls":"button","text_hint":null,"score":0.78}`
  * **排序**：使用 `_sort_indices_tl`（你 `app.py` 里已有 Top->Bottom, Left->Right 辅助）

## 2.3 AnchorsService（封装 anchors.py）

* **文件**：`anchors_service.py`（新）
* **职责**：

  * `quick_match(image, anchors) -> Optional[(point, confidence, id)]`
  * `propose_anchor(image, decision, dom_hints) -> AnchorProposal`
  * `verify_anchor(image, anchor) -> score`
  * `lock_anchor(old, delta) -> new`（版本+1 / 更新 descriptors）

> 你已有 `anchors.py`（模板/ORB/色直方图/ROI 裁剪等），此层主要是把接口**稳定化**，便于 API 层直接调用。

## 2.4 VerificationService（验证判定）

* **文件**：`verification_service.py`（新）
* **职责**：

  * `verify(image, plan) -> pass|fail + reason + delta_anchor`
  * 规则来源：`verification_plan.expect_text_any/expect_absent/post_delay_ms`
  * 可选 OCR：`anchors.py` 里有 `OcrClient` 兼容（没有就纯视觉/启发式）

## 2.5 LLMService（薄封装）

* **文件**：继续用 `llm_client.py`。
* **动作**：把 `prompt_builder` 给的提示词 + 候选 JSON 输入给 `LLMClient`；解析出 `decision.click_id`、`per_candidate` 等。

## 2.6 API 层（FastAPI）

* **文件**：依然在 `app.py`（你已经在用 FastAPI）
* **动作**：定义 Pydantic 模型、路由、异常、幂等校验、计费钩子、速率限制（可选）

---

# 3. 数据模型（Pydantic）

**推荐**在 `schemas.py` 新建，API 层与服务层共享。

* `CaptureSpec`：`mode/screen_size/window_offset/window_size/dpr`
* `ContextSpec`：`workflow_id/step_id/goal/intent/history/vars/allow_rewrite/dom_hints`
* `PickRequest / PickResponse`
* `VerifyRequest / VerifyResponse`
* `AnchorSpec / AnchorProposal / AnchorDelta`
* `VerificationPlan`
* `ErrorResponse`（统一错误格式）

> 字段名与上面请求/响应 JSON 保持一致，方便落地。

---

# 4. 坐标与 DPR（重要的坑位）

**统一约定**：

* **上传图像的坐标系** = **`point_in_capture` 所在坐标系**
* 若 `capture.mode=full`，则 `point_in_capture` == 屏幕逻辑坐标（大多数平台下就是 PyAutoGUI 的坐标）。
* 若 `capture.mode=active_window|region`，则 `point_in_capture` 是**相对窗口/区域**；客户端点击时需：

  ```
  P_screen = (ox + xc, oy + yc)           # ox/oy = window_offset（逻辑坐标）
  ```
* 如果你在某些平台**截的是物理像素**，则点击前**除以 dpr**：

  ```
  P_screen = (ox + xc/dpr, oy + yc/dpr)
  ```

**YOLO 端的职责**：

* **只**返回 `point_in_capture`，并在 `mapping_hint` 中明确是否需要 `apply_window_offset` 和 `expects_dpr`；
* **不要**替客户端做屏幕坐标换算（避免和不同平台 DPI 策略冲突）。

---

# 5. 错误模型与重试策略

* **HTTP 422**：请求格式错误（Pydantic 校验）
* **HTTP 409**：幂等冲突（相同 `idempotency_key` 与不同 payload）
* **HTTP 429**：限流（可选）
* **HTTP 500**：内部错误（LLM/YOLO 出错或超时）

**响应体**统一：

```json
{"error": {"code":"LLM_TIMEOUT","message":"...", "hint":"retry_later", "req_id":"..."}}
```

**重试建议**：

* `/v1/pick`：LLM/YOLO 超时 → 客户端退回到**锚点**或**DOM 直点**一次
* `/v1/verify`：建议**二次截图**后重试（加 `post_delay_ms`）

---

# 6. 计费/审计/风控钩子（预留）

* **计费粒度**：`cache_hit`（锚点）< `yolo` < `yolo+llm` < `autostep`
* **幂等键**：`idempotency_key`；记录在 Redis/本地 KV（开发期可内存字典）
* **审计与追踪**：返回 `telemetry.req_id`，服务端日志按此贯穿
* **风控**：限制图片 size（如 < 4MB）、宽高上限（如 4K），黑名单域名（可由 `context.vars.host`）

---

# 7. 日志与指标

* **结构化日志**：`req_id, endpoint, stage_lat_ms, yolo_hit, anchor_hit, llm_model, decision_conf`
* **Prometheus 指标**：

  * `yolo_pick_qps`、`verify_qps`、`anchor_hit_ratio`、`llm_used_ratio`
  * `pick_latency_ms_p50/p95/p99`、`verify_pass_rate`
  * `autostep_patch_proposed_total`

---

# 8. 与现有代码的对齐与修改点

| 模块                                                         | 复用/修改  | 说明                                                   |
| ---------------------------------------------------------- | ------ | ---------------------------------------------------- |
| `app.py`                                                   | **扩展** | 增加 `/v1/pick`、`/v1/verify` 等路由；保留 `/health`          |
| `anchors.py`                                               | **复用** | 模板/ORB 匹配、ROI、OCR（可选）；新建 `anchors_service.py` 做接口稳定化 |
| `prompt_builder.py`                                        | **复用** | 使用 `PromptSpec` 生成 LLM 输入（包含候选 JSON）                 |
| `llm_client.py`                                            | **复用** | 统一 LLM 调用；支持 gemini/openai；解析 OUTPUT\_SCHEMA         |
| `action_engine.py / executor.py / runner.py / workflow.py` | **保持** | 这些属于执行/编排端；YOLO 端不直接调用，除非你要在服务端 dry-run（不建议）         |
| `services.py`                                              | **轻用** | 可作为 DI 容器（注册 Detector/Anchors/LLM/Verify 服务）         |

---

# 9. 关键实现片段（示例骨架）

> 以下代码片段展示**如何把你的模块拼起来**（可直接放到你的项目里；类型名按“数据模型”章节自行调整）。

### 9.1 Orchestrator（核心）

```python
# orchestrator.py
from typing import Dict, Any, List, Optional, Tuple
import time

from anchors_service import AnchorsService
from detector_service import DetectorService
from verification_service import VerificationService
from llm_client import LLMClient
from prompt_builder import PromptSpec

class Orchestrator:
    def __init__(self, anchors: AnchorsService, det: DetectorService,
                 verifier: VerificationService, llm: LLMClient):
        self.anchors = anchors
        self.det = det
        self.verifier = verifier
        self.llm = llm

    def pick(self, img_bgr, req) -> Dict[str, Any]:
        t0 = time.time()

        # 0) 快速锚点匹配
        if req.anchors_known:
            hit = self.anchors.quick_match(img_bgr, req.anchors_known)
            if hit:
                point, conf, anchor_id = hit
                return {
                    "decision": {"action":"click","point_in_capture": point,
                                 "bbox_in_capture": None, "confidence": conf, "reason": "anchor_hit"},
                    "mapping_hint": {"apply_window_offset": req.capture.mode != "full",
                                     "expects_dpr": req.capture.dpr},
                    "anchor_proposal": None,
                    "verification_plan": self.verifier.default_plan(req.context),
                    "telemetry": {"req_id": req.idempotency_key, "cache_hit": True,
                                  "stage_lat_ms": {"total": int((time.time()-t0)*1000)}}
                }

        # 1) YOLO 候选
        t1 = time.time()
        cands = self.det.run_yolo(img_bgr, conf=req.options.yolo.conf, iou=req.options.yolo.iou)
        # 2) Prompt 构建
        spec = PromptSpec(goal=req.context.goal, page=req.context.vars.get("site") or "page",
                          preferred_classes=None, negative_classes=None,
                          hints=req.context.dom_hints.get("text") if req.context.dom_hints else None)
        prompt, cand_json = self._build_prompt(spec, cands)
        # 3) LLM 决策
        t2 = time.time()
        decision = self.llm.decide(prompt, cand_json)
        click_id = decision["decision"]["click_id"]
        pick_cand = next((c for c in cands if c["id"] == click_id), None)
        if not pick_cand:
            # 回退策略：按 per-candidate 最大或 ABSTAIN
            pick_cand = self._fallback_candidate(cands, decision)

        # 4) 组装输出
        bbox = pick_cand["xyxy"]
        point = [(bbox[0]+bbox[2])//2, (bbox[1]+bbox[3])//2]
        anchor_prop = self.anchors.propose_anchor(img_bgr, bbox, req.context.dom_hints)

        return {
            "decision": {"action":"click","bbox_in_capture": bbox,"point_in_capture": point,
                         "confidence": pick_cand.get("score", 0.5), "reason": decision["decision"].get("reason","llm_pick")},
            "mapping_hint": {"apply_window_offset": req.capture.mode != "full",
                             "expects_dpr": req.capture.dpr},
            "anchor_proposal": anchor_prop,
            "verification_plan": self.verifier.plan_for(req.context, pick_cand),
            "telemetry": {"req_id": req.idempotency_key, "cache_hit": False,
                          "stage_lat_ms": {"yolo": int((t2-t1)*1000), "llm": decision.get("lat_ms", -1)}}
        }

    def _build_prompt(self, spec: PromptSpec, cands: List[Dict[str,Any]]):
        # 使用 prompt_builder 把 spec + cands 变成 LLM 可消费的文本/JSON
        # 你的 prompt_builder 里已有 OUTPUT_SCHEMA 和规则点，这里只需薄封装
        ...
```

### 9.2 FastAPI 路由（`app.py` 内）

```python
from fastapi import APIRouter, Depends
from schemas import PickRequest, PickResponse, VerifyRequest, VerifyResponse
from orchestrator import Orchestrator
from dependencies import get_orchestrator

router = APIRouter(prefix="/v1")

@router.post("/pick", response_model=PickResponse)
def pick(req: PickRequest, orch: Orchestrator = Depends(get_orchestrator)):
    img_bgr = decode_image_to_bgr(req.image)     # 你在 app.py 里已有 PIL->BGR 的转换工具
    return orch.pick(img_bgr, req)

@router.post("/verify", response_model=VerifyResponse)
def verify(req: VerifyRequest, orch: Orchestrator = Depends(get_orchestrator)):
    img_bgr = decode_image_to_bgr(req.image)
    ok, reason, lock_delta = orch.verifier.verify(img_bgr, req.expected)
    return {"pass": ok, "reason": reason, "lock_anchor": lock_delta, "telemetry": {"latency_ms": ...}}
```

> **注意**：把 `decode_image_to_bgr` 复用/抽取于你现有 `app.py`（我看到你已经有 PIL→BGR 的代码片段）。

---

# 10. AutoStep/AutoFix（白名单改写）

* **策略**（默认白名单，仅自动化以下）：

  * 插入 `instr.wait(ms<=1200)`（等待页面静稳）
  * `scroll_then_retry(±400px)`（滚动后重试关键点击）
  * 追加 `selector/text`（**只加不删**原有选择）
* **输出**：`patches=[{"op":"insert_before","state":"X","action":{"do":"instr.wait","ms":600}}, ...]`
* **落地**：由**客户端或你的 WAM** CLI 应用，YOLO 端仅**提供建议**（含 `risk=low|medium|high`）

---

# 11. 测试清单（最小可用）

1. **/v1/pick（full）**：1920×1080 全屏图，返回 point 与 bbox，`apply_window_offset=false`
2. **/v1/pick（active\_window）**：给 `window_offset/size`，验证 `mapping_hint.apply_window_offset=true`
3. **锚点命中**：先 `/verify` 锁定锚点，再 `/pick` 应命中 **fast path**
4. **/v1/verify**：提供点击后截图，验证返回 `pass=true` 与 `lock_anchor.version+1`
5. **LLM 超时回退**：模拟 LLM 超时，检查 `decision.reason=fallback` 且依旧返回可点击点
6. **幂等**：同 `idempotency_key` 重复请求，确保返回一致 & 只计费一次
7. **大图限制/风控**：>4MB 图返回 413 或 400（可配置）
8. **AutoStep**：构造 3 次连续失败，检查 `/autostep/patch-proposal` 返回**白名单补丁**

---

# 12. 性能与扩展

* **图像裁剪**：如 `capture.mode=window|region`，服务端先做**局部裁剪**送 YOLO/LLM（降耗）
* **候选上限**：`max_candidates` 默认 32；超长列表可能拖慢 LLM
* **多模型**：轻量 YOLO（如 `imgsz=960`）做首轮；失败再用大模型
* **缓存**：同一 `workflow_id+step_id+fingerprint(image)` 命中短缓存（几秒）
* **并发**：FastAPI + Uvicorn 多 worker；YOLO torch 线程数与队列隔离

---

# 13. 安全与合规

* **TLS**、**请求时间窗**（签名/HMAC 可选）
* **图片不落盘**（只存指纹/统计）；调试模式另启
* **敏感词脱敏**：OCR/DOM 文本只保哈希或星号化存储
* **域名白名单**：`context.vars.host` 可用于限制业务域

---

# 14. 迁移步骤（从你现有仓库出发）

1. 新增模块：`schemas.py / orchestrator.py / detector_service.py / anchors_service.py / verification_service.py / dependencies.py`
2. 扩展 `app.py`：注册 `/v1/pick`、`/v1/verify`、`/v1/anchors/*`、`/v1/autostep/patch-proposal` 路由
3. 在 `dependencies.py` 里**构建单例**服务（YOLO 模型、LLMClient、AnchorsService 等）
4. 把你 `app.py` 的图像解码/排序辅助函数抽成 util，API 层直接复用
5. 加入**幂等与计费钩子**（开发期用内存 dict，生产替换为 Redis/DB）
6. 跑“测试清单”八个用例，逐项对齐
