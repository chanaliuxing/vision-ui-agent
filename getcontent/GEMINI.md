# Open Plan Roadmap

This roadmap is generated from the "Open Plan". We will follow these phases to build the project.

---

# Project Configuration & Environment Notes

*   **Secrets**: All API keys (LLMs) and database credentials are located in the `.env` directory.
*   **LLM Preference**:
    *   For **vision-related** tasks, use the **Gemini** API.
    *   For **text-related** tasks, use the **DeepSeek/NVIDIA** API.
*   **Database**: The project uses **PostgreSQL**. Connection details (host, etc.) are in the `.env` directory.

---

# Open Plan Roadmap

This roadmap is generated from the "Open Plan". We will follow these phases to build the project.

---

## 阶段 0｜仓库与密钥初始化

*   **目标**: 一次性把工程脚手架与签名体系立起来。
*   **产物**:
    *   单一 monorepo：`/backend`、`/extension`、`/tools`、`/docs`
    *   服务器签名密钥对（Ed25519 或 P-256），公钥写入扩展
    *   基础 JSON Schema：`observation.schema.json`、`eqp.schema.json`、`skillcard.schema.json`、`result.schema.json`
*   **关键任务**:
    *   生成密钥对，并将公钥（SPKI, base64）写入 `/extension/keys.json`。
    *   起草各模块的最小化 JSON Schema。
    *   在项目中定义统一的 `PRODUCT_ID` 和 `KEY_ID`。
*   **验收标准 (DoD)**:
    *   Repo 初始化完成，目录结构符合规划。
    *   公钥能被扩展端的 `WebCrypto` API 成功导入并用于验签（通过本地测试函数验证）。

---

## 阶段 1｜后端最小可用（授权 + 签名返回）

*   **目标**: 提供受签名保护的授权与计划下发接口。
*   **产物**:
    *   `/auth/login`
    *   `/entitlement/issue`
    *   `/plans/fetch`
    *   `/events/ingest`
    *   `/revocations`
*   **关键任务**:
    *   选择 Node/FastAPI 搭建后端服务。
    *   实现 `SignedEnvelope` 格式：`{payload, sig, keyId, issued_at, ttl_sec}`。
    *   使用 Redis/PG 存储授权、吊销、EQP/SkillCard 等数据。
*   **验收标准 (DoD)**:
    *   通过 curl 能请求到带签名的响应。
    *   使用 `/tools/verify.js` 脚本对后端响应验签通过。

---

## 阶段 2｜扩展骨架（MV3）与验签链路

*   **目标**: 把“无签名不执行”的底座立起来。
*   **产物**:
    *   `manifest.json`
    *   Service Worker (`bootstrap.js`, `verify.js`, `api.js`)
    *   Popup 页面 (`popup.html/js`)
    *   IndexedDB 封装 (`db.js`)
*   **关键任务**:
    *   实现公钥导入和对 `entitlement` / `plans` 的验签逻辑。
    *   检查 `ttl`、`product_id`、`device_id` 等声明。
    *   将授权缓存到 `chrome.storage.session`。
*   **验收标准 (DoD)**:
    *   登录后能获取授权并通过验签，UI 显示“已授权”。
    *   未授权或吊销时，UI 变为“未授权”，且执行功能不可用。

---

## 阶段 3｜Observation 采样（DOM/AX + CDP）

*   **目标**: 在不 OCR 的前提下，得到 LLM 足够“读懂”的 UI 快照。
*   **产物**:
    *   `cs/observer.js` (DOM/AX 遍历与过滤)
    *   `sw/cdp.js` (通过 `chrome.debugger` 处理 iframe/Shadow DOM)
    *   轻量截图指纹 (`phash`)
*   **关键任务**:
    *   向 Service Worker 提供 `getObservation()` 接口。
    *   使用 `MutationObserver` 优化性能。
*   **验收标准 (DoD)**:
    *   在目标网站上调用能返回包含 `framePath` 的元素摘要。
    *   跨域 iframe 的节点能出现在快照中。

---

## 阶段 4｜EQP 解释器 v1（只做“读”）

