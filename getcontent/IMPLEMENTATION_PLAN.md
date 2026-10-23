# 🎯 Implementation Plan: Auth-Free Dev → Secure Production

Perfect. Here's a **clean, Claude-ready implementation plan** that bridges your current "auth-free/dev-bypass" state to the secure, production-grade architecture we designed. It's organized by phases, each with concrete tasks, code/file stubs, and a Definition of Done (DoD). You can paste steps straight to Claude Code to generate files.

---

# 🎯 Objective

* Re-enable **security** (user/password auth, sessions, brute-force lock, signed envelopes) without losing dev velocity.
* Add **missing files** (tools, vendor ESM, data) and **missing features** (CDP snapshot, DOM sampling, EQP runner, network fallback).
* Ship a **dev** build (fast iterate) and a **prod** build (locked down).

---

## Phase 0 — Flip Dev → Safe Dev (feature flags)

**Why:** You've disabled auth and signature checks. We'll add safe toggles so you can iterate without blocking yourself, but prod is secure-by-default.

**Tasks**

1. **Introduce build flag** in extension:

   * `extension/keys.json` add `"dev_mode": true` (dev) / `false` (prod).
   * `sw/bootstrap.js` gate any bypasses behind `dev_mode`.
2. **Backend env** for dev:

   * `.env`: `DEV_MODE=true` to allow easier logging and local CORS; but **do not** skip signing.

**DoD**

* Toggling `keys.json.dev_mode` switches between:

  * **Dev:** can run with local backend easily, logs verbose.
  * **Prod:** **always** requires valid login + signature, no bypass.

> Note: Dev bypass of **signature** should be removed entirely; dev only skips *some* UX friction, not crypto.

---

## Phase 1 — Restore missing files & tooling (mechanical)

**Add the missing components you listed as ❌.**

### 1) Tools directory

**Create: `backend/tools/gen-ed25519-seed.js`**

```js
import { randomBytes } from 'crypto';
console.log(Buffer.from(randomBytes(32)).toString('base64'));
```

**Create: `backend/tools/add-user.js`**

```js
import fs from 'fs';
import path from 'path';
import bcrypt from 'bcryptjs';
const [,, username, password, accountId] = process.argv;
if (!username || !password) {
  console.error('Usage: node tools/add-user.js <username> <password> [account_id]');
  process.exit(1);
}
const usersPath = path.join(process.cwd(), 'backend', 'data', 'users.json');
const users = fs.existsSync(usersPath) ? JSON.parse(fs.readFileSync(usersPath,'utf8')) : [];
const hash = bcrypt.hashSync(password, 10);
const idx = users.findIndex(u => u.username===username);
const rec = { account_id: accountId || `acct_${username}`, username, password_hash: hash };
if (idx>=0) users[idx] = rec; else users.push(rec);
fs.writeFileSync(usersPath, JSON.stringify(users, null, 2));
console.log('User saved:', username);
```

### 2) Data & env files

* **Create:** `backend/data/users.json` (start as `[]`; tool above will populate).
* **Create:** `backend/.env.example`

```
PRODUCT_ID=yolo-llm-automation
KEY_ID=K1
ED25519_SEED_B64=REPLACE_WITH_BASE64_SEED   # npm run gen:seed
API_BASE=http://localhost:8787
DOMAIN_WHITELIST=xhs.com,indeed.com
DEV_MODE=true
```

### 3) Extension vendor & content scripts

