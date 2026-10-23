# 0. 结论先给：怎么既快落地又能防破解？

* **把关键能力放到“服务端签名的配置与任务计划（EQP/SkillCard）”上**，扩展只是解释器；**没有服务器私钥签名，扩展拒绝执行**。
* **授权=短期凭证（Entitlement JWT）+ 离线签名**：扩展内置**公钥**，收到的 EQP/SkillCard/授权都要 **ECDSA 验签**；就算被人抓包，也改不了。
* **强绑定 & 可吊销**：授权绑定**账号 + 设备ID**（可选：本机原生宿主保存密钥），服务器能随时吊销；扩展端有 **kill-switch**。
* **最小化客户端秘密**：扩展不存任何长期密钥；**自学习数据也要签名**后才允许执行与分享。
* **分发最快路径**：先上**Chrome Web Store 非公开（Unlisted）**分发 + 你自己的授权系统；后续企业客户可走**企业策略私有分发**。

> 这套设计的“安全闭环”不是靠把代码藏住（做不到 100%），而是靠**签名 + 短证 + 服务器裁决**。客户端离线时也能跑一小段时间（有签名与TTL），超期就自动停。

---

# 1. 总体架构（MVP）

```
┌───────────────────────┐
│  后端 License&Config  │  PostgreSQL/Redis
│  - /auth/login        │  账号/密码/SSO（可选）
│  - /entitlement/issue │  设备绑定、短期JWT（24h）
│  - /plans/fetch       │  返回 EQP/SkillCard（ECDSA签名）
│  - /events/ingest     │  匿名遥测/错误/成功率
│  - /revocations       │  吊销名单/心跳审计
└─────────────▲─────────┘
              │ HTTPS(JSON)，响应都带签名(sig + keyId)
              │
┌─────────────┴──────────┐
│   Chrome Extension(MV3) │
│  service_worker         │  授权、CDP、网络拦截、EQP解释器、签名验签
│  content_scripts        │  DOM/AX采样、数据抽取、注入最小逻辑
│  (可选)native host      │  本机密钥/设备绑定/系统秘钥链（提高抗破解）
│  indexedDB              │  本地SkillCard缓存（带签名+TTL）
└─────────────┬──────────┘
              │
         目标网站/应用
```

---

# 2. 扩展模块分层

## 2.1 权限与结构（MV3）

* `permissions`: `activeTab`, `scripting`, `storage`, `tabs`, **`debugger`**（CDP），`declarativeNetRequest`（限域）
* `host_permissions`: 只允许你支持的网站（xhs.com/indeed.com 等）
* 目录：

```
/extension
  manifest.json
  sw/                # service worker
    bootstrap.js     # 启动、授权刷新、远程拉取
    verify.js        # ECDSA 验签(WebCrypto)
    cdp.js           # chrome.debugger -> DOMSnapshot/Network
    eqp_runner.js    # EQP解释器（执行器）
    skill_store.js   # IndexedDB + UCB多臂老虎机
  cs/
    observer.js      # DOM/AX 采样、增量刷新
    actions.js       # 点击/输入/滚动安全执行
  ui/
    popup.html/js    # 登录/授权状态/域白名单
```

## 2.2 “签名优先”的数据流

* **扩展固定内置**：`publicKey(keyId=K1)`、`product_id`、`api_base`、`csp 白名单`
* 后端返回格式统一：

```json
{
  "payload": { ... EQP 或 SkillCard 或 Entitlement ... },
  "sig": "base64-ecdsa",
  "keyId": "K1",
  "issued_at": 173637..., "ttl_sec": 86400
}
```

* 扩展执行前：

  1. `verify(keyId, sig, payload)` → 失败即丢弃
  2. 检查 `issued_at + ttl_sec`、`aud`/`product_id`、`scope`、`device_id`
  3. 通过再写入 IndexedDB（连同签名），否则拒绝

> ✅ 这样即使别人改了 EQP/SkillCard/授权，验签不过就无法执行。

---

# 3. 授权与防破解（MVP 版）

## 3.1 账户 & 设备绑定

* **登录**：邮箱+一次性验证码 / OAuth 企业SSO 皆可
* **设备ID**：MVP 直接生成 UUID v4 存 `chrome.storage.local`（可更换设备需后端解绑）
* **可选增强（推荐）**：Native Messaging Host（本机小助手）

  * 用于把设备私钥保存在 OS Keychain（Windows Credential Manager/macOS Keychain）
  * 后端下发 `challenge`，由本机私钥签名返回（扩展仅转发），伪造难度大大增加
  * 扩展与本机小助手通过 `chrome.runtime.connectNative` 通信