*   **目标**: 让扩展“按 JSON 开计划，严执行”。
*   **产物**:
    *   `sw/eqp_runner.js` (支持选择器、提取、迭代、验证)
    *   结构化的 `results` 和 `metrics`
*   **关键任务**:
    *   解释器严格执行 JSON 定义的计划。
    *   失败时返回结构化错误码。
*   **验收标准 (DoD)**:
    *   手动提供 EQP 模板，能稳定抽到目标数据。
    *   通过 MHTML/DOMSnapshot 回放进行单元测试，结果保持一致。

---

## 阶段 5｜SkillCard & 自学习（UCB）

*   **目标**: 命中“页型签名”后，不再依赖 LLM，靠本地 SkillCard 稳定执行。
*   **产物**:
    *   `sw/skill_store.js` (SkillCard 存取与 UCB1 调度)
    *   Card 合并逻辑
*   **关键任务**:
    *   定义 `page_signature` 的组成。
    *   实现失败N次后回退到 LLM 的逻辑。
*   **验收标准 (DoD)**:
    *   同页面反复执行，只有首次请求 EQP，后续走本地 Card。
    *   页面元素被修改导致失败后，能自动请求新候选并恢复。

---

## 阶段 6｜Network Sniff（优先于视觉）

*   **目标**: 直接从接口响应获取结构化数据，绕开 DOM 变化。
*   **产物**:
    *   `sw/cdp.js` 增强，订阅 `Network` 事件。
    *   EQP fallback 增加 `network_sniff` 策略。
*   **关键任务**:
    *   在白名单和授权下启用，并严格限流。
    *   支持 JSONPath/正则抽取。
*   **验收标准 (DoD)**:
    *   在目标网站上，能直接从接口获取主要文本数据。

---

## 阶段 7｜视觉兜底（ROI 级）

*   **目标**: 只对缺口区域做轻量视觉解析。
*   **产物**:
    *   `vision_bridge.js` 对接推理服务。
    *   EQP fallback 增加 `vision_roi_ocr` 策略。
*   **关键任务****:**
    *   实现截图 -> 裁剪 ROI -> 发送 -> 对齐返回结果的流程。
*   **验收标准 (DoD)**:
    *   聊天图片中的文字或 JD 图片中的段落能被正确提取和补充。

---

## 阶段 8｜场景模板与端到端验收

*   **目标**: 让两个核心场景可端到端运行并可收费交付。
*   **产物**:
    *   `plans/xhs_im.eqp.json`
    *   `plans/indeed_viewjob.eqp.json`
    *   `/docs/runbooks/*.md`
*   **关键任务**:
    *   先完成“读”的闭环并上线。
    *   上报成功率、耗时、回退率等核心指标。
*   **验收标准 (DoD)**:
    *   两个场景在多台设备上稳定通过。
    *   断网后在授权 TTL 内可继续执行，超期后停止。

---

## 阶段 9｜安全与分发（收费最小闭环）

*   **目标**: 可收费、可吊销、难白嫖。
*   **产物**:
    *   `Unlisted` 扩展上架。
    *   简易的后端开票/开通页面。
    *   吊销与灰度策略。
*   **关键任务**:
    *   构建时使用 `javascript-obfuscator` 进行代码混淆。
    *   收紧 CSP 策略。
    *   实现离线宽限逻辑。
*   **验收标准 (DoD)**:
    *   CRX 文件被拷贝到其他机器后，无授权无法执行。
    *   后端吊销设备后，扩展端立即停用。

---

## 阶段 10｜动作层（可选下一步）

*   **目标**: 在“读”稳定后，加入“写/点”能力。
*   **产物**:
    *   `cs/actions.js`
    *   EQP 增加 `actions` 字段。
*   **关键任务**:
    *   设置安全护栏，仅在用户显式启动时执行动作。
    *   执行后重新采样以验证结果。
*   **验收标准 (DoD)**:
    *   在测试页面上完成“输入 -> 点击”的闭环，并具备失败回滚能力。

---

## 阶段 11｜运营度量与灰度