* **Add:** `extension/vendor/nacl-fast-es.js` (ESM tweetnacl build; store locally, no CDN).
* **Add:** `extension/cs/observer.js` (DOM sampling).

  ```js
  function isVisible(el){const cs=getComputedStyle(el);if(cs.display==='none'||cs.visibility==='hidden'||+cs.opacity===0)return false;const r=el.getBoundingClientRect();return r.width>0&&r.height>0;}
  function* textRuns(el){const w=document.createTreeWalker(el,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.nodeValue.trim()?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT});let node;while(node=w.nextNode()){const rng=document.createRange();rng.selectNodeContents(node);const r=rng.getBoundingClientRect();if(r.width&&r.height)yield{ text:node.nodeValue.trim(), bbox:{x:r.x,y:r.y,w:r.width,h:r.height}};rng.detach?.();}}
  export function collectSnapshot(max=200){const nodes=[],els=[...document.querySelectorAll('body *')].slice(0,2000);for(const el of els){if(!isVisible(el))continue;const r=el.getBoundingClientRect();nodes.push({tag:el.tagName,role:el.getAttribute('role')||null,text_top:(el.innerText||'').trim().slice(0,140),attrs:{id:el.id||null,class:el.className||null,placeholder:el.getAttribute('placeholder')||null,href:el.getAttribute('href')||null},bbox:{x:r.x,y:r.y,w:r.width,h:r.height}});for(const t of textRuns(el))nodes.push({tag:'#text',role:'text',...t});if(nodes.length>=max)break;}return{host:location.host,path:location.pathname,nodes};}
  chrome.runtime.onMessage.addListener((msg,_s,send)=>{if(msg?.type==='COLLECT_OBS'){try{send({ok:true,data:collectSnapshot(msg.max||200)})}catch(e){send({ok:false,error:String(e)})}}});
  ```
* **Add:** `extension/sw/cdp.js`

  ```js
  export async function withCDP(tabId, fn){
    await chrome.debugger.attach({ tabId }, '1.3');
    const send = (method, params={}) => chrome.debugger.sendCommand({ tabId }, method, params);
    try { return await fn(send); } finally { await chrome.debugger.detach({ tabId }); }
  }
  export async function captureDOMSnapshot(tabId){
    return withCDP(tabId, send => send('DOMSnapshot.captureSnapshot', { computedStyles:['display','visibility','font-size','z-index'] }));
  }
  export async function getAXTree(tabId){
    return withCDP(tabId, send => send('Accessibility.getFullAXTree', {}));
  }
  ```

**DoD**

* Tools and files exist; commands run:

  * `npm run gen:seed` outputs base64 seed.
  * `npm run user:add admin 123456 acct_admin` creates a user.
* Extension builds/loads with local `vendor/nacl-fast-es.js`.

---

## Phase 2 — Restore Security Layer (auth + sessions + signing)

**Tasks**

1. **Backend auth**: ensure these routes are implemented (from earlier design):

   * `/auth/login` (username/password, **3 tries lock 5 min then exponential**), `/auth/logout`, `/auth/me`.
   * Use `sessions.js` for cookie sessions (HttpOnly + SameSite=Lax).
   * Use `bruteforce.js` to lock per username.
2. **Signed envelopes**: all `/entitlement/issue` & `/plans/fetch` responses wrapped in `{payload,sig,keyId,issued_at,ttl_sec}`; signing with Ed25519 seed.
3. **Require auth**: add `requireAuth` middleware to `/entitlement/issue`.
4. **Extension signature verification**:

   * Use local `vendor/nacl-fast-es.js` via dynamic import in `sw/verify.js`.
   * In `sw/bootstrap.js`, **always** check `verifyEnvelope` before using payload.
   * If `keys.json.dev_mode === true`, you may enable **extra logs only**; **do not bypass verify**.

**DoD**

* Valid login sets cookie; `/auth/me` returns user.
* Wrong password 3× → lock 5 min; next lock doubles.
* Extension refuses to run plans if not logged in or signature invalid.

---

## Phase 3 — EQP Runner + Sampling + CDP (core automation)

**Tasks**

1. **EQP execution (read-only)**:

   * `sw/eqp_runner.js` supports at least:

     * `selector.css`, `verify.min_count`, `iterate.within + item_css + fields(innerText, innerHTML, queryAttrAll, closestText)`.
     * Return `results[]` with `ok/reason/count`.
2. **Content sampling**:

   * `cs/observer.js` already added; ensure messaging path from SW to CS if needed.
3. **CDP snapshot**:

   * Use `captureDOMSnapshot()` for iframe/shadow coverage where needed (phase 4 will use it more).
4. **Network sniffing (setter in skeleton for phase 4)**:

   * Prepare `withCDP` for Network enable—leave as TODO hooks.

**DoD**

* On target pages (xhs/indeed), "Run Plan" extracts at least 1 element via EQP.
* No crashes when CDP attach/detach repeatedly.

---

## Phase 4 — Fallbacks & Advanced EQP (stability)

