# YOLO+LLM Automation — Chrome Extension & Backend Integration Guide

This document is for the **owner agent (Claude Code)** and any engineer responsible for the **entire project**, especially those who haven’t touched the Chrome Extension side yet. It explains the architecture, code layout, data flows, APIs, and how the **auto-runner extension** and **backend** work together to deliver fully automated, one-click workflows (e.g., **reply on xiaohongshu.com**).

---

## 0) What you get (capabilities)

* **One-click Start** in the browser popup → the extension turns into a **daemon**.
* The daemon **polls the backend**, **opens pages**, **resolves UI targets** (heuristics + optional LLM), **executes plans**, **verifies success**, and **acks results**.
* **Server queue** (Postgres): `/commands/*` + `/devices/*`.
* **Resolver** service returns a **Task Query Plan (TQP)** with selectors and actions.
* **Self-learning selectors** via **SkillCards** (UCB bandit) and verifications (DOM + optional network pattern).
* **Structured outputs** (e.g., recent messages from a chat) returned on success.
* **Webhooks** optional: backend can POST results to your YOLO tool.

---

## 1) Repository map (relevant bits)
it is under folder:./getcontent/

```
backend/
  migrations/
    001_init.sql                 # users, sessions, brute_force, events, schema_migrations
    002_commands.sql             # devices, commands, cmd_status enum
    003_command_callbacks.sql    # callback_url, idempotency_key
  src/
    index.js                     # Express app, middleware, routes
    config.js                    # (if present; env glue)
    lib/
      db.js                      # pg Pool, q(), tx()
      users.js                   # createUser, findUserByUsername, bcrypt verify
      sessions.js                # create/get/destroy + middleware
      bruteforce.js              # lockout logic (5m, exponential)
      envelope.js, keys.js       # signed payload helpers (already in repo)
    routes/
      auth.js                    # POST /auth/login, /auth/logout, GET/POST /auth/me
      entitlement.js             # signed entitlement issuance (unchanged)
      plans.js                   # /plans/fetch (EQP or TQP files)
      resolve.js                 # /resolve/xhs_reply (LLM+heuristics → TQP)
      events.js                  # /events/ingest (telemetry)
      commands.js                # /devices/*, /commands/*
  data/
    plans/
      xhs_im.tqp.json            # example task: auto-reply on XHS IM
      indeed_apply.tqp.json      # example task: click Apply on Indeed
  tools/
    migrate.js                   # applies SQL migrations
    add-user.js                  # CLI to add a user

extension/
  manifest.json                  # MV3 permissions, background SW
  offscreen.html                 # keepalive during runs
  sw/
    bootstrap.js                 # SW entry: auth, messaging, signed fetch, daemon control
    daemon.js                    # auto-runner: poll/claim/run/ack + navigation + snapshot
    task_runner.js               # executes TQP (retries, post-verify, network waits, emits)
    actions.js                   # click/type/waitFor helpers (execute in MAIN world)
    actions_upload.js            # drop/prompt upload helpers
    output.js                    # extract structured outputs
    skill_store.js               # local UCB SkillCards (selector success/fail)
    db.js                        # KV (chrome.storage.local wrapper)
    verify.js, eqp_runner.js     # signature check & legacy EQP support
  ui/
    popup.html / popup.js / popup.css  # login + Start/Stop auto mode
  keys.json                      # public key for signature verify (no secrets)
  vendor/                        # (tweetnacl ESM if used)
sdk/
  node/yoloAuto.ts               # TypeScript SDK for /devices, /commands
  python/yolo_auto.py            # Python SDK
```

---

## 2) Database schema (key tables)

* `users (account_id, username, password_hash, is_active, created_at)`
* `sessions (sid, account_id, username, exp, last_seen, ip, ua)`
* `brute_force (username_lower, streak, exponent, lock_until)` — 3 failed → lock, exponential backoff (5m, 10m, 20m…)
* `events (id, account_id, type, host, payload, created_at)`
* `devices (device_id, account_id, last_seen, ua, created_at)`
* `commands (id, account_id, device_id, type, url, scope, vars, status, run_after, claimed_at, started_at, finished_at, result, error, callback_url, idempotency_key, updated_at)`