*   **目标**: 实现可见的质量与自学习效果度量。
*   **产物**:
    *   `/metrics` 仪表盘 (Grafana/Metabase)。
*   **关键任务**:
    *   通过事件采样上报进行级联统计。
    *   实现“问题页型”一键诊断功能。
*   **验收标准 (DoD)**:
    *   能筛出 Top 10 失败最多的页型，并能快速发布补丁 EQP。


*   **目标**: 一次性把工程脚手架与签名体系立起来。
*   **产物**:
    *   单一 monorepo：`/backend`、`/extension`、`/tools`、`/docs`
    *   服务器签名密钥对（Ed25519 或 P-256），公钥写入扩展
    *   基础 JSON Schema：`observation.schema.json`、`eqp.schema.json`、`skillcard.schema.json`、`result.schema.json`
*   **关键任务**:
    *   生成密钥对，并将公钥（SPKI, base64）写入 `/extension/keys.json`。
    *   起草各模块的最小化 JSON Schema。
    *   在项目中定义统一的 `PRODUCT_ID` 和 `KEY_ID`。
*   **验收标准 (DoD)**:
    *   Repo 初始化完成，目录结构符合规划。
    *   公钥能被扩展端的 `WebCrypto` API 成功导入并用于验签（通过本地测试函数验证）。

---

## 阶段 1｜后端最小可用（授权 + 签名返回）

*   **目标**: 提供受签名保护的授权与计划下发接口。
*   **产物**:
    *   `/auth/login`
    *   `/entitlement/issue`
    *   `/plans/fetch`
    *   `/events/ingest`
    *   `/revocations`
*   **关键任务**:
    *   选择 Node/FastAPI 搭建后端服务。
    *   实现 `SignedEnvelope` 格式：`{payload, sig, keyId, issued_at, ttl_sec}`。
    *   使用 Redis/PG 存储授权、吊销、EQP/SkillCard 等数据。
*   **验收标准 (DoD)**:
    *   通过 curl 能请求到带签名的响应。
    *   使用 `/tools/verify.js` 脚本对后端响应验签通过。

---

## 阶段 2｜扩展骨架（MV3）与验签链路

*   **目标**: 把“无签名不执行”的底座立起来。
*   **产物**:
    *   `manifest.json`
    *   Service Worker (`bootstrap.js`, `verify.js`, `api.js`)
    *   Popup 页面 (`popup.html/js`)
    *   IndexedDB 封装 (`db.js`)
*   **关键任务**:
    *   实现公钥导入和对 `entitlement` / `plans` 的验签逻辑。
    *   检查 `ttl`、`product_id`、`device_id` 等声明。
    *   将授权缓存到 `chrome.storage.session`。
*   **验收标准 (DoD)**:
    *   登录后能获取授权并通过验签，UI 显示“已授权”。
    *   未授权或吊销时，UI 变为“未授权”，且执行功能不可用。

---

## 阶段 3｜Observation 采样（DOM/AX + CDP）

*   **目标**: 在不 OCR 的前提下，得到 LLM 足够“读懂”的 UI 快照。
*   **产物**:
    *   `cs/observer.js` (DOM/AX 遍历与过滤)
    *   `sw/cdp.js` (通过 `chrome.debugger` 处理 iframe/Shadow DOM)
    *   轻量截图指纹 (`phash`)
*   **关键任务**:
    *   向 Service Worker 提供 `getObservation()` 接口。
    *   使用 `MutationObserver` 优化性能。
*   **验收标准 (DoD)**:
    *   在目标网站上调用能返回包含 `framePath` 的元素摘要。
    *   跨域 iframe 的节点能出现在快照中。

---

## 阶段 4｜EQP 解释器 v1（只做“读”）

*   **目标**: 让扩展“按 JSON 开计划，严执行”。
*   **产物**:
    *   `sw/eqp_runner.js` (支持选择器、提取、迭代、验证)
    *   结构化的 `results` 和 `metrics`
*   **关键任务**:
    *   解释器严格执行 JSON 定义的计划。
    *   失败时返回结构化错误码。