## 3.2 短期授权（Entitlement）

* 扩展启动/切换站点时调用 `/entitlement/issue`：

  * 请求体：`account_id, device_id, product_id, scopes, version, domain`
  * 响应：`payload{exp, scopes, domain_whitelist, rate_limits, features}`, `sig`
* **离线宽限**：缓存最近一个有效授权 + 回放计数（例如 72 小时）；过期即停

## 3.3 反滥用与吊销

* 服务器维护 `revocation_list`（licenseId/deviceId 维度）
* 扩展定时心跳（例如每 30 分钟）拉取；命中则**立即停用并清理缓存**
* **速率限制**：服务器按账号/设备/域名限流；超限返回带签名的“限流策略”，扩展本地执行

## 3.4 代码防护（MVP）

* **构建**：esbuild/rollup → `javascript-obfuscator`（标记关键模块）
* **拆分**：把 EQP/SkillCard 逻辑放在**数据**里（签名），避免远程下发 JS 脚本（CSP/审查风险）
* **WASM 可选**：把 UCB/SimHash 小算法与验签逻辑放 WASM（增加逆向成本）

> 重要提醒：**浏览器扩展无法 100% 防逆向**，真正的安全来自“**无签名不执行 + 短证可吊销**”。

---

# 4. “自动感知 → 固化技能卡”在收费架构里怎么跑

## 4.1 Observation（扩展采样）

* DOM/AX 子集、framePath、bbox、aria、文本TopTokens、phash 的**轻快照**
* 跨域/closed shadow 用 **CDP.DOMSnapshot** 补齐
* （按域名白名单触发，保障隐私）

## 4.2 LLM 生成 EQP（后端）

* 后端收到 Observation（**不含敏感内容，或脱敏后**）→ 调 LLM 产出 **EQP**
* **服务器用私钥签名** EQP 再返回给扩展
* 扩展 **只执行验签通过的 EQP**

## 4.3 扩展执行 EQP → 产出 Result

* EQP 支持：`css_select / anchor_select / role_select / iterate / verify / fallback(network_sniff, vision_roi)`
* 结果打分与样例（不回传全文，仅摘要与结构）
* 成功→ 生成/更新 **SkillCard**（多候选选择器 + 成败计数 + 验证规则）
* SkillCard 上传服务器→ **服务器签名后回下发**（可复用给同一租户的其他设备）

## 4.4 日常运行（不再调 LLM）

* 命中**页面签名**（host+pathHint+phashTop）→ 直接跑本地 **SkillCard**
* 失败次数 > 阈值 → 请求 **差分 EQP**（低频）
* 全都失败 → 触发**网络拦截或视觉兜底**（仅 ROI）

---

# 5. 分发与更新

## 5.1 最快落地的分发

* \*\*Chrome Web Store 非公开（Unlisted）\*\*发布，只有链接的人能装
* 购买/开通在你的后台，扩展里**登录→换取授权**
* 版本升级靠商店自动更新（省心稳定）

## 5.2 企业分发（可选第二阶段）

* 通过 **Chrome Enterprise 管控**的 policy 推送（你给 CRX+更新URL/或者私域商店）
* 绑定企业域名邮箱 + 后端授权

## 5.3 远程配置与热修

* 所有远程配置（域白名单、速率、特性开关、EQP/SkillCard）都是**数据（JSON）+签名**
* 你的后端可随时热更新；扩展拿到新版本后**验签→替换**

---

# 6. 具体到“你要的几个场景”

## 6.1 小红书自动回复（读取对方消息 + 定位输入框 + 发出）

* **EQP 模板**：已给（上一轮），服务器签名后下发
* **多条消息**：用 `messageId`（若可从接口抓到），否则 `SimHash(text+time+path)` 去重
* **图片/视频**：只取 `src`/尺寸/时长；要读文字再触发 ROI 视觉兜底
* **发送**：三套候选（`textarea` / `div[contenteditable]` / `input[type=text]`）+ 验证（focus/insertText/附近 send 按钮）

## 6.2 Indeed 自动投递（抓 JD + Apply）

* **DOMSnapshot** 抓 iframe 内文
* **by\_anchor** 找 `Full job description/职位描述` 容器，抽 innerHTML（保留 `<li>`）
* **Network sniff** 优先（很多站有 jobPosting JSON）
* **Apply 按钮** 多候选选择器 + 验证（可见、可点击）