---

## 3) Backend HTTP APIs (used by extension & YOLO tool)

### Auth

* `POST /auth/login` → `{ username, password }`
  Sets cookie `sid`.
* `GET /devices/list` (requires session) → `{ devices:[{device_id, ua, last_seen}] }`
  List devices belonging to the logged-in account.

### Device heartbeat (from extension)

* `POST /devices/heartbeat` → `{ device_id, ua }`
  Upserts device row for current account; returns `{ ok, at }`.

### Command queue

* `POST /commands/enqueue`
  Body:

  ```
  {
    device_id: string,
    type: "xhs_reply" | "indeed_apply" | ...,
    url?: string,               // where to navigate before executing
    scope?: string,             // e.g., "task:xhs_auto_reply" (if using canned TQP)
    vars?: object,              // task variables (e.g., target_name, reply_text)
    run_after?: ISO string,     // schedule later (optional)
    callback_url?: string,      // if set, backend POSTs result on finished
    idempotency_key?: string    // dedupe key (optional)
  }
  ```

  Returns `{ ok, id, idempotent }`.

* `POST /commands/next` (from extension) → `{ cmd | null }`
  Claims the oldest `pending` command for `device_id`.

* `POST /commands/ack` (from extension)
  Body: `{ id, status: "running"|"succeeded"|"failed", result?, error? }`
  On terminal states and if `callback_url` exists, backend POSTs:

  ```
  {
    id, status, type, url, vars, result?, error?
  }
  ```

  to the given `callback_url`.

### Resolver & Plans

* `POST /resolve/xhs_reply`
  Body: `{ target_name, reply_text, snapshot? }`
  Returns `{ tqp, debug? }` — dynamic **Task Query Plan** for XHS reply.

  * If `OPENAI_API_KEY` is set, Tier-2 LLM picks selectors; otherwise heuristics.

* `POST /plans/fetch` (signed; used for canned plans or EQP)
  Body: `{ page_signature:{host}, scope }`
  Returns `envelope(payload)` with `payload.eqp` or `payload.tasks.tqp`.

### Telemetry

* `POST /events/ingest`
  Accepts any JSON payload; stored in `events`.

---

## 4) Chrome Extension: how it works

### MV3 lifecycle

* On **Start** (popup), the extension:

  * Logs in (`/auth/login`) to set cookie (if not already).
  * Stores account id & `auto_mode=true` in KV.
  * Calls `startDaemon()`.

* **Daemon** (`sw/daemon.js`) loop:

  1. **Heartbeat** → `/devices/heartbeat` (creates/updates `device_id`).
  2. Poll **`/commands/next`** → if a command exists:

     * Open **offscreen document** (`offscreen.html`) to keep SW alive.
     * If command has `url`, navigate (ensure tab & wait for load).
     * **Collect snapshot** (candidate selectors on page).
     * If `type === 'xhs_reply'`: call `/resolve/xhs_reply` with snapshot and vars → **TQP**.

       * Else if `scope` like `task:*`: call `/plans/fetch` → TQP.
     * Run **Task Runner** (`runTask(tqp, vars)`).
     * `POST /commands/ack` with `succeeded/failed` and `outputs` (see below).
     * Close offscreen document.
  3. Sleep and repeat (poll + `chrome.alarms` keepalive).

### Task Runner (TQP executor)

* **TQP format** supports steps:

  * `{"wait": { "selector"?, "ms"? }}`
  * `{"slot", "candidates":[css...], "action": { "type": "click"|"type"|"waitFor"|"uploadResumeDrop"|"uploadResumePrompt", ... }, "retry"?, "wait_after_ms"?, "post_verify"?, "await_network_after"? }`
  * `{"verify": { "selector", "sample_contains_any"?, "min_length"? }}`
  * `{"emit": { "name", "list"? | "props"? }}` — **structured outputs** via `output.js`