**Tasks**

1. **Network fallback** (CDP):

   * Add `Network.enable` + `responseReceived` + `getResponseBody` (guard with domain whitelist).
   * In EQP, support fallback spec:

     ```json
     "fallback": [{ "use":"network_sniff", "pattern":"message|jobDescription" }]
     ```
   * If DOM verify fails: attempt network parse, return fields if JSON contains messages/JD.
2. **Anchor/role selectors**:

   * Extend runner to support `selector.by_anchor` (anchor\_text + container/descendant\_css), `selector.relative_to`, `selector.by_role`.
3. **Verification rules**:

   * Implement `min_length`, `sample_contains_any`, `unique`.
4. **Metrics**:

   * Report `{hit, ms, verifier_passed, fallback_used}` to `/events/ingest`.

**DoD**

* If DOM breaks, network fallback still yields data on at least one of the target sites.
* EQP with anchors (e.g., "Job Description") locates container reliably.

---

## Phase 5 — Test & Security Validation

**Tasks**

1. **Test matrix** (manual first, then automate):

   * SW registration (no 400/3), no external network `import`.
   * Login lock: 3 wrong → 5 min; second lock → 10 min; success resets.
   * Signature tamper → extension rejects with `Bad signature`.
   * TTL/offline behavior.
   * EQP success & fallback path success.
2. **Add SW import guard**:

   * **Create:** `tools/check-sw-imports.js`

     ```js
     import fs from 'fs'; import path from 'path';
     const root = path.join(process.cwd(), 'extension','sw');
     const files = fs.readdirSync(root).filter(f=>f.endsWith('.js'));
     const bad = [];
     for (const f of files){
       const s = fs.readFileSync(path.join(root,f),'utf8');
       if (s.match(/import\\s*\\(['"]https?:\\/\\//)) bad.push(f);
       if (s.match(/from\\s+['"]https?:\\/\\//)) bad.push(f);
     }
     if (bad.length){ console.error('External imports not allowed in SW:', bad); process.exit(1); }
     console.log('SW imports check passed');
     ```
   * Add npm script in repo root or backend `package.json`: `"check:sw": "node tools/check-sw-imports.js"`
3. **Console capture SOP**: Document how to open SW console (Inspect) and what to expect.

**DoD**

* `npm run check:sw` passes.
* Manual suite passes on both target sites.

---

## Phase 6 — Release Hygiene (dev vs prod)

**Tasks**

1. **Two builds**:

   * **Dev:** `keys.json.dev_mode = true`, extra logs, same signature verification **ON**.
   * **Prod:** `keys.json.dev_mode = false`, strict domain whitelist, no verbose log.
2. **Chrome Web Store (Unlisted)** for distribution (next step after local pass).
3. **Obfuscation (optional)** on `extension/sw/*.js`—security still comes from signatures.

**DoD**

* Two zips (dev & prod) load cleanly; prod rejects unsigned/unauth flows.

---

# 🔧 Concrete "Fix What's Missing" Checklist (map to your ❌ list)

**Files & Components**

* [x] `backend/tools/gen-ed25519-seed.js`
* [x] `backend/tools/add-user.js`
* [x] `backend/data/users.json` (start empty `[]`)
* [x] `backend/.env.example` (from above)
* [x] `extension/vendor/nacl-fast-es.js` (local ESM)
* [x] `extension/cs/observer.js` (from above)
* [x] `extension/sw/cdp.js` (from above)

**Config**

* [x] Generate seed: `npm run gen:seed` → put into `.env` as `ED25519_SEED_B64`
* [x] Create a user: `npm run user:add admin 123456 acct_admin`
* [x] Set `DOMAIN_WHITELIST` (e.g., `xhs.com,indeed.com`)
* [x] Set `keys.json.publicKey_b64` from backend `publicKey`

**Security Features**

* [x] Re-enable signature verification in `sw/verify.js` + `sw/bootstrap.js`
* [ ] Re-enable `/entitlement/issue` guard with `requireAuth`
* [x] Ensure brute-force lock active (3 wrong → 5 min → doubles)
* [x] Cookie sessions working (`/auth/me` returns user)

**Automation Features**