> 以上都在**授权+签名**保护下执行；没有授权/签名即停。

---

# 7. MVP 交付内容（两周量级）

**第 1–3 天：底座**

* MV3 骨架（manifest、SW、CS）
* 登录 & 授权：`/auth/login`、`/entitlement/issue`、ECDSA 验签（P-256）
* IndexedDB 封装；基础 UI（登录/状态）

**第 4–6 天：解释器与采样**

* `observer.js`（DOM/AX + CDP DOMSnapshot）
* `eqp_runner.js`（选择器/锚点/迭代/验证/回退）
* `cdp.js`（Network sniff 到 JSON）

**第 7–9 天：自学习与安全**

* `skill_store.js`（SkillCard + UCB 多候选选择）
* 事件遥测 `/events/ingest` + 吊销检查 `/revocations`
* 构建与混淆（obfuscator）+ CSP 收紧

**第 10–14 天：场景与灰度**

* 小红书 IM & Indeed JD **签名 EQP 模板**上线
* 域白名单灰度、速率限制、离线宽限
* 文档与最小单测（本地快照回放）

---

# 8. 后端接口契约（精简版）

* `POST /auth/login` → `{ account_id, token }`
* `POST /entitlement/issue`
  **req**: `{ account_id, device_id, product_id, scopes, version, domain }`
  **res**: `{ payload:{ exp, scopes, domain_whitelist, rate_limits, features }, sig, keyId }`
* `POST /plans/fetch`
  **req**: `{ page_signature, product_id, scope }`
  **res**: `{ payload: EQP or SkillCard, sig, keyId, ttl }`
* `POST /events/ingest`
  **req**: `{ anon_id, device_id, event, ts, version, domain }`
* `GET /revocations?device_id=...` → `{ revoked: boolean, reason }`

> 服务端用 **Ed25519 或 P-256** 签名，**只暴露公钥**在扩展中；支持 `keyId` 滚动换钥。

---

# 9. 关键实现片段（验签 & 授权）

**WebCrypto ECDSA 验签（P-256, SHA-256）**

```js
// sw/verify.js
export async function importPublicKey(rawSpkiBase64) {
  const der = Uint8Array.from(atob(rawSpkiBase64), c => c.charCodeAt(0));
  return crypto.subtle.importKey(
    'spki', der.buffer, { name: 'ECDSA', namedCurve: 'P-256' }, true, ['verify']
  );
}

export async function verifySig(publicKey, payloadObj, sigBase64) {
  const enc = new TextEncoder();
  const data = enc.encode(JSON.stringify(payloadObj));
  const sig = Uint8Array.from(atob(sigBase64), c => c.charCodeAt(0));
  return crypto.subtle.verify({ name: 'ECDSA', hash: 'SHA-256' }, publicKey, sig, data);
}
```

**授权刷新（含离线宽限）**

```js
// sw/bootstrap.js
import { importPublicKey, verifySig } from './verify.js';

let pubKey;
async function ensureKey() { pubKey ||= await importPublicKey(PUBLIC_SPKI_B64); }

export async function refreshEntitlement() {
  await ensureKey();
  const res = await fetch(API_BASE + '/entitlement/issue', { method:'POST', credentials:'include', body: /*...*/});
  const { payload, sig, keyId } = await res.json();
  if (!(await verifySig(pubKey, payload, sig))) throw new Error('Bad signature');
  if (Date.now()/1000 > payload.exp) throw new Error('Entitlement expired');
  await chrome.storage.session.set({ entitlement: { payload, sig, keyId }});
  return payload;
}
```

---

# 10. 威胁模型与对策（MVP 要点）

| 威胁               | 对策                                                     |
| ---------------- | ------------------------------------------------------ |
| 盗装/复制 CRX        | 没有**服务器签名的授权/EQP/SkillCard**就不执行；授权与**账号+设备ID**绑定；随时吊销 |
| 篡改 EQP/SkillCard | **ECDSA 验签**不过→丢弃                                      |
| 本地脱离服务器长期运行      | **短期授权（24h）+ 离线宽限（≤72h）**，超期停用                         |
| 反射型攻击（恶意站点）      | **域白名单** + `declarativeNetRequest` 限制；UI 明示当前域         |
| 调试注入/改代码         | **混淆 + 拆分 + WASM（可选）**，但核心靠“无签名不执行”                    |
| 数据隐私             | 只上传**结构摘要/指标**；文本脱敏/只样例；企业域名单独存储策略                     |