* **Variables**: strings in TQP can use `{{var}}` (rendered by `interp.js`).
* **Retries & backoff**: per action with post-verification.
* **Network waits**: after actions to confirm server-side completion (pattern match).
* **SkillCards UCB**: for each `slot`, multiple candidate selectors are tried and **success/failure** is recorded (`skill_store.js`) so the best selector is chosen next time.

### Actions & Outputs

* `actions.js`: `clickSelector`, `typeSelector`, `waitForSelector` (executed in the **MAIN** world).
* `actions_upload.js`: simulate **drag-and-drop** upload from a Data URL (`dropFileFromDataUrl`), or **focus** the `<input type="file">` to let the user pick (fallback).
* `output.js`: `extractList` and `extractOne` to return JSON (e.g., last 5 messages).

### Offscreen Keepalive

* `offscreen.html` is created **only during a run** to reduce MV3 suspension; closed after completion.

---

## 5) Resolver logic (XHS example)

* Input: `{ target_name, reply_text, snapshot }`.
* **Heuristics**: rank thread candidates by fuzzy match (name in text, timestamp patterns), pick input & send candidates.
* **Optional LLM** (if `OPENAI_API_KEY` configured):

  * Tier-2 calls LLM with constrained response format (JSON object with three selectors).
  * If LLM fails or is absent → fallback to heuristics.
* Output: a **TQP** that:

  1. waits for main container,
  2. clicks the resolved thread item,
  3. types `reply_text`,
  4. clicks `send`,
  5. waits for network pattern,
  6. emits last few messages,
  7. verifies last outgoing bubble contains our text.

---

## 6) End-to-end flows

### Bootstrapping

1. **Migrate & start backend**

   ```bash
   cd backend
   npm run db:migrate      # runs 001, 002, 003
   npm run user:add admin 123456 acct_admin
   npm run dev
   ```

2. **Load extension** (unpacked) in Chrome.
   Popup:

   * Login using the user you created.
   * Click **Start** (auto mode on).

3. **Enqueue a command** (from YOLO tool or a curl with your session cookie):

   ```bash
   curl -X POST -H 'Content-Type: application/json' -b 'sid=YOUR_SID' \
     -d '{
       "device_id":"DEVICE_ID_FROM_DEVICES_LIST",
       "type":"xhs_reply",
       "url":"https://www.xhs.com/im",
       "vars":{"target_name":"Alice","reply_text":"你好～已收到你的消息，我们尽快回复你哈！"},
       "callback_url":"https://your-yolo.app/automation/callback",
       "idempotency_key":"xhs-Alice-2025-09-10T10"
     }' \
     http://localhost:8787/commands/enqueue
   ```

4. The extension daemon:

   * Claims → navigates → resolves → executes → acks.
   * Backend POSTs to your `callback_url` (if provided).

### How the extension “knows who you want”

* The **command** includes intent & variables: `type: "xhs_reply"`, `vars.target_name`, `vars.reply_text`.
* Extension snapshots UI; **resolver** (LLM + heuristics) picks selectors.
* **Task Runner** executes deterministic actions; **verify** confirms success.
* **SkillCards** learns best selectors → fewer resolver calls over time.

---

## 7) SDKs (for YOLO tool)

### TypeScript

```ts
import { YoloAuto } from './sdk/node/yoloAuto';

const client = new YoloAuto('http://localhost:8787', /* optional cookie */);
const { devices } = await client.listDevices();
const deviceId = devices[0].device_id;

await client.enqueue({
  deviceId,
  type: 'xhs_reply',
  url: 'https://www.xhs.com/im',
  vars: { target_name: 'Alice', reply_text: '你好～' },
  callbackUrl: 'https://your-yolo.app/automation/callback',
  idempotencyKey: 'xhs-Alice-…'
});
```

### Python

```python
from sdk.python.yolo_auto import YoloAuto

client = YoloAuto('http://localhost:8787')
devs = client.list_devices()
device_id = devs[0]['device_id']

client.enqueue(device_id=device_id,
               type_='xhs_reply',
               url='https://www.xhs.com/im',
               vars={'target_name':'Alice','reply_text':'你好～'},
               callback_url='https://your-yolo.app/automation/callback',
               idempotency_key='xhs-Alice-…')
```