*   **验收标准 (DoD)**:
    *   手动提供 EQP 模板，能稳定抽到目标数据。
    *   通过 MHTML/DOMSnapshot 回放进行单元测试，结果保持一致。

---

## 阶段 5｜SkillCard & 自学习（UCB）

*   **目标**: 命中“页型签名”后，不再依赖 LLM，靠本地 SkillCard 稳定执行。
*   **产物**:
    *   `sw/skill_store.js` (SkillCard 存取与 UCB1 调度)
    *   Card 合并逻辑
*   **关键任务**:
    *   定义 `page_signature` 的组成。
    *   实现失败N次后回退到 LLM 的逻辑。
*   **验收标准 (DoD)**:
    *   同页面反复执行，只有首次请求 EQP，后续走本地 Card。
    *   页面元素被修改导致失败后，能自动请求新候选并恢复。

---

## 阶段 6｜Network Sniff（优先于视觉）

*   **目标**: 直接从接口响应获取结构化数据，绕开 DOM 变化。
*   **产物**:
    *   `sw/cdp.js` 增强，订阅 `Network` 事件。
    *   EQP fallback 增加 `network_sniff` 策略。
*   **关键任务**:
    *   在白名单和授权下启用，并严格限流。
    *   支持 JSONPath/正则抽取。
*   **验收标准 (DoD)**:
    *   在目标网站上，能直接从接口获取主要文本数据。

---

## 阶段 7｜视觉兜底（ROI 级）

*   **目标**: 只对缺口区域做轻量视觉解析。
*   **产物**:
    *   `vision_bridge.js` 对接推理服务。
    *   EQP fallback 增加 `vision_roi_ocr` 策略。
*   **关键任务****:**
    *   实现截图 -> 裁剪 ROI -> 发送 -> 对齐返回结果的流程。
*   **验收标准 (DoD)**:
    *   聊天图片中的文字或 JD 图片中的段落能被正确提取和补充。

---

## 阶段 8｜场景模板与端到端验收

*   **目标**: 让两个核心场景可端到端运行并可收费交付。
*   **产物**:
    *   `plans/xhs_im.eqp.json`
    *   `plans/indeed_viewjob.eqp.json`
    *   `/docs/runbooks/*.md`
*   **关键任务**:
    *   先完成“读”的闭环并上线。
    *   上报成功率、耗时、回退率等核心指标。
*   **验收标准 (DoD)**:
    *   两个场景在多台设备上稳定通过。
    *   断网后在授权 TTL 内可继续执行，超期后停止。

---

## 阶段 9｜安全与分发（收费最小闭环）

*   **目标**: 可收费、可吊销、难白嫖。
*   **产物**:
    *   `Unlisted` 扩展上架。
    *   简易的后端开票/开通页面。
    *   吊销与灰度策略。
*   **关键任务**:
    *   构建时使用 `javascript-obfuscator` 进行代码混淆。
    *   收紧 CSP 策略。
    *   实现离线宽限逻辑。
*   **验收标准 (DoD)**:
    *   CRX 文件被拷贝到其他机器后，无授权无法执行。
    *   后端吊销设备后，扩展端立即停用。

---

## 阶段 10｜动作层（可选下一步）

*   **目标**: 在“读”稳定后，加入“写/点”能力。
*   **产物**:
    *   `cs/actions.js`
    *   EQP 增加 `actions` 字段。
*   **关键任务**:
    *   设置安全护栏，仅在用户显式启动时执行动作。
    *   执行后重新采样以验证结果。
*   **验收标准 (DoD)**:
    *   在测试页面上完成“输入 -> 点击”的闭环，并具备失败回滚能力。

---

## 阶段 11｜运营度量与灰度

*   **目标**: 实现可见的质量与自学习效果度量。
*   **产物**:
    *   `/metrics` 仪表盘 (Grafana/Metabase)。
*   **关键任务**:
    *   通过事件采样上报进行级联统计。
    *   实现“问题页型”一键诊断功能。
*   **验收标准 (DoD)**:
    *   能筛出 Top 10 失败最多的页型，并能快速发布补丁 EQP。