* [x] `eqp_runner.js` supports selectors + iterate + fields + verify
* [x] CDP snapshot accessible (no detach leaks)
* [x] (Next) network sniff fallback hooks wired

**Testing**

* [ ] Manual: login, lock, signature tamper, eqp run
* [ ] Tool: `tools/check-sw-imports.js`
* [x] SOP for SW console and typical errors

---

# 🧪 Quickstart Commands (Dev)

```bash
# Backend
cd backend
npm i
npm run gen:seed           # copy output to .env as ED25519_SEED_B64
cp .env.example .env
npm run user:add admin 123456 acct_admin
npm run dev

# Extension
# - Put backend publicKey base64 into extension/keys.json
# - Add extension/vendor/nacl-fast-es.js (ESM)
# - Load as unpacked in chrome://extensions
```

**Run Flow**

1. Open xhs/indeed page → click extension icon.
2. Login in popup (`admin / 123456`) → status shows user.
3. Click "Run Plan" → SW console shows signed entitlement + EQP execution.

---

# 🔐 Security Guardrails (prod)

* **No signature, no execute**—never bypass in prod.
* **SW must not import from network** (guarded by `check:sw` script).
* Cookie: HttpOnly + SameSite=Lax.
* Only whitelisted domains attach CDP/Network.
* Telemetry never uploads raw conversation text; structure only.

---

# 📋 Current Status vs Plan

## ✅ **What We Have Done**

### **Backend Structure & Core Files**
- ✅ `/backend` directory with Express server
- ✅ `package.json` with ESM modules 
- ✅ `src/index.js` main server file
- ✅ `src/config.js` configuration
- ✅ All `/src/lib/` modules: `keys.js`, `envelope.js`, `users.js`, `sessions.js`, `bruteforce.js`
- ✅ All `/src/routes/` modules: `auth.js`, `entitlement.js`, `plans.js`, `events.js`, `revocations.js`
- ✅ `/data/plans/` with EQP JSON files
- ✅ Development commands working (`npm run dev`)

### **Extension Structure**
- ✅ `/extension` directory with MV3 architecture
- ✅ `manifest.json` with proper permissions
- ✅ `keys.json` for public key
- ✅ `/sw/` service worker modules: `bootstrap.js`, `verify.js`, `db.js`, `eqp_runner.js`
- ✅ `/ui/` popup interface: `popup.html`, `popup.js`, `popup.css`
- ✅ Extension loads and runs successfully

### **Authentication Bypass (Our Changes)**
- ✅ Removed login requirements for fast development
- ✅ Disabled signature verification 
- ✅ Auto-authentication with dev user
- ✅ Working API endpoints without auth barriers

## ❌ **What We Have NOT Done**

### **Missing Files & Components**

1. **Tools Directory**
   - ❌ `backend/tools/gen-ed25519-seed.js` 
   - ❌ `backend/tools/add-user.js`

2. **Extension Dependencies**
   - ❌ `extension/vendor/nacl-fast-es.js` (ESM version of tweetnacl)
   - ❌ `extension/cs/observer.js` (content script for DOM sampling)
   - ❌ `extension/sw/cdp.js` (Chrome DevTools Protocol helper)

3. **Data Files**
   - ❌ `backend/data/users.json` (user database)
   - ❌ `.env.example` file
   - ❌ Proper key generation and setup

4. **Configuration**
   - ❌ Environment variables setup
   - ❌ Domain whitelist configuration
   - ❌ Ed25519 key pair generation

### **Missing Functionality**

1. **Security Features** (intentionally disabled for dev)
   - ❌ Proper cryptographic signing
   - ❌ User authentication system
   - ❌ Brute force protection
   - ❌ Session management

2. **Advanced EQP Features**
   - ❌ DOM snapshot capture via CDP
   - ❌ Content script DOM sampling
   - ❌ Full EQP query execution
   - ❌ Network sniffing fallbacks

3. **Testing Infrastructure**
   - ❌ Comprehensive test matrix
   - ❌ Security validation tests
   - ❌ Extension SW console log capture

## 🎯 **Current State**

We have a **simplified, auth-free version** that allows rapid development but is missing the full security architecture and advanced automation features from the original plan. The core structure is in place, but we've bypassed the security layer entirely for fast iteration.