### LLM function schema

* **Function:** `enqueue_automation`
* **Params:**
  `device_id` (string), `type` (string), `url` (string), `vars` (object), `callback_url` (string, optional), `idempotency_key` (string, optional)

Use this in your agent to trigger browser actions.

---

## 8) Configuration & environment

**Backend `.env`**

```
DATABASE=postgresql://postgres:postgres@localhost:5432/postgres
PRODUCT_ID=yolo-llm-automation
KEY_ID=K1
ED25519_SEED_B64=REPLACE_WITH_BASE64_SEED
API_BASE=http://localhost:8787
DOMAIN_WHITELIST=xhs.com,indeed.com
NODE_ENV=development
OPENAI_API_KEY=...         # optional; enables LLM in resolver
```

**Extension**

* `manifest.json` requires permissions: `scripting`, `tabs`, `storage`, `webNavigation`, `alarms`, `offscreen`.
* **Service worker** files are bundled with the extension; no remote URLs.
* `keys.json` contains **public key** only (no secrets); used to verify `/plans/fetch` envelopes.

---

## 9) Testing & debugging

**SW logs**: `chrome://extensions` → “Service Worker” → Inspect.
**Network**: DevTools Network in the active tab.
**Backend logs**: `npm run dev`.
**DB**: check `commands` table:

```sql
select id, device_id, type, status, created_at from commands order by id desc limit 10;
```

**Common issues**

* **Service worker 400/registration failed**

  * Ensure `background.service_worker` points to a file that exists.
  * Keep `"type":"module"` and valid ESM imports (`./file.js` with the right relative paths).
  * Check `manifest_version: 3`.

* **Not authenticated (401)** from backend

  * Login via popup → check cookie set.
  * `app.set('trust proxy', 1)` configured if behind a proxy; set `NODE_ENV=production` in prod so cookies use `Secure`.

* **Nothing happens after Start**

  * Watch `/devices/heartbeat` in backend logs.
  * Make sure commands are enqueued for **the same account’s device**.

* **Click/type does nothing**

  * Verify `world: 'MAIN'` in `chrome.scripting.executeScript`.
  * Expand candidate selectors; use `post_verify` to ensure it really typed, and `await_network_after` to confirm server side.

---

## 10) Security & multi-tenancy (MVP ready)

* Users/passwords are in Postgres (bcrypt).
* Sessions in Postgres; brute-force lock in DB.
* Commands/devices scoped by **account\_id**.
* No secrets inside the extension; **signed plans** for `/plans/fetch`.
* For production hardening:

  * Add **Row-Level Security (RLS)** by `account_id`.
  * Add feature flags per tenant.
  * Use `callback_url` HMAC or allow-list IPs.

---

## 11) Extending beyond MVP (later)

* **Semantic locators service** (multi-signal scoring + server-side bandit).
* **Offscreen doc** only during runs (already implemented) + **event-driven** navigation handlers.
* **Admin UI** for devices/commands.
* **Native Messaging** for file IO (enterprise-only).
* **Headless runner** (Playwright) for cloud execution (reusing TQP).

---

## 12) Quick “XHS reply” walkthrough (what to wire in YOLO)

1. **List devices** → pick one device for the user.
2. **Enqueue**:

   ```json
   {
     "device_id":"dev_123",
     "type":"xhs_reply",
     "url":"https://www.xhs.com/im",
     "vars":{"target_name":"Alice","reply_text":"你好～"},
     "callback_url":"https://your-yolo.app/automation/callback"
   }
   ```
3. Extension **claims → navigates → resolves → runs → verifies**.
4. Backend **POSTs callback**:

   ```json
   { "id": 42, "status": "succeeded", "type": "xhs_reply", "url": "https://www.xhs.com/im",
     "vars": {"target_name":"Alice","reply_text":"你好～"},
     "result": {"messages":[{"dir":"msg right ...","text":"你好～"}, ...]} }
   ```
5. YOLO stores result, continues workflow (e.g., log CRM, follow-up tasks).

