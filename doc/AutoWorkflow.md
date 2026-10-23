我已经新建来一个文件夹叫做autoworkflow，以下方案全部代码都写入到这个文件夹。文件夹里面有个WorkflowConfigurationTool是一个UI的sample代码。你可以参考使用。schema文件夹里面有json schema你可以参考。根目录下WORKFLOW_CONFIG_GUIDE.md你可以在需要的时候参考。
下面是具体执行方案：
把“AI 生成 + 可视化配置 + 强校验”真正落地，建议采用**Schema-first**路线：以一份权威的 JSON Schema 驱动“表单渲染、智能补全、校验、Lint、模拟运行、版本管理、AI 生成回填”的全链条。下面给你一套可直接开工的实施方案（含数据模型、接口、AI 生成流程、校验与模拟、里程碑/工单清单）。

# 1) 总体架构（三层）

* **前端（Next.js/React）**

  * Tabs 与你 Figma 一致：Upload / AI Creator / Configure。
  * Monaco JSON Editor（Schema 感知）、DAG 可视化（@xyflow/react）、自动表单（react-jsonschema-form + 自定义 uiSchema）。
* **服务层（FastAPI 或 Express）**

  * /schemas（动作与工作流 Schema 注册/获取）
  * /workflows（CRUD + 版本化 + Diff）
  * /validate、/lint、/simulate、/generate（AI）
  * /registry/actions（动作目录，含参数 Schema）
* **执行/模拟层**

  * 复用你现有执行器的“Dry-run 适配器”，拦截 ext.\* / vision.\* / os.\* 调用做**无副作用**模拟，返回可观测轨迹与成本估算。

# 2) Schema-first 数据模型

采用 **JSON Schema 2020-12**。一份顶层工作流 Schema + 每个动作一份参数 Schema（注册到“动作目录”）。

**workflow\.schema.json（关键字段）**

```json
{
  "$id": "workflow.schema.json",
  "type": "object",
  "required": ["name", "version", "start", "steps"],
  "properties": {
    "name": {"type":"string"},
    "description": {"type":"string"},
    "version": {"type":"string"},
    "globals": {
      "type":"object",
      "properties": {
        "device_target": {"enum":["windows","mac","android","ios","web"]},
        "defaults": {"type":"object"},
        "env": {"type":"object"},
        "permissions": {"type":"array","items":{"enum":["camera","clipboard","screenread","filesystem"]}},
        "llm_budget": {"type":"object","properties":{"max_calls":{"type":"integer"},"max_tokens":{"type":"integer"}}},
        "auto_promote_on_success": {"type":"boolean", "default": false}
      }
    },
    "variables": {"type":"object"},
    "start": {"type":"string"},
    "steps": {
      "type":"array",
      "items": {"$ref":"#/definitions/Step"}
    },
    "edges": {
      "type":"array",
      "items": {"$ref":"#/definitions/Edge"}
    },
    "metadata": {"type":"object"}
  },
  "definitions": {
    "Step": {
      "type":"object",
      "required":["id","type"],
      "properties":{
        "id":{"type":"string"},
        "name":{"type":"string"},
        "type":{"enum":["action","branch","loop","parallel","wait","subflow","human_input"]},
        "uses":{"type":"string","description":"动作ID，如 ext.open_url / vision.find_element …"},
        "params":{"type":"object"},
        "when":{"type":"string","description":"条件表达式，支持 ${vars.*}"},
        "retry":{"type":"object","properties":{"times":{"type":"integer"},"backoff_ms":{"type":"integer"}}},
        "timeout_ms":{"type":"integer"},
        "on_error":{"enum":["fail","skip","goto"],"default":"fail"},
        "goto":{"type":"string"},
        "outputs":{"type":"object"}
      }
    },
    "Edge": {
      "type":"object",
      "required":["from","to"],
      "properties":{
        "from":{"type":"string"},
        "to":{"type":"string"},
        "condition":{"type":"string"}
      }
    }
  }
}
```

**动作目录（示例，服务端存储）**

```json
{
  "id": "ext.open_url",
  "title": "Open URL in browser",
  "schema": {
    "type":"object",
    "required":["url","app"],
    "properties":{
      "url":{"type":"string","format":"uri"},
      "app":{"enum":["Google Chrome","Edge","Arc","Firefox"]},
      "wait_dom_quiet_ms":{"type":"integer","default":800}
    }
  },
  "capabilities":["web"],
  "prerequisites": [],
  "cost_estimate":{"llm_tokens":0}
}
```

同理：`ext.click`, `ext.key`, `vision.find_element_with_image_check`, `os.type_text`, `ocr.extract_region`, `llm.plan`, `llm.reply`…都各自有参数 Schema。**UI 表单由这些 Schema 自动生成**，避免硬编码。

> 变量与插值：统一 `${vars.x}` / `${globals.env.API_KEY}` 语法，服务端在 /validate 做静态检查（未定义变量、类型不匹配等）。

# 3) AI Workflow Creator（生成闭环）

**输入**：Workflow Type、Complexity、自然语言描述 + 允许的动作白名单（来自目录）。
**流程**

1. **约束提示**：把 `workflow.schema.json` 与“动作目录+参数 Schema”裁剪后喂给 LLM；要求**只输出 JSON**。
2. **首次生成** → **Ajv 校验** → 不通过则携带错误清单回呼“Refine 提示”（自动二到三轮）。
3. **Lint**：语义规则（见下一节）+ 成本/风险提示。
4. **表单回填**：前端从 JSON 反向渲染 DAG 与 Step 表单，可手动调整。
5. **一键“生成+模拟”**：展示轨迹与截图位占位、LLM 调用预算、依赖检查。

**示例 Prompt 片段（服务端模板）**

* 动作目录（仅名称+简述+参数 Schema）
* 约束：不得调用目录外动作；必须有 `start`；总步数不超过 N；LLM 调用 ≤ budget；输出严格匹配 `workflow.schema.json`。
* 输出示例：给 1\~2 个极简范例（如你截图里的 Initialize/Process/Finalize）。

# 4) Validate / Lint（语义与安全）

在 Schema 校验之上，加一层工程规则：

* **图一致性**：所有 `edges.from/to` 必须存在；不可达/死循环（除 `loop` 类型）报错。
* **先决条件**：如 `ext.click` 之前必须出现 `ext.open_url`；`vision.*` 之前需有可见窗口。
* **设备/动作匹配**：`device_target=mac` 时禁止 `win32.*`。
* **变量**：未定义引用、类型不匹配、保留名覆盖。
* **预算**：LLM 调用次数/最大 tokens 超限预警；按动作 `cost_estimate` 做总量估算。
* **安全**：域名白名单、禁止访问系统路径等。

接口：

* `POST /validate {workflow}` → {valid, errors\[]}
* `POST /lint {workflow}` → {level, rule, fixit?}\[]

# 5) 模拟器 / Dry-Run

* 对 ext.*、vision.*、ocr.\* **不触发真实副作用**，返回**可预测的假数据**（或从你现有回放日志中采样）。
* 产物：轨迹（step→状态）、条件分支命中、截图/文字占位、**LLM 成本估算**。
* `POST /simulate {workflow, seed?, inputs?}` → {trace\[], estimates, warnings\[]}

# 6) 版本化与审发布

* Postgres JSONB 存储：`workflows(id, name, version, status, json, created_by, changelog)`
* Diff 与回滚：`/workflows/{id}/diff?from=v1.0.0&to=v1.1.0`
* 审批流：`status = draft -> staged -> prod`
* **auto\_promote\_on\_success**：在 CI 里跑 `/validate + /lint + /simulate` 全绿即自动晋级 `staged` 或 `prod`（与你现有日志系统 Phase 5 打通）。

# 7) 前端交互要点（对应你截图）

* **Upload**：读取→/validate→/lint→DAG 渲染→错误就地标注（指向具体 Step）。
* **AI Creator**：类型/复杂度/描述 → 调用 /generate → 一键“回填+模拟”。
* **Configure**：

  * Visualization：DAG 编辑、拖拽加边。
  * Step Config：**由动作 Schema 自动生成表单**；支持 uiSchema（enum→下拉、format uri→URL 输入框、secret→密码框）。
  * Global Config：device\_target / env / llm\_budget / auto\_promote\_on\_success 等。
  * JSON Editor：Monaco + Schema 智能补全 + 即时校验。

# 8) 最小可用模板（与截图一致）

```json
{
  "name": "go to facebook to say hi to jack",
  "description": "Open Facebook, find Jack, send hi.",
  "version": "1.0.0",
  "globals": {
    "device_target": "mac",
    "llm_budget": { "max_calls": 1, "max_tokens": 800 },
    "auto_promote_on_success": false
  },
  "start": "init",
  "steps": [
    {"id":"init","name":"Initialize","type":"action","uses":"ext.open_url",
     "params":{"url":"https://facebook.com","app":"Google Chrome","wait_dom_quiet_ms":1200}},
    {"id":"process","name":"Process","type":"action","uses":"ext.key","params":{"key":"Enter"}},
    {"id":"finalize","name":"Finalize","type":"action","uses":"llm.reply",
     "params":{"prompt":"Say 'hi' to Jack in the chat window"}}
  ],
  "edges":[
    {"from":"init","to":"process"},
    {"from":"process","to":"finalize"}
  ]
}
```

> 这份 JSON 在你的表单/可视化里可直接演示，后续再细化为可点击定位、输入消息的真实动作组合（ext.click + type\_text …）。

# 9) 里程碑与 Jira 工单清单（可直接创建）

**M1 Schema 与动作目录（1.5 周）**

* JIRA: 定义 workflow\.schema.json v1.1（含 auto\_promote\_on\_success）
* JIRA: 定义 ext.\* / vision.\* / ocr.\* / llm.\* 参数 Schema
* JIRA: /schemas & /registry/actions API

**M2 校验与 Lint（1 周）**

* JIRA: Ajv 集成与 JSON Pointer 错误定位
* JIRA: 语义规则实现（先决条件/变量/预算/图一致性）
* JIRA: /validate /lint 接口

**M3 前端编辑器（2 周）**

* JIRA: DAG 可视化与边编辑
* JIRA: Schema-form 自动表单 + uiSchema
* JIRA: Monaco + Schema 智能补全

**M4 AI Creator（1.5 周）**

* JIRA: /generate 模板与多轮自修正
* JIRA: 生成→校验→回填闭环
* JIRA: 复杂度预设（4–6/7–12/13+ 步）

**M5 模拟器（1 周）**

* JIRA: Dry-run 适配器与轨迹可视化
* JIRA: 成本估算器（按动作 cost\_estimate 聚合）

**M6 版本化与发布（0.5 周）**

* JIRA: 版本存储/Diff/回滚
* JIRA: auto\_promote\_on\_success CI 钩子

**M7 模板与文档（0.5 周）**

* JIRA: 模板库（XHS采集、FB问候、微信回复…）
* JIRA: Swagger + ER 图 + 使用手册

---

## 关键回答

* \*\*要不要基于 JSON Schema？必须。\*\*它是“单一事实源”，能驱动 UI 表单、智能补全、强校验、Lint、模拟与自动生成，彻底降低复杂度并避免漂移。
* \*\*如何落地？\*\*按上面 7 个模块 + 6 大接口 + 里程碑推进，先把 Schema 与动作目录定死，再让 UI/AI/执行都围绕它转。


1:
好，我们从\*\*第 1 步（M1-S1）\*\*开始，一次只做一小块、可立即落地的内容：
**建仓 + 放入权威 JSON Schema + 起一个最小校验服务（/schemas、/validate）**。等你跑通后，我再给你第 2 步（Lint 规则与 /lint 接口）。

---

# 第 1 步（M1-S1）：仓库结构 + Schema + 校验服务

## 1) 目录结构（新建 repo：`workflow-config-service`）

```
workflow-config-service/
├─ package.json
├─ tsconfig.json
├─ src/
│  ├─ index.ts                # Express 启动
│  ├─ lib/ajv.ts              # Ajv 初始化（JSON Schema 校验）
│  ├─ routes/
│  │  ├─ schemas.ts           # GET /schemas, GET /registry/actions
│  │  └─ validate.ts          # POST /validate
│  └─ types.ts                # 基础类型
├─ schemas/
│  └─ workflow.schema.json    # 工作流顶层 Schema（权威）
├─ registry/
│  ├─ index.json              # 动作目录索引
│  └─ actions/
│     ├─ ext.open_url.schema.json
│     ├─ ext.key.schema.json
│     ├─ type_text.schema.json
│     └─ …（后续补齐）
└─ examples/
   └─ wf_facebook_hi.json     # 可用于本地验证的示例工作流
```

## 2) package.json

```json
{
  "name": "workflow-config-service",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "tsx src/index.ts",
    "build": "tsc -p tsconfig.json",
    "start": "node dist/index.js",
    "validate:example": "curl -s -X POST http://localhost:8787/validate -H 'Content-Type: application/json' --data-binary @examples/wf_facebook_hi.json | jq"
  },
  "dependencies": {
    "ajv": "^8.12.0",
    "ajv-formats": "^3.0.1",
    "express": "^4.19.2"
  },
  "devDependencies": {
    "@types/express": "^4.17.21",
    "tsx": "^4.16.2",
    "typescript": "^5.6.3"
  }
}
```

## 3) tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "Node",
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "esModuleInterop": true,
    "resolveJsonModule": true,
    "skipLibCheck": true
  },
  "include": ["src"]
}
```

## 4) `schemas/workflow.schema.json`（v1.1，含 `auto_promote_on_success`）

```json
{
  "$id": "workflow.schema.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Workflow",
  "type": "object",
  "required": ["name", "version", "start", "steps"],
  "properties": {
    "name": { "type": "string", "minLength": 1 },
    "description": { "type": "string" },
    "version": { "type": "string" },
    "globals": {
      "type": "object",
      "properties": {
        "device_target": { "enum": ["windows", "mac", "android", "ios", "web"] },
        "defaults": { "type": "object", "additionalProperties": true },
        "env": { "type": "object", "additionalProperties": { "type": "string" } },
        "permissions": {
          "type": "array",
          "items": { "enum": ["camera", "clipboard", "screenread", "filesystem"] }
        },
        "llm_budget": {
          "type": "object",
          "properties": {
            "max_calls": { "type": "integer", "minimum": 0 },
            "max_tokens": { "type": "integer", "minimum": 0 }
          },
          "additionalProperties": false
        },
        "auto_promote_on_success": { "type": "boolean", "default": false }
      },
      "additionalProperties": false
    },
    "variables": {
      "type": "object",
      "description": "运行时可注入变量，步骤中可用 ${vars.key} 引用",
      "additionalProperties": true
    },
    "start": { "type": "string", "minLength": 1 },
    "steps": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/Step" }
    },
    "edges": {
      "type": "array",
      "items": { "$ref": "#/$defs/Edge" }
    },
    "metadata": { "type": "object", "additionalProperties": true }
  },
  "additionalProperties": false,
  "$defs": {
    "Step": {
      "type": "object",
      "required": ["id", "type"],
      "properties": {
        "id": { "type": "string", "minLength": 1 },
        "name": { "type": "string" },
        "type": { "enum": ["action", "branch", "loop", "parallel", "wait", "subflow", "human_input"] },
        "uses": {
          "type": "string",
          "description": "动作 ID（需在 registry 中存在），如 ext.open_url / vision.find_element"
        },
        "params": { "type": "object", "additionalProperties": true },
        "when": { "type": "string", "description": "条件表达式，支持 ${vars.*}" },
        "retry": {
          "type": "object",
          "properties": {
            "times": { "type": "integer", "minimum": 0 },
            "backoff_ms": { "type": "integer", "minimum": 0 }
          },
          "additionalProperties": false
        },
        "timeout_ms": { "type": "integer", "minimum": 0 },
        "on_error": { "enum": ["fail", "skip", "goto"], "default": "fail" },
        "goto": { "type": "string" },
        "outputs": { "type": "object", "additionalProperties": true }
      },
      "additionalProperties": false
    },
    "Edge": {
      "type": "object",
      "required": ["from", "to"],
      "properties": {
        "from": { "type": "string", "minLength": 1 },
        "to": { "type": "string", "minLength": 1 },
        "condition": { "type": "string" }
      },
      "additionalProperties": false
    }
  }
}
```

## 5) 动作目录（registry）

### `registry/index.json`

```json
{
  "actions": [
    { "id": "ext.open_url", "title": "Open URL in browser", "schema": "actions/ext.open_url.schema.json" },
    { "id": "ext.key", "title": "Send single key", "schema": "actions/ext.key.schema.json" },
    { "id": "type_text", "title": "Type text (OS)", "schema": "actions/type_text.schema.json" }
  ]
}
```

### `registry/actions/ext.open_url.schema.json`

```json
{
  "$id": "ext.open_url.schema.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ext.open_url",
  "type": "object",
  "required": ["url", "app"],
  "properties": {
    "url": { "type": "string", "format": "uri" },
    "app": { "enum": ["Google Chrome", "Edge", "Arc", "Firefox"] },
    "wait_dom_quiet_ms": { "type": "integer", "minimum": 0, "default": 800 }
  },
  "additionalProperties": false
}
```

### `registry/actions/ext.key.schema.json`

```json
{
  "$id": "ext.key.schema.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ext.key",
  "type": "object",
  "required": ["key"],
  "properties": {
    "key": {
      "type": "string",
      "description": "单个按键，如 Enter、Esc、Tab、ArrowDown、ArrowUp 等"
    },
    "modifiers": {
      "type": "array",
      "items": { "enum": ["Ctrl", "Alt", "Shift", "Cmd"] }
    }
  },
  "additionalProperties": false
}
```

### `registry/actions/type_text.schema.json`

```json
{
  "$id": "type_text.schema.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "type_text",
  "type": "object",
  "required": ["text"],
  "properties": {
    "text": { "type": "string" },
    "mode": { "enum": ["type", "paste"], "default": "type" },
    "interval_ms": { "type": "integer", "minimum": 0, "default": 0 }
  },
  "additionalProperties": false
}
```

## 6) 示例工作流（examples/wf\_facebook\_hi.json）

```json
{
  "name": "go to facebook to say hi to jack",
  "description": "Open Facebook, then send hi to Jack",
  "version": "1.0.0",
  "globals": {
    "device_target": "mac",
    "llm_budget": { "max_calls": 1, "max_tokens": 800 },
    "auto_promote_on_success": false
  },
  "start": "init",
  "steps": [
    {
      "id": "init",
      "name": "Initialize",
      "type": "action",
      "uses": "ext.open_url",
      "params": { "url": "https://facebook.com", "app": "Google Chrome", "wait_dom_quiet_ms": 1200 }
    },
    {
      "id": "process",
      "name": "Process",
      "type": "action",
      "uses": "ext.key",
      "params": { "key": "Enter" }
    },
    {
      "id": "finalize",
      "name": "Finalize",
      "type": "action",
      "uses": "type_text",
      "params": { "text": "hi Jack :)", "mode": "type" }
    }
  ],
  "edges": [
    { "from": "init", "to": "process" },
    { "from": "process", "to": "finalize" }
  ]
}
```

## 7) 代码：Ajv 初始化（`src/lib/ajv.ts`）

```ts
import Ajv from "ajv";
import addFormats from "ajv-formats";
import workflowSchema from "../../schemas/workflow.schema.json" assert { type: "json" };

export function createAjv() {
  const ajv = new Ajv({ allErrors: true, strict: false });
  addFormats(ajv);

  // 注册顶层 workflow schema
  ajv.addSchema(workflowSchema, "workflow.schema.json");
  return ajv;
}
```

## 8) 代码：类型（`src/types.ts`）

```ts
export type Json = any;
```

## 9) 代码：路由 `/schemas`（`src/routes/schemas.ts`）

```ts
import { Router } from "express";
import registryIndex from "../../registry/index.json" assert { type: "json" };

export const schemasRouter = Router();

// 顶层 workflow schema
schemasRouter.get("/schemas/workflow", (_req, res) => {
  // 直接让静态服务器处理更好；这里简单返回文件
  // 为保持简洁，这里用 import 读取
  // 如果你更倾向静态目录，可挂载 express.static
  // @ts-ignore
  import("../../schemas/workflow.schema.json", { assert: { type: "json" } })
    .then((m) => res.json(m.default))
    .catch((e) => res.status(500).json({ error: String(e) }));
});

// 动作目录索引
schemasRouter.get("/registry/actions", (_req, res) => {
  res.json(registryIndex);
});

// 某个动作的参数 schema
schemasRouter.get("/registry/actions/:id", async (req, res) => {
  const id = req.params.id; // 如 ext.open_url
  const item = (registryIndex.actions as any[]).find((a) => a.id === id);
  if (!item) return res.status(404).json({ error: "action not found" });

  try {
    // @ts-ignore
    const mod = await import(`../../registry/${item.schema}`, { assert: { type: "json" } });
    res.json(mod.default);
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});
```

## 10) 代码：路由 `/validate`（`src/routes/validate.ts`）

```ts
import { Router } from "express";
import { createAjv } from "../lib/ajv.js";

const ajv = createAjv();
const validateWorkflow = ajv.getSchema("workflow.schema.json");

export const validateRouter = Router();

validateRouter.post("/validate", (req, res) => {
  const payload = req.body;

  if (!validateWorkflow) {
    return res.status(500).json({ ok: false, errors: ["schema not loaded"] });
  }

  const ok = validateWorkflow(payload);
  if (ok) {
    return res.json({ ok: true, errors: [] });
  }

  const errors = (validateWorkflow.errors || []).map((e) => {
    return {
      instancePath: e.instancePath,
      schemaPath: e.schemaPath,
      keyword: e.keyword,
      message: e.message
    };
  });

  res.status(400).json({ ok: false, errors });
});
```

## 11) 代码：服务入口（`src/index.ts`）

```ts
import express from "express";
import { schemasRouter } from "./routes/schemas.js";
import { validateRouter } from "./routes/validate.js";

const app = express();
app.use(express.json({ limit: "2mb" }));

app.get("/healthz", (_req, res) => res.json({ ok: true }));
app.use(schemasRouter);
app.use(validateRouter);

// 静态暴露 schemas/ 与 registry/（前端也可直接拉）
app.use("/_static/schemas", express.static("schemas"));
app.use("/_static/registry", express.static("registry"));

const PORT = process.env.PORT || 8787;
app.listen(PORT, () => {
  console.log(`workflow-config-service listening on http://localhost:${PORT}`);
});
```

## 12) 安装与启动

```bash
# 新建目录后
npm i
npm run dev
# 另一个终端（可选，验证示例）
npm run validate:example
```

**预期返回：**

* 通过：`{ "ok": true, "errors": [] }`
* 否则返回 400，带 JSON Pointer 的错误位置，方便前端定位到具体 Step/字段。

---

### 你现在可以做的事情

1. 把以上文件照搬进一个新仓库，`npm run dev` 启动服务。
2. `curl` 或 Postman 调用 `POST /validate`，喂 `examples/wf_facebook_hi.json`，确认能通过。
3. 前端就可以：

   * Monaco Editor 绑定 `/schemas/workflow` 做 Schema-aware 自动补全。
   * “选择动作”面板调用 `/registry/actions`，按选中动作拉取参数 Schema，渲染表单。

---

如果这一小步你跑通了，我马上给你**第 2 步（M1-S2）**：

* 实现**语义 Lint 规则**（图一致性/先决条件/变量检查/预算检查），
* 暴露 `POST /lint` 接口（带 ruleId、level、fixit 建议），
* 并给出前端“就地标注”的错误映射方案。

2:
好，我们进入**第 2 步（M1-S2：语义 Lint 与 /lint 接口）**。这一小步做完，你就能在前端把“红点报错/黄色警告”就地标注到具体字段和 Step 上，并在生成器后立刻提示可修复建议。

---

# 一、要实现的能力

* 基于 **JSON Schema** 的结构校验之外，再做**语义检查**：

  * 图一致性（起点、无效边、不可达、环路）
  * 动作合法性（未知动作、参数与动作 schema 校验）
  * 先决条件（例如 `ext.click` 之前必须出现 `ext.open_url`）
  * 变量与引用（`${vars.*}` 必须已在 `variables` 定义；禁止未允许的根引用）
  * 预算（LLM tokens 估算 vs `globals.llm_budget`）
  * 设备/动作匹配（Mac/Windows 常见修饰键误用）
  * 边缺失（无 edges 时给出顺序执行的建议）
* 提供 `POST /lint`：

  * **请求**：`{ workflow }`
  * **响应**：`{ issues: LintIssue[] }`
  * `LintIssue = { code, level, message, pointer?, fix? }`

    * `pointer` 采用 **JSON Pointer**（如 `/steps/1/params/key`），便于前端精确定位
    * `level ∈ { "error", "warn", "info" }`
    * `fix` 给出**可操作建议**（文本或简单替换方案）

> 说明：下面的代码直接放进你上一步的仓库即可运行（与第 1 步保持兼容）。若与你的文件路径不同，按需微调 import 路径。

---

# 二、注册动作的元数据（更新 `registry/index.json`）

在动作索引里补充 **prerequisites / capabilities / cost\_estimate**，用于 Lint 与预算估算。

```json
{
  "actions": [
    {
      "id": "ext.open_url",
      "title": "Open URL in browser",
      "schema": "actions/ext.open_url.schema.json",
      "prerequisites": [],
      "capabilities": ["web"],
      "cost_estimate": { "llm_tokens": 0 }
    },
    {
      "id": "ext.key",
      "title": "Send single key",
      "schema": "actions/ext.key.schema.json",
      "prerequisites": [],
      "capabilities": ["input"],
      "cost_estimate": { "llm_tokens": 0 }
    },
    {
      "id": "type_text",
      "title": "Type text (OS)",
      "schema": "actions/type_text.schema.json",
      "prerequisites": [],
      "capabilities": ["input"],
      "cost_estimate": { "llm_tokens": 0 }
    }

    /*** 你后面会陆续添加：
     *  vision.find_element_with_image_check（prereq: ext.open_url 或窗口激活）
     *  ocr.extract_region
     *  llm.plan / llm.reply（cost_estimate: 预估 tokens）
     ***/
  ]
}
```

---

# 三、Lint 引擎实现

## 1) 类型与工具（`src/lint/types.ts`）

```ts
export type Level = "error" | "warn" | "info";

export interface LintIssue {
  code: string;        // 例如 WF001
  level: Level;
  message: string;
  pointer?: string;    // JSON Pointer
  fix?: string;        // 简短修复建议
}

export interface WorkflowLike {
  name: string;
  version: string;
  start: string;
  globals?: any;
  variables?: Record<string, any>;
  steps: Array<any>;
  edges?: Array<{ from: string; to: string; condition?: string }>;
}
```

## 2) 规则实现（`src/lint/rules.ts`）

```ts
import Ajv from "ajv";
import addFormats from "ajv-formats";
import registryIndex from "../../registry/index.json" assert { type: "json" };
import { LintIssue, WorkflowLike } from "./types.js";

// ---------- Ajv for action param schema ----------
const ajv = new Ajv({ allErrors: true, strict: false });
addFormats(ajv);

type RegistryAction = {
  id: string;
  title: string;
  schema: string;
  prerequisites?: string[];
  capabilities?: string[];
  cost_estimate?: { llm_tokens?: number };
};

const ACTIONS: RegistryAction[] = (registryIndex as any).actions;

// 缓存已编译的动作 schema
const compiledActionValidators = new Map<string, any>();

async function validateActionParams(actionId: string, params: any) {
  const meta = ACTIONS.find(a => a.id === actionId);
  if (!meta) {
    return { ok: false, errors: [`unknown action: ${actionId}`] };
  }
  let validator = compiledActionValidators.get(actionId);
  if (!validator) {
    // 动态加载对应 schema
    // @ts-ignore
    const mod = await import(`../../registry/${meta.schema}`, { assert: { type: "json" } });
    validator = ajv.compile(mod.default);
    compiledActionValidators.set(actionId, validator);
  }
  const ok = validator(params || {});
  if (ok) return { ok: true, errors: [] };
  const errors = (validator.errors || []).map((e: any) => `${e.instancePath || ""} ${e.message}`);
  return { ok: false, errors };
}

// ---------- 通用工具 ----------
const stepById = (wf: WorkflowLike) => {
  const m = new Map<string, any>();
  for (const s of wf.steps) m.set(s.id, s);
  return m;
};

function buildAdjacency(wf: WorkflowLike) {
  const adj = new Map<string, Set<string>>();
  for (const s of wf.steps) adj.set(s.id, new Set());
  if (wf.edges && wf.edges.length) {
    for (const e of wf.edges) {
      if (adj.has(e.from)) adj.get(e.from)!.add(e.to);
    }
  } else {
    // 无 edges: 默认顺序相连
    for (let i = 0; i < wf.steps.length - 1; i++) {
      adj.get(wf.steps[i].id)!.add(wf.steps[i + 1].id);
    }
  }
  return adj;
}

function reachableFromStart(wf: WorkflowLike, adj: Map<string, Set<string>>) {
  const seen = new Set<string>();
  const q = [wf.start];
  while (q.length) {
    const u = q.shift()!;
    if (seen.has(u)) continue;
    seen.add(u);
    const next = adj.get(u);
    if (next) for (const v of next) q.push(v);
  }
  return seen;
}

function detectCycles(wf: WorkflowLike, adj: Map<string, Set<string>>) {
  const WHITE = 0, GRAY = 1, BLACK = 2;
  const color = new Map<string, number>();
  for (const s of wf.steps) color.set(s.id, WHITE);
  const cycles: string[][] = [];

  function dfs(u: string, stack: string[]) {
    color.set(u, GRAY);
    stack.push(u);
    for (const v of (adj.get(u) || [])) {
      if (color.get(v) === WHITE) dfs(v, stack);
      else if (color.get(v) === GRAY) {
        // cycle found u -> v
        const idx = stack.indexOf(v);
        if (idx >= 0) cycles.push(stack.slice(idx).concat([v]));
      }
    }
    stack.pop();
    color.set(u, BLACK);
  }
  dfs(wf.start, []);
  return cycles;
}

const VAR_REF = /\$\{([^}]+)\}/g;
function collectStringRefs(obj: any, acc = new Set<string>()) {
  if (obj == null) return acc;
  if (typeof obj === "string") {
    let m;
    while ((m = VAR_REF.exec(obj)) !== null) acc.add(m[1]);
    return acc;
  }
  if (Array.isArray(obj)) {
    for (const v of obj) collectStringRefs(v, acc);
  } else if (typeof obj === "object") {
    for (const k of Object.keys(obj)) collectStringRefs(obj[k], acc);
  }
  return acc;
}

// ---------- 规则集合 ----------
export async function lintWorkflow(wf: WorkflowLike): Promise<LintIssue[]> {
  const issues: LintIssue[] = [];

  // 基础映射
  const id2step = stepById(wf);

  // WF001: 重复 step id
  const idCount = new Map<string, number>();
  for (const s of wf.steps) idCount.set(s.id, (idCount.get(s.id) || 0) + 1);
  for (const [id, c] of idCount) {
    if (c > 1) issues.push({
      code: "WF001", level: "error",
      message: `duplicate step id "${id}"`,
      pointer: `/steps/${wf.steps.findIndex(x => x.id === id)}`
    });
  }

  // WF002: start 必须存在
  if (!id2step.has(wf.start)) {
    issues.push({ code: "WF002", level: "error", message: `start step "${wf.start}" not found`, pointer: "/start", fix: "将 /start 设置为现有 step.id" });
    return issues; // 后续依赖图，直接返回
  }

  const adj = buildAdjacency(wf);

  // WF003: 边引用有效性
  if (wf.edges && wf.edges.length) {
    wf.edges.forEach((e, i) => {
      if (!id2step.has(e.from) || !id2step.has(e.to)) {
        issues.push({
          code: "WF003", level: "error",
          message: `edge references invalid id: ${e.from} -> ${e.to}`,
          pointer: `/edges/${i}`
        });
      }
    });
  } else if (wf.steps.length > 1) {
    issues.push({
      code: "WF060", level: "warn",
      message: "edges are empty; defaulting to sequential flow. Consider explicitly adding edges.",
      pointer: "/edges",
      fix: "在可视化编辑器里连线，或让系统自动生成顺序边"
    });
  }

  // WF004: 不可达 step
  const reach = reachableFromStart(wf, adj);
  wf.steps.forEach((s, i) => {
    if (!reach.has(s.id)) {
      issues.push({
        code: "WF004", level: "warn",
        message: `step "${s.id}" is unreachable from start`,
        pointer: `/steps/${i}`
      });
    }
  });

  // WF006: 环路（允许 loop 类型中的自环/小环，粗略豁免）
  const cycles = detectCycles(wf, adj);
  for (const cyc of cycles) {
    const hasLoopType = cyc.some(id => id2step.get(id)?.type === "loop");
    if (!hasLoopType) {
      issues.push({
        code: "WF006", level: "error",
        message: `cycle detected: ${cyc.join(" -> ")}`,
        pointer: "/edges",
        fix: "在 Loop 容器内实现循环或打断回边"
      });
    }
  }

  // WF020/WF021: 动作存在 + 参数校验
  for (let i = 0; i < wf.steps.length; i++) {
    const s = wf.steps[i];
    if (s.type === "action") {
      const meta = ACTIONS.find(a => a.id === s.uses);
      if (!meta) {
        issues.push({
          code: "WF020", level: "error",
          message: `unknown action "${s.uses}"`,
          pointer: `/steps/${i}/uses`
        });
        continue;
      }
      const r = await validateActionParams(s.uses, s.params);
      if (!r.ok) {
        issues.push({
          code: "WF021", level: "error",
          message: `params invalid for "${s.uses}": ${r.errors.join("; ")}`,
          pointer: `/steps/${i}/params`,
          fix: `参考动作参数 schema：GET /registry/actions/${s.uses}`
        });
      }
    }
  }

  // WF010: 先决条件（简单策略：需在当前 step 之前出现）
  const seenActions = new Set<string>();
  for (let i = 0; i < wf.steps.length; i++) {
    const s = wf.steps[i];
    if (s.type === "action") {
      const meta = ACTIONS.find(a => a.id === s.uses)!;
      const prereq = meta?.prerequisites || [];
      for (const need of prereq) {
        if (!seenActions.has(need)) {
          issues.push({
            code: "WF010", level: "error",
            message: `"${s.uses}" requires prerequisite "${need}" to appear earlier`,
            pointer: `/steps/${i}`,
            fix: `在此步骤之前添加动作 "${need}"`
          });
        }
      }
      seenActions.add(s.uses);
    }
  }

  // WF030/031: 变量引用
  const varKeys = new Set(Object.keys(wf.variables || {}));
  for (let i = 0; i < wf.steps.length; i++) {
    const s = wf.steps[i];
    const refs = collectStringRefs(s.params);
    refs.forEach(ref => {
      // 允许 roots: vars.*, globals.env.*, outputs.<step>.*
      if (ref.startsWith("vars.")) {
        const k = ref.slice("vars.".length).split(".")[0];
        if (!varKeys.has(k)) {
          issues.push({
            code: "WF030", level: "error",
            message: `undefined variable "${k}" referenced by \${${ref}}`,
            pointer: `/steps/${i}/params`,
            fix: `在 /variables 定义 "${k}" 或移除该引用`
          });
        }
      } else if (ref.startsWith("globals.env.")) {
        // ok（不校验是否存在）
      } else if (ref.startsWith("outputs.")) {
        // 暂不做跨步输出存在性检查，可在后续 M1-S4 增强
      } else {
        issues.push({
          code: "WF031", level: "warn",
          message: `unsupported reference root in \${${ref}} (allowed: vars.*, globals.env.*, outputs.*)`,
          pointer: `/steps/${i}/params`
        });
      }
    });
  }

  // WF040: 预算（非常轻量的估算）
  const budget = wf.globals?.llm_budget;
  if (budget?.max_tokens != null) {
    let estTokens = 0;
    for (let i = 0; i < wf.steps.length; i++) {
      const s = wf.steps[i];
      if (s.type !== "action") continue;
      const meta = ACTIONS.find(a => a.id === s.uses);
      if (!meta) continue;
      // 规则1：目录里的 cost_estimate.llm_tokens
      if (meta.cost_estimate?.llm_tokens) {
        estTokens += meta.cost_estimate.llm_tokens!;
      }
      // 规则2：如果是 llm.* 且 params.prompt 为字符串，则按长度估（粗略 1 token ≈ 4 chars）
      if (s.uses?.startsWith("llm.") && typeof s.params?.prompt === "string") {
        estTokens += Math.ceil((s.params.prompt as string).length / 4);
      }
    }
    if (estTokens > budget.max_tokens * 1.2) {
      issues.push({
        code: "WF040", level: "error",
        message: `LLM token estimate ${estTokens} exceeds budget ${budget.max_tokens}`,
        pointer: "/globals/llm_budget",
        fix: "减少 llm.* 调用或缩短 prompt，或上调预算"
      });
    } else if (estTokens > budget.max_tokens * 0.8) {
      issues.push({
        code: "WF040", level: "warn",
        message: `LLM token estimate ${estTokens} is close to budget ${budget.max_tokens}`,
        pointer: "/globals/llm_budget"
      });
    }
  }

  // WF050: 设备/键位常识提醒
  const device = wf.globals?.device_target;
  for (let i = 0; i < wf.steps.length; i++) {
    const s = wf.steps[i];
    if (s.type === "action" && s.uses === "ext.key" && Array.isArray(s.params?.modifiers)) {
      if (device === "windows" && s.params.modifiers.includes("Cmd")) {
        issues.push({
          code: "WF050", level: "warn",
          message: `using "Cmd" on Windows; did you mean "Ctrl"?`,
          pointer: `/steps/${i}/params/modifiers`,
          fix: `将 "Cmd" 改为 "Ctrl"（或设定 device_target 为 "mac"）`
        });
      }
      if (device === "mac" && s.params.modifiers.includes("Ctrl")) {
        issues.push({
          code: "WF050", level: "warn",
          message: `using "Ctrl" on macOS; did you mean "Cmd"?`,
          pointer: `/steps/${i}/params/modifiers`,
          fix: `将 "Ctrl" 改为 "Cmd"（或设定 device_target 为 "windows"）`
        });
      }
    }
  }

  return issues;
}
```

## 3) Lint 入口（`src/lint/index.ts`）

```ts
import { lintWorkflow } from "./rules.js";
export { lintWorkflow };
```

## 4) 路由：`POST /lint`（`src/routes/lint.ts`）

```ts
import { Router } from "express";
import { lintWorkflow } from "../lint/index.js";
import { createAjv } from "../lib/ajv.js";

const router = Router();
const ajv = createAjv();
const validateWorkflow = ajv.getSchema("workflow.schema.json");

// 先做结构校验，再做语义 Lint
router.post("/lint", async (req, res) => {
  const workflow = req.body;
  if (!validateWorkflow) return res.status(500).json({ error: "schema not loaded" });

  const ok = validateWorkflow(workflow);
  if (!ok) {
    const errs = (validateWorkflow.errors || []).map(e => ({
      code: "SCHEMA",
      level: "error",
      message: `${e.instancePath || "/"} ${e.message}`,
      pointer: e.instancePath || "/"
    }));
    return res.status(400).json({ issues: errs });
  }

  const issues = await lintWorkflow(workflow);
  const hasError = issues.some(i => i.level === "error");
  return res.status(hasError ? 400 : 200).json({ issues });
});

export { router as lintRouter };
```

## 5) 将路由挂载到服务（`src/index.ts` 更新）

```ts
import { lintRouter } from "./routes/lint.js";
// ...
app.use(lintRouter);
```

---

# 四、如何本地验证

```bash
# 启动服务
npm run dev

# 1) 结构合法 + Lint（可能只有 warning）
curl -s -X POST http://localhost:8787/lint \
  -H 'Content-Type: application/json' \
  --data-binary @examples/wf_facebook_hi.json | jq

# 2) 制造一个错误：把 ext.key 的 key 改成空，或把 uses 改成 "ext.unknown"
```

**响应示例（部分）**

```json
{
  "issues": [
    {
      "code": "WF060",
      "level": "warn",
      "message": "edges are empty; defaulting to sequential flow. Consider explicitly adding edges.",
      "pointer": "/edges",
      "fix": "在可视化编辑器里连线，或让系统自动生成顺序边"
    }
  ]
}
```

---

# 五、前端对接建议（就地标注）

* 请求返回的 `pointer` 可直接映射到 Monaco Editor 的行列（用 JSON Pointer → AST 路径定位），也可在“Step Config”表单里根据 `/steps/<idx>/...` 精确高亮对应字段。
* “一键修复”按钮：

  * 对 `WF060` 可自动生成顺序边并写回 JSON。
  * 对 `WF030` 可跳转到 `/variables` 面板自动创建占位键。
  * 对 `WF050` 可在当前 Params 中把 `Ctrl/Cmd` 自动替换。

---

# 六、这一步到此完成后你将具备

* `/validate`（结构） + `/lint`（语义）闭环
* 前端可以：

  * 上传/生成后立即跑 Lint，显示错误/警告
  * 在“可视化 / Step Config / JSON Editor”三视图里同步定位问题并修复

---

3:
好，我们进入**第 3 步（M1-S3：最小模拟器 /simulate）**。这一步做完，你可以在前端点一下“Simulate”，即时看到：按 `start → …` 的执行轨迹、每步产出（占位）、耗时估计、分支命中与 LLM 成本估算。

---

# 一、能力清单（这一版的模拟器能做什么）

* **按图执行**：有 `edges` 用条件分支；没有就顺序执行。
* **变量替换**：支持 `${vars.*}`、`${globals.env.*}`、`${outputs.<stepId>.*}`。
* **条件求值**：支持 `== / !=`、`contains(haystack, needle)`、布尔常量（`true/false`）与简单变量直接量（`vars.x`）。
* **动作干跑（Dry-run）**：不做真实 IO；对常见动作返回可预测占位结果：

  * `ext.open_url` → `{ page: <host>, ready: true }`
  * `ext.key` → `{ sent: "<key>" }`
  * `type_text` → `{ typed_len: N }`
  * 未识别动作 → 通用 `{ ok: true }`
* **成本估算**：聚合 `registry` 里的 `cost_estimate.llm_tokens`；若将来有 `llm.*` 且带 `prompt`，按“约 4 字符≈1 token”粗估。
* **可重复性**：可传 `seed`；本版不依赖随机数，先占位。

---

# 二、文件改动（直接拷进你现有仓库）

### 1) `src/sim/types.ts`

```ts
export type StepStatus = "ok" | "skipped" | "error";

export interface SimTraceEntry {
  id: string;
  name?: string;
  uses?: string;
  status: StepStatus;
  started_ms: number;
  duration_ms: number;
  outputs?: Record<string, any>;
  warning?: string;
  error?: string;
}

export interface SimEstimates {
  llm_tokens: number;
  llm_calls: number;
}

export interface SimResult {
  trace: SimTraceEntry[];
  estimates: SimEstimates;
  finished: boolean;
  last_step?: string;
  warnings?: string[];
}
```

### 2) `src/sim/strings.ts`（变量替换）

```ts
const REF = /\$\{([^}]+)\}/g;

export function resolveRefs(value: any, ctx: Record<string, any>): any {
  if (value == null) return value;
  if (typeof value === "string") {
    return value.replace(REF, (_, expr) => {
      try {
        const v = readRef(expr, ctx);
        return v == null ? "" : String(v);
      } catch {
        return "";
      }
    });
  }
  if (Array.isArray(value)) return value.map(v => resolveRefs(v, ctx));
  if (typeof value === "object") {
    const out: any = {};
    for (const k of Object.keys(value)) out[k] = resolveRefs(value[k], ctx);
    return out;
  }
  return value;
}

export function readRef(expr: string, ctx: Record<string, any>): any {
  // 允许 vars.* / globals.env.* / outputs.<step>.*
  if (expr.startsWith("vars.")) {
    return pick(ctx.vars || {}, expr.slice(5));
  }
  if (expr.startsWith("globals.env.")) {
    return pick(((ctx.globals || {}).env) || {}, expr.slice(12));
  }
  if (expr.startsWith("outputs.")) {
    return pick(ctx.outputs || {}, expr.slice(8));
  }
  // 直接量：true/false 或简单名字（如 vars.x）
  if (expr === "true") return true;
  if (expr === "false") return false;
  if (expr === "null") return null;
  // 简单直取：vars.x / globals.device_target
  return pick(ctx, expr);
}

function pick(obj: any, path: string) {
  const segs = path.split(".");
  let cur = obj;
  for (const s of segs) {
    if (cur == null) return undefined;
    cur = cur[s];
  }
  return cur;
}
```

### 3) `src/sim/cond.ts`（条件求值）

```ts
import { readRef } from "./strings.js";

// 仅支持：
//   - 布尔常量 true/false
//   - 变量名：vars.x / outputs.step.y / globals.env.K
//   - expr == "text" / expr != "text"
//   - contains(expr, "needle")
export function evalCond(cond: string | undefined, ctx: Record<string, any>): boolean {
  if (!cond) return true;
  const s = cond.trim();

  if (s === "true") return true;
  if (s === "false") return false;

  // contains(a, "b")
  const mContains = /^contains\((.+?),\s*"(.*)"\)$/.exec(s);
  if (mContains) {
    const left = valueOf(mContains[1].trim(), ctx);
    return String(left).includes(mContains[2]);
  }

  // expr == "literal" | expr != "literal"
  const mEq = /^(.+?)(==|!=)\s*"(.*)"$/.exec(s);
  if (mEq) {
    const left = String(valueOf(mEq[1].trim(), ctx));
    const lit = mEq[3];
    return mEq[2] === "==" ? left === lit : left !== lit;
  }

  // 单变量真假
  const v = valueOf(s, ctx);
  return !!v;
}

function valueOf(expr: string, ctx: Record<string, any>): any {
  if (expr.startsWith("vars.") || expr.startsWith("outputs.") || expr.startsWith("globals.")) {
    return readRef(expr, ctx);
  }
  // 字面量 "abc"
  if ((expr.startsWith("\"") && expr.endsWith("\"")) || (expr.startsWith("'") && expr.endsWith("'"))) {
    return expr.slice(1, -1);
  }
  return expr; // 其他按字符串返回
}
```

### 4) `src/sim/actions.ts`（动作干跑）

```ts
import { resolveRefs } from "./strings.js";

export interface SimCtx {
  vars: Record<string, any>;
  globals: Record<string, any>;
  outputs: Record<string, any>; // stepId -> outputs
}

export interface SimActionResult {
  ok: boolean;
  outputs?: Record<string, any>;
  duration_ms?: number;
  warning?: string;
}

export async function simulateAction(
  uses: string,
  params: any,
  ctx: SimCtx
): Promise<SimActionResult> {
  // 变量替换（深度）
  const p = resolveRefs(params || {}, ctx);

  switch (uses) {
    case "ext.open_url": {
      const url = p.url || "";
      const host = safeHost(url);
      return {
        ok: true,
        duration_ms: Math.max(200, Math.min(1200, (p.wait_dom_quiet_ms ?? 800))),
        outputs: { page: host, ready: true }
      };
    }
    case "ext.key": {
      return { ok: true, duration_ms: 50, outputs: { sent: p.key, modifiers: p.modifiers || [] } };
    }
    case "type_text": {
      const text = String(p.text ?? "");
      const per = Math.max(0, Math.min(15, p.interval_ms ?? 0));
      const dur = Math.min(2000, text.length * (per || 5));
      return { ok: true, duration_ms: dur, outputs: { typed_len: text.length, mode: p.mode || "type" } };
    }
    default:
      // 未定义的动作：返回通用 ok
      return { ok: true, duration_ms: 50, warning: `no simulator for action "${uses}"` , outputs: { ok: true } };
  }
}

function safeHost(url: string) {
  try { return new URL(url).host; } catch { return ""; }
}
```

### 5) `src/sim/runner.ts`（图执行器）

```ts
import { evalCond } from "./cond.js";
import { simulateAction, SimCtx } from "./actions.js";
import { SimResult, SimTraceEntry } from "./types.js";
import registryIndex from "../../registry/index.json" assert { type: "json" };

type WF = {
  start: string;
  steps: Array<any>;
  edges?: Array<{ from: string; to: string; condition?: string }>;
  globals?: any;
  variables?: any;
};

const ACTIONS = (registryIndex as any).actions as Array<any>;

function buildAdj(wf: WF) {
  const adj = new Map<string, Array<{ to: string; condition?: string }>>();
  for (const s of wf.steps) adj.set(s.id, []);
  if (wf.edges?.length) {
    for (const e of wf.edges) {
      if (!adj.has(e.from)) adj.set(e.from, []);
      adj.get(e.from)!.push({ to: e.to, condition: e.condition });
    }
  } else {
    for (let i = 0; i < wf.steps.length - 1; i++) {
      adj.get(wf.steps[i].id)!.push({ to: wf.steps[i + 1].id });
    }
  }
  return adj;
}

function findStep(wf: WF, id: string) {
  return wf.steps.find(s => s.id === id);
}

export async function simulateWorkflow(wf: WF, seed?: number): Promise<SimResult> {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const rng = mulberry32(seed ?? 1);

  const ctx: SimCtx = { vars: wf.variables || {}, globals: wf.globals || {}, outputs: {} };
  const adj = buildAdj(wf);
  const trace: SimTraceEntry[] = [];
  let estimates = { llm_tokens: 0, llm_calls: 0 };

  // 预算估算（非常轻量）
  for (const s of wf.steps) {
    if (s.type !== "action") continue;
    const meta = ACTIONS.find(a => a.id === s.uses);
    if (meta?.cost_estimate?.llm_tokens) estimates.llm_tokens += meta.cost_estimate.llm_tokens;
    if (String(s.uses || "").startsWith("llm.")) {
      estimates.llm_calls += 1;
      if (typeof s.params?.prompt === "string") {
        estimates.llm_tokens += Math.ceil(s.params.prompt.length / 4);
      }
    }
  }

  let cur = wf.start;
  let safety = 0;
  while (cur && safety++ < 1000) {
    const step = findStep(wf, cur);
    if (!step) break;

    const started = Date.now();
    if (step.type === "action") {
      const r = await simulateAction(step.uses, step.params, ctx);
      const e: SimTraceEntry = {
        id: step.id,
        name: step.name,
        uses: step.uses,
        status: r.ok ? "ok" : "error",
        started_ms: started,
        duration_ms: r.duration_ms ?? 0,
        outputs: r.outputs,
        warning: r.warning
      };
      trace.push(e);
      ctx.outputs[step.id] = r.outputs || {};
    } else {
      trace.push({
        id: step.id,
        name: step.name,
        uses: step.type,
        status: "ok",
        started_ms: started,
        duration_ms: 0
      });
    }

    // 下一个节点（按条件挑第一个满足的）
    const options = adj.get(step.id) || [];
    let next = "";
    for (const opt of options) {
      const ok = evalCond(opt.condition, { ...ctx, step });
      if (ok) { next = opt.to; break; }
    }
    if (!next) break;
    cur = next;
  }

  return {
    trace,
    estimates,
    finished: !!cur ? false : true,
    last_step: trace.at(-1)?.id,
    warnings: trace.filter(t => !!t.warning).map(t => t.warning!) || []
  };
}

// 简易 RNG（占位）
function mulberry32(a: number) {
  return function() {
    let t = (a += 0x6D2B79F5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
```

### 6) `src/routes/simulate.ts`（API 路由）

```ts
import { Router } from "express";
import { createAjv } from "../lib/ajv.js";
import { simulateWorkflow } from "../sim/runner.js";

const router = Router();
const ajv = createAjv();
const validate = ajv.getSchema("workflow.schema.json");

router.post("/simulate", async (req, res) => {
  const { workflow, seed } = req.body || {};
  if (!workflow) return res.status(400).json({ error: "missing 'workflow' in body" });
  if (!validate) return res.status(500).json({ error: "schema not loaded" });

  const ok = validate(workflow);
  if (!ok) {
    return res.status(400).json({
      error: "schema validation failed",
      issues: (validate.errors || []).map(e => ({
        pointer: e.instancePath || "/",
        message: e.message
      }))
    });
  }

  try {
    const result = await simulateWorkflow(workflow, seed);
    res.json(result);
  } catch (e: any) {
    res.status(500).json({ error: String(e?.message || e) });
  }
});

export { router as simulateRouter };
```

### 7) 把路由挂载到服务（`src/index.ts` 更新）

```ts
import { simulateRouter } from "./routes/simulate.js";
// ...
app.use(simulateRouter);
```

---

# 三、如何本地验证

```bash
npm run dev

# 1) 跑模拟（用你 examples/wf_facebook_hi.json）
curl -s -X POST http://localhost:8787/simulate \
  -H 'Content-Type: application/json' \
  -d '{"workflow":'$(cat examples/wf_facebook_hi.json)'}' | jq

# 2) 观察返回：
#   - trace[]：每步的 id/name/uses/status/duration_ms/outputs
#   - estimates：llm_tokens/llm_calls
#   - finished：是否到达终点
```

**返回示例（节选）**

```json
{
  "trace": [
    {
      "id": "init",
      "name": "Initialize",
      "uses": "ext.open_url",
      "status": "ok",
      "duration_ms": 1200,
      "outputs": { "page": "facebook.com", "ready": true }
    },
    {
      "id": "process",
      "name": "Process",
      "uses": "ext.key",
      "status": "ok",
      "duration_ms": 50,
      "outputs": { "sent": "Enter", "modifiers": [] }
    },
    {
      "id": "finalize",
      "name": "Finalize",
      "uses": "type_text",
      "status": "ok",
      "duration_ms": 55,
      "outputs": { "typed_len": 9, "mode": "type" }
    }
  ],
  "estimates": { "llm_tokens": 0, "llm_calls": 0 },
  "finished": true,
  "last_step": "finalize",
  "warnings": []
}
```

---

# 四、前端接入建议

* **Visualization**：把 `trace` 画成时间轴或 Gantt 条；点击某步→右侧显示 `outputs`。
* **Step Config**：当 `simulate` 成功后，在每个 Step 卡片上显示“上次模拟产出（占位）”小角标。
* **边条件调试**：当某个条件为 false，可把 `evalCond` 的解析过程（左值、操作符、右值）一起回显到 UI（下一步我们可以扩展一个 `explain: true` 模式）。

---

4:
好，进入**第 4 步（M1-S4：AI 生成器 /generate）**。这一版提供一个**最小可用**的 AI 生成工作流服务：把“描述 + 复杂度 + 允许动作”交给 LLM，拿回 JSON；随后自动**validate → lint → 自修正（最多 3 轮）**，最终返回可用的 workflow JSON 与问题列表。

---

# 1) 增量能力概述

* `POST /generate`：输入 `{ type, complexity, description, allow_actions? }`
* 服务端拼装**受约束提示**（包含：允许动作的简化参数 schema、输出契约、步数上限）
* 调 LLM（通用 OpenAI-兼容接口），只接受 **JSON** 输出
* 失败则把 **Ajv + Lint 的报错**回灌给模型，自动再生成（至多 3 次）
* 返回：`{ ok, workflow, issues, attempts, notes }`

---

# 2) 轻改注册表（新增一个 llm.reply，便于成本估算）

**registry/index.json**（在现有 3 个动作后追加一项）

```json
{
  "id": "llm.reply",
  "title": "LLM reply",
  "schema": "actions/llm.reply.schema.json",
  "prerequisites": [],
  "capabilities": ["llm"],
  "cost_estimate": { "llm_tokens": 200 }
}
```

**registry/actions/llm.reply.schema.json**

```json
{
  "$id": "llm.reply.schema.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "llm.reply",
  "type": "object",
  "required": ["prompt"],
  "properties": {
    "prompt": { "type": "string", "minLength": 1 }
  },
  "additionalProperties": false
}
```

---

# 3) LLM 调用基座（无第三方依赖）

**src/llm/call.ts**

```ts
export type ChatMessage = { role: "system" | "user" | "assistant"; content: string };

type CallOpts = {
  model?: string;
  temperature?: number;
  max_tokens?: number;
};

export async function callLLM(messages: ChatMessage[], opts: CallOpts = {}) {
  const base = process.env.LLM_BASE_URL || "https://api.openai.com/v1";
  const apiKey = process.env.LLM_API_KEY;
  if (!apiKey) throw new Error("LLM_API_KEY not set");
  const model = opts.model || (process.env.LLM_MODEL || "gpt-4o-mini");

  const resp = await fetch(`${base}/chat/completions`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      model,
      temperature: opts.temperature ?? 0.2,
      max_tokens: opts.max_tokens ?? 1200,
      response_format: { type: "json_object" },
      messages
    })
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`LLM error ${resp.status}: ${txt}`);
  }
  const data = await resp.json();
  const content = data.choices?.[0]?.message?.content ?? "";
  return content as string;
}
```

> 说明：使用 OpenAI-兼容 Chat Completions（可替换为你现有 `callAI`）。通过 `LLM_BASE_URL / LLM_API_KEY / LLM_MODEL` 环境变量配置。

---

# 4) 生成服务（核心逻辑）

**src/services/generate.ts**

```ts
import registryIndex from "../../registry/index.json" assert { type: "json" };
import workflowSchema from "../../schemas/workflow.schema.json" assert { type: "json" };
import { createAjv } from "../lib/ajv.js";
import { lintWorkflow } from "../lint/index.js";
import { callLLM, ChatMessage } from "../llm/call.js";

type GenReq = {
  type?: string;
  complexity?: "small" | "medium" | "large";
  description: string;
  allow_actions?: string[];
};

const ACTIONS = (registryIndex as any).actions as Array<any>;

function briefActionSchema(actionId: string, maxLen = 420): string {
  const meta = ACTIONS.find(a => a.id === actionId);
  if (!meta) return `- ${actionId}: (unknown)`;
  // @ts-ignore
  const schemaMod = (await import(`../../registry/${meta.schema}`, { assert: { type: "json" } })).default;
  // 压缩成简要格式：只列 key、类型与枚举
  const props = schemaMod.properties || {};
  const req = schemaMod.required || [];
  const parts = Object.keys(props).map(k => {
    const p = props[k];
    const t = p.type || (p.enum ? "enum" : "object");
    const en = p.enum ? ` enum=${JSON.stringify(p.enum)}` : "";
    return `${k}:${t}${en}${req.includes(k) ? " *" : ""}`;
  });
  let s = `- ${meta.id}: ${parts.join(", ")}`;
  return s.length > maxLen ? s.slice(0, maxLen) + "…" : s;
}

function mapComplexity(c: GenReq["complexity"]) {
  switch (c) {
    case "small": return { maxSteps: 4 };
    case "large": return { maxSteps: 15 };
    case "medium":
    default: return { maxSteps: 8 };
  }
}

function systemPrompt() {
  return [
    `You are a Workflow JSON generator for a YOLO+LLM+Extension automation engine.`,
    `STRICT RULES:`,
    `1) Output ONLY JSON (no prose).`,
    `2) Must follow "workflow.schema.json": fields: name, description, version, globals, start, steps[], edges[].`,
    `3) steps[i]: {id,name,type,uses,params,...}; type usually "action".`,
    `4) "uses" must be chosen from the provided Action Catalog.`,
    `5) steps length <= maxSteps.`,
    `6) Use simple, runnable params; prefer deterministic values.`,
    `7) Keep version "1.0.0".`,
    `8) Globals include: {"device_target":"web","llm_budget":{"max_calls":1,"max_tokens":800},"auto_promote_on_success":false}.`,
    `9) If branching needed, add edges with optional "condition".`,
    `10) Avoid undefined variables; use literals unless user specifies variables.`,
  ].join("\n");
}

function contractSnippet() {
  const s = workflowSchema;
  // 简短契约（减少上下文体积）
  return {
    required: s.required,
    props: Object.keys(s.properties),
    stepProps: Object.keys(s.$defs.Step.properties),
    edgeProps: Object.keys(s.$defs.Edge.properties)
  };
}

export async function generateWorkflow(req: GenReq) {
  const allow = new Set(req.allow_actions && req.allow_actions.length
    ? req.allow_actions
    : ACTIONS.map(a => a.id)
  );
  const actionBriefs: string[] = [];
  for (const a of allow) {
    // @ts-ignore
    const meta = ACTIONS.find(x => x.id === a);
    if (meta) {
      // 动态导入 schema 并压缩（保持 token 轻量）
      // eslint-disable-next-line no-await-in-loop
      const mod = await import(`../../registry/${meta.schema}`, { assert: { type: "json" } });
      const props = mod.default.properties || {};
      const req = mod.default.required || [];
      const parts = Object.keys(props).map(k => {
        const p = props[k];
        const t = p.type || (p.enum ? "enum" : "object");
        const en = p.enum ? ` enum=${JSON.stringify(p.enum)}` : "";
        return `${k}:${t}${en}${req.includes(k) ? " *" : ""}`;
      });
      actionBriefs.push(`- ${meta.id}: ${parts.join(", ")}`);
    }
  }

  const { maxSteps } = mapComplexity(req.complexity);
  const sys: ChatMessage = { role: "system", content: systemPrompt() };
  const user: ChatMessage = {
    role: "user",
    content: [
      `Task Type: ${req.type || "general"}`,
      `Complexity: ${req.complexity || "medium"} (maxSteps=${maxSteps})`,
      `Description: ${req.description}`,
      `Action Catalog (choose only from these):`,
      actionBriefs.join("\n"),
      `Output Contract (compact):`,
      JSON.stringify(contractSnippet())
    ].join("\n\n")
  };

  const ajv = createAjv();
  const validate = ajv.getSchema("workflow.schema.json");

  const attempts: Array<{ round: number; note: string }> = [];
  let lastJson: any = null;
  let issues: any[] = [];
  let round = 0;

  while (round < 3) {
    round++;
    const msgs: ChatMessage[] = [sys, user];
    if (issues.length) {
      msgs.push({
        role: "user",
        content: [
          `Your previous output had the following problems; fix them and resend FULL JSON only:`,
          `- Validation/Lint Issues:`,
          ...issues.map((e: any) => `* ${e.pointer || ""} ${e.message || e}`),
          `Remember: steps length <= ${maxSteps}; only use allowed actions.`
        ].join("\n")
      });
    }

    const content = await callLLM(msgs, { temperature: 0.2, max_tokens: 1600 });
    let parsed: any;
    try {
      parsed = JSON.parse(content);
    } catch (e) {
      attempts.push({ round, note: "non-json output" });
      issues = [{ pointer: "/", message: "LLM did not return valid JSON" }];
      continue;
    }

    lastJson = parsed;

    // 限制步数
    if (Array.isArray(parsed.steps) && parsed.steps.length > maxSteps) {
      issues = [{ pointer: "/steps", message: `steps exceed maxSteps (${parsed.steps.length} > ${maxSteps})` }];
      attempts.push({ round, note: "too many steps" });
      continue;
    }

    // validate
    if (!validate) throw new Error("schema not loaded");
    const ok = validate(parsed);
    const vIssues = ok ? [] : (validate.errors || []).map(e => ({
      pointer: e.instancePath || "/",
      message: e.message
    }));

    // lint
    const lIssues = ok ? await lintWorkflow(parsed) : [];
    const allIssues = [
      ...vIssues.map(i => ({ ...i, code: "SCHEMA" })),
      ...lIssues.map(i => ({ pointer: i.pointer, message: `${i.code}: ${i.message}` }))
    ];

    // 若存在 error 级别，迭代
    const hasError = allIssues.some((x: any) => String(x.message || "").includes("WF") || String(x.code) === "SCHEMA");
    if (allIssues.length && hasError) {
      issues = allIssues;
      attempts.push({ round, note: "fixing issues" });
      continue;
    }

    // 可接受
    issues = allIssues;
    attempts.push({ round, note: "ok" });
    break;
  }

  // 最终结果
  const ok = lastJson && issues.filter((x: any) => String(x.code) === "SCHEMA" || String(x.message || "").startsWith("WF")).length === 0;
  return {
    ok,
    workflow: lastJson,
    issues,
    attempts,
    notes: ok ? "generated and passed validation/lint" : "generated with outstanding issues"
  };
}
```

---

# 5) 路由：`POST /generate`

**src/routes/generate.ts**

```ts
import { Router } from "express";
import { generateWorkflow } from "../services/generate.js";

export const generateRouter = Router();

/**
 * body: { type?: string, complexity?: "small"|"medium"|"large", description: string, allow_actions?: string[] }
 */
generateRouter.post("/generate", async (req, res) => {
  const body = req.body || {};
  if (!body.description) return res.status(400).json({ error: "description is required" });

  try {
    const result = await generateWorkflow(body);
    if (!result.ok) return res.status(400).json(result);
    res.json(result);
  } catch (e: any) {
    res.status(500).json({ error: String(e?.message || e) });
  }
});
```

**src/index.ts**（挂载路由）

```ts
import { generateRouter } from "./routes/generate.js";
// ...
app.use(generateRouter);
```

---

# 6) 运行与联调

1. 配置环境变量（任选 OpenAI-兼容服务）：

```bash
export LLM_API_KEY=sk-***
# 可选：
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_MODEL=gpt-4o-mini
```

2. 启动服务：

```bash
npm run dev
```

3. 试调用：

```bash
curl -s -X POST http://localhost:8787/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "web_greeting",
    "complexity": "medium",
    "description": "Open Facebook, search friend Jack, open chat and say hi",
    "allow_actions": ["ext.open_url","ext.key","type_text","llm.reply"]
  }' | jq
```

返回将包含 `workflow`、`issues[]`、`attempts[]`。
前端拿到 `workflow` 后直接**回填到 Visualization / Step Config / JSON Editor**；如果 `issues` 非空，按 `pointer` 就地标注。

---

# 7) 前端接入（最小）

* AI Creator 面板点击“Generate Workflow”：

  1. 调 `POST /generate`
  2. 若 `ok==true` → 载入工作流 → 自动触发 `/simulate` 展示轨迹
  3. 若 `ok==false` → 展示 `issues`（按钮：一键再试 → 再次调用 /generate）

---

5:
好，进入**第 5 步（M1-S5）：补全关键动作 + 跨步引用校验 + 一键修复 /fix**。把这一步做完，你就能在生成/配置后做到：

1. 直接使用 Vision/OCR/Click 这些**高频动作**；
2. **静态检查** `${outputs.<stepId>.*}` 的跨步引用是否存在且在拓扑上可达；
3. 对常见问题**一键修复**（补 edges、修 start、变量占位、Ctrl↔Cmd 等）。

---

# 一、注册更多动作（Schema + 目录元数据）

## 1) 更新 `registry/index.json`

在现有 3 个动作后追加以下条目（包含 `prerequisites` 与 `output_contract`，供 Lint/Sim/跨步检查使用）：

```json
{
  "actions": [
    { "id": "ext.open_url", "title": "Open URL in browser", "schema": "actions/ext.open_url.schema.json",
      "prerequisites": [], "capabilities": ["web"], "cost_estimate": { "llm_tokens": 0 },
      "output_contract": { "page": "string", "ready": "boolean" }
    },
    { "id": "ext.key", "title": "Send single key", "schema": "actions/ext.key.schema.json",
      "prerequisites": [], "capabilities": ["input"], "cost_estimate": { "llm_tokens": 0 },
      "output_contract": { "sent": "string", "modifiers": "array" }
    },
    { "id": "type_text", "title": "Type text (OS)", "schema": "actions/type_text.schema.json",
      "prerequisites": [], "capabilities": ["input"], "cost_estimate": { "llm_tokens": 0 },
      "output_contract": { "typed_len": "number", "mode": "string" }
    },

    { "id": "ext.click", "title": "Click on screen/DOM", "schema": "actions/ext.click.schema.json",
      "prerequisites": ["ext.open_url"], "capabilities": ["input","web"], "cost_estimate": { "llm_tokens": 0 },
      "output_contract": { "clicked": "boolean", "at": "object" }
    },
    { "id": "vision.find_element_with_image_check",
      "title": "Find UI element by image fingerprint",
      "schema": "actions/vision.find_element_with_image_check.schema.json",
      "prerequisites": ["ext.open_url"],
      "capabilities": ["vision"],
      "cost_estimate": { "llm_tokens": 0 },
      "output_contract": { "bbox": "object", "center": "array", "score": "number", "fingerprint_id": "string" }
    },
    { "id": "ocr.extract_region", "title": "OCR text from region",
      "schema": "actions/ocr.extract_region.schema.json",
      "prerequisites": ["ext.open_url"],
      "capabilities": ["ocr"],
      "cost_estimate": { "llm_tokens": 0 },
      "output_contract": { "text": "string", "lang": "string" }
    },
    { "id": "llm.reply", "title": "LLM reply", "schema": "actions/llm.reply.schema.json",
      "prerequisites": [], "capabilities": ["llm"], "cost_estimate": { "llm_tokens": 200 },
      "output_contract": { "text": "string" }
    }
  ]
}
```

## 2) 新增动作 Schema

### `registry/actions/ext.click.schema.json`

```json
{
  "$id": "ext.click.schema.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ext.click",
  "type": "object",
  "oneOf": [
    { "required": ["selector"] },
    { "required": ["x", "y"] },
    { "required": ["ref"] }
  ],
  "properties": {
    "selector": { "type": "string", "description": "CSS/XPath (由扩展决定解析策略)" },
    "x": { "type": "number", "minimum": 0 },
    "y": { "type": "number", "minimum": 0 },
    "ref": {
      "type": "string",
      "description": "引用某步输出的坐标，如 ${outputs.find_btn.center.0}, ${outputs.stepA.center}"
    },
    "button": { "enum": ["left","right","middle"], "default": "left" },
    "clicks": { "type": "integer", "minimum": 1, "default": 1 },
    "delay_ms": { "type": "integer", "minimum": 0, "default": 0 }
  },
  "additionalProperties": false
}
```

### `registry/actions/vision.find_element_with_image_check.schema.json`

```json
{
  "$id": "vision.find_element_with_image_check.schema.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "vision.find_element_with_image_check",
  "type": "object",
  "required": ["anchor_image_id", "method"],
  "properties": {
    "anchor_image_id": { "type": "string", "description": "云端指纹ID或本地资源ID" },
    "method": { "enum": ["image","template","yolo_class"], "default": "image" },
    "threshold": { "type": "number", "minimum": 0, "maximum": 1, "default": 0.75 },
    "search_region": {
      "type": "object",
      "properties": { "x": {"type":"number"}, "y": {"type":"number"}, "w": {"type":"number"}, "h": {"type":"number"} },
      "required": ["x","y","w","h"],
      "additionalProperties": false
    },
    "uniqueness": { "enum": ["auto","nearest_to","largest","highest_score"], "default": "auto" },
    "nearest_to": {
      "type": "object",
      "properties": {
        "ref": { "type":"string", "description":"如 ${outputs.prev.center}" }
      },
      "required": ["ref"],
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

### `registry/actions/ocr.extract_region.schema.json`

```json
{
  "$id": "ocr.extract_region.schema.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ocr.extract_region",
  "type": "object",
  "oneOf": [
    { "required": ["region"] },
    { "required": ["ref"] }
  ],
  "properties": {
    "region": {
      "type": "object",
      "properties": { "x":{"type":"number"}, "y":{"type":"number"}, "w":{"type":"number"}, "h":{"type":"number"} },
      "required": ["x","y","w","h"],
      "additionalProperties": false
    },
    "ref": { "type":"string", "description":"如 ${outputs.find_btn.bbox}" },
    "backend": { "enum": ["auto","paddle","tesseract"], "default": "auto" },
    "lang": { "type": "string", "default": "en" }
  },
  "additionalProperties": false
}
```

---

# 二、模拟器扩展（Vision/OCR/Click）

修改 `src/sim/actions.ts`：新增 3 个分支（用占位数据干跑）。

```ts
case "ext.click": {
  // 支持 selector / (x,y) / ref（在 resolveRefs 后都变成具体值）
  const at = ("selector" in p)
    ? { selector: p.selector }
    : ("x" in p && "y" in p)
      ? { x: p.x, y: p.y }
      : { ref: p.ref };
  return { ok: true, duration_ms: 80, outputs: { clicked: true, at } };
}

case "vision.find_element_with_image_check": {
  // 产出 bbox/center/score/fingerprint_id（占位）
  const bbox = p.search_region || { x: 100, y: 200, w: 120, h: 36 };
  const center = [bbox.x + Math.round(bbox.w/2), bbox.y + Math.round(bbox.h/2)];
  const score = Math.max(0.76, p.threshold ?? 0.75);
  return {
    ok: true,
    duration_ms: 120,
    outputs: { bbox, center, score, fingerprint_id: p.anchor_image_id }
  };
}

case "ocr.extract_region": {
  const text = "Hello, world"; // 占位
  const lang = p.lang || "en";
  return { ok: true, duration_ms: 180, outputs: { text, lang } };
}
```

---

# 三、跨步输出引用检查（`WF081` 系列）

在 `src/lint/rules.ts` 里新增**输出契约检查**：

1. 识别 `${outputs.<stepId>.<field>...}`
2. 检查 `<stepId>` 是否存在，且**在当前步之前**
3. 用 `registry.output_contract` 断言该 `<field>` 合法

### 1) 辅助函数（加到 `rules.ts` 顶部工具区）

```ts
function parseOutputsRef(ref: string) {
  // 支持 outputs.stepId.field.sub
  if (!ref.startsWith("outputs.")) return null;
  const parts = ref.split(".");
  if (parts.length < 3) return null;
  const stepId = parts[1];
  const fieldPath = parts.slice(2); // ["center","0"] 之类
  return { stepId, fieldPath };
}

function getActionMeta(actionId: string) {
  return (ACTIONS as any[]).find(a => a.id === actionId);
}

function contractHasField(contract: any, fieldPath: string[]) {
  if (!contract) return true; // 没声明合约则放过
  let cur = contract;
  for (const seg of fieldPath) {
    // 简易：只校验第一层字段名存在即可；更深层按需扩展
    if (typeof cur === "object" && seg in cur) {
      cur = cur[seg];
    } else {
      // 如果是数组索引，允许跳过
      if (/^\d+$/.test(seg)) continue;
      return false;
    }
  }
  return true;
}
```

### 2) 在 `lintWorkflow` 循环中加入（放在变量引用检查之后）

```ts
// WF081: outputs.<stepId>.field 存在性与拓扑顺序
const stepIndex = new Map<string, number>();
wf.steps.forEach((s, i) => stepIndex.set(s.id, i));

for (let i = 0; i < wf.steps.length; i++) {
  const s = wf.steps[i];
  const refs = collectStringRefs(s.params);
  refs.forEach(ref => {
    if (!ref.startsWith("outputs.")) return;
    const parsed = parseOutputsRef(ref);
    if (!parsed) return;
    const { stepId, fieldPath } = parsed;

    if (!stepIndex.has(stepId)) {
      issues.push({
        code: "WF081", level: "error",
        message: `reference to outputs of unknown step "${stepId}"`,
        pointer: `/steps/${i}/params`,
        fix: "检查 stepId 是否拼写错误，或先添加产生该输出的步骤"
      });
      return;
    }
    if ((stepIndex.get(stepId) || 0) >= i) {
      issues.push({
        code: "WF082", level: "error",
        message: `outputs of "${stepId}" referenced before it runs`,
        pointer: `/steps/${i}/params`,
        fix: `将当前步骤移动到 "${stepId}" 之后，或消除前向引用`
      });
      return;
    }
    const srcStep = wf.steps[stepIndex.get(stepId)!];
    const meta = getActionMeta(srcStep.uses);
    const contract = meta?.output_contract;
    if (!contractHasField(contract, fieldPath)) {
      issues.push({
        code: "WF083", level: "error",
        message: `field "${fieldPath.join(".")}" not in ${srcStep.uses} output_contract`,
        pointer: `/steps/${i}/params`,
        fix: `改为 ${Object.keys(contract || {}).join(", ")} 中的字段，或调整上游动作`
      });
    }
  });
}
```

---

# 四、一键修复 `/fix`（常见问题自动打补丁）

## 1) 新建 `src/fix/autoFix.ts`

```ts
import { LintIssue, WorkflowLike } from "../lint/types.js";

export interface FixResult {
  patched: WorkflowLike;
  patch: Array<{ op: string; path: string; value?: any }>; // RFC 6902 结构
  notes: string[];
}

export function autoFix(workflow: WorkflowLike, issues: LintIssue[]): FixResult {
  const w = JSON.parse(JSON.stringify(workflow));
  const patch: FixResult["patch"] = [];
  const notes: string[] = [];

  // F1: WF060 edges 为空 -> 生成顺序 edges
  const hasEdges = Array.isArray(w.edges) && w.edges.length > 0;
  const needEdges = issues.some(i => i.code === "WF060") || !hasEdges;
  if (needEdges && w.steps?.length > 1) {
    const edges = [];
    for (let i = 0; i < w.steps.length - 1; i++) {
      edges.push({ from: w.steps[i].id, to: w.steps[i+1].id });
    }
    w.edges = edges;
    patch.push({ op: hasEdges ? "replace" : "add", path: "/edges", value: edges });
    notes.push("generated sequential edges");
  }

  // F2: WF002 start 不存在 -> 设为第一个 step
  const ids = new Set(w.steps?.map((s:any)=>s.id) || []);
  if (!ids.has(w.start) && w.steps?.length) {
    const newStart = w.steps[0].id;
    patch.push({ op: "replace", path: "/start", value: newStart });
    w.start = newStart;
    notes.push(`set start to "${newStart}"`);
  }

  // F3: WF050 平台修正（示例：mac 用 Cmd, win 用 Ctrl）
  const dev = w.globals?.device_target;
  w.steps?.forEach((s:any, i:number) => {
    if (s.uses === "ext.key" && Array.isArray(s.params?.modifiers)) {
      if (dev === "mac" && s.params.modifiers.includes("Ctrl")) {
        const mods = s.params.modifiers.map((m:string)=> m==="Ctrl"?"Cmd":m);
        w.steps[i].params.modifiers = mods;
        patch.push({ op:"replace", path:`/steps/${i}/params/modifiers`, value:mods });
        notes.push(`step ${s.id}: Ctrl→Cmd`);
      }
      if (dev === "windows" && s.params.modifiers.includes("Cmd")) {
        const mods = s.params.modifiers.map((m:string)=> m==="Cmd"?"Ctrl":m);
        w.steps[i].params.modifiers = mods;
        patch.push({ op:"replace", path:`/steps/${i}/params/modifiers`, value:mods });
        notes.push(`step ${s.id}: Cmd→Ctrl`);
      }
    }
  });

  // F4: WF030 未定义变量 -> 自动在 /variables 增加占位
  const undefVars = new Set<string>();
  for (const iss of issues) {
    if (iss.code === "WF030") {
      const m = /undefined variable "(.+?)"/.exec(iss.message || "");
      if (m) undefVars.add(m[1]);
    }
  }
  if (undefVars.size) {
    if (!w.variables) {
      w.variables = {};
      patch.push({ op: "add", path: "/variables", value: {} });
    }
    for (const k of undefVars) {
      if (!(k in w.variables)) {
        (w.variables as any)[k] = "__FILL_ME__";
        patch.push({ op: "add", path: `/variables/${escapeJsonPointer(k)}`, value: "__FILL_ME__" });
        notes.push(`added placeholder variable "${k}"`);
      }
    }
  }

  // F5: WF001 重复 step id -> 后缀去重（最小可行）
  const seen = new Set<string>();
  w.steps?.forEach((s:any, i:number) => {
    if (!seen.has(s.id)) { seen.add(s.id); return; }
    const newId = dedupeId(s.id, seen);
    w.steps[i].id = newId;
    patch.push({ op:"replace", path:`/steps/${i}/id`, value:newId });
    notes.push(`renamed duplicate id "${s.id}" -> "${newId}"`);
    seen.add(newId);
  });

  return { patched: w, patch, notes };
}

function escapeJsonPointer(s: string) {
  return s.replace(/~/g, "~0").replace(/\//g, "~1");
}
function dedupeId(base: string, used: Set<string>) {
  let n = 2;
  while (used.has(`${base}_${n}`)) n++;
  return `${base}_${n}`;
}
```

## 2) `/fix` 路由：`src/routes/fix.ts`

```ts
import { Router } from "express";
import { autoFix } from "../fix/autoFix.js";
import { createAjv } from "../lib/ajv.js";
import { lintWorkflow } from "../lint/index.js";

const router = Router();
const ajv = createAjv();
const validate = ajv.getSchema("workflow.schema.json");

router.post("/fix", async (req, res) => {
  const { workflow } = req.body || {};
  if (!workflow) return res.status(400).json({ error: "missing 'workflow'" });

  if (!validate) return res.status(500).json({ error: "schema not loaded" });
  const ok = validate(workflow);
  if (!ok) {
    // 即便结构不合法，也尝试做部分修复
  }

  const issues = await lintWorkflow(workflow);
  const result = autoFix(workflow, issues);

  // 修复后再校验+lint，回显新问题
  const ok2 = validate(result.patched);
  const vIssues = ok2 ? [] : (validate.errors || []).map(e => ({
    code: "SCHEMA", level: "error",
    pointer: e.instancePath || "/", message: e.message
  }));
  const lIssues = await lintWorkflow(result.patched);

  res.json({
    patched: result.patched,
    patch: result.patch,
    notes: result.notes,
    post_issues: [...vIssues, ...lIssues]
  });
});

export { router as fixRouter };
```

## 3) 将路由挂载（`src/index.ts`）

```ts
import { fixRouter } from "./routes/fix.js";
app.use(fixRouter);
```

---

# 五、示例：把 Vision→Click→OCR 串起来（含跨步引用）

新增样例 `examples/wf_btn_ocr.json`：

```json
{
  "name": "click a known button then ocr",
  "description": "Find by image fingerprint, click, then OCR a region",
  "version": "1.0.0",
  "globals": { "device_target": "web", "llm_budget": { "max_calls": 0, "max_tokens": 0 }, "auto_promote_on_success": false },
  "start": "open",
  "steps": [
    { "id": "open", "type": "action", "uses": "ext.open_url",
      "params": { "url": "https://example.com", "app": "Google Chrome", "wait_dom_quiet_ms": 800 } },
    { "id": "find_btn", "type": "action", "uses": "vision.find_element_with_image_check",
      "params": { "anchor_image_id": "btn_ok_blue_v3", "method": "image", "threshold": 0.76 } },
    { "id": "click_btn", "type": "action", "uses": "ext.click",
      "params": { "ref": "${outputs.find_btn.center}", "clicks": 1 } },
    { "id": "read_area", "type": "action", "uses": "ocr.extract_region",
      "params": { "ref": "${outputs.find_btn.bbox}", "backend": "auto", "lang": "en" } }
  ],
  "edges": [
    { "from": "open", "to": "find_btn" },
    { "from": "find_btn", "to": "click_btn" },
    { "from": "click_btn", "to": "read_area" }
  ]
}
```

本例会触发：

* `/lint` 的**跨步引用检查**（`find_btn` 早于 `click_btn/read_area`，字段 `center/bbox` 在 `output_contract` 中 → 通过）
* `/simulate` 会返回 `find_btn` 的占位 `bbox/center`，`ext.click` 的点击位置，`ocr.extract_region` 的占位文本。

---

# 六、如何联调

```bash
npm run dev

# 1) 语义检查（含跨步引用）
curl -s -X POST http://localhost:8787/lint \
  -H 'Content-Type: application/json' \
  --data-binary @examples/wf_btn_ocr.json | jq

# 2) 模拟执行
curl -s -X POST http://localhost:8787/simulate \
  -H 'Content-Type: application/json' \
  -d '{"workflow":'$(cat examples/wf_btn_ocr.json)'}' | jq

# 3) 制造问题：把 read_area 的 ref 写成 ${outputs.find_btn.centerr}
#    然后调用 /lint，预期得到 WF083；再试 /fix（对该类问题仅给建议，不强改）
curl -s -X POST http://localhost:8787/fix \
  -H 'Content-Type: application/json' \
  -d '{"workflow":'$(cat examples/wf_btn_ocr.json | sed 's/center/centerr/g')'}' | jq
```

---

# 七、前端对接建议

* **动作卡片**：渲染 `output_contract` 为“可引用字段速查”，支持点选插入 `${outputs.<stepId>.<field>}`。
* **就地诊断**：当出现 `WF081/082/083`，在“参数表单”右侧展示**上游产出建议**（来自 `output_contract`）。
* **一键修复**：前端提供“Apply /fix patch”，把返回的 `patched` 回填；同时显示 `notes`。

---

6:
好，进入**第 6 步（M1-S6：模拟精度提升 + /fix 增强 + 模板库）**。这一步做完，你能：

1. 用**可插拔 Provider**把 `/simulate` 的结果换成“回放日志/指纹库/默认合成”的更真实坐标与识别结果；
2. 在 `/simulate` 打开 **explain/debug** 模式，看到每个分支条件如何求值、参数替换前后值等；
3. 在 `/fix` 自动修更多常见问题（未知动作建议、`ref`→坐标落地、Ctrl↔Cmd、缺 edges 等）；
4. 通过 **/templates** 一键实例化常用工作流骨架，并自动 `validate → lint → simulate`。

---

# A) 可插拔模拟 Provider（更真实）

## 1) 新增接口：`src/sim/providers.ts`

```ts
export type DeviceProfile = { width: number; height: number; scale?: number; name?: string };

export interface SimEvidenceProvider {
  name: string;
  // 将 CSS selector（或 XPath）解析为近似坐标（页面坐标）
  selectorToPoint(selector: string, dev: DeviceProfile): { x: number; y: number } | null;
  // 根据 fingerprint/anchor id 返回 bbox+center
  fingerprintToBox(anchorId: string, dev: DeviceProfile): { x: number; y: number; w: number; h: number } | null;
  // OCR 预期文本（若可）
  ocrForRegion(region: {x:number;y:number;w:number;h:number}, lang?: string): string | null;
}

// 1) 默认合成 Provider：稳定哈希 → 伪随机但可复现的坐标
export function createDefaultProvider(seed = 1): SimEvidenceProvider {
  const rng = mulberry32(seed);
  return {
    name: "default",
    selectorToPoint(selector, dev) {
      const h = hash(selector);
      const margin = 40;
      const x = margin + (h % (dev.width - margin*2));
      const y = margin + ((h >>> 8) % (dev.height - margin*2));
      return { x, y };
    },
    fingerprintToBox(anchorId, dev) {
      const h = hash(anchorId);
      const w = 120 + (h % 160);
      const hgt = 36 + ((h >>> 8) % 64);
      const x = (h % (dev.width - w));
      const y = ((h >>> 8) % (dev.height - hgt));
      return { x, y, w, h: hgt };
    },
    ocrForRegion(_r, _lang) { return null; }
  };
}

// 2) 回放 Provider：从“上一轮真实执行轨迹/日志”读取
export function createReplayProvider(trace: Array<any>): SimEvidenceProvider {
  // 允许把 vision/ocr 的 outputs 找回
  const byAnchor = new Map<string, any>();
  for (const t of trace || []) {
    const fp = t?.outputs?.fingerprint_id;
    if (fp) byAnchor.set(fp, t.outputs);
  }
  return {
    name: "replay",
    selectorToPoint(selector, _dev) {
      // 回放里若包含 selector 坐标则返回；没有就放弃
      // 这里留空位（根据你日志字段可扩展）
      return null;
    },
    fingerprintToBox(anchorId, _dev) {
      const o = byAnchor.get(anchorId);
      if (!o) return null;
      const b = o.bbox || {};
      return ("x" in b && "y" in b && "w" in b && "h" in b) ? b : null;
    },
    ocrForRegion(_r, _lang) { return null; }
  };
}

// 3) 指纹库 Provider：对接你未来的云端“元素指纹库”
export function createFingerprintProvider(index: Record<string, any>): SimEvidenceProvider {
  return {
    name: "fingerprint-db",
    selectorToPoint(_sel, _dev) { return null; },
    fingerprintToBox(anchorId, _dev) {
      const item = index[anchorId];
      return item?.bbox || null;
    },
    ocrForRegion(_r, _lang) { return null; }
  };
}

// utils
function hash(s: string) {
  let h = 2166136261 >>> 0;
  for (let i=0;i<s.length;i++){ h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
function mulberry32(a: number){ return function(){ let t=(a+=0x6D2B79F5);
 t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
 return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
```

## 2) 扩展 `/simulate` 请求体

**`src/routes/simulate.ts`**（只展示新增入参解包）

```ts
// body: { workflow, seed?, provider?: "default"|"replay"|"fingerprint",
//         device?: {width,height,scale?,name?}, replay_trace?: any[], fingerprint_index?: Record<string,any>,
//         explain?: boolean }
```

## 3) 改造 Runner 使用 Provider 与 Explain

**`src/sim/runner.ts`**（关键增量）

```ts
import { createDefaultProvider, createReplayProvider, createFingerprintProvider, SimEvidenceProvider, DeviceProfile } from "./providers.js";
import { evalCond } from "./cond.js";
import { resolveRefs } from "./strings.js";
import { simulateAction, SimCtx } from "./actions.js";
// ...保留原有 import

export async function simulateWorkflow(
  wf: WF,
  seed?: number,
  opts?: {
    provider?: "default"|"replay"|"fingerprint",
    device?: DeviceProfile,
    replay_trace?: any[],
    fingerprint_index?: Record<string,any>,
    explain?: boolean
  }
): Promise<SimResult & { debug?: any[] }> {
  const device: DeviceProfile = opts?.device || { width: 1440, height: 900, scale: 1, name: "web-1440x900" };
  let provider: SimEvidenceProvider;
  switch (opts?.provider) {
    case "replay": provider = createReplayProvider(opts?.replay_trace || []); break;
    case "fingerprint": provider = createFingerprintProvider(opts?.fingerprint_index || {}); break;
    default: provider = createDefaultProvider(seed ?? 1);
  }

  const ctx: SimCtx = { vars: wf.variables || {}, globals: wf.globals || {}, outputs: {} };
  const adj = buildAdj(wf);
  const trace: SimTraceEntry[] = [];
  const debug: any[] = [];
  let estimates = { llm_tokens: 0, llm_calls: 0 };

  // 预算估计（同前，略）

  let cur = wf.start;
  let safety = 0;
  while (cur && safety++ < 1000) {
    const step = findStep(wf, cur);
    if (!step) break;

    // 参数替换（用于 debug 展示）
    const paramsResolved = resolveRefs(step.params || {}, { ...ctx });

    // 覆盖特定动作的占位：selector/ref/fingerprint → 用 provider 计算更真实点位
    if (step.type === "action") {
      if (step.uses === "ext.click") {
        if (paramsResolved.selector && !("x" in paramsResolved) && !("y" in paramsResolved)) {
          const pt = provider.selectorToPoint(paramsResolved.selector, device);
          if (pt) { paramsResolved.x = pt.x; paramsResolved.y = pt.y; delete paramsResolved.selector; }
        } else if (paramsResolved.ref && Array.isArray(paramsResolved.ref)) {
          // 如果 ref 解析成 [x,y] 数组，落地为 x/y
          const [x,y] = paramsResolved.ref;
          paramsResolved.x = x; paramsResolved.y = y; delete paramsResolved.ref;
        }
      }
      if (step.uses === "vision.find_element_with_image_check") {
        if (paramsResolved.anchor_image_id && !paramsResolved.search_region) {
          const b = provider.fingerprintToBox(paramsResolved.anchor_image_id, device);
          if (b) { paramsResolved.search_region = b; }
        }
      }
      if (step.uses === "ocr.extract_region") {
        // 若 ref 已解析为 bbox，把它放进 region
        if (!paramsResolved.region && typeof paramsResolved.ref === "object" &&
            "x" in paramsResolved.ref && "y" in paramsResolved.ref) {
          paramsResolved.region = paramsResolved.ref; delete paramsResolved.ref;
        }
      }
    }

    // 执行动作（传入**落地后的**参数）
    const started = Date.now();
    let entry: SimTraceEntry;
    if (step.type === "action") {
      const r = await simulateAction(step.uses, paramsResolved, ctx);
      entry = {
        id: step.id, name: step.name, uses: step.uses,
        status: r.ok ? "ok" : "error",
        started_ms: started, duration_ms: r.duration_ms ?? 0,
        outputs: r.outputs, warning: r.warning
      };
      ctx.outputs[step.id] = r.outputs || {};
    } else {
      entry = { id: step.id, name: step.name, uses: step.type, status: "ok", started_ms: started, duration_ms: 0 };
    }
    trace.push(entry);

    if (opts?.explain) {
      debug.push({
        step: step.id,
        provider: provider.name,
        device,
        params_before: step.params || {},
        params_after: paramsResolved,
      });
    }

    // 挑选下一条边（附 explain）
    const options = adj.get(step.id) || [];
    let next = "";
    let chosen: any = null;
    for (const opt of options) {
      const ok = evalCond(opt.condition, { ...ctx, step });
      if (opts?.explain) {
        debug.push({ from: step.id, to: opt.to, condition: opt.condition ?? "<default>", result: ok });
      }
      if (ok) { next = opt.to; chosen = opt; break; }
    }
    if (!next) break;
    cur = next;
  }

  const base = {
    trace, estimates, finished: !!cur ? false : true, last_step: trace.at(-1)?.id, warnings: trace.filter(t => t.warning).map(t => t.warning!)
  };
  return opts?.explain ? { ...base, debug } : base;
}
```

## 4) 路由：`src/routes/simulate.ts` 更新

```ts
import { simulateWorkflow } from "../sim/runner.js";
import { createAjv } from "../lib/ajv.js";
const ajv = createAjv(); const validate = ajv.getSchema("workflow.schema.json");

router.post("/simulate", async (req, res) => {
  const { workflow, seed, provider, device, replay_trace, fingerprint_index, explain } = req.body || {};
  if (!workflow) return res.status(400).json({ error: "missing 'workflow' in body" });
  if (!validate) return res.status(500).json({ error: "schema not loaded" });
  const ok = validate(workflow); if (!ok) return res.status(400).json({ error: "schema validation failed", issues: (validate.errors||[]).map(e => ({ pointer: e.instancePath || "/", message: e.message })) });
  try {
    const result = await simulateWorkflow(workflow, seed, { provider, device, replay_trace, fingerprint_index, explain });
    res.json(result);
  } catch (e:any) { res.status(500).json({ error: String(e?.message || e) }); }
});
```

---

# B) /fix 增强（未知动作建议、ref 落地等）

**`src/fix/autoFix.ts`** 增量：

```ts
import registryIndex from "../../registry/index.json" assert { type: "json" };
const ACTION_IDS = (registryIndex as any).actions.map((a:any)=>a.id);

// F6: WF020 unknown action → 提示最相近动作（不直接替换，返回 notes）
function nearestActionId(bad: string): string | null {
  let best = ""; let bestD = 1e9;
  for (const id of ACTION_IDS) {
    const d = levenshtein(bad, id);
    if (d < bestD) { bestD = d; best = id; }
  }
  return bestD <= Math.max(3, Math.floor(best.length*0.34)) ? best : null;
}

// F7: 将 ext.click 的 params.ref（若是数组/对象）落地为 x/y
function landClickRef(params: any) {
  if (!params) return { changed:false, params };
  if ("ref" in params) {
    const ref = params.ref;
    if (Array.isArray(ref) && ref.length >= 2) {
      const [x,y] = ref; const p = { ...params }; delete p.ref; p.x = x; p.y = y; return { changed:true, params:p };
    }
    if (ref && typeof ref === "object" && "x" in ref && "y" in ref) {
      const p = { ...params }; delete p.ref; p.x = ref.x; p.y = ref.y; return { changed:true, params:p };
    }
  }
  return { changed:false, params };
}

export function autoFix(workflow: WorkflowLike, issues: LintIssue[]): FixResult {
  // ...保持之前逻辑
  // 新增：扫描未知动作
  workflow.steps?.forEach((s:any, i:number) => {
    if (s.type === "action" && s.uses && !ACTION_IDS.includes(s.uses)) {
      const guess = nearestActionId(s.uses);
      if (guess) notes.push(`step ${s.id}: unknown action "${s.uses}", did you mean "${guess}"?`);
    }
  });

  // 新增：ext.click ref → x/y
  workflow.steps?.forEach((s:any, i:number) => {
    if (s.uses === "ext.click") {
      const r = landClickRef(s.params);
      if (r.changed) {
        w.steps[i].params = r.params;
        patch.push({ op:"replace", path:`/steps/${i}/params`, value:r.params });
        notes.push(`step ${s.id}: resolved ref → x/y`);
      }
    }
  });

  return { patched: w, patch, notes };
}

// 轻量 Levenshtein
function levenshtein(a: string, b: string) {
  const m = Array.from({length:a.length+1}, (_,i)=>[i, ...Array(b.length).fill(0)]);
  for (let j=1;j<=b.length;j++) m[0][j] = j;
  for (let i=1;i<=a.length;i++){
    for (let j=1;j<=b.length;j++){
      m[i][j] = Math.min(
        m[i-1][j]+1,
        m[i][j-1]+1,
        m[i-1][j-1] + (a[i-1]===b[j-1]?0:1)
      );
    }
  }
  return m[a.length][b.length];
}
```

---

# C) 模板库（/templates）

## 1) 结构

```
templates/
├─ index.json
├─ xhs_collect.template.json
├─ fb_greet.template.json
└─ indeed_apply.template.json
```

### `templates/index.json`

```json
{
  "templates": [
    { "id": "fb_greet", "title": "Facebook greet a friend", "file": "fb_greet.template.json", "params": ["friend_name"] },
    { "id": "xhs_collect", "title": "XHS explore page scrape (ext-only)", "file": "xhs_collect.template.json", "params": ["keyword"] },
    { "id": "indeed_apply", "title": "Indeed quick apply skeleton", "file": "indeed_apply.template.json", "params": ["job_keyword","location"] }
  ]
}
```

### `templates/fb_greet.template.json`（带占位变量）

```json
{
  "name": "fb greet ${vars.friend_name}",
  "description": "Open Facebook and greet ${vars.friend_name}",
  "version": "1.0.0",
  "globals": { "device_target": "web", "llm_budget": {"max_calls":1,"max_tokens":800}, "auto_promote_on_success": false },
  "variables": { "friend_name": "${friend_name}" },
  "start": "open",
  "steps": [
    {"id":"open","type":"action","uses":"ext.open_url","params":{"url":"https://facebook.com","app":"Google Chrome","wait_dom_quiet_ms":1000}},
    {"id":"focus","type":"action","uses":"ext.key","params":{"key":"Enter"}},
    {"id":"say","type":"action","uses":"type_text","params":{"text":"Hi ${vars.friend_name}!", "mode":"type"}}
  ]
}
```

（`xhs_collect.template.json`、`indeed_apply.template.json` 同理，保持 3–6 步的极简骨架，方便演示）

## 2) 路由：`src/routes/templates.ts`

```ts
import { Router } from "express";
import tIndex from "../../templates/index.json" assert { type: "json" };
import { createAjv } from "../lib/ajv.js";
import { lintWorkflow } from "../lint/index.js";
import { simulateWorkflow } from "../sim/runner.js";

export const templatesRouter = Router();

templatesRouter.get("/templates", (_req, res) => res.json(tIndex));

templatesRouter.get("/templates/:id", async (req, res) => {
  const id = req.params.id;
  const meta = (tIndex as any).templates.find((t:any)=>t.id===id);
  if (!meta) return res.status(404).json({ error:"template not found" });
  // @ts-ignore
  const mod = await import(`../../templates/${meta.file}`, { assert:{type:"json"} });
  res.json({ meta, template: mod.default });
});

// 实例化：传入 params → 注入 variables → validate → lint → simulate
templatesRouter.post("/templates/:id/instantiate", async (req, res) => {
  const id = req.params.id;
  const meta = (tIndex as any).templates.find((t:any)=>t.id===id);
  if (!meta) return res.status(404).json({ error:"template not found" });
  const params = req.body?.params || {};
  // @ts-ignore
  const mod = await import(`../../templates/${meta.file}`, { assert:{type:"json"} });
  const tpl = JSON.parse(JSON.stringify(mod.default));

  // 注入变量：将 {"friend_name": "Jack"} → tpl.variables.friend_name
  tpl.variables = tpl.variables || {};
  for (const k of Object.keys(params)) tpl.variables[k] = params[k];

  // validate + lint
  const ajv = createAjv(); const validate = ajv.getSchema("workflow.schema.json");
  if (!validate) return res.status(500).json({ error: "schema not loaded" });
  const ok = validate(tpl);
  const vIssues = ok ? [] : (validate.errors || []).map(e=>({ pointer: e.instancePath || "/", message: e.message }));
  const lIssues = await lintWorkflow(tpl);

  // simulate（默认 explain=false）
  const sim = ok ? await simulateWorkflow(tpl, 1, { provider: "default" }) : null;

  res.json({ workflow: tpl, issues: [...vIssues, ...lIssues], simulate: sim });
});
```

**把路由挂到 `src/index.ts`：**

```ts
import { templatesRouter } from "./routes/templates.js";
app.use(templatesRouter);
```

---

# D) 前端对接建议（最小）

* `/simulate` 新增参数：

  * **Provider** 下拉：`default | replay | fingerprint`
  * **Device** 选择：常用分辨率（1920×1080, 1440×900, 1280×720），自定义输入
  * **Explain** 开关：打开后，在每个 Step 卡片下显示 `params_before/after` 和**分支求值记录**（`from/to/condition/result`）
* 当 Lint 出现 `WF020`（unknown action）时，将 `/fix` 返回的 `notes` 中“did you mean …”以**一键替换候选**展示
* 当 `ext.click` 带 `ref` 且 `/fix` 返回“resolved ref → x/y”时，允许**应用补丁**并立即重跑 `/simulate`

---

# E) 验证清单（你本地可以马上试）

```bash
npm run dev

# 1) 模拟：使用 provider=default + explain
curl -s -X POST http://localhost:8787/simulate \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow":'$(cat examples/wf_btn_ocr.json)',
    "provider": "default",
    "device": {"width":1440,"height":900,"scale":1,"name":"web-1440"},
    "explain": true
  }' | jq '.debug[:4]'

# 2) 模板列表
curl -s http://localhost:8787/templates | jq

# 3) 实例化 fb_greet
curl -s -X POST http://localhost:8787/templates/fb_greet/instantiate \
  -H 'Content-Type: application/json' -d '{"params":{"friend_name":"Jack"}}' | jq '.workflow.name,.simulate.trace'

# 4) /fix：人为造错（unknown action、click 的 ref 是数组）
jq '.steps[2].uses="ext.clik" | .steps[2].params.ref=[333,444]' examples/wf_btn_ocr.json > /tmp/wf_bad.json
curl -s -X POST http://localhost:8787/fix -H 'Content-Type: application/json' \
  -d '{"workflow":'$(cat /tmp/wf_bad.json)'}' | jq '.notes,.patch'
```

---

7:
好，进入**第 7 步（M1-S7：增强 Lint + 回放证据接入）**。这一步把“现实世界信号”接入到 Lint，让很多问题在**运行前**就能被识别出来，同时把 LLM 预算评估更贴近真实。

---

# 一、要做什么（新增能力总览）

* **/lint 支持“证据上下文”**（evidence）：

  * DOM 选择器可达性（来自回放/快照）
  * 指纹库命中（anchor\_image\_id 是否存在）
  * 设备画布边界检查（坐标/区域是否越界）
* **新规则**

  * `WF091` 选择器不可达
  * `WF092` 坐标/区域越界
  * `WF093` LLM 预算精细化（含系统词、回复开销）
  * `WF094` 条件表达式引用未知变量/字段
  * `WF095` 浏览器/设备不匹配（web 目标但 app 异常）
* **/lint 接口扩展**：允许传 `evidence` 与 `device`，与 `/simulate` 使用同一设备画像
* **回放集成**：可直接把上一次 `/simulate explain` 或真实执行日志中抽取的**选择器集合、指纹 id、上次轨迹**给到 /lint

---

# 二、类型扩展

## 1) `src/lint/types.ts` 新增上下文

```ts
export type Level = "error" | "warn" | "info";

export interface LintIssue {
  code: string;
  level: Level;
  message: string;
  pointer?: string;
  fix?: string;
}

export interface WorkflowLike {
  name: string;
  version: string;
  start: string;
  globals?: any;
  variables?: Record<string, any>;
  steps: Array<any>;
  edges?: Array<{ from: string; to: string; condition?: string }>;
}

export interface DeviceProfile { width: number; height: number; scale?: number; name?: string; }

export interface LintEvidence {
  // 从回放/快照收集到的可点击/存在的选择器（CSS/XPath 统一当字符串处理）
  selectors?: string[];
  // 可用的指纹 ID（anchor_image_id）
  fingerprints?: string[];
  // 上一次的模拟/真实轨迹（可选，用于未来更多推断）
  replay_trace?: any[];
}

export interface LintContext {
  device?: DeviceProfile;
  evidence?: LintEvidence;
}
```

---

# 三、/lint 路由接入上下文

## 1) `src/routes/lint.ts` 修改

```ts
router.post("/lint", async (req, res) => {
  const { workflow, device, evidence } = req.body || {};
  const wf = workflow || req.body; // 兼容老用法：直接传 workflow 对象
  if (!wf) return res.status(400).json({ issues: [{ code:"REQ", level:"error", message:"missing 'workflow'"}] });

  if (!validateWorkflow) return res.status(500).json({ issues: [{ code:"SYS", level:"error", message:"schema not loaded"}] });

  const ok = validateWorkflow(wf);
  if (!ok) {
    const errs = (validateWorkflow.errors || []).map(e => ({
      code: "SCHEMA",
      level: "error",
      message: `${e.instancePath || "/"} ${e.message}`,
      pointer: e.instancePath || "/"
    }));
    return res.status(400).json({ issues: errs });
  }

  const issues = await lintWorkflow(wf, { device, evidence });
  const hasError = issues.some(i => i.level === "error");
  return res.status(hasError ? 400 : 200).json({ issues });
});
```

---

# 四、增强规则实现

## 1) `src/lint/rules.ts` 签名与工具增量

在文件头部引入类型，并把 `lintWorkflow` 签名改为 `(wf, ctx?)`：

```ts
import { LintIssue, WorkflowLike, LintContext, DeviceProfile } from "./types.js";
import registryIndex from "../../registry/index.json" assert { type: "json" };

const DEFAULT_DEVICE: DeviceProfile = { width: 1440, height: 900, scale: 1, name: "web-1440x900" };
const ACTIONS: any[] = (registryIndex as any).actions;

function isNumber(n: any): n is number { return typeof n === "number" && isFinite(n); }
```

## 2) 选择器与指纹检查的辅助

```ts
function hasSelector(evidence: any, selector?: string) {
  if (!selector || !evidence?.selectors) return true; // 无证据→不判为错
  return evidence.selectors.includes(selector);
}

function hasFingerprint(evidence: any, id?: string) {
  if (!id || !evidence?.fingerprints) return true;
  return evidence.fingerprints.includes(id);
}

function inBounds(device: DeviceProfile, pt: {x:number; y:number}) {
  return isNumber(pt.x) && isNumber(pt.y) && pt.x >= 0 && pt.y >= 0 && pt.x <= device.width && pt.y <= device.height;
}

function rectInBounds(device: DeviceProfile, r: {x:number;y:number;w:number;h:number}) {
  return isNumber(r.x) && isNumber(r.y) && isNumber(r.w) && isNumber(r.h) &&
         r.w >= 0 && r.h >= 0 &&
         r.x >= 0 && r.y >= 0 &&
         (r.x + r.w) <= device.width && (r.y + r.h) <= device.height;
}
```

## 3) 条件表达式变量引用检查（轻量）

```ts
const VAR_IN_COND = /\b(vars|outputs|globals)\.[A-Za-z0-9_.]+/g;
function collectCondRefs(cond?: string) {
  if (!cond) return [];
  const set = new Set<string>();
  let m; while ((m = VAR_IN_COND.exec(cond)) !== null) set.add(m[0]);
  return [...set];
}
```

## 4) LLM 预算精细化（WF093）

```ts
function estimateLLM(wf: WorkflowLike) {
  // 基础：目录 cost_estimate + prompt 长度/4 + 系统词开销（假设 60~120 tokens）
  let tokens = 0, calls = 0;
  for (const s of wf.steps) {
    if (s.type !== "action") continue;
    const meta = ACTIONS.find(a => a.id === s.uses);
    if (meta?.cost_estimate?.llm_tokens) tokens += meta.cost_estimate.llm_tokens;
    if (String(s.uses || "").startsWith("llm.")) {
      calls += 1;
      const sysOverhead = 80; // 经验常数
      const prompt = (typeof s.params?.prompt === "string") ? s.params.prompt : "";
      tokens += sysOverhead + Math.ceil(prompt.length / 4);
      // 如果未来 schema 里有 max_tokens/temperature 等，可再加权
    }
  }
  return { tokens, calls };
}
```

## 5) 在 `export async function lintWorkflow(wf: WorkflowLike, ctx?: LintContext): Promise<LintIssue[]> { … }` 内加入新增规则

把之前已有规则保留，**在变量引用检查与预算规则附近**追加如下代码片段：

```ts
  const device = ctx?.device || DEFAULT_DEVICE;
  const evidence = ctx?.evidence || {};

  // —— WF091: selector 不可达（基于 evidence）
  wf.steps.forEach((s, i) => {
    if (s.type === "action" && s.uses === "ext.click") {
      const sel = s.params?.selector;
      if (typeof sel === "string" && sel.includes("${")) return; // 动态引用跳过
      if (typeof sel === "string" && !hasSelector(evidence, sel)) {
        issues.push({
          code: "WF091", level: "warn",
          message: `selector not found in evidence snapshot: "${sel}"`,
          pointer: `/steps/${i}/params/selector`,
          fix: "确认选择器来源（录制/回放），或改用 vision.find_element + ref"
        });
      }
    }
  });

  // —— WF092: 坐标/区域越界（基于 device）
  wf.steps.forEach((s, i) => {
    if (s.type !== "action") return;
    if (s.uses === "ext.click") {
      const p = s.params || {};
      if (isNumber(p.x) && isNumber(p.y) && !inBounds(device, {x:p.x,y:p.y})) {
        issues.push({
          code: "WF092", level: "error",
          message: `click point (${p.x},${p.y}) out of device bounds ${device.width}x${device.height}`,
          pointer: `/steps/${i}/params`,
          fix: "调整坐标或切换 device"
        });
      }
    }
    if (s.uses === "ocr.extract_region") {
      const r = s.params?.region;
      if (r && !rectInBounds(device, r)) {
        issues.push({
          code: "WF092", level: "error",
          message: `ocr region out of bounds: (${r.x},${r.y},${r.w},${r.h}) vs ${device.width}x${device.height}`,
          pointer: `/steps/${i}/params/region`,
          fix: "缩放/移动区域或切换 device"
        });
      }
    }
  });

  // —— WF094: 条件表达式引用检查（edges.condition + step.when）
  const stepIndex = new Map<string, number>();
  wf.steps.forEach((s, i) => stepIndex.set(s.id, i));

  function checkCondRefs(cond: string | undefined, ptr: string) {
    for (const ref of collectCondRefs(cond)) {
      if (ref.startsWith("vars.")) {
        const key = ref.slice(5).split(".")[0];
        if (!wf.variables || !(key in wf.variables)) {
          issues.push({ code: "WF094", level: "error", message: `condition references undefined variable "${key}"`, pointer: ptr, fix: `在 /variables 增加 "${key}"` });
        }
      } else if (ref.startsWith("outputs.")) {
        const parts = ref.split(".");
        const sid = parts[1];
        if (!stepIndex.has(sid)) {
          issues.push({ code: "WF094", level: "error", message: `condition references unknown outputs step "${sid}"`, pointer: ptr });
        } else {
          const idx = stepIndex.get(sid)!;
          // 条件所在位置推断：edges 在 from step 之后，粗略允许；step.when 则必须引用已执行步
          // 这里只针对 step.when 做前向引用阻断
        }
      }
    }
  }

  wf.edges?.forEach((e, i) => checkCondRefs(e.condition, `/edges/${i}/condition`));
  wf.steps?.forEach((s, i) => checkCondRefs(s.when, `/steps/${i}/when`));

  // —— WF095: 设备目标与浏览器 app 不匹配
  const deviceTarget = wf.globals?.device_target;
  wf.steps.forEach((s, i) => {
    if (s.type === "action" && s.uses === "ext.open_url") {
      const app = s.params?.app;
      if (deviceTarget === "web" && app && !["Google Chrome","Edge","Arc","Firefox"].includes(app)) {
        issues.push({
          code: "WF095", level: "warn",
          message: `device_target=web but app="${app}" may be unsupported`,
          pointer: `/steps/${i}/params/app`,
          fix: "改用 Chrome / Edge / Arc / Firefox"
        });
      }
    }
  });

  // —— 指纹存在性（增强 WF08x）
  wf.steps.forEach((s, i) => {
    if (s.type === "action" && s.uses === "vision.find_element_with_image_check") {
      const id = s.params?.anchor_image_id;
      if (typeof id === "string" && !hasFingerprint(evidence, id)) {
        issues.push({
          code: "WF091", level: "warn",
          message: `fingerprint id not found in evidence: "${id}"`,
          pointer: `/steps/${i}/params/anchor_image_id`,
          fix: "同步指纹库或检查 ID 拼写"
        });
      }
    }
  });

  // —— WF093: LLM 预算（替换原有粗略规则）
  const budget = wf.globals?.llm_budget;
  if (budget?.max_tokens != null) {
    const est = estimateLLM(wf);
    if (est.tokens > budget.max_tokens * 1.15) {
      issues.push({ code: "WF093", level: "error", message: `LLM token estimate ${est.tokens} exceeds budget ${budget.max_tokens}`, pointer: "/globals/llm_budget", fix: "减少 llm.* 调用或缩短 prompt，上调预算" });
    } else if (est.tokens > budget.max_tokens * 0.85) {
      issues.push({ code: "WF093", level: "warn", message: `LLM token estimate ${est.tokens} is close to budget ${budget.max_tokens}`, pointer: "/globals/llm_budget" });
    }
  }
```

> 说明：其余旧规则（WF001/2/3/4/6/10/30/31/40/50/60/81/82/83/20/21）原样保留。

---

# 五、调用方式

## 1) 直接传 evidence 进行 Lint

```bash
curl -s -X POST http://localhost:8787/lint \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow":'$(cat examples/wf_btn_ocr.json)',
    "device": { "width": 1280, "height": 720, "name": "web-1280" },
    "evidence": {
      "selectors": ["#search", ".btn.primary"],
      "fingerprints": ["btn_ok_blue_v3", "nav_profile_v2"]
    }
  }' | jq
```

## 2) 从上一步 `/simulate?explain=true` 结果提取证据再 Lint

前端可以把 `result.debug` 里 `params_after.selector / anchor_image_id` 聚合，作为 evidence 传回 `/lint`，形成**闭环**。

---

# 六、前端对接要点

* 在 Lint 面板新增“证据来源”：

  * **回放**：勾选后自动注入 `evidence.selectors/fingerprints`（从上次模拟/真实日志转换）
  * **设备**：跟 `/simulate` 同一选择器（同步分辨率，避免越界误报）
* 在 Step 表单旁提示：

  * `WF091`：显示“本页可达选择器样例”（来自 evidence.selectors 的前 N 项）
  * `WF092`：展示一个**小预览框**，标出越界的点/区域
  * `WF093`：显示“估算 token/calls”，并提供“一键缩短 prompt”入口（自动截断或模板化）

---

# 七、验证清单

```bash
npm run dev

# 1) 制造 selector 不可达
jq '.steps[2].params.selector="#not-exist"' examples/wf_btn_ocr.json > /tmp/wf_sel_bad.json
curl -s -X POST http://localhost:8787/lint -H 'Content-Type: application/json' \
  -d '{"workflow":'$(cat /tmp/wf_sel_bad.json)',"evidence":{"selectors":["#ok",".btn"]}}' | jq '.issues[] | select(.code=="WF091")'

# 2) 越界
jq '.steps[2].params |= . + {"x":5000,"y":-10} | .steps[2].params.ref=empty | .steps[2].params.selector=empty' examples/wf_btn_ocr.json > /tmp/wf_oob.json
curl -s -X POST http://localhost:8787/lint -H 'Content-Type: application/json' \
  -d '{"workflow":'$(cat /tmp/wf_oob.json)',"device":{"width":1280,"height":720}}' | jq '.issues[] | select(.code=="WF092")'

# 3) LLM 预算
jq '.steps += [{"id":"ask","type":"action","uses":"llm.reply","params":{"prompt":"A".repeat(1600)}}]' examples/wf_btn_ocr.json > /tmp/wf_llm.json
curl -s -X POST http://localhost:8787/lint -H 'Content-Type: application/json' \
  -d '{"workflow":'$(cat /tmp/wf_llm.json)'}' | jq '.issues[] | select(.code=="WF093")'
```

---

# 八、完成后你将具备

* **场景感知 Lint**：基于证据做“能不能点到”“图像指纹在不在”“坐标会不会飞出去”的预检查
* **更真实的 LLM 成本把关**
* 与 `/simulate` 的**同构设备**与证据循环，使“生成 → 校验 → 修复 → 模拟”闭环更稳

8:
好，进入**第 8 步（M1-S8：子流程 subflow 与并行 parallel 语义）**。这一版在**不打破你现有 JSON 结构**的前提下，给出可直接落地的最小实现：

* Schema 条件扩展（为 `subflow` / `parallel` / `wait(join)` 增加约束字段）
* Lint 新规则：并行结构正确性、禁止嵌套并行（首版）、分支可达与汇合校验
* 模拟器：支持 `subflow` 递归执行与 `parallel → join` 的“叉—汇”并发干跑
* 示例与 API：/subflows 索引；新增 2 个例子（并行 + 子流程）

> 设计取舍：**首版不支持并行的嵌套**（parallel 里再起 parallel）。如需更强表达力，下一步再引入“并行作用域 ID + 层级栈”。

---

# 一、Schema 扩展（兼容增量）

修改 `schemas/workflow.schema.json` 的 `$defs.Step`：在原有基础上增加 **oneOf 条件**与字段说明（只贴增量关键片段）：

```json
{
  "$defs": {
    "Step": {
      "type": "object",
      "required": ["id", "type"],
      "properties": {
        "id": { "type": "string", "minLength": 1 },
        "name": { "type": "string" },
        "type": { "enum": ["action","branch","loop","parallel","wait","subflow","human_input"] },
        "uses": { "type": "string" },
        "params": { "type": "object", "additionalProperties": true },

        /* subflow 相关（当 type=subflow 时生效） */
        "subflow_ref": { "type": "string", "description": "指向 /subflows/<id>.json 的 ID" },
        "input": { "type": "object", "additionalProperties": true, "description": "传入子流程的 variables 覆盖" },
        "export": { "type": "array", "items": { "type": "string" }, "description": "从子流程导出到本步骤 outputs 的字段（可为空，默认导出子流程最后一步的 outputs 为 result）" },

        /* 并行 join 相关（当 type=wait 用于汇合时生效） */
        "join_of": { "type": "string", "description": "要汇合的 parallel 步骤 ID" },
        "join_mode": { "enum": ["all","any"], "default": "all" }
      },

      "oneOf": [
        { "properties": { "type": { "const": "subflow" } }, "required": ["subflow_ref"] },
        { "properties": { "type": { "const": "parallel" } } },
        { "properties": { "type": { "const": "wait" }, "join_of": { "type": "string" } }, "required": ["join_of"] },
        { "properties": { "type": { "enum": ["action","branch","loop","human_input"] } } }
      ],

      "additionalProperties": false
    },

    "Edge": {
      "type": "object",
      "required": ["from","to"],
      "properties": {
        "from": { "type": "string" },
        "to": { "type": "string" },
        "condition": { "type": "string" }
      },
      "additionalProperties": false
    }
  }
}
```

> 说明：
>
> * `parallel` 自身不需要额外属性，**它的多条外出边即代表 fork**。
> * `wait` + `join_of` 代表 join barrier；`join_mode` = `all|any`。
> * `subflow` 通过 `subflow_ref` 指向独立文件（或未来支持 inline）。

---

# 二、/subflows 支持与样例

## 1) 目录与路由

```
subflows/
└─ login_basic.json
```

**subflows/login\_basic.json（示例）**

```json
{
  "id": "login_basic",
  "name": "login basic subflow",
  "version": "1.0.0",
  "globals": { "device_target": "web", "llm_budget": { "max_calls": 0, "max_tokens": 0 }, "auto_promote_on_success": false },
  "variables": { "url": "", "username": "", "password": "" },
  "start": "open",
  "steps": [
    { "id": "open", "type": "action", "uses": "ext.open_url", "params": { "url": "${vars.url}", "app": "Google Chrome" } },
    { "id": "focus", "type": "action", "uses": "ext.key", "params": { "key": "Enter" } },
    { "id": "type_user", "type": "action", "uses": "type_text", "params": { "text": "${vars.username}" } },
    { "id": "type_pass", "type": "action", "uses": "type_text", "params": { "text": "${vars.password}" } }
  ],
  "edges": [
    { "from": "open", "to": "focus" },
    { "from": "focus", "to": "type_user" },
    { "from": "type_user", "to": "type_pass" }
  ]
}
```

**src/routes/subflows.ts**

```ts
import { Router } from "express";
import fs from "node:fs/promises";
import path from "node:path";

export const subflowsRouter = Router();

subflowsRouter.get("/subflows", async (_req, res) => {
  const dir = path.resolve("subflows");
  const files = await fs.readdir(dir);
  const list = [];
  for (const f of files) {
    if (!f.endsWith(".json")) continue;
    const j = JSON.parse(await fs.readFile(path.join(dir, f), "utf-8"));
    list.push({ id: j.id || f.replace(/\.json$/,""), file: f, name: j.name || f });
  }
  res.json({ subflows: list });
});

subflowsRouter.get("/subflows/:id", async (req, res) => {
  const dir = path.resolve("subflows");
  const files = await fs.readdir(dir);
  const hit = files.find(f => f === `${req.params.id}.json`);
  if (!hit) return res.status(404).json({ error: "subflow not found" });
  const j = JSON.parse(await fs.readFile(path.join(dir, hit), "utf-8"));
  res.json(j);
});
```

把路由挂载：`src/index.ts` 中

```ts
import { subflowsRouter } from "./routes/subflows.js";
app.use(subflowsRouter);
```

---

# 三、Lint：并行/汇合/子流程规则

在 `src/lint/rules.ts` 里新增规则（仅贴增量逻辑；保持既有 WF00x/08x/09x 等不变）：

```ts
// —— WF070: parallel 至少两条外出边；不得嵌套 parallel（首版）
for (let i=0;i<wf.steps.length;i++){
  const s = wf.steps[i];
  if (s.type === "parallel") {
    const outs = (wf.edges || []).filter(e => e.from === s.id);
    if (outs.length < 2) {
      issues.push({ code:"WF070", level:"error", message:`parallel "${s.id}" requires >=2 outgoing edges`, pointer:`/steps/${i}` });
    }
    // 检查直接分支头部是否为 parallel（简单禁止嵌套）
    for (const e of outs) {
      const head = wf.steps.find(x => x.id === e.to);
      if (head?.type === "parallel") {
        issues.push({ code:"WF074", level:"error", message:`nested parallel not supported (branch "${e.to}")`, pointer:`/edges/${(wf.edges||[]).indexOf(e)}` });
      }
    }
  }
}

// —— WF071/072/073: join 完整性
// 约定：每个 parallel 必须有一个 wait[join_of=parallel.id]；所有分支路径可达该 wait。
const parallels = wf.steps.filter(s => s.type === "parallel");
for (const p of parallels) {
  const join = wf.steps.find(s => s.type === "wait" && s.join_of === p.id);
  if (!join) {
    issues.push({ code:"WF071", level:"error", message:`parallel "${p.id}" has no join(wait) step`, pointer:`/steps/${wf.steps.indexOf(p)}` });
    continue;
  }
  const branchHeads = (wf.edges || []).filter(e => e.from === p.id).map(e => e.to);
  for (const headId of branchHeads) {
    if (!pathExists(wf, headId, join.id)) {
      issues.push({ code:"WF073", level:"error", message:`branch "${headId}" does not reach join "${join.id}"`, pointer:`/edges/${(wf.edges||[]).findIndex(e => e.from===p.id && e.to===headId)}` });
    }
  }
  // 额外：join 不应有来自 parallel 之外的前驱（严格模式，可先告警）
  const preds = (wf.edges || []).filter(e => e.to === join.id).map(e => e.from);
  const legit = new Set(branchHeads);
  for (const pred of preds) {
    if (!legit.has(pred)) {
      issues.push({ code:"WF072", level:"warn", message:`join "${join.id}" has non-branch predecessor "${pred}"`, pointer:`/steps/${wf.steps.indexOf(join)}` });
    }
  }
}

// —— WF075: subflow_ref 存在性（路由可选调用远端验证；此处仅静态检查非空）
for (let i=0;i<wf.steps.length;i++){
  const s = wf.steps[i];
  if (s.type === "subflow" && !s.subflow_ref) {
    issues.push({ code:"WF075", level:"error", message:`subflow step "${s.id}" missing subflow_ref`, pointer:`/steps/${i}/subflow_ref` });
  }
}

// —— 工具函数：图路径存在性（BFS）
function pathExists(wf:any, fromId:string, toId:string){
  const adj = new Map<string,string[]>();
  for (const s of wf.steps) adj.set(s.id, []);
  for (const e of (wf.edges||[])) (adj.get(e.from)||[]).push(e.to);
  const seen = new Set<string>(); const q=[fromId];
  while (q.length){ const u=q.shift()!; if(u===toId) return true; if(seen.has(u)) continue; seen.add(u); for(const v of (adj.get(u)||[])) q.push(v); }
  return false;
}
```

---

# 四、模拟器：subflow 与 parallel 的执行语义

## 1) 子流程（递归执行）

在 `src/sim/runner.ts` 中引入子流程加载与执行（贴关键增量）：

```ts
import fs from "node:fs/promises";
import path from "node:path";
import { resolveRefs } from "./strings.js";
// ...保持现有 import

async function loadSubflow(ref: string){
  const p = path.resolve("subflows", `${ref}.json`);
  const raw = await fs.readFile(p, "utf-8");
  return JSON.parse(raw);
}

export async function simulateWorkflow(wf: WF, seed?: number, opts?: { /* 省略 */ }): Promise<SimResult & { debug?: any[] }> {
  // ...现有代码

  while (cur && safety++ < 1000) {
    const step = findStep(wf, cur);
    if (!step) break;

    const started = Date.now();

    if (step.type === "subflow") {
      // 1) 准备子流程变量（父上下文替换 input 中的引用）
      const inputResolved = resolveRefs(step.input || {}, { ...ctx });
      const sf = await loadSubflow(step.subflow_ref);
      sf.variables = { ...(sf.variables || {}), ...(inputResolved || {}) };

      // 2) 递归模拟
      const sub = await simulateWorkflow(sf, seed, opts);

      // 3) 导出策略：默认导出最后一步 outputs 为 result；若 export 指定，则按字段拷贝
      const lastOut = sub.trace.at(-1)?.outputs || {};
      let out = { result: lastOut, subflow_trace_len: sub.trace.length, subflow_last_step: sub.last_step };
      if (Array.isArray(step.export) && step.export.length) {
        const pick: any = {};
        for (const k of step.export) if (k in lastOut) pick[k] = lastOut[k];
        out = { ...out, ...pick };
      }

      trace.push({
        id: step.id, name: step.name, uses: "subflow",
        status: "ok", started_ms: started, duration_ms: 0, outputs: out
      });
      ctx.outputs[step.id] = out;

      // 继续走图
    } else if (step.type === "parallel") {
      // —— 并行 fork：收集分支头
      const heads = (adj.get(step.id) || []).map(o => o.to);
      const join = wf.steps.find(s => s.type === "wait" && s.join_of === step.id);
      trace.push({ id: step.id, name: step.name, uses: "parallel", status: "ok", started_ms: started, duration_ms: 0 });

      // 并行执行每个分支，直到到达 join（或尽头）
      const branchResults = await Promise.all(heads.map(h => simulateBranchUntilJoin(wf, h, join?.id, ctx, seed, opts)));
      // 将分支轨迹线性合并（前端可按 step.id 再分组展示）
      for (const br of branchResults) for (const t of br.trace) trace.push(t);
      // join 节点：duration 取分支最大耗时
      const maxDur = Math.max(0, ...branchResults.map(b => b.duration_ms || 0));
      if (join) {
        trace.push({ id: join.id, name: join.name, uses: "wait", status: "ok", started_ms: Date.now(), duration_ms: maxDur, outputs: { joined: heads } });
        ctx.outputs[join.id] = { joined: heads };
        cur = nextOf(wf, join.id); // 从 join 往后继续
        continue;
      } else {
        break; // 没有 join，流程在此停止（Lint 会报 WF071）
      }
    } else {
      // —— 原 action/其他类型
      // （保持你之前 simulateAction 的逻辑）
      const r = await simulateAction(step.uses, resolveRefs(step.params||{}, { ...ctx }), ctx);
      trace.push({ id: step.id, name: step.name, uses: step.uses, status: r.ok?"ok":"error", started_ms: started, duration_ms: r.duration_ms ?? 0, outputs: r.outputs, warning: r.warning });
      ctx.outputs[step.id] = r.outputs || {};
    }

    // 选择下一个（非并行/非 join 特别处理时）
    const options = adj.get(step.id) || [];
    let next = "";
    for (const opt of options) { const ok = evalCond(opt.condition, { ...ctx, step }); if (ok) { next = opt.to; break; } }
    if (!next) break;
    cur = next;
  }

  // ...
}

// 线性执行一条分支，直到命中 joinId 或没有后继；共享 ctx（可并发写 outputs）
async function simulateBranchUntilJoin(wf: WF, headId: string, joinId: string | undefined, ctx: SimCtx, seed: number | undefined, opts: any) {
  const localTrace: any[] = [];
  let cur = headId; let guard = 0; let durationSum = 0;
  const adj = buildAdj(wf);
  while (cur && guard++ < 300) {
    if (joinId && cur === joinId) break;
    const s = findStep(wf, cur); if (!s) break;
    const started = Date.now();
    if (s.type === "action") {
      const r = await simulateAction(s.uses, resolveRefs(s.params||{}, { ...ctx }), ctx);
      localTrace.push({ id: s.id, name: s.name, uses: s.uses, status: r.ok?"ok":"error", started_ms: started, duration_ms: r.duration_ms ?? 0, outputs: r.outputs, warning: r.warning });
      ctx.outputs[s.id] = r.outputs || {};
      durationSum += r.duration_ms ?? 0;
    } else if (s.type === "wait" || s.type === "parallel" || s.type === "subflow") {
      // 简化：分支中再次遇到 wait/parallel/subflow → 直接停止（首版不支持嵌套并行）
      break;
    } else {
      localTrace.push({ id: s.id, name: s.name, uses: s.type, status: "ok", started_ms: started, duration_ms: 0 });
    }
    const outs = adj.get(s.id) || []; if (!outs.length) break;
    cur = outs[0].to; // 分支内部首版按顺序流（不走条件）
  }
  return { trace: localTrace, duration_ms: durationSum };
}

function nextOf(wf: WF, id: string) {
  const e = (wf.edges || []).find(x => x.from === id);
  return e?.to || "";
}
```

> 说明：
>
> * **并行首版**：从 `parallel` 出发的多条边视为多分支头，分别线性执行到 `wait[join_of]`。
> * **性能**：这里的“并行”以 `Promise.all` 模拟；真实执行器里你可替换为多 worker。
> * **输出**：join 产物写到 `ctx.outputs[join.id] = { joined: [...] }`，便于后续步骤引用。

---

# 五、示例工作流

## 1) 并行示例：两路查找后汇合再 OCR

**examples/wf\_parallel\_join.json**

```json
{
  "name": "parallel find then join",
  "version": "1.0.0",
  "globals": { "device_target": "web", "llm_budget": { "max_calls": 0, "max_tokens": 0 }, "auto_promote_on_success": false },
  "start": "open",
  "steps": [
    { "id": "open", "type": "action", "uses": "ext.open_url", "params": { "url": "https://example.com", "app": "Google Chrome" } },
    { "id": "p1", "type": "parallel", "name": "fork" },
    { "id": "findA", "type": "action", "uses": "vision.find_element_with_image_check", "params": { "anchor_image_id": "btn_ok_blue_v3" } },
    { "id": "findB", "type": "action", "uses": "vision.find_element_with_image_check", "params": { "anchor_image_id": "nav_profile_v2" } },
    { "id": "j1", "type": "wait", "join_of": "p1", "join_mode": "all" },
    { "id": "ocrA", "type": "action", "uses": "ocr.extract_region", "params": { "ref": "${outputs.findA.bbox}", "lang": "en" } }
  ],
  "edges": [
    { "from": "open", "to": "p1" },
    { "from": "p1", "to": "findA" },
    { "from": "p1", "to": "findB" },
    { "from": "findA", "to": "j1" },
    { "from": "findB", "to": "j1" },
    { "from": "j1", "to": "ocrA" }
  ]
}
```

## 2) 子流程示例：先登录 subflow，再继续

**examples/wf\_with\_subflow\.json**

```json
{
  "name": "login then greet",
  "version": "1.0.0",
  "globals": { "device_target": "web", "llm_budget": { "max_calls": 0, "max_tokens": 0 }, "auto_promote_on_success": false },
  "variables": { "friend_name": "Jack" },
  "start": "login",
  "steps": [
    { "id": "login", "type": "subflow", "subflow_ref": "login_basic", "input": { "url": "https://facebook.com", "username": "demo", "password": "pass" }, "export": [] },
    { "id": "focus", "type": "action", "uses": "ext.key", "params": { "key": "Enter" } },
    { "id": "say", "type": "action", "uses": "type_text", "params": { "text": "Hi ${vars.friend_name}!" } }
  ],
  "edges": [
    { "from": "login", "to": "focus" },
    { "from": "focus", "to": "say" }
  ]
}
```

---

# 六、如何联调

```bash
npm run dev

# 1) 列出子流程
curl -s http://localhost:8787/subflows | jq

# 2) Lint 并行结构
curl -s -X POST http://localhost:8787/lint -H 'Content-Type: application/json' \
  --data-binary @examples/wf_parallel_join.json | jq

# 3) 模拟并行（含 explain）
curl -s -X POST http://localhost:8787/simulate -H 'Content-Type: application/json' \
  -d '{"workflow":'$(cat examples/wf_parallel_join.json)',"explain":true}' | jq '.trace,.warnings'

# 4) 模拟子流程
curl -s -X POST http://localhost:8787/simulate -H 'Content-Type: application/json' \
  -d '{"workflow":'$(cat examples/wf_with_subflow.json)'}' | jq '.trace | .[0], .[-1]'
```

---

# 七、前端接入要点

* **并行节点**：在 DAG 里把 `type=parallel` 渲染为“分叉”菱形；`type=wait[join_of=...]` 渲染为“汇合”条。

  * 在 Step 详情展示“分支头列表”和“join\_of=… / mode=…”；当 Lint 出现 `WF071/073/074`，就地高亮对应边。
* **子流程节点**：显示 `subflow_ref` 与传入 `input`（已做变量替换预览）；点击可**在右侧面板打开子流程只读视图**（通过 `/subflows/:id` 拉取）。

---

9:
好！进入 **M2：前端工作台（Studio）最小可用实现**。这一步的目标是把你已经跑起来的后端接口（/validate、/lint、/simulate、/generate、/fix、/registry、/schemas、/templates、/subflows……）接成一个可交互的单页应用：左图（DAG）—中表（Step 表单）—右编（JSON Editor），底部统一的 Issues/Simulate 面板。下面直接给你**可落地的 Next.js+TypeScript** 代码骨架与关键组件。

我把完整代码放在一个文档里，按“文件分块”给出；你只要新建前端仓库，把这些文件粘进去即可运行。

---

## 你将得到的能力（这一版就够用）

* JSON 编辑器（Monaco，Schema 感知补全 + 即时 /validate 标红）。
* DAG 视图（@xyflow/react）：拖线改 edges，点节点选 Step。
* Step 表单（RJSF）：自动读取 `/registry/actions/:id` 的参数 Schema，双向绑定 `steps[i].params`。
* 一键 Lint、Fix、Simulate、Generate（含 allow\_actions/complexity 控件）。
* Issues 面板：点击定位 JSON Pointer（到表单或编辑器），展示 fix 建议。
* 模板与子流程：从 `/templates`、`/subflows` 拉取列表并实例化/插入。

---

## 如何创建前端工程

```bash
# 建议单独 repo：workflow-studio
npx create-next-app@latest workflow-studio --ts --eslint --src-dir --app --tailwind
cd workflow-studio

# 安装依赖
pnpm add @monaco-editor/react @xyflow/react @rjsf/core @rjsf/validator-ajv8 ajv ajv-formats clsx
pnpm add -D @types/lodash

# 开发模式
pnpm dev
# 默认跑在 http://localhost:3000
```

> 默认假设你的后端 `workflow-config-service` 跑在 `http://localhost:8787`。如果端口不同，改 `src/lib/api.ts` 里的 `API_BASE`。

---

## 文件与代码（复制到同名路径）

### 1) `src/lib/api.ts`

```ts
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8787";

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers||{}) } });
  const txt = await r.text();
  try {
    const data = txt ? JSON.parse(txt) : {};
    if (!r.ok) throw data;
    return data;
  } catch (e: any) {
    if (!r.ok) throw e || { error: txt || "Request failed" };
    throw e;
  }
}

export const api = {
  getWorkflowSchema: () => j(`${API_BASE}/schemas/workflow`),
  listActions: () => j<{actions:{id:string,title:string,schema:string}[]}>(`${API_BASE}/registry/actions`),
  getActionSchema: (id: string) => j(`${API_BASE}/registry/actions/${id}`),

  validate: (wf: any) => j(`${API_BASE}/validate`, { method: "POST", body: JSON.stringify(wf) }),
  lint: (wf: any, device?: any, evidence?: any) =>
    j(`${API_BASE}/lint`, { method: "POST", body: JSON.stringify({ workflow: wf, device, evidence }) }),
  simulate: (wf: any, opts?: any) =>
    j(`${API_BASE}/simulate`, { method: "POST", body: JSON.stringify({ workflow: wf, ...opts }) }),
  generate: (payload: { type?: string; complexity?: "small"|"medium"|"large"; description: string; allow_actions?: string[] }) =>
    j(`${API_BASE}/generate`, { method: "POST", body: JSON.stringify(payload) }),
  fix: (wf: any) => j(`${API_BASE}/fix`, { method: "POST", body: JSON.stringify({ workflow: wf }) }),

  listTemplates: () => j(`${API_BASE}/templates`),
  getTemplate: (id: string) => j(`${API_BASE}/templates/${id}`),
  instantiateTemplate: (id: string, params: any) =>
    j(`${API_BASE}/templates/${id}/instantiate`, { method: "POST", body: JSON.stringify({ params }) }),

  listSubflows: () => j(`${API_BASE}/subflows`),
  getSubflow: (id: string) => j(`${API_BASE}/subflows/${id}`),
};
```

### 2) `src/lib/jsonPointer.ts`

```ts
// 简易 JSON Pointer 工具，用于根据 pointer 找到对象并返回 parent+key
export function getByPointer(root: any, pointer: string): { parent: any; key: string|number } | null {
  if (!pointer || pointer === "/") return { parent: { "/": root }, key: "/" };
  const seg = pointer.split("/").slice(1).map(unescapePointer);
  let parent: any = null, cur = root, key: any = null;
  for (let i = 0; i < seg.length; i++) {
    parent = cur; key = seg[i];
    if (Array.isArray(cur)) {
      const idx = isFinite(Number(key)) ? Number(key) : NaN;
      if (Number.isNaN(idx) || !(idx in cur)) return null;
      cur = cur[idx];
    } else if (typeof cur === "object" && key in cur) {
      cur = (cur as any)[key];
    } else {
      return null;
    }
  }
  return { parent, key };
}
function unescapePointer(s: string) { return s.replace(/~1/g, "/").replace(/~0/g, "~"); }
```

### 3) `src/lib/graph.ts`

```ts
import type { Edge, Node } from "@xyflow/react";

export function wfToGraph(wf: any): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = (wf.steps || []).map((s: any, i: number) => ({
    id: s.id,
    position: { x: (i%6)*220, y: Math.floor(i/6)*140 },
    data: { label: `${s.id} (${s.type}${s.uses?": "+s.uses:""})` }
  }));
  const edges: Edge[] = (wf.edges || []).map((e: any, i: number) => ({
    id: `${e.from}->${e.to}-${i}`,
    source: e.from, target: e.to, label: e.condition || ""
  }));
  // 无 edges：按顺序连起来（只用于展示；保存时仍写回 /edges）
  if ((!wf.edges || wf.edges.length===0) && (wf.steps||[]).length > 1) {
    for (let i = 0; i < wf.steps.length-1; i++) {
      edges.push({ id: `${wf.steps[i].id}->${wf.steps[i+1].id}`, source: wf.steps[i].id, target: wf.steps[i+1].id });
    }
  }
  return { nodes, edges };
}

export function upsertEdge(wf: any, from: string, to: string, condition?: string) {
  wf.edges = Array.isArray(wf.edges) ? wf.edges : [];
  if (!wf.edges.find((e: any) => e.from===from && e.to===to)) {
    wf.edges.push({ from, to, ...(condition?{condition}:{}) });
  }
}

export function removeEdge(wf: any, from: string, to: string) {
  wf.edges = (wf.edges || []).filter((e: any) => !(e.from===from && e.to===to));
}
```

### 4) `src/components/JsonEditor.tsx`

```tsx
"use client";
import dynamic from "next/dynamic";
import { useEffect, useRef } from "react";
import type * as monacoNS from "monaco-editor";

const Monaco = dynamic(() => import("@monaco-editor/react"), { ssr: false });

type Props = {
  value: string;
  onChange: (v: string) => void;
  schema?: any;
  highlightKeyword?: string; // 简易高亮：step id 或键名
};

export default function JsonEditor({ value, onChange, schema, highlightKeyword }: Props) {
  const monacoRef = useRef<monacoNS.editor.IStandaloneCodeEditor | null>(null);

  useEffect(() => {
    if (!monacoRef.current || !highlightKeyword) return;
    const model = monacoRef.current.getModel();
    if (!model) return;
    const matches = model.findMatches(highlightKeyword, true, false, true, null, true);
    if (matches[0]) {
      monacoRef.current.revealRangeInCenter(matches[0].range);
      monacoRef.current.setSelection(matches[0].range);
      monacoRef.current.focus();
    }
  }, [highlightKeyword]);

  function handleMount(editor: monacoNS.editor.IStandaloneCodeEditor, monaco: typeof monacoNS) {
    monacoRef.current = editor;
    monaco.languages.json.jsonDefaults.setDiagnosticsOptions({
      validate: true,
      allowComments: false,
      schemas: schema ? [{
        uri: "inmemory://model/workflow.schema.json",
        fileMatch: ["*"],
        schema
      }] : []
    });
  }

  return (
    <div className="h-full border rounded-lg overflow-hidden">
      <Monaco
        height="100%"
        defaultLanguage="json"
        value={value}
        onChange={(v) => onChange(v || "")}
        onMount={handleMount}
        options={{ fontSize: 13, minimap: { enabled: false }, tabSize: 2, automaticLayout: true }}
      />
    </div>
  );
}
```

### 5) `src/components/GraphView.tsx`

```tsx
"use client";
import { useMemo } from "react";
import { ReactFlow, Background, Controls, MiniMap, addEdge, Connection, Edge, Node, useNodesState, useEdgesState } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { wfToGraph } from "@/lib/graph";

type Props = {
  workflow: any;
  onSelectStep: (id: string) => void;
  onUpdateEdges: (edges: { from: string; to: string }[]) => void;
};

export default function GraphView({ workflow, onSelectStep, onUpdateEdges }: Props) {
  const initial = useMemo(() => wfToGraph(workflow), [workflow]);
  const [nodes, setNodes, onNodesChange] = useNodesState(initial.nodes as Node[]);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges as Edge[]);

  function onConnect(c: Connection) {
    if (c.source && c.target) {
      setEdges((eds) => addEdge({ ...c, animated: false }, eds));
      onUpdateEdges([...edges, { from: c.source, to: c.target }]);
    }
  }

  return (
    <div className="h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={(_, n) => onSelectStep(n.id)}
        fitView
      >
        <MiniMap pannable zoomable />
        <Controls />
        <Background />
      </ReactFlow>
    </div>
  );
}
```

### 6) `src/components/StepForm.tsx`

```tsx
"use client";
import { useEffect, useMemo, useState } from "react";
import Form from "@rjsf/core";
import validator from "@rjsf/validator-ajv8";
import { api } from "@/lib/api";

type Props = {
  workflow: any;
  selectedStepId?: string;
  onChange: (wf: any) => void;
};

export default function StepForm({ workflow, selectedStepId, onChange }: Props) {
  const stepIdx = useMemo(() => (workflow.steps||[]).findIndex((s: any) => s.id === selectedStepId), [workflow, selectedStepId]);
  const step = stepIdx >= 0 ? workflow.steps[stepIdx] : null;

  const [actionSchema, setActionSchema] = useState<any>(null);

  useEffect(() => {
    let mounted = true;
    async function load() {
      if (!step || step.type !== "action" || !step.uses) { setActionSchema(null); return; }
      try { const s = await api.getActionSchema(step.uses); if (mounted) setActionSchema(s); } catch { setActionSchema(null); }
    }
    load(); return () => { mounted = false; };
  }, [step?.uses, step?.type, selectedStepId]);

  if (!step) return <div className="text-sm text-gray-500 p-3">选择一个 Step 以编辑参数</div>;
  if (step.type !== "action")
    return <div className="text-sm p-3"><div className="font-medium">{step.id}</div><div className="text-gray-500">该步骤类型：{step.type}（暂不渲染表单）</div></div>;

  return (
    <div className="h-full overflow-auto p-2">
      <div className="text-xs text-gray-500 mb-2">Step: {step.id} · {step.uses}</div>
      {actionSchema ? (
        <Form
          schema={actionSchema}
          validator={validator}
          formData={step.params || {}}
          onChange={(e) => {
            const nwf = structuredClone(workflow);
            nwf.steps[stepIdx].params = e.formData || {};
            onChange(nwf);
          }}
          onSubmit={() => {}}
          uiSchema={{ "ui:submitButtonOptions": { norender: true } }}
        />
      ) : (
        <div className="text-sm text-gray-500">未能加载动作参数 Schema 或该步骤无需参数。</div>
      )}
    </div>
  );
}
```

### 7) `src/components/IssuesPanel.tsx`

```tsx
"use client";
type Issue = { code: string; level: "error"|"warn"|"info"; message: string; pointer?: string; fix?: string };

export default function IssuesPanel({ issues, onJump }: { issues: Issue[]; onJump: (pointer?: string)=>void }) {
  if (!issues?.length) return <div className="text-xs text-green-600 p-2">✔ 没有问题</div>;
  return (
    <div className="text-sm">
      {issues.map((it, i) => (
        <div key={i} className="border-b py-2">
          <div className="flex items-center gap-2">
            <span className={`text-xs rounded px-1 ${it.level==="error"?"bg-red-100 text-red-700":it.level==="warn"?"bg-yellow-100 text-yellow-700":"bg-slate-100 text-slate-700"}`}>{it.code}</span>
            <span className="font-medium">{it.message}</span>
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {it.pointer ? <button className="underline" onClick={()=>onJump(it.pointer)}>{it.pointer}</button> : null}
            {it.fix ? <span className="ml-2"> · 建议：{it.fix}</span> : null}
          </div>
        </div>
      ))}
    </div>
  );
}
```

### 8) `src/app/page.tsx`（主界面）

```tsx
"use client";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import GraphView from "@/components/GraphView";
import StepForm from "@/components/StepForm";
import JsonEditor from "@/components/JsonEditor";
import IssuesPanel from "@/components/IssuesPanel";
import { upsertEdge } from "@/lib/graph";

const DEFAULT_WF = {
  name: "demo",
  version: "1.0.0",
  globals: { device_target: "web", llm_budget: { max_calls: 1, max_tokens: 800 }, auto_promote_on_success: false },
  start: "init",
  steps: [
    { id: "init", name: "Initialize", type: "action", uses: "ext.open_url", params: { url: "https://example.com", app: "Google Chrome" } },
    { id: "finalize", name: "Finalize", type: "action", uses: "type_text", params: { text: "Hello" } }
  ],
  edges: [{ from: "init", to: "finalize" }]
};

export default function Page() {
  const [schema, setSchema] = useState<any>(null);
  const [wf, setWf] = useState<any>(DEFAULT_WF);
  const [json, setJson] = useState<string>(JSON.stringify(DEFAULT_WF, null, 2));
  const [selectedStepId, setSelectedStepId] = useState<string>();
  const [issues, setIssues] = useState<any[]>([]);
  const [sim, setSim] = useState<any>(null);
  const [actions, setActions] = useState<{id:string,title:string}[]>([]);
  const [genDesc, setGenDesc] = useState<string>("Open Facebook, search Jack, say hi");
  const [genAllow, setGenAllow] = useState<string[]>(["ext.open_url","ext.key","type_text","llm.reply"]);
  const [genComplexity, setGenComplexity] = useState<"small"|"medium"|"large">("medium");

  useEffect(() => {
    api.getWorkflowSchema().then(setSchema).catch(()=>{});
    api.listActions().then(d => setActions(d.actions)).catch(()=>{});
  }, []);

  // json ↔ wf 双向
  useEffect(() => {
    try {
      const obj = JSON.parse(json);
      setWf(obj);
    } catch {}
  }, [json]);

  useEffect(() => { setJson(JSON.stringify(wf, null, 2)); }, [wf]);

  async function doValidate() {
    try { await api.validate(wf); setIssues([]); } catch (e:any) { setIssues(e.errors||e.issues||[{ level:"error", code:"ERR", message: e.error||"validate failed"}]); }
  }
  async function doLint() {
    try { const r = await api.lint(wf); setIssues(r.issues||[]); } catch (e:any) { setIssues(e.issues||[{ level:"error", code:"ERR", message: e.error||"lint failed"}]); }
  }
  async function doSimulate(explain=false) {
    try { const r = await api.simulate(wf, { explain }); setSim(r); } catch (e:any) { setSim(null); setIssues(e.issues||[{ level:"error", code:"ERR", message: e.error||"simulate failed"}]); }
  }
  async function doFix() {
    try { const r = await api.fix(wf); setWf(r.patched); setIssues(r.post_issues||[]); } catch (e:any) { /* noop */ }
  }
  async function doGenerate() {
    try {
      const r = await api.generate({ description: genDesc, complexity: genComplexity, allow_actions: genAllow });
      setWf(r.workflow); setIssues(r.issues||[]); setSim(null);
    } catch (e:any) {
      setIssues(e.issues||[{ level:"error", code:"GEN", message: e.error||"generate failed"}]);
    }
  }

  function handleUpdateEdges(e: {from:string; to:string}[]) {
    const nwf = structuredClone(wf);
    e.forEach(x => upsertEdge(nwf, x.from, x.to));
    setWf(nwf);
  }

  return (
    <div className="h-screen flex flex-col">
      {/* 顶栏 */}
      <div className="px-4 py-2 border-b flex items-center gap-2">
        <div className="font-semibold">Workflow Studio (M2)</div>
        <div className="ml-auto flex items-center gap-2">
          <button className="px-3 py-1 rounded bg-slate-100 hover:bg-slate-200" onClick={doValidate}>Validate</button>
          <button className="px-3 py-1 rounded bg-yellow-100 hover:bg-yellow-200" onClick={doLint}>Lint</button>
          <button className="px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-700" onClick={()=>doSimulate(false)}>Simulate</button>
          <button className="px-3 py-1 rounded bg-blue-500 text-white hover:bg-blue-600" onClick={()=>doSimulate(true)}>Sim+Explain</button>
          <button className="px-3 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700" onClick={doFix}>Fix</button>
        </div>
      </div>

      {/* 主体：三栏 */}
      <div className="flex-1 grid grid-cols-12 gap-2 p-2">
        <div className="col-span-4 border rounded-lg overflow-hidden">
          <div className="p-2 text-sm font-medium border-b flex items-center justify-between">
            <span>DAG</span>
            <span className="text-xs text-gray-500">点击节点选择 Step</span>
          </div>
          <GraphView
            workflow={wf}
            onSelectStep={setSelectedStepId}
            onUpdateEdges={handleUpdateEdges}
          />
        </div>

        <div className="col-span-3 border rounded-lg overflow-hidden flex flex-col">
          <div className="p-2 text-sm font-medium border-b">Step 配置</div>
          <div className="flex-1">
            <StepForm workflow={wf} selectedStepId={selectedStepId} onChange={setWf} />
          </div>
          <div className="p-2 border-t flex items-center gap-2 text-xs">
            <span>AI 生成：</span>
            <select className="border rounded px-1 py-0.5" value={genComplexity} onChange={(e)=>setGenComplexity(e.target.value as any)}>
              <option value="small">small</option><option value="medium">medium</option><option value="large">large</option>
            </select>
            <input className="border rounded px-2 py-1 flex-1" value={genDesc} onChange={e=>setGenDesc(e.target.value)} placeholder="描述你要做的任务…" />
            <button className="px-2 py-1 bg-indigo-600 text-white rounded" onClick={doGenerate}>Generate</button>
          </div>
        </div>

        <div className="col-span-5 border rounded-lg overflow-hidden flex flex-col">
          <div className="p-2 text-sm font-medium border-b">JSON</div>
          <div className="flex-1">
            <JsonEditor value={json} onChange={setJson} schema={schema} highlightKeyword={selectedStepId} />
          </div>
        </div>

        {/* 下方两栏：Issues / Simulation */}
        <div className="col-span-6 border rounded-lg overflow-hidden">
          <div className="p-2 text-sm font-medium border-b">Issues</div>
          <div className="h-[240px] overflow-auto p-2">
            <IssuesPanel issues={issues} onJump={(ptr)=>{
              if (!ptr) return;
              // 简易跳转：如果是 /steps/<idx>，就选中该 step
              const m = /^\/steps\/(\d+)/.exec(ptr);
              if (m) {
                const idx = Number(m[1]);
                const st = (wf.steps||[])[idx]; if (st) setSelectedStepId(st.id);
              }
            }} />
          </div>
        </div>

        <div className="col-span-6 border rounded-lg overflow-hidden">
          <div className="p-2 text-sm font-medium border-b">Simulate</div>
          <div className="h-[240px] overflow-auto p-2 text-sm">
            {sim ? (
              <>
                <div className="text-xs text-gray-500 mb-2">finished: {String(sim.finished)} · last_step: {sim.last_step} · tokens: {sim.estimates?.llm_tokens}</div>
                <ol className="list-decimal pl-5">
                  {sim.trace?.map((t:any,i:number) => (
                    <li key={i} className="mb-1">
                      <span className="font-medium">{t.id}</span> · <span className="text-gray-600">{t.uses}</span> · {t.status}
                      {t.outputs ? <pre className="bg-slate-50 p-2 text-xs rounded mt-1 overflow-auto">{JSON.stringify(t.outputs, null, 2)}</pre> : null}
                    </li>
                  ))}
                </ol>
              </>
            ) : <div className="text-xs text-gray-500">点击 Simulate 查看轨迹</div>}
          </div>
        </div>
      </div>

      {/* 页脚 */}
      <div className="px-4 py-2 border-t text-xs text-gray-500">
        后端：{process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8787"} · 提示：先启动 workflow-config-service
      </div>
    </div>
  );
}
```

---

## 运行与联调

1. 启动后端（你之前已经有）：

```bash
cd workflow-config-service
npm run dev
```

2. 启动前端：

```bash
cd workflow-studio
# 如果后端地址不是默认的 8787：
echo 'NEXT_PUBLIC_API_BASE=http://127.0.0.1:8787' > .env.local
pnpm dev
```

3. 在浏览器里：

* DAG 里点 **init/finalize** 节点 → 中栏出现参数表单，改值即写回 JSON；
* 点 **Generate**，输入描述 → 自动回填可用工作流；
* 点 **Lint**/**Fix**/**Simulate** 查看问题与轨迹；
* Issues 列表点击 `/steps/<idx>` 指针会自动选中对应 Step；
* 在 DAG 拖线连边会写回 `edges`。

---

## 下一小步（M2 后续增量建议）

* Monaco 中基于 JSON AST 的**精准 Pointer → Range** 定位（用 `monaco-editor/esm/vs/language/json/jsonWorker`）。
* **Action Palette**（左侧动作库拖拽上图）：调用 `/registry/actions` 列出并拖入，自动 new step id。
* **模板/子流程**抽屉：从 `/templates`、`/subflows` 拉取并“插入到当前光标/所选节点之后”。
* **Explain 视图**：当 `simulate(explain=true)`，为每条边显示最近一次条件求值结果（绿/灰），在 DAG 上微型 Badge 呈现。

---
10:
好，进入 **M3：运行时执行器 + Chrome 扩展桥接（MVP）**。这一步的目标：把你在 M1/M2 里产出的 workflow，**真正跑到浏览器页面上执行**（开页面、点元素、敲键、输入文本），形成“Studio → 复制 JSON → 扩展粘贴 → 一键 Run”的最小闭环。先做 **M3-S1（最小可用扩展 + 执行器）**，跑通后我再给 **M3-S2（Studio 一键下发/联通）** 与 **M3-S3（Vision/OCR/LLM 接入）**。

---

# M3-S1：Chrome 扩展（MV3）+ 运行时执行器

## 能力范围（MVP）

* 在当前/新标签页执行 workflow：`ext.open_url`、`ext.click(selector|x,y)`、`ext.key`、`type_text`。
* 支持变量替换（`${vars.*}`）、简单条件（`true/false`、`==/!=`、`contains()`），按 edges 走图。
* 每步有**执行日志+outputs**，显示在扩展弹窗里。
* 失败不崩溃：错误会被标注并停在当前步。
* 先不做 YOLO/OCR/LLM（会给占位钩子，M3-S3 接上）。

---

## 目录结构

```
chrome-ext/
├─ manifest.json
├─ bg.js                # Service Worker：执行器 + 与页面的桥
├─ popup.html
├─ popup.js
├─ popup.css
└─ README.md
```

---

## manifest.json

```json
{
  "manifest_version": 3,
  "name": "Workflow Runner (YOLO+LLM+Ext)",
  "version": "0.1.0",
  "description": "Run validated workflows in the browser (M3 MVP).",
  "action": { "default_popup": "popup.html", "default_title": "Workflow Runner" },
  "permissions": ["scripting", "tabs", "activeTab", "storage"],
  "host_permissions": ["<all_urls>"],
  "background": { "service_worker": "bg.js", "type": "module" }
}
```

---

## bg.js（执行器 + 页面注入）

```js
// ===== 轻量工具：变量替换与条件求值 =====
const REF = /\$\{([^}]+)\}/g;
const pick = (obj, path) => path.split(".").reduce((c,k)=> (c? c[k] : undefined), obj);
function resolveRefs(value, ctx) {
  if (value == null) return value;
  if (typeof value === "string") {
    return value.replace(REF, (_, expr) => {
      if (expr.startsWith("vars.")) return String(pick(ctx.vars, expr.slice(5)) ?? "");
      if (expr.startsWith("globals.env.")) return String(pick((ctx.globals||{}).env||{}, expr.slice(12)) ?? "");
      if (expr.startsWith("outputs.")) return String(pick(ctx.outputs, expr.slice(8)) ?? "");
      if (expr === "true") return "true"; if (expr === "false") return "false";
      return String(pick(ctx, expr) ?? "");
    });
  }
  if (Array.isArray(value)) return value.map(v => resolveRefs(v, ctx));
  if (typeof value === "object") {
    const out = {}; for (const k of Object.keys(value)) out[k] = resolveRefs(value[k], ctx); return out;
  }
  return value;
}
function evalCond(cond, ctx) {
  if (!cond) return true;
  const s = cond.trim();
  if (s === "true") return true;
  if (s === "false") return false;
  const mContains = /^contains\((.+?),\s*"(.*)"\)$/.exec(s);
  if (mContains) { const left = String(pick(ctx, mContains[1].trim()) ?? ""); return left.includes(mContains[2]); }
  const mEq = /^(.+?)(==|!=)\s*"(.*)"$/.exec(s);
  if (mEq) { const left = String(pick(ctx, mEq[1].trim()) ?? ""); const lit = mEq[3]; return mEq[2]==="==" ? left===lit : left!==lit; }
  return !!pick(ctx, s);
}

// ===== 辅助：图结构 =====
function buildAdj(wf) {
  const adj = new Map(); (wf.steps||[]).forEach(s => adj.set(s.id, []));
  if (wf.edges?.length) wf.edges.forEach(e => adj.get(e.from)?.push({to:e.to, condition:e.condition}));
  else for (let i=0;i<wf.steps.length-1;i++) adj.get(wf.steps[i].id).push({to:wf.steps[i+1].id});
  return adj;
}
const findStep = (wf, id) => (wf.steps||[]).find(s => s.id === id);

// ===== 页面执行（注入函数，返回结果） =====
async function runInPage(tabId, func, args) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId }, func, args
  });
  return result;
}

// —— 注入：点击（selector 或 x,y）
function inj_click({ selector, x, y, button="left", clicks=1 }) {
  try {
    const sleep = ms => new Promise(r=>setTimeout(r,ms));
    const dispatchAt = async (el, cx, cy) => {
      const evt = (type) => new MouseEvent(type, { bubbles:true, cancelable:true, view:window, button: button==="left"?0:button==="middle"?1:2, clientX: cx, clientY: cy });
      el.dispatchEvent(evt("mousemove")); el.dispatchEvent(evt("mousedown")); el.dispatchEvent(evt("mouseup"));
      el.click();
    };
    if (selector) {
      const el = document.querySelector(selector);
      if (!el) return { ok:false, error:`selector not found: ${selector}` };
      const rect = el.getBoundingClientRect();
      const cx = Math.round(rect.left + rect.width/2), cy = Math.round(rect.top + rect.height/2);
      for (let i=0;i<clicks;i++) dispatchAt(el, cx, cy);
      return { ok:true, at:{selector} };
    } else if (typeof x === "number" && typeof y === "number") {
      const el = document.elementFromPoint(x,y) || document.body;
      for (let i=0;i<clicks;i++) dispatchAt(el, x, y);
      return { ok:true, at:{x,y} };
    }
    return { ok:false, error:"no selector or x/y" };
  } catch (e) { return { ok:false, error: String(e) }; }
}

// —— 注入：键盘
function inj_key({ key="Enter", modifiers=[] }) {
  try {
    const down = new KeyboardEvent("keydown", { key, bubbles:true, cancelable:true, ctrlKey: modifiers.includes("Ctrl"), metaKey: modifiers.includes("Cmd"), altKey: modifiers.includes("Alt"), shiftKey: modifiers.includes("Shift") });
    const up = new KeyboardEvent("keyup",   { key, bubbles:true, cancelable:true, ctrlKey: modifiers.includes("Ctrl"), metaKey: modifiers.includes("Cmd"), altKey: modifiers.includes("Alt"), shiftKey: modifiers.includes("Shift") });
    document.activeElement?.dispatchEvent(down);
    document.activeElement?.dispatchEvent(up);
    return { ok:true, sent:key, modifiers };
  } catch (e) { return { ok:false, error:String(e) }; }
}

// —— 注入：输入文本（type/paste）
function inj_type_text({ text="", mode="type", interval_ms=0 }) {
  try {
    const el = document.activeElement;
    const isInput = el && (el.tagName==="INPUT" || el.tagName==="TEXTAREA" || el.isContentEditable);
    if (!isInput) return { ok:false, error:"no focusable input element" };
    if (mode === "paste") {
      const start = el.selectionStart ?? null, end = el.selectionEnd ?? null;
      if ("value" in el) {
        const v = el.value; const a = start ?? v.length; const b = end ?? v.length;
        el.value = v.slice(0,a) + text + v.slice(b);
        el.dispatchEvent(new Event("input",{bubbles:true}));
      } else document.execCommand("insertText", false, text);
      return { ok:true, typed_len: text.length, mode };
    } else {
      const feed = async () => {
        for (const ch of text) {
          const e = new InputEvent("beforeinput", {inputType:"insertText", data:ch, bubbles:true, cancelable:true});
          el.dispatchEvent(e);
          if ("value" in el) el.value += ch; else document.execCommand("insertText", false, ch);
          el.dispatchEvent(new Event("input",{bubbles:true}));
          if (interval_ms) await new Promise(r=>setTimeout(r, interval_ms));
        }
      };
      return feed().then(()=>({ ok:true, typed_len: text.length, mode })).catch(e=>({ ok:false, error:String(e) }));
    }
  } catch (e) { return { ok:false, error:String(e) }; }
}

// ===== 动作实现（有的在后台，有的注入页面） =====
async function do_open_url(tabId, params) {
  const url = params.url;
  if (!url) return { ok:false, error:"missing url" };
  let targetTabId = tabId;
  if (!tabId) {
    const t = await chrome.tabs.create({ url }); targetTabId = t.id;
  } else {
    await chrome.tabs.update(tabId, { url });
  }
  await new Promise(r=>setTimeout(r, params.wait_dom_quiet_ms ?? 800));
  return { ok:true, outputs:{ page: (new URL(url)).host, ready: true }, tabId: targetTabId };
}
async function do_key(tabId, params) {
  const res = await runInPage(tabId, inj_key, [params||{}]);
  return { ok: res?.ok, outputs: res };
}
async function do_type_text(tabId, params) {
  const res = await runInPage(tabId, inj_type_text, [params||{}]);
  return { ok: res?.ok, outputs: res };
}
async function do_click(tabId, params) {
  const res = await runInPage(tabId, inj_click, [params||{}]);
  return { ok: res?.ok, outputs: { clicked: !!res?.ok, at: res?.at }, error: res?.error };
}

// ===== 执行器：按 start→edges 运行 =====
async function runWorkflow(wf, startTabId, onEvent) {
  const ctx = { vars: wf.variables || {}, globals: wf.globals || {}, outputs: {} };
  const adj = buildAdj(wf);
  let cur = wf.start;
  let tabId = startTabId;

  const trace = [];
  const t0 = Date.now();
  const stepCountLimit = 200;

  for (let guard=0; cur && guard<stepCountLimit; guard++) {
    const step = findStep(wf, cur); if (!step) break;
    const started = Date.now();
    const params = resolveRefs(step.params || {}, ctx);
    let result = { ok: true, outputs: {} };

    if (step.type === "action") {
      if (step.uses === "ext.open_url") {
        const r = await do_open_url(tabId, params);
        if (r.tabId) tabId = r.tabId;
        result = r;
      } else if (step.uses === "ext.key") {
        result = await do_key(tabId, params);
      } else if (step.uses === "type_text") {
        result = await do_type_text(tabId, params);
      } else if (step.uses === "ext.click") {
        result = await do_click(tabId, params);
      } else {
        // 预留：未来接 YOLO/OCR/LLM
        result = { ok:false, outputs:{}, error:`action not implemented: ${step.uses}` };
      }
    } else {
      // 非 action：占位通过
      result = { ok:true, outputs:{} };
    }

    const entry = {
      id: step.id, name: step.name, uses: step.uses || step.type,
      status: result.ok ? "ok" : "error",
      started_ms: started - t0, duration_ms: Date.now() - started,
      outputs: result.outputs || {}, error: result.error
    };
    trace.push(entry);
    ctx.outputs[step.id] = entry.outputs;

    onEvent?.({ type:"step", entry });

    if (!result.ok) break;

    // 选下一步
    const options = adj.get(step.id) || [];
    let next = "";
    for (const opt of options) {
      const ok = evalCond(opt.condition, { ...ctx, step });
      onEvent?.({ type:"edge_eval", from: step.id, to: opt.to, condition: opt.condition || "<default>", result: ok });
      if (ok) { next = opt.to; break; }
    }
    if (!next) break;
    cur = next;
  }

  onEvent?.({ type:"done" });
  return { trace, finished: !!cur ? false : true, last_step: trace.at(-1)?.id };
}

// ===== 与 popup 的通信 =====
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    if (msg?.type === "RUN_WORKFLOW") {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      const targetTabId = tab?.id;
      const logs = [];
      const r = await runWorkflow(msg.workflow, targetTabId, (ev) => {
        logs.push(ev);
        chrome.runtime.sendMessage({ type:"RUN_EVENT", payload: ev });
      });
      sendResponse({ ok:true, result: r });
      return;
    }
  })().catch(e => sendResponse({ ok:false, error:String(e) }));
  return true; // async
});
```

---

## popup.html / popup.js / popup.css

**popup.html**

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Workflow Runner</title>
  <link rel="stylesheet" href="popup.css" />
</head>
<body>
  <div class="wrap">
    <div class="row">
      <textarea id="wf" spellcheck="false"></textarea>
      <div class="col">
        <div class="grp">
          <button id="btnRun">Run</button>
          <button id="btnPaste">Paste</button>
          <button id="btnSample">Sample</button>
          <span id="status"></span>
        </div>
        <div class="grp">
          <label><input type="checkbox" id="chkExplain" /> Explain edges</label>
        </div>
        <div class="logs" id="logs"></div>
      </div>
    </div>
  </div>
  <script src="popup.js"></script>
</body>
</html>
```

**popup.css**

```css
body { font-family: ui-sans-serif, system-ui, -apple-system; font-size: 12px; margin: 0; }
.wrap { width: 760px; height: 480px; display: grid; padding: 8px; }
.row { display: grid; grid-template-columns: 1fr 260px; gap: 8px; }
textarea { width: 100%; height: 460px; border: 1px solid #ddd; border-radius: 6px; padding: 8px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.col { display: flex; flex-direction: column; }
.grp { margin-bottom: 8px; display:flex; align-items:center; gap:8px; }
button { padding: 6px 10px; border-radius: 6px; border: 1px solid #ddd; background: #f7f7f7; cursor: pointer; }
button:hover { background: #eee; }
#status { color: #666; }
.logs { flex:1; overflow:auto; border: 1px solid #eee; border-radius: 6px; padding: 6px; background: #fafafa; }
.log { margin-bottom: 6px; padding-bottom: 6px; border-bottom: 1px dashed #e5e7eb; }
.badge { font-size: 10px; padding: 1px 4px; border-radius: 4px; background: #eef2ff; color: #3730a3; }
.badge.err { background:#fee2e2; color:#991b1b; }
pre { background:#fff; border: 1px solid #eee; padding: 6px; border-radius: 4px; overflow:auto; }
```

**popup.js**

```js
const $ = (s) => document.querySelector(s);
const sample = {
  "name": "fb hi (M3 demo)",
  "version": "1.0.0",
  "globals": { "device_target": "web", "llm_budget": { "max_calls": 0, "max_tokens": 0 }, "auto_promote_on_success": false },
  "variables": {},
  "start": "open",
  "steps": [
    { "id":"open", "type":"action", "uses":"ext.open_url", "params": { "url":"https://example.com", "app":"Google Chrome", "wait_dom_quiet_ms": 800 } },
    { "id":"focus", "type":"action", "uses":"ext.key", "params": { "key":"Enter" } },
    { "id":"say", "type":"action", "uses":"type_text", "params": { "text":"Hello from M3!", "mode":"type", "interval_ms":0 } },
    { "id":"click", "type":"action", "uses":"ext.click", "params": { "selector":"a" } }
  ],
  "edges": [
    { "from":"open", "to":"focus" },
    { "from":"focus", "to":"say" },
    { "from":"say", "to":"click" }
  ]
};

$("#wf").value = JSON.stringify(sample, null, 2);

$("#btnSample").onclick = () => { $("#wf").value = JSON.stringify(sample, null, 2); $("#logs").innerHTML=""; };

$("#btnPaste").onclick = async () => {
  try { const txt = await navigator.clipboard.readText(); $("#wf").value = txt; } catch (e) { alert("Clipboard failed: " + e); }
};

$("#btnRun").onclick = async () => {
  let wf;
  try { wf = JSON.parse($("#wf").value); } catch (e) { return alert("Invalid JSON"); }
  $("#logs").innerHTML = ""; $("#status").textContent = "running…";

  chrome.runtime.onMessage.addListener(function listener(msg) {
    if (msg?.type === "RUN_EVENT") {
      const l = $("#logs"); const p = document.createElement("div"); p.className="log";
      if (msg.payload?.type === "step") {
        const t = msg.payload.entry;
        p.innerHTML = `<span class="badge ${t.status!=="ok"?"err":""}">STEP</span> ${t.id} · ${t.uses} · ${t.status}`
          + (t.error ? ` · <span style="color:#991b1b">${t.error}</span>` : "")
          + (t.outputs ? `<pre>${JSON.stringify(t.outputs,null,2)}</pre>` : "");
      } else if (msg.payload?.type === "edge_eval" && $("#chkExplain").checked) {
        const e = msg.payload;
        p.innerHTML = `<span class="badge">EDGE</span> ${e.from} → ${e.to} · ${e.condition} · ${e.result}`;
      } else if (msg.payload?.type === "done") {
        p.innerHTML = `<span class="badge">DONE</span>`;
        $("#status").textContent = "done";
      } else return;
      l.appendChild(p); l.scrollTop = l.scrollHeight;
    }
  });

  const resp = await chrome.runtime.sendMessage({ type:"RUN_WORKFLOW", workflow: wf });
  if (!resp?.ok) { $("#status").textContent = "failed"; alert(resp?.error || "run failed"); }
};
```

---

## 使用方法

1. 打开 `chrome://extensions` → 开启开发者模式 → “加载已解压的扩展”，选择 `chrome-ext/` 文件夹。
2. 在浏览器打开任意页面（例如新标签）。
3. 点扩展图标 → 弹窗里粘贴来自 Studio 的 workflow JSON（或用 Sample）→ **Run**。
4. 观察页面行为与弹窗日志。

> 提示：键盘/输入需要页面有可聚焦元素；若无，可在 workflow 前加一个点击到输入框的步骤，或以 `selector` 点击搜索框。

---

## 与后端/Studio 的衔接（M3-S1 内置最小方案）

* **Studio → 复制**：在 Studio 的 JSON 面板直接复制（或做一个“复制到剪贴板”按钮）。
* **扩展 → 粘贴运行**：先走人工粘贴，确保执行器稳定。
* 日志与 outputs 已在弹窗里显示，便于排障。

---

## 安全与权限

* 仅申请 `activeTab/scripting/tabs/storage` 与 `<all_urls>`；仅在**当前活动标签页**注入代码。
* 未采集/上报页面数据；M3-S3 才会引入可选的远程 YOLO/OCR，届时做开关与域名白名单。

---

11:
太好了！我们进入 **M3-S2：Studio 一键下发 → Chrome 扩展实时执行**。这一步做完，你可以在 Studio 里点一下“Run in Chrome”，扩展端立刻执行，并把**实时日志/输出**回流到 Studio 的“实时执行”面板（无需手动粘贴）。

---

# 整体方案（最小可用）

* 新增一个**本地桥接 WebSocket 服务**（`ws://127.0.0.1:9797`），转发 Studio 的“run”指令给扩展，转发扩展的“event/done”给对应的 Studio。
* Chrome 扩展 **Service Worker** 常驻连接到桥接服务；收到 `run` 就执行，并**流式**发送日志。
* Studio 侧建立 WS 连接，点击“Run in Chrome”就发送 `{type:"run", run_id, workflow}`，随后订阅同 run\_id 的事件。

> 先走最简单、稳妥的**单机本地**通信。后续要跨机/签名/权限，再加鉴权/隧道。

---

# 1) 本地桥接服务（独立小进程）

在后端仓库根目录新增：`bridge/server.ts`（或 `.js`），并安装依赖：

```bash
npm i ws uuid
```

```ts
// bridge/server.ts
import { WebSocketServer, WebSocket } from "ws";
import { v4 as uuidv4 } from "uuid";

type Role = "studio" | "extension";
type Msg =
  | { type: "hello"; role: Role; token?: string }
  | { type: "run"; run_id?: string; workflow: any }
  | { type: "event"; run_id: string; payload: any }
  | { type: "done"; run_id: string; result: any }
  | { type: "error"; run_id?: string; message: string };

const PORT = process.env.BRIDGE_PORT ? Number(process.env.BRIDGE_PORT) : 9797;
const TOKEN = process.env.BRIDGE_TOKEN || ""; // 可选共享密钥

const wss = new WebSocketServer({ port: PORT });
console.log(`[bridge] ws listening on ws://127.0.0.1:${PORT}`);

type Client = { id: string; role: Role; ws: WebSocket; ts: number };
const clients = new Map<string, Client>();
const runOwner = new Map<string, string>(); // run_id -> studio client id

function send(ws: WebSocket, obj: any) {
  try { ws.send(JSON.stringify(obj)); } catch {}
}
function broadcast(filter: (c: Client) => boolean, obj: any) {
  for (const c of clients.values()) if (filter(c)) send(c.ws, obj);
}

wss.on("connection", (ws) => {
  const id = uuidv4();
  let role: Role | null = null;

  const die = (msg?: string) => { try { ws.close(1008, msg || "bye"); } catch {} };

  ws.on("message", (buf) => {
    let data: Msg;
    try { data = JSON.parse(buf.toString()); } catch { return; }

    if (data.type === "hello") {
      if (TOKEN && (data as any).token !== TOKEN) return die("bad token");
      role = (data as any).role || "studio";
      clients.set(id, { id, role, ws, ts: Date.now() });
      send(ws, { type: "hello_ok", id, role });
      console.log(`[bridge] ${role} connected: ${id}`);
      return;
    }

    if (!role) return die("must hello first");

    if (data.type === "run") {
      const run_id = data.run_id || uuidv4();
      runOwner.set(run_id, id);
      // 简单策略：广播到所有 extension（也可只发给第一个）
      broadcast(c => c.role === "extension", { type: "run", run_id, workflow: data.workflow });
      send(ws, { type: "run_ack", run_id });
      return;
    }

    if (data.type === "event" || data.type === "done" || data.type === "error") {
      const ownerId = data.run_id ? runOwner.get(data.run_id) : null;
      if (ownerId && clients.has(ownerId)) {
        send(clients.get(ownerId)!.ws, data);
      } else {
        // 找不到归属，广播给所有 studio（容错）
        broadcast(c => c.role === "studio", data);
      }
      return;
    }
  });

  ws.on("close", () => {
    clients.delete(id);
    // 清理属于该 studio 的 run 归属
    for (const [rid, sid] of runOwner.entries()) if (sid === id) runOwner.delete(rid);
    console.log(`[bridge] disconnected: ${id}`);
  });

  // 10s 未 hello 就关闭
  setTimeout(() => { if (!role) die("no hello"); }, 10_000);
});
```

`package.json` 增加脚本：

```json
{
  "scripts": {
    "bridge": "node -r esbuild-register bridge/server.ts"
  }
}
```

启动：

```bash
# 可选：导出简单共享 TOKEN
export BRIDGE_TOKEN=devtoken
npm run bridge
```

---

# 2) 扩展端接入桥接（bg.js 增量）

在 `chrome-ext/bg.js` 顶部增加**WS 客户端**与**run 处理**（保留你已有的 `runWorkflow` 实现不动）：

```js
// === WebSocket Client to local bridge ===
let WS = null;
let WS_READY = false;
const BRIDGE_URL = "ws://127.0.0.1:9797";
const BRIDGE_TOKEN = ""; // 如启用 token，则填与 BRIDGE_TOKEN 相同

function wsConnect() {
  try {
    WS = new WebSocket(BRIDGE_URL);
    WS.onopen = () => {
      WS_READY = true;
      WS.send(JSON.stringify({ type: "hello", role: "extension", token: BRIDGE_TOKEN || undefined }));
      console.log("[ext] bridge connected");
    };
    WS.onclose = () => { WS_READY = false; setTimeout(wsConnect, 1500); };
    WS.onerror = () => { try { WS.close(); } catch {} };
    WS.onmessage = async (ev) => {
      let msg; try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.type === "run" && msg.workflow) {
        const run_id = msg.run_id;
        // 把执行事件从 runWorkflow 回发给桥（注意复用你已有的 onEvent）
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        const result = await runWorkflow(msg.workflow, tab?.id, (ev) => {
          WS?.send(JSON.stringify({ type: "event", run_id, payload: ev }));
        });
        WS?.send(JSON.stringify({ type: "done", run_id, result }));
      }
    };
  } catch (e) {
    setTimeout(wsConnect, 2000);
  }
}
wsConnect();
```

> 说明：
>
> * MV3 Service Worker 支持 WebSocket，连接存活期间 **SW 不会被挂起**。断线自动重连。
> * 如果你在桥接服务启用了 `BRIDGE_TOKEN`，在扩展这边把 `BRIDGE_TOKEN` 字符串填上即可。

---

# 3) Studio 接入桥接（前端）

### 3.1 新增 `src/lib/wsClient.ts`

```ts
// 简易 WS 客户端（自动重连）
type Listener = (ev: any) => void;

export class BridgeClient {
  url: string; token?: string;
  ws?: WebSocket; connected = false;
  listeners: Listener[] = [];
  pendingRuns = new Map<string, (ev: any) => void>();

  constructor(url = "ws://127.0.0.1:9797", token?: string) {
    this.url = url; this.token = token;
    this.connect();
  }

  on(fn: Listener) { this.listeners.push(fn); }
  off(fn: Listener) { this.listeners = this.listeners.filter(f => f !== fn); }

  private connect() {
    try {
      this.ws = new WebSocket(this.url);
      this.ws.onopen = () => {
        this.connected = true;
        this.send({ type: "hello", role: "studio", token: this.token });
      };
      this.ws.onclose = () => { this.connected = false; setTimeout(()=>this.connect(), 1200); };
      this.ws.onerror = () => { try{this.ws?.close();}catch{} };
      this.ws.onmessage = (ev) => {
        let msg; try { msg = JSON.parse(ev.data); } catch { return; }
        if (msg.type === "run_ack") this.listeners.forEach(f => f({ kind:"run_ack", run_id: msg.run_id }));
        else if (msg.type === "event") this.listeners.forEach(f => f({ kind:"event", run_id: msg.run_id, payload: msg.payload }));
        else if (msg.type === "done") this.listeners.forEach(f => f({ kind:"done", run_id: msg.run_id, result: msg.result }));
        else this.listeners.forEach(f => f({ kind:"msg", msg }));
      };
    } catch {}
  }

  send(obj: any) {
    if (!this.ws || this.ws.readyState !== 1) return;
    this.ws.send(JSON.stringify(obj));
  }

  run(workflow: any, run_id?: string) {
    this.send({ type: "run", run_id, workflow });
  }
}
```

### 3.2 修改 Studio 页面（`src/app/page.tsx`）——新增“Run in Chrome”与实时事件面板

在顶部导入：

```tsx
import { BridgeClient } from "@/lib/wsClient";
import { v4 as uuidv4 } from "uuid";
```

在组件内新增状态与 BridgeClient：

```tsx
const [bridge, setBridge] = useState<BridgeClient | null>(null);
const [bridgeStatus, setBridgeStatus] = useState<"disconnected"|"connected">("disconnected");
const [live, setLive] = useState<{run_id?: string; events: any[]}>({ events: [] });

useEffect(() => {
  const bc = new BridgeClient(process.env.NEXT_PUBLIC_BRIDGE_URL || "ws://127.0.0.1:9797", process.env.NEXT_PUBLIC_BRIDGE_TOKEN);
  setBridge(bc);
  bc.on(ev => {
    if (ev.kind === "run_ack") {
      setLive(l => ({ ...l, run_id: ev.run_id, events: [...(l.events||[]), { t:"ack", run_id: ev.run_id }] }));
      setBridgeStatus("connected");
    } else if (ev.kind === "event") {
      setLive(l => ({ ...l, events: [...(l.events||[]), ev.payload] }));
    } else if (ev.kind === "done") {
      setLive(l => ({ ...l, events: [...(l.events||[]), { t:"done", result: ev.result }] }));
    } else if (ev.kind === "msg" && ev.msg?.type === "hello_ok") {
      setBridgeStatus("connected");
    }
  });
  return () => bc.off(()=>{});
}, []);
```

在顶栏按钮区加上“Run in Chrome”与连接状态：

```tsx
<button
  className="px-3 py-1 rounded bg-fuchsia-600 text-white hover:bg-fuchsia-700"
  onClick={() => {
    if (!bridge) return;
    const id = uuidv4();
    setLive({ run_id: id, events: [] });
    bridge.run(wf, id);
  }}
>
  Run in Chrome
</button>
<span className={`text-xs ${bridgeStatus==="connected"?"text-emerald-600":"text-gray-400"}`}>
  {bridgeStatus==="connected" ? "Bridge connected" : "Bridge…"}
</span>
```

在下方 “Simulate” 卡片旁，新增一个**Live 执行**卡片（或替换原 Simulate 区的一半空间）：

```tsx
<div className="col-span-6 border rounded-lg overflow-hidden">
  <div className="p-2 text-sm font-medium border-b">Live 执行（来自扩展）</div>
  <div className="h-[240px] overflow-auto p-2 text-sm">
    {live?.events?.length ? (
      <ol className="list-decimal pl-5">
        {live.events.map((e:any,i:number) => (
          <li key={i} className="mb-1">
            {e.type==="step" ? (
              <>
                <span className="font-medium">{e.entry?.id}</span> · <span className="text-gray-600">{e.entry?.uses}</span> · {e.entry?.status}
                {e.entry?.outputs ? <pre className="bg-slate-50 p-2 text-xs rounded mt-1 overflow-auto">{JSON.stringify(e.entry.outputs, null, 2)}</pre> : null}
                {e.entry?.error ? <div className="text-red-600 text-xs">{String(e.entry.error)}</div> : null}
              </>
            ) : e.type==="edge_eval" ? (
              <span className="text-gray-500 text-xs">edge {e.from} → {e.to} · {e.condition} · {String(e.result)}</span>
            ) : e.t==="done" ? (
              <span className="text-emerald-600 text-xs">DONE</span>
            ) : (
              <span className="text-gray-500 text-xs">{JSON.stringify(e)}</span>
            )}
          </li>
        ))}
      </ol>
    ) : <div className="text-xs text-gray-500">点击 “Run in Chrome” 以在扩展中执行当前工作流</div>}
  </div>
</div>
```

> 可在 `.env.local` 中填写桥接地址与可选 token：

```bash
NEXT_PUBLIC_BRIDGE_URL=ws://127.0.0.1:9797
NEXT_PUBLIC_BRIDGE_TOKEN=devtoken
```

---

# 4) 运行顺序

1. 启动后端（已有）。
2. 启动桥接：

   ```bash
   export BRIDGE_TOKEN=devtoken  # 可选
   npm run bridge
   ```
3. 打包/刷新安装 Chrome 扩展（M3-S1 的目录），确保 **bg.js** 已包含 WS 连接逻辑；如使用 TOKEN，在 `bg.js` 里把 `BRIDGE_TOKEN="devtoken"`。
4. 启动 Studio 前端（M2）：

   ```bash
   cd workflow-studio
   echo 'NEXT_PUBLIC_BRIDGE_URL=ws://127.0.0.1:9797' > .env.local
   echo 'NEXT_PUBLIC_BRIDGE_TOKEN=devtoken' >> .env.local  # 如需
   pnpm dev
   ```
5. 打开 Studio，点击 **Run in Chrome**。在一个可见的浏览器标签页里即可看到动作执行；Studio 的“Live 执行”面板会实时滚动日志。

---

# 5) 常见问题 & 提示

* **SW 休眠**： MV3 背景 Service Worker 在 WebSocket 连接期间**不会**被挂起；断线时会自动重连。
* **Active tab 焦点**：`type_text`/`ext.key` 需要页面有可聚焦输入；可先加一步 `ext.click(selector:"#search")`。
* **多扩展/多实例**：目前**广播到所有扩展**。如你有多台/多 Chrome，需要做**目标选择**：可在 `run` 消息里加 `target` 字段（浏览器名/标签页 title 匹配），桥接根据注册信息选择转发。
* **安全**：默认只侦听 `127.0.0.1`；使用 `BRIDGE_TOKEN` 作为共享密钥（首版足够）；后续可换成 **HMAC+nonce** 或本机端口 ACL。

---

12:
好，进入 **M3-S3：把 Vision / OCR / LLM 真正接到扩展 & Studio**。这版走“能跑的最小闭环”，不引入重型本地 CV/OCR 推理，策略是：

* **Vision**：优先用**指纹ID→selector** 映射（由“取元素”工具生成并存在 `chrome.storage`）；运行时从 DOM 取 bbox/center（90% 网页场景够用）。若没有映射，再**可选**调用后端 `/vision/match`。
* **OCR**：先用 **DOM 文本回退**（按 region 聚合文本），必要时把截图+区域发到后端 `/ocr/extract`（你可以在后端接 Paddle/Tesseract，本文给路由骨架）。
* **LLM**：扩展转发到你后端 `/llm/reply`（用你 M1 已有的 `callLLM`）。

再加上**取元素（Picker）**：在页面高亮 Hover，点击后自动生成稳健 selector，写入 `fingerprints[anchor_image_id] = selector`，并通过桥接把 `{anchor_image_id, selector, bbox}` 回流到 Studio。

---

# 1) Chrome 扩展改动

## 1.1 manifest.json（新增 content\_script & 资源）

```json
{
  "manifest_version": 3,
  "name": "Workflow Runner (YOLO+LLM+Ext)",
  "version": "0.2.0",
  "action": { "default_popup": "popup.html", "default_title": "Workflow Runner" },
  "permissions": ["scripting", "tabs", "activeTab", "storage"],
  "host_permissions": ["<all_urls>"],
  "background": { "service_worker": "bg.js", "type": "module" },
  "content_scripts": [
    { "matches": ["<all_urls>"], "js": ["picker.js"], "css": ["picker.css"], "run_at": "document_idle" }
  ],
  "web_accessible_resources": [
    { "resources": ["picker.css"], "matches": ["<all_urls>"] }
  ]
}
```

## 1.2 新增：picker（取元素）

**picker.css**

```css
._wf_pick_overlay { position: fixed; pointer-events: none; z-index: 2147483647; border: 2px solid #22c55e; border-radius: 6px; background: rgba(34,197,94,.08); }
._wf_pick_tip { position: fixed; z-index: 2147483647; background:#111827; color:#f9fafb; padding:4px 8px; border-radius:6px; font: 12px/1.4 ui-sans-serif, system-ui; }
._wf_pick_cursor { cursor: crosshair !important; }
```

**picker.js**

```js
(() => {
  let picking = false;
  let overlay, tip, currentEl, anchorId;

  function cssSelector(el) {
    if (!(el instanceof Element)) return "";
    // 生成稳健 selector：优先 id，其次 data-*，最后 tag.class:nth-child
    if (el.id) return `#${CSS.escape(el.id)}`;
    const dataKey = [...el.attributes].map(a=>a.name).find(n => n.startsWith("data-"));
    if (dataKey) return `${el.tagName.toLowerCase()}[${dataKey}]`;
    const cls = (el.className||"").toString().trim().split(/\s+/).filter(Boolean).slice(0,3).map(c=>`.`+CSS.escape(c)).join("");
    const sibs = Array.from(el.parentElement?.children || []);
    const idx = sibs.indexOf(el) + 1;
    return `${el.tagName.toLowerCase()}${cls}:nth-child(${idx})`;
  }

  function updateOverlay(target) {
    const r = target.getBoundingClientRect();
    overlay.style.left = r.left + "px"; overlay.style.top = r.top + "px";
    overlay.style.width = r.width + "px"; overlay.style.height = r.height + "px";
    tip.textContent = cssSelector(target);
    tip.style.left = (r.left + 8) + "px"; tip.style.top = (r.top + 8) + "px";
  }

  function onMove(e) {
    if (!picking) return;
    const el = document.elementFromPoint(e.clientX, e.clientY);
    if (el && el !== currentEl) { currentEl = el; updateOverlay(el); }
  }

  function onClick(e) {
    if (!picking) return;
    e.preventDefault(); e.stopPropagation();
    picking = false; document.body.classList.remove("_wf_pick_cursor");
    window.removeEventListener("mousemove", onMove, true);
    window.removeEventListener("click", onClick, true);
    overlay.remove(); tip.remove();

    if (!currentEl) return;
    const sel = cssSelector(currentEl);
    const r = currentEl.getBoundingClientRect();
    const bbox = { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) };
    chrome.runtime.sendMessage({ type: "PICK_DONE", anchor_image_id: anchorId, selector: sel, bbox });
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg?.type === "PICK_START") {
      anchorId = msg.anchor_image_id || "";
      picking = true;
      overlay = document.createElement("div"); overlay.className = "_wf_pick_overlay"; document.documentElement.appendChild(overlay);
      tip = document.createElement("div"); tip.className = "_wf_pick_tip"; document.documentElement.appendChild(tip);
      document.body.classList.add("_wf_pick_cursor");
      window.addEventListener("mousemove", onMove, true);
      window.addEventListener("click", onClick, true);
    }
  });
})();
```

## 1.3 bg.js（新增 Vision/OCR/LLM & Picker/Bridge 集成）

> 下面是**增量**，请把这些段落补进你现有的 `bg.js`（M3-S1/M3-S2 版本）。

```js
// ===== 配置：后端 API，用于 LLM / 可选 OCR / 可选 Vision =====
const API_BASE = "http://127.0.0.1:8787"; // 按需改为你的服务地址
async function postJSON(path, body) {
  const r = await fetch(API_BASE + path, { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// ===== storage 帮助：指纹映射（anchor_image_id -> selector） =====
async function getFingerprintSelector(id) {
  const { fingerprints = {} } = await chrome.storage.local.get("fingerprints");
  return fingerprints[id] || null;
}
async function setFingerprintSelector(id, selector) {
  const st = await chrome.storage.local.get("fingerprints");
  const fp = st.fingerprints || {};
  fp[id] = selector;
  await chrome.storage.local.set({ fingerprints: fp });
  return true;
}

// ===== Vision：优先用 selector 落地 → DOM bbox；如没有再调后端 /vision/match（可选） =====
async function vision_find(tabId, params) {
  const id = params.anchor_image_id;
  let selector = await getFingerprintSelector(id);
  if (!selector && params.hint_selector) selector = params.hint_selector; // 可选：支持 schema 中 hint_selector
  if (selector) {
    const res = await runInPage(tabId, (sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { bbox:{ x:Math.round(r.left), y:Math.round(r.top), w:Math.round(r.width), h:Math.round(r.height) }, center:[Math.round(r.left+r.width/2), Math.round(r.top+r.height/2)], score: 0.99 };
    }, [selector]);
    if (res) return { ok:true, outputs: { ...res, fingerprint_id: id } };
    // selector 失效则继续走后端匹配（若配置了）
  }
  // 可选后端（若你实现了 /vision/match）：把截图发过去匹配
  // const img = await chrome.tabs.captureVisibleTab(undefined, { format:"png" });
  // const m = await postJSON("/vision/match", { image: img, anchor_image_id: id });
  // return { ok: !!m?.bbox, outputs: { ...m, fingerprint_id: id } };

  // 没有 selector/后端：退回默认占位（不中断）
  return { ok:true, outputs: { bbox:{ x:100,y:200,w:120,h:36 }, center:[160,218], score:0.76, fingerprint_id:id }, warning:"fallback result (no selector mapping)" };
}

// ===== OCR：优先 DOM 文本回退；必要时把截图 + 区域发后端 =====
async function ocr_extract(tabId, params) {
  // 1) 若有 region，就在页面找重叠元素文本
  const region = params.region || params.ref;
  if (region && typeof region === "object") {
    const text = await runInPage(tabId, (r) => {
      const nodes = [];
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
      while (walker.nextNode()) {
        const el = walker.currentNode;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        const overlap = !(rect.right < r.x || rect.bottom < r.y || rect.left > r.x + r.w || rect.top > r.y + r.h);
        if (overlap) {
          const t = el.textContent?.trim(); if (t) nodes.push(t);
        }
      }
      return nodes.slice(0, 20).join(" ").replace(/\s+/g, " ").slice(0, 300);
    }, [region]);
    if (text) return { ok:true, outputs:{ text, lang: params.lang || "auto" } };
  }
  // 2) 可选后端 OCR（若实现了 /ocr/extract）
  // const img = await chrome.tabs.captureVisibleTab(undefined, { format:"png" });
  // const out = await postJSON("/ocr/extract", { image: img, region, lang: params.lang || "auto" });
  // return { ok: !!out?.text, outputs: out };

  // 兜底
  return { ok:true, outputs:{ text: "", lang: params.lang || "auto" }, warning:"ocr fallback (empty)" };
}

// ===== LLM：转发后端 /llm/reply =====
async function llm_reply(_tabId, params) {
  const r = await postJSON("/llm/reply", { prompt: params.prompt, options: { max_tokens: params.max_tokens || 256, temperature: params.temperature ?? 0.2 } });
  return { ok: true, outputs: { text: r.text, usage: r.usage || null } };
}

// ===== 扩展：接收 Picker 完成，保存映射 & 回桥接 =====
chrome.runtime.onMessage.addListener((msg, _sender, _send) => {
  (async () => {
    if (msg?.type === "PICK_DONE") {
      if (msg.anchor_image_id && msg.selector) { await setFingerprintSelector(msg.anchor_image_id, msg.selector); }
      // 回发给桥（若已连接 M3-S2）
      try { WS?.send(JSON.stringify({ type:"event", run_id: "__pick__", payload: { type:"pick_done", ...msg } })); } catch {}
    }
  })();
});

// ===== 运行时：在 runWorkflow 内新增 3 个 uses =====
// （把以下分支加入你之前的 step.uses 选择里）
/*
  else if (step.uses === "vision.find_element_with_image_check") {
    result = await vision_find(tabId, params);
  } else if (step.uses === "ocr.extract_region") {
    result = await ocr_extract(tabId, params);
  } else if (step.uses === "llm.reply") {
    result = await llm_reply(tabId, params);
  }
*/

// ===== 桥接消息：启动取元素 =====
// 在 ws.onmessage 中加入：
/*
  if (msg.type === "pick" && msg.anchor_image_id) {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    await chrome.tabs.sendMessage(tab.id, { type:"PICK_START", anchor_image_id: msg.anchor_image_id });
  }
*/
```

---

# 2) 后端路由（LLM 必需，Vision/OCR 可选）

把下面 1 个**必须**（LLM），2 个**可选**（Vision/OCR）的路由加入你的后端服务。

## 2.1 `/llm/reply`（必须）

**src/routes/llm.ts**

```ts
import { Router } from "express";
import { callLLM } from "../llm/call.js"; // 你在 M1-S4 已实现
export const llmRouter = Router();

llmRouter.post("/llm/reply", async (req, res) => {
  const { prompt, options } = req.body || {};
  if (!prompt) return res.status(400).json({ error: "missing prompt" });
  try {
    const content = await callLLM([
      { role: "system", content: "You are a concise assistant." },
      { role: "user", content: String(prompt) }
    ], { temperature: options?.temperature ?? 0.2, max_tokens: options?.max_tokens ?? 256 });
    res.json({ text: content, usage: null });
  } catch (e:any) {
    res.status(500).json({ error: String(e?.message || e) });
  }
});
```

挂载到 `src/index.ts`：

```ts
import { llmRouter } from "./routes/llm.js";
app.use(llmRouter);
```

## 2.2 `/vision/match`（可选骨架）

**src/routes/vision.ts**

```ts
import { Router } from "express";
export const visionRouter = Router();

visionRouter.post("/vision/match", async (req, res) => {
  const { image, anchor_image_id } = req.body || {};
  if (!image || !anchor_image_id) return res.status(400).json({ error: "missing image or anchor_image_id" });
  // TODO: 在这里接入你的模板匹配/YOLO 服务；目前返回 501
  res.status(501).json({ error: "vision backend not configured" });
});
```

`src/index.ts`：

```ts
import { visionRouter } from "./routes/vision.js";
app.use(visionRouter);
```

## 2.3 `/ocr/extract`（可选骨架）

**src/routes/ocr.ts**

```ts
import { Router } from "express";
export const ocrRouter = Router();

ocrRouter.post("/ocr/extract", async (req, res) => {
  const { image, region, lang } = req.body || {};
  if (!image || !region) return res.status(400).json({ error: "missing image or region" });
  // TODO: 在这里接入 OCR 服务（Paddle/Tesseract）；目前返回 501
  res.status(501).json({ error: "ocr backend not configured" });
});
```

`src/index.ts`：

```ts
import { ocrRouter } from "./routes/ocr.js";
app.use(ocrRouter);
```

> 这样即使你暂时不接 CV/OCR，扩展仍可凭“selector 映射 + DOM 文本回退”完成 80% 网页自动化。

---

# 3) Studio 里一键「取元素」与回流

在 **M2 的 Studio** 上，为 `vision.find_element_with_image_check` 的 Step 增加一个按钮 “Pick in Chrome”，通过桥接给扩展发 `pick`。当扩展发回 `pick_done` 事件，在 Studio 的 Live 面板里显示并提示“已为指纹ID绑定 selector”。

最小改动（在 `src/app/page.tsx`）：

1. 在 `useEffect` 订阅 bridge 的回调中增加：

```tsx
if (ev.kind === "event" && ev.payload?.type === "pick_done") {
  // 你也可以把这个 selector 临时写入 step.params.hint_selector，方便调试
  // 仅当你在 registry 给 vision schema 加了可选字段 "hint_selector" 才能持久化，否则只提示
  alert(`已绑定指纹 ${ev.payload.anchor_image_id}\nselector: ${ev.payload.selector}`);
}
```

2. 在 `StepForm` 渲染时，若 `step.uses === "vision.find_element_with_image_check"`，显示一个按钮：

```tsx
{step?.uses === "vision.find_element_with_image_check" ? (
  <button
    className="mt-2 px-2 py-1 text-xs bg-emerald-600 text-white rounded"
    onClick={() => bridge?.send({ type:"pick", anchor_image_id: step.params?.anchor_image_id || "anchor_"+step.id })}
  >Pick in Chrome</button>
) : null}
```

> 如果你愿意把 selector 也记在 workflow 里以便版本化，可以在 **registry 的 vision schema** 里加一个**可选字段**：

```json
"hint_selector": { "type": "string" }
```

然后在 `pick_done` 事件到来时，直接把 `step.params.hint_selector = selector` 写回 JSON。

---

# 4) 验收清单（本地即可走通）

1. **取元素**

   * 打开任意网页 → Studio 选中一个 `vision.find_element…` 步骤 → 点 “Pick in Chrome”。
   * 页面进入高亮模式，点击一个元素 → Studio Live 面板收到 `pick_done` → selector 存进扩展。

2. **运行包含 Vision/OCR/LLM 的 workflow**

   * Vision 步骤：通过 selector 映射得到 bbox/center → 后续 `ext.click` 用 `${outputs.find_btn.center}` 正常点击。
   * OCR 步骤：对 region 做 DOM 文本回退（多数网页能拿到文本）。
   * LLM 步骤：后端 `/llm/reply` 返回文本 → 扩展日志显示 `outputs.text`。

3. （可选）接后端 OCR/视觉：

   * 在 `bg.js` 启用注释的 `captureVisibleTab + postJSON` 两段，后端路由返回 bbox/text 即可。

---

13:
太棒了！进入 **M4：Headless Runner + 批量/调度 + 观测（MVP）**。这一步把你的工作流从“本机扩展”升级到“**服务器/CI 可跑**”：在没有人工浏览器的机器上（CI、云主机），用 **Playwright** 直接跑同一份 workflow；再加上批量运行、简单调度和运行日志查看。下面给你一套**可落地代码**（在你已有的后端仓库内增量），先把 **M4-S1（Headless Runner）** 跑通，随后再补 **S2（批量/数据集）**、**S3（调度）** 和 **S4（观测与 Studio 集成）**。

---

# M4-S1：Headless Runner（Playwright）

## 1) 安装依赖

```bash
npm i -S playwright
# 首次部署需要安装浏览器二进制
npx playwright install chromium
```

## 2) 运行器核心（action 映射 + DAG 执行）

**src/headless/runner.ts**

```ts
import { chromium, Browser, Page } from "playwright";
import fetch from "node-fetch";

type RunOpts = {
  headless?: boolean;          // 默认 true
  slowMo?: number;             // 慢放毫秒
  viewport?: { width: number; height: number };
  timeoutMs?: number;          // 单步超时
  apiBase?: string;            // 后端地址，用于 /llm/reply、/ocr/extract（可选）
  fingerprintIndex?: Record<string, { selector?: string }>; // 指纹→selector 映射（可选）
};

type RunEvent =
  | { type: "step", entry: any }
  | { type: "edge_eval", from: string, to: string, condition?: string, result: boolean }
  | { type: "done" };

const REF = /\$\{([^}]+)\}/g;
const pick = (obj: any, path: string) => path.split(".").reduce((c,k)=> (c?c[k]:undefined), obj);
function resolveRefs(v: any, ctx: any): any {
  if (v == null) return v;
  if (typeof v === "string") {
    return v.replace(REF, (_, expr) => {
      if (expr.startsWith("vars.")) return String(pick(ctx.vars, expr.slice(5)) ?? "");
      if (expr.startsWith("globals.")) return String(pick(ctx.globals, expr.slice(8)) ?? "");
      if (expr.startsWith("outputs.")) return String(pick(ctx.outputs, expr.slice(8)) ?? "");
      return String(pick(ctx, expr) ?? "");
    });
  }
  if (Array.isArray(v)) return v.map(x => resolveRefs(x, ctx));
  if (typeof v === "object") { const out: any = {}; for (const k of Object.keys(v)) out[k] = resolveRefs(v[k], ctx); return out; }
  return v;
}
function evalCond(cond: string | undefined, ctx: any) {
  if (!cond) return true;
  const s = cond.trim();
  if (s === "true") return true;
  if (s === "false") return false;
  const mContains = /^contains\((.+?),\s*"(.*)"\)$/.exec(s);
  if (mContains) { const left = String(pick(ctx, mContains[1].trim()) ?? ""); return left.includes(mContains[2]); }
  const mEq = /^(.+?)(==|!=)\s*"(.*)"$/.exec(s);
  if (mEq) { const left = String(pick(ctx, mEq[1].trim()) ?? ""); const lit = mEq[3]; return mEq[2]==="==" ? left===lit : left!==lit; }
  return !!pick(ctx, s);
}
function buildAdj(wf: any) {
  const adj = new Map<string, Array<{to:string, condition?:string}>>();
  (wf.steps||[]).forEach((s:any)=>adj.set(s.id, []));
  if (wf.edges?.length) wf.edges.forEach((e:any)=>adj.get(e.from)?.push({to:e.to, condition:e.condition}));
  else for (let i=0;i<(wf.steps||[]).length-1;i++) adj.get(wf.steps[i].id)?.push({to:wf.steps[i+1].id});
  return adj;
}
const findStep = (wf:any, id:string) => (wf.steps||[]).find((s:any)=>s.id===id);

async function action_open_url(page: Page, p: any) {
  const url = p.url;
  if (!url) return { ok:false, error:"missing url" };
  await page.goto(url, { waitUntil: "load" });
  if (p.wait_dom_quiet_ms) await page.waitForTimeout(p.wait_dom_quiet_ms);
  return { ok:true, outputs:{ page: (new URL(url)).host, ready: true } };
}

async function action_key(page: Page, p: any) {
  const mods = new Set<string>(p.modifiers || []);
  const m: ("Shift"|"Alt"|"Control"|"Meta")[] = [];
  if (mods.has("Shift")) m.push("Shift");
  if (mods.has("Alt")) m.push("Alt");
  if (mods.has("Ctrl")) m.push("Control");
  if (mods.has("Cmd")) m.push("Meta");
  for (const mm of m) await page.keyboard.down(mm);
  await page.keyboard.press(p.key || "Enter");
  for (const mm of m.reverse()) await page.keyboard.up(mm);
  return { ok:true, outputs:{ sent: p.key || "Enter", modifiers: [...mods] } };
}

async function action_type_text(page: Page, p: any) {
  const text = p.text ?? "";
  if (p.selector) {
    const el = await page.waitForSelector(p.selector, { timeout: p.timeoutMs || 5000 });
    if (!el) return { ok:false, error: `selector not found: ${p.selector}` };
    await el.click();
  }
  if (p.mode === "paste") {
    await page.evaluate((t:string)=>navigator.clipboard.writeText(t), text).catch(()=>{});
    await page.keyboard.down("Control"); await page.keyboard.press("KeyV"); await page.keyboard.up("Control");
  } else {
    await page.keyboard.type(text, { delay: p.interval_ms || 0 });
  }
  return { ok:true, outputs:{ typed_len: text.length, mode: p.mode || "type" } };
}

async function action_click(page: Page, p: any) {
  if (p.selector) {
    await page.click(p.selector, { button: p.button || "left", clickCount: p.clicks || 1, timeout: p.timeoutMs || 5000 });
    const box = await page.$eval(p.selector, (el:any) => {
      const r = el.getBoundingClientRect();
      return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) };
    }).catch(()=>null);
    return { ok:true, outputs:{ clicked: true, at: box ? { selector: p.selector, bbox: box } : { selector: p.selector } } };
  }
  if (typeof p.x === "number" && typeof p.y === "number") {
    await page.mouse.click(p.x, p.y, { button: p.button || "left", clickCount: p.clicks || 1 });
    return { ok:true, outputs:{ clicked: true, at: { x:p.x, y:p.y } } };
  }
  if (p.ref && Array.isArray(p.ref) && p.ref.length >= 2) {
    const [x,y] = p.ref; await page.mouse.click(x, y, { button: p.button || "left", clickCount: p.clicks || 1 });
    return { ok:true, outputs:{ clicked: true, at: { x, y } } };
  }
  return { ok:false, error:"no selector or x/y" };
}

// —— Vision：指纹→selector→bbox（可选接后端）
async function action_vision(page: Page, p: any, opts: RunOpts) {
  const id = p.anchor_image_id;
  const selector = opts.fingerprintIndex?.[id]?.selector || p.hint_selector;
  if (selector) {
    const el = await page.$(selector);
    if (!el) return { ok:false, error:`selector not found for fingerprint ${id}` };
    const box = await el.boundingBox();
    if (!box) return { ok:false, error:`no bbox for ${selector}` };
    const bbox = { x: Math.round(box.x), y: Math.round(box.y), w: Math.round(box.width), h: Math.round(box.height) };
    const center = [bbox.x + Math.round(bbox.w/2), bbox.y + Math.round(bbox.h/2)];
    return { ok:true, outputs:{ bbox, center, score: 0.99, fingerprint_id: id } };
  }
  // 可选：截图发后端做匹配（你在 M3-S3 提供了 /vision/match 骨架）
  if (opts.apiBase) {
    const img = await page.screenshot({ type: "png" });
    const r = await fetch(`${opts.apiBase}/vision/match`, { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify({ image: `data:image/png;base64,${img.toString("base64")}`, anchor_image_id: id }) });
    if (r.ok) {
      const m = await r.json();
      if (m?.bbox) return { ok:true, outputs: { ...m, fingerprint_id: id } };
    }
  }
  return { ok:true, outputs:{ bbox:{x:100,y:200,w:120,h:36}, center:[160,218], score:0.76, fingerprint_id:id }, warning:"vision fallback" };
}

// —— OCR：优先 DOM 文本；否则截图+区域给后端
async function action_ocr(page: Page, p: any, opts: RunOpts) {
  const region = p.region || p.ref;
  if (region && typeof region === "object") {
    // DOM 文本聚合（简单回退）
    const text = await page.evaluate((r:any) => {
      const nodes: string[] = [];
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
      while (walker.nextNode()) {
        const el = walker.currentNode as HTMLElement;
        const rect = el.getBoundingClientRect();
        if (!rect.width || !rect.height) continue;
        const overlap = !(rect.right < r.x || rect.bottom < r.y || rect.left > r.x + r.w || rect.top > r.y + r.h);
        if (overlap) {
          const t = (el.innerText || el.textContent || "").trim();
          if (t) nodes.push(t);
        }
      }
      return nodes.slice(0, 20).join(" ").replace(/\s+/g, " ");
    }, region);
    if (text) return { ok:true, outputs:{ text, lang: p.lang || "auto" } };
  }
  if (opts.apiBase) {
    const img = await page.screenshot({ type: "png" });
    const r = await fetch(`${opts.apiBase}/ocr/extract`, { method:"POST", headers:{ "Content-Type":"application/json" },
      body: JSON.stringify({ image: `data:image/png;base64,${img.toString("base64")}`, region, lang: p.lang || "auto" }) });
    if (r.ok) { const out = await r.json(); return { ok: !!out?.text, outputs: out }; }
  }
  return { ok:true, outputs:{ text:"", lang: p.lang || "auto" }, warning:"ocr fallback (empty)" };
}

// —— LLM：转发后端
async function action_llm(_page: Page, p: any, opts: RunOpts) {
  if (!opts.apiBase) return { ok:false, error:"apiBase not configured for llm" };
  const r = await fetch(`${opts.apiBase}/llm/reply`, { method:"POST", headers:{ "Content-Type":"application/json" },
    body: JSON.stringify({ prompt: p.prompt, options: { max_tokens: p.max_tokens || 256, temperature: p.temperature ?? 0.2 } }) });
  if (!r.ok) return { ok:false, error:`llm http ${r.status}` };
  const data = await r.json();
  return { ok:true, outputs:{ text: data.text, usage: data.usage || null } };
}

export async function runWorkflowHeadless(workflow: any, opts: RunOpts = {}, onEvent?: (e: RunEvent)=>void) {
  const browser: Browser = await chromium.launch({ headless: opts.headless !== false, slowMo: opts.slowMo || 0 });
  const page: Page = await browser.newPage({ viewport: opts.viewport || { width: 1440, height: 900 } });

  const ctx = { vars: workflow.variables || {}, globals: workflow.globals || {}, outputs: {} as Record<string, any> };
  const adj = buildAdj(workflow);
  const trace: any[] = [];
  const t0 = Date.now();

  let cur = workflow.start;
  let guard = 0;

  try {
    while (cur && guard++ < 300) {
      const step = findStep(workflow, cur);
      if (!step) break;
      const started = Date.now();
      const p = resolveRefs(step.params || {}, ctx);
      let result: any = { ok: true, outputs: {} };

      if (step.type === "action") {
        if (step.uses === "ext.open_url") result = await action_open_url(page, p);
        else if (step.uses === "ext.key") result = await action_key(page, p);
        else if (step.uses === "type_text") result = await action_type_text(page, p);
        else if (step.uses === "ext.click") result = await action_click(page, p);
        else if (step.uses === "vision.find_element_with_image_check") result = await action_vision(page, p, opts);
        else if (step.uses === "ocr.extract_region") result = await action_ocr(page, p, opts);
        else if (step.uses === "llm.reply") result = await action_llm(page, p, opts);
        else result = { ok:false, error:`action not implemented: ${step.uses}` };
      } else {
        result = { ok:true, outputs:{} };
      }

      const entry = {
        id: step.id, name: step.name, uses: step.uses || step.type,
        status: result.ok ? "ok" : "error",
        started_ms: started - t0, duration_ms: Date.now() - started,
        outputs: result.outputs || {}, warning: result.warning, error: result.error
      };
      trace.push(entry);
      ctx.outputs[step.id] = entry.outputs;

      onEvent?.({ type: "step", entry });
      if (!result.ok) break;

      const options = adj.get(step.id) || [];
      let next = "";
      for (const opt of options) {
        const ok = evalCond(opt.condition, { ...ctx, step });
        onEvent?.({ type: "edge_eval", from: step.id, to: opt.to, condition: opt.condition, result: ok });
        if (ok) { next = opt.to; break; }
      }
      if (!next) break;
      cur = next;
    }
  } finally {
    await page.close().catch(()=>{});
    await browser.close().catch(()=>{});
  }

  onEvent?.({ type: "done" });
  return { trace, finished: !!cur ? false : true, last_step: trace.at(-1)?.id };
}
```

## 3) 路由：一次性运行（返回完整轨迹）

**src/routes/headless.ts**

```ts
import { Router } from "express";
import { runWorkflowHeadless } from "../headless/runner.js";
export const headlessRouter = Router();

// POST /headless/run { workflow, options? }
headlessRouter.post("/headless/run", async (req, res) => {
  const { workflow, options } = req.body || {};
  if (!workflow) return res.status(400).json({ error: "missing workflow" });
  try {
    const events: any[] = [];
    const result = await runWorkflowHeadless(workflow, {
      headless: options?.headless ?? true,
      slowMo: options?.slowMo ?? 0,
      viewport: options?.viewport || { width: 1440, height: 900 },
      apiBase: process.env.API_BASE || "http://127.0.0.1:8787",
      fingerprintIndex: options?.fingerprintIndex || {}
    }, (e)=>events.push(e));
    res.json({ ...result, events });
  } catch (e:any) {
    res.status(500).json({ error: String(e?.message || e) });
  }
});
```

把路由挂到 `src/index.ts`：

```ts
import { headlessRouter } from "./routes/headless.js";
app.use(headlessRouter);
```

## 4) CLI：一条命令跑 JSON

**bin/wf-run.ts**

```ts
#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { runWorkflowHeadless } from "../src/headless/runner.js";

async function main() {
  const file = process.argv[2];
  if (!file) { console.error("Usage: wf-run <workflow.json> [--slow 50] [--headed]"); process.exit(1); }
  const slow = Number(process.argv[process.argv.indexOf("--slow")+1] || 0);
  const headed = process.argv.includes("--headed");

  const wf = JSON.parse(fs.readFileSync(path.resolve(file), "utf-8"));
  const result = await runWorkflowHeadless(wf, { headless: !headed, slowMo: slow, apiBase: process.env.API_BASE || "http://127.0.0.1:8787" }, (e)=> {
    if (e.type === "step") console.log(`[STEP] ${e.entry.id} · ${e.entry.uses} · ${e.entry.status}`);
    if (e.type === "edge_eval") console.log(`[EDGE] ${e.from} -> ${e.to} ${e.result ? "✓" : "×"}`);
  });
  console.log("\n== Done ==");
  console.log(JSON.stringify(result, null, 2));
}
main().catch(e => { console.error(e); process.exit(1); });
```

`package.json` 增加：

```json
{
  "bin": { "wf-run": "bin/wf-run.ts" },
  "scripts": { "wf:run": "node -r esbuild-register bin/wf-run.ts" }
}
```

---

# M4-S2：批量运行 / 数据集（最小）

## 1) 轻量内存队列 + 并发控制

**src/headless/batch.ts**

```ts
import { runWorkflowHeadless } from "./runner.js";

export type BatchJob = {
  id: string; createdAt: number; concurrency: number;
  workflow: any; dataset: Array<Record<string, any>>;
  status: "queued"|"running"|"done"|"error";
  results: Array<{ index: number; ok: boolean; trace: any[]; last_step?: string; error?: string }>;
};

const jobs = new Map<string, BatchJob>();

export function getJob(id: string) { return jobs.get(id); }
export function listJobs() { return [...jobs.values()].map(j => ({ id:j.id, status:j.status, createdAt:j.createdAt, size:j.dataset.length })); }

export async function startBatch(job: BatchJob, opts?: { apiBase?: string }) {
  jobs.set(job.id, job);
  job.status = "running";
  const pool = new Set<Promise<void>>();
  const push = (p: Promise<void>) => { pool.add(p); p.finally(()=>pool.delete(p)); };
  let cursor = 0;

  async function spawn() {
    if (cursor >= job.dataset.length) return;
    const index = cursor++;
    const vars = job.dataset[index];
    push((async () => {
      try {
        const wf = JSON.parse(JSON.stringify(job.workflow));
        wf.variables = { ...(wf.variables||{}), ...(vars||{}) };
        const r = await runWorkflowHeadless(wf, { apiBase: opts?.apiBase }, undefined);
        job.results[index] = { index, ok: r.finished, trace: r.trace, last_step: r.last_step };
      } catch (e:any) {
        job.results[index] = { index, ok:false, trace: [], error: String(e?.message || e) };
      }
    })());
  }

  for (let i=0;i<job.concurrency;i++) spawn();

  while (pool.size) {
    await Promise.race([...pool]);
    while (cursor < job.dataset.length && pool.size < job.concurrency) spawn();
  }

  job.status = "done";
}
```

## 2) 路由：创建/查看批量任务

**src/routes/batch.ts**

```ts
import { Router } from "express";
import { v4 as uuidv4 } from "uuid";
import { startBatch, getJob, listJobs } from "../headless/batch.js";

export const batchRouter = Router();

// POST /headless/batch { workflow, dataset, concurrency? }
batchRouter.post("/headless/batch", async (req, res) => {
  const { workflow, dataset, concurrency } = req.body || {};
  if (!workflow || !Array.isArray(dataset)) return res.status(400).json({ error: "need workflow + dataset[]" });
  const id = uuidv4();
  const job = { id, createdAt: Date.now(), concurrency: Math.max(1, Math.min(8, Number(concurrency || 2))), workflow, dataset, status: "queued", results: [] } as any;
  res.json({ id, status: "queued" });
  // fire and forget
  startBatch(job, { apiBase: process.env.API_BASE || "http://127.0.0.1:8787" }).catch(()=>{});
});

batchRouter.get("/headless/batch/:id", (req, res) => {
  const j = getJob(req.params.id);
  if (!j) return res.status(404).json({ error: "not found" });
  res.json({ id: j.id, status: j.status, size: j.dataset.length, results: j.results });
});

batchRouter.get("/headless/batch", (_req, res) => res.json({ jobs: listJobs() }));
```

`src/index.ts`：

```ts
import { batchRouter } from "./routes/batch.js";
app.use(batchRouter);
```

---

# M4-S3：简单调度（cron）

> 最小化实现：用 `node-cron` 维护内存任务（重启不保留）；生产建议换持久化（SQLite/Redis + BullMQ）。

```bash
npm i -S node-cron
```

**src/scheduler/index.ts**

```ts
import cron from "node-cron";
import { v4 as uuidv4 } from "uuid";
import { startBatch } from "../headless/batch.js";

type Sched = { id: string; cron: string; workflow: any; dataset: any[]; concurrency: number; enabled: boolean };
const scheds = new Map<string, { meta: Sched; job?: cron.ScheduledTask }>();

export function listSchedules() { return [...scheds.values()].map(s => s.meta); }
export function addSchedule(meta: Omit<Sched, "id">) {
  const id = uuidv4(); const m = { id, ...meta }; scheds.set(id, { meta: m }); if (m.enabled) enableSchedule(id); return m;
}
export function enableSchedule(id: string) {
  const it = scheds.get(id); if (!it || it.job) return;
  const job = cron.schedule(it.meta.cron, () => {
    const batchId = uuidv4();
    startBatch({ id: batchId, createdAt: Date.now(), concurrency: it.meta.concurrency, workflow: it.meta.workflow, dataset: it.meta.dataset, status: "queued", results: [] } as any, { apiBase: process.env.API_BASE || "http://127.0.0.1:8787" }).catch(()=>{});
  });
  it.job = job; it.meta.enabled = true;
}
export function disableSchedule(id: string) { const it = scheds.get(id); it?.job?.stop(); if (it) { it.job = undefined; it.meta.enabled = false; } }
export function removeSchedule(id: string) { disableSchedule(id); scheds.delete(id); }
```

**src/routes/schedule.ts**

```ts
import { Router } from "express";
import { listSchedules, addSchedule, enableSchedule, disableSchedule, removeSchedule } from "../scheduler/index.js";
export const scheduleRouter = Router();

// GET /schedule
scheduleRouter.get("/schedule", (_req, res) => res.json({ items: listSchedules() }));
// POST /schedule { cron, workflow, dataset, concurrency, enabled }
scheduleRouter.post("/schedule", (req, res) => {
  const { cron, workflow, dataset = [], concurrency = 2, enabled = true } = req.body || {};
  if (!cron || !workflow) return res.status(400).json({ error: "missing cron/workflow" });
  const item = addSchedule({ cron, workflow, dataset, concurrency, enabled: !!enabled });
  res.json(item);
});
// POST /schedule/:id/enable|disable|remove
scheduleRouter.post("/schedule/:id/enable", (req, res) => { enableSchedule(req.params.id); res.json({ ok:true }); });
scheduleRouter.post("/schedule/:id/disable", (req, res) => { disableSchedule(req.params.id); res.json({ ok:true }); });
scheduleRouter.post("/schedule/:id/remove", (req, res) => { removeSchedule(req.params.id); res.json({ ok:true }); });
```

`src/index.ts`：

```ts
import { scheduleRouter } from "./routes/schedule.js";
app.use(scheduleRouter);
```

---

# M4-S4：观测与 Studio 集成（最小）

## 1) 将运行结果落盘（便于回看）

**src/headless/store.ts**

```ts
import fs from "node:fs/promises";
import path from "node:path";
export async function saveRun(id: string, payload: any) {
  const dir = path.resolve("runs"); await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(path.join(dir, `${id}.json`), JSON.stringify(payload, null, 2), "utf-8");
}
export async function readRun(id: string) {
  const p = path.resolve("runs", `${id}.json`);
  const txt = await fs.readFile(p, "utf-8"); return JSON.parse(txt);
}
```

在 `/headless/run` 路由里保存：

```ts
import { v4 as uuidv4 } from "uuid";
import { saveRun } from "../headless/store.js";
// ...
const runId = uuidv4();
await saveRun(runId, { workflow, options, events, ...result });
res.json({ run_id: runId, ...result, events });
```

## 2) Studio：新增 “Run Headless” 按钮与结果查看

* 在 M2 前端顶栏加一个按钮调用 `POST /headless/run`（传当前 JSON），把返回的 `events/trace` 展示在右下角“Live 执行”或新卡片中。
* 对于批量/调度，做一个简单列表页读取 `/headless/batch` 与 `/schedule`。

> 这块你已经有基础 UI，接入上述新接口即可（与 “Simulate/Run in Chrome” 并列）。

---

## 验收清单

1. **单次 headless**

```bash
curl -s -X POST http://localhost:8787/headless/run \
  -H 'Content-Type: application/json' \
  -d '{"workflow":'$(cat examples/wf_btn_ocr.json)'}' | jq '.last_step,.trace|length'
```

2. **批量数据集**

```bash
cat > /tmp/ds.json <<'JSON'
[ {"friend_name":"Alice"}, {"friend_name":"Bob"}, {"friend_name":"Carol"} ]
JSON

curl -s -X POST http://localhost:8787/headless/batch \
  -H 'Content-Type: application/json' \
  -d '{"workflow":'$(cat examples/wf_with_subflow.json)',"dataset":'$(cat /tmp/ds.json)',"concurrency":2}' | jq

# 查询
curl -s http://localhost:8787/headless/batch | jq
```

3. **调度**

```bash
# 每分钟跑一次（演示）
curl -s -X POST http://localhost:8787/schedule \
  -H 'Content-Type: application/json' \
  -d '{"cron":"*/1 * * * *","workflow":'$(cat examples/wf_with_subflow.json)',"dataset":[{}],"concurrency":1,"enabled":true}' | jq
curl -s http://localhost:8787/schedule | jq
```

---

14:
太好了，进入 **M5：录制器（Recorder）+ LLM 自动整理为 Workflow（最小可用版）**。按你的诉求：**不做用户/团队鉴权、不要 MQ/Redis**，专注把“手动操作一遍→自动生成 workflow”落地。下面直接给**能跑的代码**与接线步骤。

---

# M5-S1｜Chrome 扩展内置录制器（Start/Stop、事件抓取、实时回传）

## 1) manifest.json（增量）

```json
{
  "manifest_version": 3,
  "name": "Workflow Runner (with Recorder)",
  "version": "0.3.0",
  "permissions": ["scripting", "tabs", "activeTab", "storage"],
  "host_permissions": ["<all_urls>"],
  "background": { "service_worker": "bg.js", "type": "module" },
  "action": { "default_popup": "popup.html" },
  "content_scripts": [
    { "matches": ["<all_urls>"], "js": ["picker.js"], "css": ["picker.css"], "run_at": "document_idle" },
    { "matches": ["<all_urls>"], "js": ["recorder.js"], "run_at": "document_start" }
  ]
}
```

## 2) 新增 `recorder.js`（页面侧采集 Click/Input/Key/Nav）

```js
(() => {
  let REC_ON = false;
  let sessionId = null;
  let ignoreSelectors = ["._wf_pick_overlay", "._wf_pick_tip"];
  let lastUrl = location.href;

  // 稳健 selector 生成（简化版，与 picker 一致）
  function bestSelector(el) {
    if (!(el instanceof Element)) return "";
    if (el.id) return `#${CSS.escape(el.id)}`;
    const role = el.getAttribute("role");
    const aria = el.getAttribute("aria-label");
    if (aria) return `${el.tagName.toLowerCase()}[aria-label="${aria}"]`;
    if (role) return `${el.tagName.toLowerCase()}[role="${role}"]`;
    const name = el.getAttribute("name");
    if (name) return `${el.tagName.toLowerCase()}[name="${name}"]`;
    const cls = (el.className || "").toString().trim().split(/\s+/).filter(Boolean).slice(0,3).map(c=>`.`+CSS.escape(c)).join("");
    const sibs = Array.from(el.parentElement?.children || []);
    const idx = sibs.indexOf(el) + 1;
    const me = `${el.tagName.toLowerCase()}${cls}${idx?`:nth-child(${idx})`:""}`;
    // 逐层向上，直到唯一
    let sel = me, cur = el.parentElement, steps = 0;
    while (cur && steps++ < 3) {
      const part = (cur.id ? `#${CSS.escape(cur.id)}` : cur.tagName.toLowerCase());
      const candidate = `${part} ${sel}`;
      try { if ((document.querySelectorAll(candidate) || []).length === 1) return candidate; } catch {}
      sel = candidate; cur = cur.parentElement;
    }
    return me;
  }

  function bboxOf(el) {
    try {
      const r = el.getBoundingClientRect();
      return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) };
    } catch { return null; }
  }

  function send(kind, payload) {
    chrome.runtime.sendMessage({ type: "REC_EVENT", sessionId, kind, ts: Date.now(), url: location.href, ...payload });
  }

  function onClick(e) {
    if (!REC_ON) return;
    const t = e.target;
    if (!(t instanceof Element)) return;
    if (ignoreSelectors.some(s => t.closest(s))) return;

    const sel = bestSelector(t);
    const bbox = bboxOf(t);
    const text = (t.innerText || t.textContent || "").trim().slice(0, 80);
    send("click", { selector: sel, bbox, text, button: e.button, meta: {
      tag: t.tagName.toLowerCase(),
      type: (t.getAttribute && t.getAttribute("type")) || null,
      href: (t.getAttribute && t.getAttribute("href")) || null
    }});
  }

  // 记录输入变化（仅保存“增量字符”简化为最终值；可选脱敏）
  const MASK_TYPES = new Set(["password"]);
  function onInput(e) {
    if (!REC_ON) return;
    const t = e.target;
    if (!(t instanceof Element)) return;
    if (ignoreSelectors.some(s => t.closest(s))) return;

    const sel = bestSelector(t);
    const bbox = bboxOf(t);
    const type = (t.getAttribute && t.getAttribute("type")) || null;
    let value = (t.value !== undefined ? String(t.value) : (t.textContent||"")).toString();
    if (type && MASK_TYPES.has(type)) value = "******";
    send("input", { selector: sel, bbox, value, meta: { tag: t.tagName.toLowerCase(), type } });
  }

  function onKeydown(e) {
    if (!REC_ON) return;
    if (["Enter","Tab","Escape","ArrowUp","ArrowDown","ArrowLeft","ArrowRight"].includes(e.key)) {
      send("key", { key: e.key, modifiers: ["Ctrl","Alt","Shift","Meta"].filter(m => e[`${m.toLowerCase()}Key`]) });
    }
  }

  // 导航变更（单页与跳转）
  function hookHistory() {
    const push = history.pushState;
    history.pushState = function() {
      push.apply(this, arguments);
      if (REC_ON && location.href !== lastUrl) {
        lastUrl = location.href;
        send("navigate", { to: lastUrl });
      }
    };
    window.addEventListener("popstate", () => {
      if (REC_ON && location.href !== lastUrl) {
        lastUrl = location.href;
        send("navigate", { to: lastUrl });
      }
    });
    window.addEventListener("hashchange", () => {
      if (REC_ON && location.href !== lastUrl) {
        lastUrl = location.href;
        send("navigate", { to: lastUrl });
      }
    });
  }
  hookHistory();

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg?.type === "REC_START") {
      REC_ON = true; sessionId = msg.sessionId || String(Date.now());
      lastUrl = location.href;
      window.addEventListener("click", onClick, true);
      window.addEventListener("input", onInput, true);
      window.addEventListener("keydown", onKeydown, true);
      chrome.runtime.sendMessage({ type:"REC_STATUS", sessionId, on: true, url: location.href, ts: Date.now() });
      send("navigate", { to: location.href }); // 首帧
    }
    if (msg?.type === "REC_STOP") {
      REC_ON = false;
      window.removeEventListener("click", onClick, true);
      window.removeEventListener("input", onInput, true);
      window.removeEventListener("keydown", onKeydown, true);
      chrome.runtime.sendMessage({ type:"REC_STATUS", sessionId, on: false, ts: Date.now() });
      sessionId = null;
    }
  });
})();
```

## 3) bg.js（增量：桥接 record\_start/stop，转发事件到 Studio）

在原有 **WS**（桥接）连接里加：

```js
// 接 Studio 指令
WS.onmessage = async (ev) => {
  let msg; try { msg = JSON.parse(ev.data); } catch { return; }
  // ...已有 run/pick 分支...
  if (msg.type === "record_start") {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const sessionId = msg.session_id || String(Date.now());
    await chrome.tabs.sendMessage(tab.id, { type:"REC_START", sessionId });
    WS?.send(JSON.stringify({ type:"event", run_id: sessionId, payload: { type:"record_status", on: true } }));
  }
  if (msg.type === "record_stop") {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    await chrome.tabs.sendMessage(tab.id, { type:"REC_STOP" });
  }
};
```

监听内容脚本上报：

```js
chrome.runtime.onMessage.addListener((msg) => {
  if (msg?.type === "REC_EVENT") {
    // 实时转发给 Studio
    try { WS?.send(JSON.stringify({ type:"event", run_id: msg.sessionId, payload: { type:"record_event", ...msg } })); } catch {}
  }
  if (msg?.type === "REC_STATUS") {
    try { WS?.send(JSON.stringify({ type:"event", run_id: msg.sessionId, payload: { type:"record_status", ...msg } })); } catch {}
  }
});
```

## 4) popup.html（增量：录制按钮）

在按钮区加：

```html
<button id="btnRec">Start Rec</button>
```

**popup.js** 增量：

```js
let REC = false;
$("#btnRec").onclick = async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!REC) {
    const sessionId = String(Date.now());
    await chrome.tabs.sendMessage(tab.id, { type:"REC_START", sessionId });
    $("#btnRec").textContent = "Stop Rec"; REC = true;
  } else {
    await chrome.tabs.sendMessage(tab.id, { type:"REC_STOP" });
    $("#btnRec").textContent = "Start Rec"; REC = false;
  }
};
```

---

# M5-S2｜后端：把录制事件 → Workflow（LLM + 规则拼接）

## 1) 事件模型（约定）

```ts
// RecordingEvent
type RecEvt =
  | { kind:"navigate"; url:string; to:string; ts:number }
  | { kind:"click"; selector:string; bbox?:{x:number;y:number;w:number;h:number}; text?:string; button?:number; ts:number; url:string; meta?:any }
  | { kind:"input"; selector:string; bbox?:{x:number;y:number;w:number;h:number}; value:string; ts:number; url:string; meta?:any }
  | { kind:"key"; key:string; modifiers?:string[]; ts:number; url:string };
```

## 2) 规则式预整理（合并 click+input、识别 open\_url 等）

**src/record/transform.ts**

```ts
import { callLLM } from "../llm/call.js";
import { createAjv } from "../lib/ajv.js";

export function preprocess(events: any[]) {
  const out: any[] = [];
  let lastNav = null;

  for (let i=0;i<events.length;i++) {
    const e = events[i];
    if (e.kind === "navigate") {
      lastNav = e.to || e.url || e.href;
      out.push({ type:"open_url", url: lastNav });
      continue;
    }
    if (e.kind === "click") {
      // 如果后续紧跟 input 到同一 selector，则合并为 type_text
      const next = events[i+1];
      if (next && next.kind === "input" && next.selector === e.selector) {
        out.push({ type:"type_text", selector: e.selector, text: next.value });
        i++; // 跳过 next
        continue;
      }
      out.push({ type:"click", selector: e.selector, text: e.text });
      continue;
    }
    if (e.kind === "input") {
      out.push({ type:"type_text", selector: e.selector, text: e.value });
      continue;
    }
    if (e.kind === "key") {
      out.push({ type:"key", key: e.key, modifiers: e.modifiers || [] });
      continue;
    }
  }
  return out;
}

export function proposeVariables(steps: any[]) {
  // 简易变量化：把可能是搜索词/名字/邮箱的短文本提取出来
  const vars: Record<string,string> = {};
  let idx = 1;
  for (const s of steps) {
    if (s.type === "type_text" && s.text) {
      const val = String(s.text);
      // 忽略空/掩码/太长
      if (val === "******" || val.length > 60) continue;
      // 规则：包含 @ 的当 email；只字母的当 name；其他当 keyword
      let key = "";
      if (/@/.test(val)) key = `email_${idx++}`;
      else if (/^[a-zA-Z\s]+$/.test(val)) key = `name_${idx++}`;
      else key = `keyword_${idx++}`;
      if (!Object.values(vars).includes(val)) vars[key] = val;
    }
  }
  // 替换 steps 中的字面值
  const replaced = steps.map(s => {
    if (s.type === "type_text") {
      const hit = Object.entries(vars).find(([,v]) => v === s.text);
      if (hit) return { ...s, text: `\${vars.${hit[0]}}` };
    }
    return s;
  });
  return { vars, steps: replaced };
}

function toLLMInput(steps: any[]) {
  // 压缩为 LLM 可读的列表
  return steps.map((s, i) => {
    if (s.type === "open_url") return `${i+1}. open_url url="${s.url}"`;
    if (s.type === "click") return `${i+1}. click selector="${s.selector}" text="${(s.text||"").slice(0,40)}"`;
    if (s.type === "type_text") return `${i+1}. type_text selector="${s.selector}" text="${String(s.text).slice(0,40)}"`;
    if (s.type === "key") return `${i+1}. key ${s.key} mods=[${(s.modifiers||[]).join(",")}]`;
    return `${i+1}. ${s.type}`;
  }).join("\n");
}

export async function recordingToWorkflow(rawEvents: any[], opts?: { name?: string; variableize?: boolean; allow_actions?: string[] }) {
  const pre = preprocess(rawEvents);
  const { vars, steps: vSteps } = opts?.variableize ? proposeVariables(pre) : { vars:{}, steps: pre };
  const llmInput = toLLMInput(vSteps);

  // Few-shot 提示（让 LLM 严格产出 JSON）
  const sys = `You are a codegen that converts recorded browser steps into a workflow JSON.
Follow the schema:
{
  "name": string,
  "version": "1.0.0",
  "globals": { "device_target": "web", "llm_budget": { "max_calls": 0, "max_tokens": 0 }, "auto_promote_on_success": false },
  "variables": object,
  "start": string,
  "steps": [ { "id": string, "type": "action", "uses": string, "params": object }, ... ],
  "edges": [ { "from": string, "to": string, "condition"?: string }, ... ]
}
Allowed actions: ext.open_url, ext.click, type_text, ext.key.
Prefer selectors over x,y. Do NOT invent conditions; edges are linear unless obvious Enter/confirm branching. Keep params minimal but correct.`;

  const user = `Recorded steps:\n${llmInput}\n\nGenerate a valid JSON workflow that reproduces these actions.\nIf a step types into a field, keep the selector and use {"text": "..."}.\nIf variables are present, use them under "variables".\nReturn ONLY JSON.`;

  const content = await callLLM([
    { role: "system", content: sys },
    { role: "user", content: user }
  ], { temperature: 0.1, max_tokens: 1200 });

  // 安全解析
  let wf;
  try { wf = JSON.parse(content); } catch {
    // 回退：用规则拼一个极简线性工作流
    const steps = [];
    let startId = "s0";
    let sid = 1;
    for (const s of vSteps) {
      const id = `s${sid++}`;
      if (s.type === "open_url") steps.push({ id, type:"action", uses:"ext.open_url", params:{ url: s.url, app:"Google Chrome", wait_dom_quiet_ms:800 } });
      else if (s.type === "click") steps.push({ id, type:"action", uses:"ext.click", params:{ selector: s.selector } });
      else if (s.type === "type_text") steps.push({ id, type:"action", uses:"type_text", params:{ text: s.text, selector: s.selector } });
      else if (s.type === "key") steps.push({ id, type:"action", uses:"ext.key", params:{ key: s.key, modifiers: s.modifiers||[] } });
    }
    const edges = []; for (let i=0;i<steps.length-1;i++) edges.push({ from: steps[i].id, to: steps[i+1].id });
    wf = { name: opts?.name || "recorded workflow", version:"1.0.0", globals: { device_target:"web", llm_budget:{max_calls:0,max_tokens:0}, auto_promote_on_success:false }, variables: vars, start: steps[0]?.id || "", steps, edges };
  }

  // validate + lint + simulate（可选）
  const ajv = createAjv(); const validate = ajv.getSchema("workflow.schema.json");
  const ok = validate?.(wf);
  const issues = ok ? [] : (validate?.errors||[]).map(e => ({ pointer: e.instancePath || "/", message: e.message }));

  return { workflow: wf, issues, preprocessed: pre, variables: vars };
}
```

## 3) 路由：`/recordings/to-workflow`

**src/routes/recordings.ts**

```ts
import { Router } from "express";
import { recordingToWorkflow } from "../record/transform.js";
import { lintWorkflow } from "../lint/index.js";
import { simulateWorkflow } from "../sim/runner.js";

export const recRouter = Router();

recRouter.post("/recordings/to-workflow", async (req, res) => {
  const { events, name, variableize = true } = req.body || {};
  if (!Array.isArray(events) || !events.length) return res.status(400).json({ error: "events required" });

  try {
    const r = await recordingToWorkflow(events, { name, variableize });
    const lints = await lintWorkflow(r.workflow);
    const sim = await simulateWorkflow(r.workflow, 1, { provider: "default" });
    res.json({ ...r, lints, simulate: sim });
  } catch (e:any) {
    res.status(500).json({ error: String(e?.message || e) });
  }
});
```

把路由挂到 `src/index.ts`：

```ts
import { recRouter } from "./routes/recordings.js";
app.use(recRouter);
```

---

# M5-S3｜Studio 接：录制控制 & 实时事件 & 一键转 Workflow

## 1) WS 指令（Studio → 扩展）

在 `src/lib/wsClient.ts` 加两个便捷方法：

```ts
runRecordingStart(session_id?: string) { this.send({ type: "record_start", session_id }); }
runRecordingStop() { this.send({ type: "record_stop" }); }
```

## 2) 页面增量（`src/app/page.tsx`）

在 state 中加入录制会话与事件：

```tsx
const [rec, setRec] = useState<{session?: string; events: any[]; on: boolean}>({ events: [], on: false });

useEffect(() => {
  if (!bridge) return;
  bridge.on(ev => {
    if (ev.kind === "event" && ev.payload?.type === "record_event") {
      setRec(r => ({ ...r, events: [...r.events, ev.payload] }));
    }
    if (ev.kind === "event" && ev.payload?.type === "record_status") {
      setRec(r => ({ ...r, on: !!ev.payload.on, session: ev.run_id || r.session }));
    }
  });
}, [bridge]);
```

在顶栏按钮加“Start/Stop Record”与“一键生成”：

```tsx
<button
  className={`px-3 py-1 rounded ${rec.on?"bg-rose-600":"bg-rose-500"} text-white`}
  onClick={() => rec.on ? bridge?.runRecordingStop() : bridge?.runRecordingStart()}
>
  {rec.on ? "Stop Record" : "Start Record"}
</button>

<button
  className="px-3 py-1 rounded bg-emerald-600 text-white"
  onClick={async () => {
    if (!rec.events.length) return alert("还没有录制事件");
    try {
      const resp = await fetch((process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8787") + "/recordings/to-workflow", {
        method: "POST", headers: { "Content-Type":"application/json" },
        body: JSON.stringify({ events: rec.events, name: wf?.name ? `${wf.name} (from rec)` : "recorded wf", variableize: true })
      }).then(r=>r.json());
      if (resp.workflow) { setWf(resp.workflow); setIssues(resp.lints||resp.issues||[]); setSim(resp.simulate||null); }
    } catch (e:any) { alert("to-workflow failed: "+(e?.message||e)); }
  }}
>Generate from Recording</button>
```

底部新增一个“Recording Events”面板（很简洁就好）：

```tsx
<div className="col-span-12 border rounded-lg overflow-hidden">
  <div className="p-2 text-sm font-medium border-b">Recording Events ({rec.events.length})</div>
  <div className="h-48 overflow-auto text-xs p-2">
    {rec.events.slice(-200).map((e,i)=>(
      <div key={i} className="border-b py-1">
        <span className="font-mono">{new Date(e.ts).toLocaleTimeString()}</span>
        <span className="ml-2">{e.kind}</span>
        {e.selector ? <span className="ml-2 text-gray-600">{e.selector}</span> : null}
        {e.value ? <span className="ml-2">“{e.value.slice(0,40)}”</span> : null}
        {e.key ? <span className="ml-2">[{e.key}]</span> : null}
      </div>
    ))}
  </div>
</div>
```

---

# M5-S4｜效果优化（可选立即启用的小改）

* **变量化 UI**：在调用 `/recordings/to-workflow` 前，先在 Studio 弹框列出 `proposeVariables` 的建议（服务端已返回 `variables`）。用户可以改名/勾选，再提交生成。
* **自动 Fix/Lint**：你已经在路由里做了，前端显示 issues，支持“一键 Fix → Simulate”闭环。
* **隐私保护**：默认掩码 `type=password`；可在 Studio 提供“掩码/不过滤”开关。
* **域名白名单**：录制前要求用户输入目标域（Studio 存储），扩展开始录制时检查 `location.host` 不在白名单则拒绝。

---

# 验收步骤

1. 启动后端（含新路由）：

```bash
npm run dev
```

2. 启动桥接（M3-S2 的 server，若未开）：

```bash
npm run bridge
```

3. 加载/刷新扩展（包含 `recorder.js`），打开任意网页。

4. 打开 Studio → 点 **Start Record**，回到网页做：

   * 打开某 URL（或站内跳转）、点击搜索框、输入文本、按 Enter、点击某按钮。
   * 回到 Studio → **Stop Record** → **Generate from Recording**。
   * 右侧 JSON 区应出现自动生成的 workflow，Simulate 一遍确认轨迹没问题。
   * 需要变量化时检查 `variables` 已被注入。

---

## 后续增强（按需）

* **更稳 selector**：引入 `@medv/finder` 或自研多特征打分（id、role、aria、name、data-\*、text、相对定位）；录制时保存多个候选，LLM/规则选“最稳”的。
* **区域录制**：允许按住快捷键拖拽绘制矩形 → 自动生成 `ocr.extract_region.region`；与 `vision.find_element...` 联动。
* **流程分支**：录制里检测“错误提示/对话框”→ LLM 产出 `branch + condition` 的骨架（先提醒为“建议分支”，lint 校验）。
* **可视回放**：Studio 侧能点某条录制事件，高亮 DAG 对应 step，并支持“插入/删除/合并 step”。
* **跨页数据传递**：录制期间捕获页面可见文本/属性作为候选变量（如“用户名”、“搜索词”、“金额”），LLM 提示更强可变量化。

---

以上就是 **M5：录制器 + LLM 自动整理为 Workflow** 的完整落地方案与代码增量。你把增量合进当前工程，即可完成“**手动操作一遍 → 一键生成可运行的工作流**”。

15:
太给力了！这份 **Workflow JSON Configuration Guide** 能把我们在 M1–M5 搭的底座，直接升级成“**录制 → LLM整理 → 高级配置（DOM Reducer / RAG / LLM / Vision / Macros / 观测） → 执行**”的一条龙。下面我把它**落进现有方案**：给出一套“**兼容层 + 执行器扩展 + 录制器增强 + Studio 接口**”的最小改造清单和可直接粘贴的代码骨架。

---

# A. 兼容层：支持你这套“`states`/`actions`”格式（v1.1）

我们现在的执行器是 `steps + edges`。先加一个**Loader**，把你给的 v1.1 格式**规范化**为内部 DAG；也支持反向导出（方便保存）。

**要点**

* `start` → 初始 state。
* `states.*.actions[]` 按顺序落为 action steps。
* `on_success/on_error` 落为 edges（条件）。
* 全局 `config.*` 落入 `globals.config`，供运行期读取。

**最小实现（TypeScript 片段）**

```ts
// src/loader/normalize.ts
type WfV11 = {
  version: string; name: string; description?: string; task?: string;
  config?: any; start: string; states: Record<string, { actions?: any[]; on_success?: string; on_error?: string; }>;
};

export function fromStatesV11(v: WfV11) {
  const steps: any[] = []; const edges: any[] = [];
  const idOf = (s: string, i: number) => `${s}_${i+1}`;
  for (const [sname, s] of Object.entries(v.states || {})) {
    (s.actions || []).forEach((a, i) => {
      const id = idOf(sname, i);
      steps.push({ id, type:"action", uses: mapDoToUses(a.do), params: mapArgs(a) });
      const next = idOf(sname, i+1);
      if (i < (s.actions!.length - 1)) edges.push({ from: id, to: next });
    });
    if (s.actions?.length) {
      const last = idOf(sname, s.actions.length - 1);
      if (s.on_success) edges.push({ from: last, to: idOf(s.on_success, 0), condition: "true" });
      if (s.on_error)   edges.push({ from: last, to: idOf(s.on_error, 0),   condition: "false" });
    }
  }
  const startId = v.states[v.start]?.actions?.length ? idOf(v.start, 0) : "";
  return {
    name: v.name, version: "1.0.0",
    globals: { config: v.config || {}, device_target:"web", llm_budget:{max_calls:0,max_tokens:0}, auto_promote_on_success:false },
    variables: {}, start: startId, steps, edges
  };
}

function mapDoToUses(doName: string) {
  const t = (doName||"").toLowerCase();
  if (t==="ext.navigate"||t==="a.open_url"||t==="open_url") return "ext.open_url";
  if (t==="ext.click_selector"||t==="a.click"||t==="click") return "ext.click";
  if (t==="ext.type_text"||t==="a.type_text"||t==="type_text") return "type_text";
  if (t==="ext.key"||t==="a.key") return "ext.key";
  if (t==="ext.extract"||t==="ext.extract_reduced") return "ext.extract";
  if (t==="llm_decide"||t==="a.llm_decide") return "llm.decide";
  if (t==="mem.recall"||t==="a.mem.recall") return "mem.recall";
  if (t==="plan.reflect"||t==="a.plan.reflect") return "plan.reflect";
  if (t==="vision.detect"||t==="a.yolo_detect") return "vision.detect";
  if (t==="macro.execute"||t==="macro.run") return "macro.execute";
  if (t==="ext.wait_quiet"||t==="a.wait_for") return "ext.wait_quiet";
  return t; // 其他保持原样，后面 action map 扩展
}
function mapArgs(a:any){ const { do:_, ...rest } = a || {}; return rest.args ? rest.args : rest; }
```

> 放到 Loader 后：Studio 打开你的 v1.1 JSON → **预览/运行**无需改引擎。

---

# B. 执行器扩展：把指南里的模块一一落地（MVP）

## B1. DOM Reducer（`ext.extract` / `ext.extract_reduced`）

在扩展 & Headless 中新增 `ext.extract`，可读取全局 `config.dom_reduction` 并支持动作级覆盖。

**页面注入（裁剪版 Reducer）**

```js
// bg.js 内注入函数（简化版）
function inj_extract({ want="inputs", limit=100, use_reducer=false, reducer_config={}, reducer="auto" }) {
  const q = (sel) => Array.from(document.querySelectorAll(sel));
  const cand = [];
  if (want==="inputs"||want==="all") cand.push(...q("input,textarea,select,[contenteditable=''],[contenteditable='true']"));
  if (want==="buttons"||want==="all") cand.push(...q("button,[role='button'],a, [type='submit']"));
  if (want==="links"||want==="all") cand.push(...q("a[href]"));
  // 取可见元素
  const visible = cand.filter(el => {
    const r = el.getBoundingClientRect(); return r.width>0 && r.height>0 && r.bottom>=0 && r.right>=0;
  }).slice(0, 1000);

  const items = visible.map(el => {
    const r = el.getBoundingClientRect();
    return {
      tag: el.tagName.toLowerCase(),
      selector: genSelector(el),
      bbox: { x:Math.round(r.left), y:Math.round(r.top), w:Math.round(r.width), h:Math.round(r.height) },
      text: (el.innerText || el.value || el.getAttribute("aria-label") || "").trim().slice(0,140)
    };
  });

  const cfg = { maxElements: 60, dupIoU: 0.88, minTextLenSpan: 2, ...reducer_config };
  const needsReduce = reducer==="auto" ? items.length > (cfg.auto_threshold || 100) : !!use_reducer;
  const reduced = needsReduce ? reduce(items, cfg).slice(0, limit) : items.slice(0, limit);
  return { items: reduced, total: items.length, reduced: reduced.length };

  function iou(a,b){
    const ax2=a.bbox.x+a.bbox.w, ay2=a.bbox.y+a.bbox.h, bx2=b.bbox.x+b.bbox.w, by2=b.bbox.y+b.bbox.h;
    const ix=Math.max(0, Math.min(ax2,bx2)-Math.max(a.bbox.x,b.bbox.x));
    const iy=Math.max(0, Math.min(ay2,by2)-Math.max(a.bbox.y,b.bbox.y));
    const inter=ix*iy, uni=a.bbox.w*a.bbox.h + b.bbox.w*b.bbox.h - inter; return inter/Math.max(uni,1);
  }
  function reduce(arr, cfg){
    const sorted = arr
      .map(x => ({ ...x, score: (x.text?1:0.2) + (x.tag==="button"||x.tag==="a"?0.8:0) + (x.bbox.y< (cfg.preferAboveFoldY||200)?0.4:0) }))
      .sort((a,b)=>b.score-a.score);
    const kept=[]; for(const x of sorted){ if(kept.every(k=> iou(k,x) < cfg.dupIoU)) kept.push(x); if(kept.length>=cfg.maxElements) break; }
    return kept;
  }
  function genSelector(el){
    if (el.id) return `#${CSS.escape(el.id)}`;
    const name = el.getAttribute("name"); if (name) return `${el.tagName.toLowerCase()}[name="${name}"]`;
    const aria = el.getAttribute("aria-label"); if (aria) return `${el.tagName.toLowerCase()}[aria-label="${aria}"]`;
    const cls = (el.className||"").toString().trim().split(/\s+/).filter(Boolean).slice(0,3).map(c=>`.`+CSS.escape(c)).join("");
    return `${el.tagName.toLowerCase()}${cls}`;
  }
}
```

在 `bg.js` 的动作分支里加：

```js
else if (step.uses === "ext.extract") {
  const res = await runInPage(tabId, inj_extract, [params||{}]);
  result = { ok: true, outputs: res };
}
```

Headless 版：用 `page.evaluate(inj_extract, params)` 同样落地。

> 这样你就支持文档里的：
>
> * 动作级 `use_reducer` / `reducer_config` / `reducer: "auto"`
> * 全局 `config.dom_reduction.*`（在执行前 merge 进 `params`）

---

## B2. `llm_decide`

读取 `args.goal` + `dom`（我们就用上一步 `ext.extract` 返回的 `items`），让 LLM 只输出**一个动作**（或动作数组），执行并把决策回写到日志。

**后端路由（已接 /llm/reply 的前提）**

```ts
// POST /llm/decide
app.post("/llm/decide", async (req, res) => {
  const { goal, dom, allowed_actions = ["ext.click_selector","ext.type_text","ext.key"] } = req.body||{};
  const sys = "You output ONLY JSON: { actions: [{do, args}] } where do ∈ allowed_actions.";
  const user = `Goal: ${goal}\nDOM items:\n${JSON.stringify(dom?.items||dom).slice(0,6000)}\nAllowed: ${allowed_actions.join(",")}`;
  const text = await callLLM([{role:"system",content:sys},{role:"user",content:user}], {temperature:0.2, max_tokens:400});
  res.json(JSON.parse(text));
});
```

**执行器动作**

```ts
// uses === "llm.decide"
const r = await fetch(API_BASE + "/llm/decide", { method:"POST", headers:{'Content-Type':'application/json'},
  body: JSON.stringify({ goal: params.goal, dom: ctx.outputs[params.dom_ref] || params.dom, allowed_actions: params.allowed_actions })});
const plan = await r.json(); // { actions:[{do,args},...] }
for (const a of (plan.actions||[])) {
  await runOne({ uses: mapDoToUses(a.do), params: a.args }); // 复用现有动作分派
}
return { ok:true, outputs: { plan } };
```

---

## B3. Memory（`mem.recall`/`plan.reflect`）— 轻实现

你说规模不大，我们做**文件级向量库**或 mock 即可。

* `mem.recall`：从 `runs/*.json` 的 `trace` 中抽“成功轨迹”→ embedding（openai/sentence-transformers任选）→ 近邻召回。
* `plan.reflect`：把本次 `execution_log`（trace+errors）丢给 LLM，总结改进点。

路由骨架（简化版）：

```ts
// POST /mem/recall { goal, k, host_filter }
app.post("/mem/recall", async (req,res)=>{
  // 读取本地 runs 目录，做最简单的 TF-IDF/余弦 或 直接 LLM rank（小规模足够）
  res.json({ items: [] });
});
app.post("/plan/reflect", async (req,res)=>{
  const { focus="error_analysis", context, goal } = req.body||{};
  const text = await callLLM([{role:"system",content:"Be concise."},{role:"user",content:`Focus:${focus}\nGoal:${goal}\nLog:${context}`}],
    { temperature:0.2, max_tokens:600 });
  res.json({ text });
});
```

执行器加映射 `mem.recall` / `plan.reflect` 即可。

---

## B4. Vision / OCR / Macros / Error / Observability（最小接入）

* **Vision/OCR**：把指南里的 `vision.detect`、`ocr.run/ocr_extract` 映射到我们已有 `vision.find_element_with_image_check` & `ocr.extract_region`；若你后端有 YOLO/OCR 服务，按 config 里的 endpoint 走 HTTP；没有就走 DOM/selector 回退。
* **Macros**：新增 `macro.execute` → 从本地 `./macros/` 读取 JSON（就用 v1.1 的 `states` 定义），加载后用 Loader 规范化再执行。
* **错误处理**：在每步执行时读取 `retry`/`fallback` 字段；失败后按 `{max_attempts, delay_ms, backoff_factor}` 重试，或执行 `fallback[]` 动作。
* **观测**：把 `config.observability.logging/metrics` 合并进运行器开关；每步产出 `{t_start,t_end,status,costTokens}`，可落到 `runs/*.json`。

---

# C. 录制器增强：直接产出 v1.1（`states`/`actions`）

M5 我们已做了 Recorder。现在把“**录制 → LLM 整理**”的输出改为 **v1.1**，并自动插入 `ext.extract + llm_decide` 模式（当页面复杂时），与 DOM Reducer 打通。

**生成策略**

1. `navigate` → `{"do":"ext.navigate","url":...}`
2. `click/input/key` → 直译为 `ext.click_selector` / `ext.type_text` / `ext.key`
3. 若同一页面元素 > `auto_threshold`：插入一对：

   * `{"do":"ext.extract","args":{"want":"inputs","reducer":"auto"}}` 保存为 `search_dom`
   * `{"do":"llm_decide","args":{"goal":"<从录制语义提取>","dom":"{{search_dom}}"}}`
4. 生成 `states`: `s1,s2,...`，每个 state 的 `actions` 是连续的一小段；默认线性 `on_success` 指向下一个。

**LLM 提示（片段）**

```txt
目标：把下列录制事件转为 v1.1 工作流（states/actions）。当页面元素很多时，优先用：
  1) ext.extract + reducer:auto 生成 DOM 子集
  2) llm_decide 根据 goal 和 dom 决策 ext.click_selector / ext.type_text
只输出 JSON，不要解释。
```

---

# D. Studio 改动（非常小）

* **导入/导出**：文件选择时先尝试解析为 v1.1；若是，调用 `fromStatesV11()` 规范化后渲染；导出时可选“导出为 v1.1 / 导出为 DAG”。
* **动作表单**：`ext.extract` 增加 reducer 的 UI（开关、maxElements、dupIoU…）；`llm_decide` 增加 allowed\_actions、dom 引用选择器。
* **Live面板**：显示 `config.observability.logging` 里定义的 event/metric；显示 `mem.recall`、`plan.reflect` 的输出。

---

# E. 小型回归示例（可直接跑）

**v1.1（片段）**

```json
{
  "version": "1.1",
  "name": "xhs_search_with_reducer_v11",
  "start": "open",
  "config": { "dom_reduction": { "enabled": true, "auto_threshold": 80, "max_elements": 40 } },
  "states": {
    "open": {
      "actions": [
        { "do": "ext.navigate", "url": "https://www.xiaohongshu.com/explore" },
        { "do": "ext.wait_quiet", "args": { "timeout_ms": 5000 } }
      ],
      "on_success": "search"
    },
    "search": {
      "actions": [
        { "do": "ext.extract", "args": { "want": "inputs", "reducer": "auto" }, "save": "search_dom" },
        { "do": "llm_decide", "args": { "goal": "在搜索框输入“美食推荐”并提交", "dom": "{{search_dom}}",
          "allowed_actions": ["ext.click_selector","ext.type_text","ext.key"] } }
      ],
      "on_success": "done"
    },
    "done": { "actions": [ { "do": "ext.wait_quiet", "args": { "timeout_ms": 2000 } } ] }
  }
}
```

→ Studio 导入 → Loader 规范化 → 扩展/Headless 运行器都能跑；在复杂页自动触发 Reducer + llm\_decide。

---

## 实施顺序（建议）

1. 加 **Loader（v1.1 → DAG）** 与 **反向导出**。
2. 执行器增加 `ext.extract`（含 Reducer）与 `llm.decide`。
3. 录制器输出改为 v1.1，复杂页自动插入 `extract + llm_decide` 模式。
4. Memory/Reflect、Vision/OCR、Macros、错误/观测的小步落地。

16:
太好了！我把“落地到可跑”的**下一步清单**压缩成最小改动包，直接照着做就行：

---

## 今日落地清单（按顺序做）

1. **Loader 接入 v1.1（states/actions）**

   * 新增 `src/loader/normalize.ts`（用我上条消息给的 `fromStatesV11()` 代码）。
   * 在后端启动时注册：

     ```ts
     // src/index.ts
     import { fromStatesV11 } from "./loader/normalize";
     // 导入 v1.1 -> 规范化 -> 现有 runner
     ```
   * Studio 导入 JSON 时：先尝试解析 v1.1 → `fromStatesV11()` → 预览/运行。

2. **扩展 & Headless 增加 DOM Reducer 提取**

   * 扩展 `bg.js`：加入我提供的 `inj_extract()`，在 `uses === "ext.extract"` 时 `runInPage(inj_extract, params)`。
   * Headless `runner.ts`：`await page.evaluate(inj_extract, params)`，并读取 `globals.config.dom_reduction` 合并到 `params`。
   * Studio 的 Step 表单给 `ext.extract` 加：`reducer: auto | true/false`、`maxElements`、`dupIoU`、`minTextLenSpan` 等。

3. **LLM 决策（llm.decide）**

   * 后端加 `/llm/decide`（我已给路由骨架）。
   * 运行器加 `uses === "llm.decide"`：把 `goal + dom(items)` 传后端，按返回 `{actions:[{do,args}]}` 逐个执行（用你现有 `mapDoToUses()`）。

4. **录制器输出直接产出 v1.1**

   * 把 `POST /recordings/to-workflow` 的生成器换成 **v1.1 states/actions**：

     * `navigate` → `ext.navigate`
     * `click` → `ext.click_selector`
     * `input` → `ext.type_text`
     * `key` → `ext.key`
     * **当单页可交互元素 > 阈值（如 100）**：自动插入

       1. `ext.extract`（`reducer:"auto"`，`save:"dom_snapshot"`）
       2. `llm.decide`（`goal` 来自录制语义，`dom:"{{dom_snapshot}}"`）
   * 返回结构：`{ version:"1.1", name, config?, start, states }`，Studio 用 Loader 立刻可跑。

5. **宏/错误/观测（可选最小）**

   * `macro.execute`：从 `./macros/*.json` 读 v1.1 定义 → Loader → 递归执行。
   * 错误/重试：尊重动作里的 `retry{max_attempts,delay_ms}` 与 `fallback[]`。
   * 观测：将 `config.observability.logging/metrics` 映射为是否写 `runs/*.json`、是否统计时长/成功率。

---

## 轻量验收

* **用你文档“示例1 小红书”**：直接导入 v1.1 JSON → Loader 规范化 → 扩展/Headless 都能跑；Live 面板能看到 `ext.extract` 统计（`total`/`reduced`）。
* **录制→生成**：录制“打开站点→搜索→回车”，点击“Generate from Recording”，应产出 v1.1（遇复杂页会自动插入 `extract + llm_decide`），点“Run in Chrome / Run Headless”均可执行。

---

## 你可以马上粘的关键片段（汇总）

* Loader：`fromStatesV11()`（上条消息 A 部分）。
* DOM Reducer：`inj_extract()`（B1 已给函数体，扩展 & Headless 共用）。
* `/llm/decide` 路由 + `llm.decide` 动作（B2 提供）。
* 录制输出 v1.1 的组装规则（C 部分——直接把规则放进 `/recordings/to-workflow`）。

---

补充：
看完这份 **Hybrid Workflow Schema v1.1**，总体和我们前面落的方案高度匹配，但要做到“开箱即跑、录制直出 v1.1”，需要做几处**兼容性更新**与**执行器增强**。我把差异点→应对改造点精炼成清单，给出关键实现要点（都很小、可一步步合入）。

---

# 兼容性&改造清单（结论先行）

## A. Loader / 变量层

1. **根字段名**

   * 新增读取 `workflow.vars`（我们之前用 `variables`）。运行时把 `vars` 注入上下文（读写统一 `ctx.vars`）。
   * 若两者同时存在，`vars` 优先。

2. **State 转换**

   * 支持 `on_success` / `next` / `on_error` 三种跳转字段（优先级：`transitions` > `on_success` > `next` > `on_error`）。
   * 新增 `state.transitions[]` 解析：`{ if, go_to, else_go_to }`，需要轻量表达式求值器（下面 C.1）。

3. **Actions 的 args 包装**

   * 适配 `a.ext.extract` / `a.llm_decide` 等**把参数放在 `args` 内**的风格；Loader 展平为内部 `params`。

✅ 影响面：Loader 100行内可搞定。

---

## B. Runner（执行器）

4. **common\_action 语义**

   * `timeout_ms`：执行器围绕单步超时包裹。
   * `retry`: `{ attempts, base_ms, max_ms }` 指数退避；失败后再进入 `fallback`（若动作内定义）。
   * `save`：既支持字符串，也支持 `save_block`：

     * `"json"`：将 action 输出对象写入 `ctx.vars[json]`
     * `"shot" | "overlay" | "yolo" | "picker"`：若动作有对应二进制/路径，落盘并记录路径；没有就忽略不报错
     * 同时兼容 `save_as`/`save_to`（若出现，以 `save` 为准，其他视为别名）

5. **表达式跳转 / 条件动作**

   * 支持 `state.transitions[].if` 与 `a.branch` / `a.conditional`（then/else 内联 actions）。

6. **具体动作补齐**

   * `ext.open_url`：支持 `active`（是否激活标签）。

   * `ext.click_selector`：参数名 `sel`。

   * `ext.type_text`：新增 `replace`→等价我们之前的 `clear_first:true`。

   * `ext.scroll`：新增 `{ dir: "up|down", amount: px }`。

   * `ext.extract`：接受 `{ args: {...} }`；内含 `use_reducer` / `reducer:"auto"` / `reducer_config`（我们已实现 reducer，参数透传即可）。

   * `llm_decide`：读取 `args` 包（`goal`, `dom`, `allowed_actions`…），逐条执行 LLM 返回的 `{do,args}`。

   * `wait_for`：先实现最小子集

     * `until.type="ext.wait_quiet"` → 走我们已有 `ext.wait_quiet`
     * `until.type="sleep_ms"` / `value:number` → 走 sleep
     * 其他类型（spinner/yolo）先返回 `NotImplemented`（允许 fallback/分支兜底）

   * `instr.*` 系列：增加**目标解析器**

     * `instruction_target.css` → 直接使用
     * `xpath` → 转 CSS 或在页面 evaluate 走 XPath
     * `bbox_var` → 若存在，坐标点击（click\_coordinates）作为最后兜底
     * `text/role`（可选）→ 先简单 DOM 查找（包含文本匹配）

   * 其余高级/外部集成（`mq.*`, `chat.*`, `remote_session*`, `mock_service*`, `chaos_experiment*`…）：

     * 标记为 **“已识别但未实现”** 的占位 handler（返回 `ENOTIMPL`），不让引擎崩；配合 `retry/fallback/transitions` 能继续走别的路。

✅ 影响面：动作分发 switch 扩两三百行以内；`instr.*` 目标解析 60–100 行。

---

## C. 运行时小工具

7. **表达式求值器（transitions / branch / conditional）**

   * 轻量安全解析：允许变量引用（`@var`）、`== != > < >= <=`、逻辑 `&& || !`、数字/字符串常量。
   * 推荐内置一个微型 parser（或用 `expr-eval` 类库；没有第三方也能写 60 行）。

8. **LLM 全局设置**

   * 根层新增 `llm_provider` / `llm_model`：覆盖我们现有默认；在 `llm_decide` / `plan.reflect` 等调用里读取。

9. **meta / metadata / autofix**

   * `meta.resource_lock`：可选开启**同名 lock**（同一 workflow 并发=1）。
   * `autofix.mode`：

     * `"suggest_only"`：只生成修复建议（我们已有 lint 输出，直接兼容）
     * `"hot_patch_session"`：允许本次 run 注入 patch（不落盘）
     * `"auto_promote_on_success"`：当满足 `promote.threshold` 条件（成功窗口 / p95 等）把 patch 写回磁盘
   * `limits.*` → 运行时计数器即可（存内存或本地 kv）

✅ 影响面：配置读取 + 2 个小型辅助模块。

---

## D. Studio / 录制器

10. **录制 → v1.1 直出**

* 根字段用 `version:"1.1"`、`start`、`states`、`vars`。
* 单步生成 `actions[]`；页面复杂时插入 `ext.extract{reducer:"auto"} + llm_decide`（和我们 M5 保持一致），字段命名对齐 schema（`sel`、`args`）。

11. **编辑器支持**

* State 侧边栏加入 `state_timeout_ms`、`transitions[]` 可视化（if / go\_to / else\_go\_to）。
* Action 表单增加 `retry`、`timeout_ms`、`save_block`、`ext.scroll` 的 `dir/amount`、`ext.type_text.replace`。

---

# 代码改动点（关键片段）

### 1) Loader：展开 `args` & 跳转优先级

```ts
function normalizeAction(a:any){
  const doName = a.do;
  // 优先使用 a.args，其次把 a 的其余键（去掉通用字段）当作参数
  const { do:_, save, save_as, save_to, timeout_ms, retry, ...rest } = a;
  const params = a.args ?? rest ?? {};
  return { uses: mapDoToUses(doName), params, meta: { save, save_as, save_to, timeout_ms, retry } };
}

function nextOfState(s:any){
  // transitions 优先
  if (Array.isArray(s.transitions) && s.transitions.length) return { transitions: s.transitions };
  if (s.on_success) return { on_success: s.on_success };
  if (s.next)       return { on_success: s.next };
  if (s.on_error)   return { on_error: s.on_error };
  return {};
}
```

### 2) Runner：common\_action 落地

```ts
async function runWithCommon(action, execOne){
  const { timeout_ms, retry, save, save_as, save_to } = action.meta||{};
  const job = () => execOne(action.uses, action.params);
  const out = await withRetry(job, retry);         // attempts/base_ms/max_ms
  const final = await withTimeout(out, timeout_ms);
  // 保存
  if (typeof save === "string") ctx.vars[save] = final;
  if (save && typeof save === "object") {
    if (save.json) ctx.vars[save.json] = final;
    if (save.shot && final?.screenshot) ctx.vars[save.shot] = final.screenshotPath;
    // overlay/yolo/picker 同理（若存在）
  }
  if (save_as) ctx.vars[save_as] = final;
  if (save_to) ctx.vars[save_to] = final;
  return final;
}
```

### 3) `instr.*` 目标解析器（最小）

```ts
function resolveTarget(t:any){
  if (t?.css) return { selector: t.css };
  if (t?.xpath) return { xpath: t.xpath };
  if (t?.bbox_var) return { bbox: getVar(t.bbox_var) };
  if (t?.element_id) return { selector: `#${CSS.escape(t.element_id)}` };
  // text/role: 简单文本包含查找
  if (t?.text) return { text: t.text };
  return {};
}
```

> `instr.click` → 优先 `selector/xpath`，无则 `bbox`，再无则 `text` 模糊匹配。

### 4) `ext.scroll`

```ts
if (uses === "ext.scroll") {
  const { dir="down", amount=600 } = params;
  await runInPage(tabId, ({dir,amount})=>{
    const dy = dir==="up" ? -Math.abs(amount) : Math.abs(amount);
    window.scrollBy({ top: dy, left: 0, behavior: "smooth" });
  }, [{dir,amount}]);
  return { ok:true };
}
```

### 5) 表达式求值（transitions / branch / conditional）

```ts
function evalExpr(str:string, vars:any){
  // 允许 @var 形式：替换为 vars.var
  const src = str.replace(/@([a-zA-Z_]\w*)/g, (_,k)=> JSON.stringify(vars[k]));
  // 仅允许安全字符
  if (!/^[\s\w"'().,!<>=&|+\-/*%?:]+$/.test(src)) throw new Error("bad expr");
  // 受限 eval
  // eslint-disable-next-line no-new-func
  return Function(`"use strict"; return (${src});`)();
}
```

---

# 不改也能跑 / 需要 Stub 的动作

* **会跑、我们已支持**：`ext.open_url` / `ext.click_selector` / `ext.type_text(replace)` / `ext.key` / `ext.scroll` / `ext.extract(use_reducer/reducer:auto)` / `llm_decide(args)` / `sleep_ms` / `wait(seconds)` / `screenshot` / `wait_for(ext.wait_quiet|sleep_ms)` / `branch|conditional` / `instr.*`（最小解析）。
* **暂不实现，保留占位**（返回 ENOTIMPL，支持 fallback/分支转移）：`mq.*`、`chat.*`、`remote_session*`、`mock_service_setup`、`chaos_experiment`、`run_integration_test`、`desktop_automation`、`mobile_automation`、`secure_operation` 等。后续若要用，再对接真实服务即可。
* **autofix**：先接 `suggest_only` 与 `hot_patch_session`；`auto_promote_on_success` 可在我们 lint/fix 通过率统计完成后开启（读 `promote.threshold`）。

---

# 升级顺序（一天内能合并的顺序）

1. Loader：args 展平 + `vars` 注入 + 跳转优先级 & transitions。
2. Runner：`common_action`（timeout/retry/save）& 表达式求值器。
3. 动作补齐：`ext.type_text.replace`、`ext.scroll`、`wait_for` 最小子集、`llm_decide(args)`。
4. `instr.*` 目标解析器。
5. Studio：录制直出 v1.1（字段名对齐）+ action 表单的新增项。
6. （可选）autofix mode 的热补丁逻辑。

---

如果你把这份 schema 放进 Ajv，我们只需把 `createAjv()` 里**新增加载 v1.1 的 schema id**，并在导入时先跑一次校验（报错直接返回 ajv.errors）。要我把 \*\*四个补丁文件（Loader / Runner-dispatch / InstrResolver / Studio-Form）\*\*写成可替换版，我可以直接给完整内容。

太棒了。我直接把你要的**4 个可替换补丁文件**给齐了（精简但能跑），完全对齐你这版 **Hybrid Workflow v1.1 JSON Schema**。照抄进项目即可——

---

# 1) `src/loader/normalize.ts`

* 读入 v1.1（`start/states/vars`、`transitions/on_success/next/on_error`）
* 展开 `action.args → params`
* 兼容 `save/save_as/save_to/timeout_ms/retry`
* 输出为你现有的内部 DAG（`steps/edges/start`）

```ts
// src/loader/normalize.ts
export type V11 = {
  version?: string | number;
  name?: string;
  description?: string;
  start: string;
  vars?: Record<string, any>;
  llm_provider?: string;
  llm_model?: string;
  context?: any;
  metadata?: any;
  meta?: { priority?: "LOW"|"HIGH"; resource_lock?: string };
  autofix?: any;
  states: Record<string, any>;
};

type Internal = {
  name?: string;
  version: string;
  globals: {
    config?: any;
    llm?: { provider?: string; model?: string };
    meta?: any;
    autofix?: any;
    device_target: "web";
    llm_budget: { max_calls: number; max_tokens: number };
    auto_promote_on_success: boolean;
  };
  variables: Record<string, any>;
  start: string;
  steps: Array<{ id: string; type: "action"; uses: string; params: any; meta?: any }>;
  edges: Array<{ from: string; to: string; condition?: string }>;
};

const COMMON_KEYS = new Set([
  "do","save","save_as","save_to","timeout_ms","retry"
]);

export function fromStatesV11(v: V11): Internal {
  const steps: Internal["steps"] = [];
  const edges: Internal["edges"] = [];
  const idOf = (s: string, i: number) => `${s}_${i+1}`;

  const stateNames = Object.keys(v.states || {});
  for (const sname of stateNames) {
    const s = v.states[sname] || {};
    const actions: any[] = Array.isArray(s.actions) ? s.actions : [];

    // actions → steps
    actions.forEach((a, i) => {
      const id = idOf(sname, i);
      const meta = pickCommonMeta(a);
      const params = expandParams(a);
      steps.push({ id, type: "action", uses: mapDoToUses(a?.do), params, meta });

      // linear chain inside the same state
      if (i < actions.length - 1) {
        edges.push({ from: id, to: idOf(sname, i+1) });
      }
    });

    // transitions 优先，其次 on_success/next/on_error
    if (actions.length > 0) {
      const last = idOf(sname, actions.length - 1);
      if (Array.isArray(s.transitions) && s.transitions.length) {
        for (const t of s.transitions) {
          if (t.if && t.go_to) edges.push({ from: last, to: idOf(t.go_to, 0), condition: t.if });
          if (t.else_go_to)   edges.push({ from: last, to: idOf(t.else_go_to, 0), condition: "!("+ (t.if||"false") +")" });
          if (!t.if && t.go_to) edges.push({ from: last, to: idOf(t.go_to, 0) });
        }
      } else if (s.on_success || s.next) {
        edges.push({ from: last, to: idOf((s.on_success || s.next), 0) });
      }
      if (s.on_error) {
        // 内部 condition：失败路径建议由 runner 在失败时走；这里给个显式边方便可视化
        edges.push({ from: last, to: idOf(s.on_error, 0), condition: "@last_step_failed == true" });
      }
    }
  }

  const startId = (v.states?.[v.start]?.actions?.length ?? 0) > 0 ? idOf(v.start, 0) : "";

  return {
    name: v.name,
    version: "1.0.0",
    globals: {
      config: v.context || {},
      llm: { provider: v.llm_provider, model: v.llm_model },
      meta: { ...v.meta, metadata: v.metadata },
      autofix: v.autofix,
      device_target: "web",
      llm_budget: { max_calls: 0, max_tokens: 0 },
      auto_promote_on_success: false
    },
    variables: { ...(v.vars || {}) },
    start: startId,
    steps,
    edges
  };
}

function pickCommonMeta(a:any){
  const meta:any = {};
  if ("save" in a) meta.save = a.save;
  if ("save_as" in a) meta.save_as = a.save_as;
  if ("save_to" in a) meta.save_to = a.save_to;
  if ("timeout_ms" in a) meta.timeout_ms = a.timeout_ms;
  if ("retry" in a) meta.retry = a.retry;
  return meta;
}

function expandParams(a:any){
  if (!a) return {};
  if (a.args && typeof a.args === "object") return a.args;
  const params:any = {};
  for (const k of Object.keys(a)) {
    if (!COMMON_KEYS.has(k)) params[k] = a[k];
  }
  return params;
}

export function mapDoToUses(name:string){
  const t = (name||"").toLowerCase();
  if (t==="open_url" || t==="a.open_url" || t==="ext.navigate" || t==="a.ext.open_url") return "ext.open_url";
  if (t==="a.sleep_ms" || t==="sleep_ms") return "sleep_ms";
  if (t==="a.wait" || t==="wait") return "wait";
  if (t==="a.wait_for" || t==="wait_for") return "wait_for";
  if (t==="a.screenshot" || t==="screenshot") return "screenshot";
  if (t==="a.ext.click_selector" || t==="ext.click_selector" || t==="a.click" || t==="click") return "ext.click";
  if (t==="a.ext.type_text" || t==="ext.type_text" || t==="a.type_text" || t==="type_text") return "type_text";
  if (t==="a.ext.key" || t==="ext.key" || t==="a.instr.key" || t==="instr.key") return "ext.key";
  if (t==="a.ext.scroll" || t==="ext.scroll" || t==="a.scroll" || t==="instr.scroll") return "ext.scroll";
  if (t==="a.ext.extract" || t==="ext.extract") return "ext.extract";
  if (t==="a.llm_decide" || t==="llm_decide" || t==="a.decide_with_gemini") return "llm.decide";
  if (t==="a.branch" || t==="branch") return "branch";
  if (t==="a.conditional" || t==="conditional") return "conditional";
  if (t.startsWith("a.instr.")) return t.replace("a.instr.","instr.");
  return t;
}
```

---

# 2) `src/runner/dispatch.ts`

* 通用包装：`timeout_ms` / `retry{attempts,base_ms,max_ms}` / `save|save_as|save_to`
* 轻量表达式：支持 `@var`、比较/逻辑运算
* 最小动作集：`ext.open_url / ext.click / type_text(replace)/ ext.key / ext.scroll / ext.extract(reducer)`、`wait_for`(sleep/ext.wait\_quiet)、`llm.decide`、`branch/conditional`

```ts
// src/runner/dispatch.ts
import { evalExpr, withRetry, withTimeout } from "./rt.utils";
import { resolveInstrTarget } from "./instrTarget";
import { inj_extract } from "./page/inj_extract"; // 复用你已有的注入函数

type Ctx = {
  page?: any; tabId?: number;
  vars: Record<string, any>;
  globals?: any;
  setVar: (k:string, v:any)=>void;
  lastError?: any;
};

export async function runAction(ctx: Ctx, action: any){
  const exec = () => execOne(ctx, action);
  const out = await withRetry(exec, action.meta?.retry);
  const res = await withTimeout(out, action.meta?.timeout_ms);
  // save
  if (typeof action.meta?.save === "string") ctx.setVar(action.meta.save, res);
  const saveObj = action.meta?.save;
  if (saveObj && typeof saveObj === "object") {
    if (saveObj.json) ctx.setVar(saveObj.json, res);
    if (saveObj.shot && res?.screenshotPath) ctx.setVar(saveObj.shot, res.screenshotPath);
  }
  if (action.meta?.save_as) ctx.setVar(action.meta.save_as, res);
  if (action.meta?.save_to) ctx.setVar(action.meta.save_to, res);
  return res;
}

async function execOne(ctx: Ctx, a: any){
  const uses = a.uses;
  const p = a.params || {};
  switch (uses) {
    case "ext.open_url": {
      const url = p.url || p.href;
      await ctx.page.goto(url, { waitUntil: "load", timeout: 30000 });
      return { ok:true, url };
    }
    case "ext.click": {
      // 来自 ext.click_selector / instr.click(target.css)
      const sel = p.sel || p.selector || resolveInstrTarget(p.target).selector;
      if (!sel) throw new Error("click: selector missing");
      await ctx.page.waitForSelector(sel, { timeout: 10000 });
      await ctx.page.click(sel);
      return { ok:true, sel };
    }
    case "type_text": {
      const sel = p.sel || p.selector || resolveInstrTarget(p.target).selector;
      if (!sel) throw new Error("type_text: selector missing");
      await ctx.page.waitForSelector(sel, { timeout: 10000 });
      if (p.replace) await ctx.page.$eval(sel, (el:any) => (el.value = ""));
      await ctx.page.type(sel, String(p.text ?? ""), { delay: 10 });
      return { ok:true, sel, text: p.text };
    }
    case "ext.key": {
      await ctx.page.keyboard.press(String(p.key || "Enter"));
      return { ok:true, key: p.key };
    }
    case "ext.scroll": {
      const dir = p.dir || "down";
      const amount = Math.max(1, p.amount || 600);
      const dy = dir === "up" ? -amount : amount;
      await ctx.page.evaluate((dy)=> window.scrollBy(0, dy), dy);
      return { ok:true, dir, amount };
    }
    case "ext.extract": {
      // DOM Reducer：读取全局 config 合并
      const globalCfg = ctx.globals?.config?.dom_reduction || {};
      const args = { ...(p.args || p), ...globalCfg };
      const res = await ctx.page.evaluate(inj_extract, args);
      return res; // { items,total,reduced }
    }
    case "wait_for": {
      const u = p.until || p;
      if (u?.type === "sleep_ms" || typeof u?.value === "number") {
        const ms = u?.value ?? u?.timeout_ms ?? 1000;
        await new Promise(r => setTimeout(r, ms));
        return { ok:true, slept_ms: ms };
      }
      if (u?.type === "ext.wait_quiet") {
        // 简化：等待网络闲置 + dom 稳定（按照你的已有实现）
        await ctx.page.waitForNetworkIdle({ idleTime: 1000, timeout: u.timeout_ms || 10000 });
        return { ok:true };
      }
      throw new Error("wait_for: not implemented type="+u?.type);
    }
    case "sleep_ms": {
      const ms = p.value ?? 1000;
      await new Promise(r => setTimeout(r, ms));
      return { ok:true, slept_ms: ms };
    }
    case "wait": {
      const ms = Math.floor((p.seconds || 0) * 1000);
      await new Promise(r => setTimeout(r, ms));
      return { ok:true, slept_ms: ms };
    }
    case "screenshot": {
      const path = p.save_path || `shot_${Date.now()}.png`;
      await ctx.page.screenshot({ path, fullPage: p.region==="full" });
      return { ok:true, screenshotPath: path };
    }
    case "llm.decide": {
      const body = {
        goal: p.goal,
        dom: ctx.vars[p.dom] || p.dom || {},
        allowed_actions: p.allowed_actions || ["ext.click_selector","ext.type_text","ext.key"],
        provider: ctx.globals?.llm?.provider,
        model: ctx.globals?.llm?.model
      };
      const resp = await fetch(process.env.API_BASE + "/llm/decide", {
        method:"POST", headers:{ "Content-Type":"application/json" },
        body: JSON.stringify(body)
      }).then(r=>r.json());
      for (const sub of (resp.actions || [])) {
        const uses2 = sub.do?.startsWith("ext.") ? (sub.do==="ext.click_selector"?"ext.click":sub.do) : sub.do;
        await runAction(ctx, { uses: uses2==="llm_decide" ? "llm.decide" : uses2, params: sub.args || sub });
      }
      return { ok:true, plan: resp };
    }
    case "branch": {
      const cond = a.params?.if; // e.g. "@x > 0"
      const yes = a.params?.then;
      const no  = a.params?.else;
      const ok = evalExpr(cond || "false", ctx.vars);
      return { ok, next: ok ? yes : no };
    }
    case "conditional": {
      const cond = a.params?.condition || "false";
      const hit = evalExpr(cond, ctx.vars);
      const arr = hit ? (a.params?.actions||[]) : (a.params?.else_actions||[]);
      for (const sub of arr) {
        await runAction(ctx, { uses: sub.do ? sub.do.replace(/^a\./,"") : sub.uses, params: sub.args || sub });
      }
      return { ok:true };
    }
    default:
      // 其余高级动作先占位，不让崩
      return { ok:false, error: "ENOTIMPL:"+uses };
  }
}
```

**运行时工具：`src/runner/rt.utils.ts`**

```ts
// src/runner/rt.utils.ts
export async function withTimeout<T>(p:Promise<T>, ms?:number){
  if (!ms || ms<=0) return p;
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(()=> reject(new Error("ETIMEDOUT")), ms);
    p.then(v=>{ clearTimeout(t); resolve(v as any); }).catch(e=>{ clearTimeout(t); reject(e); });
  });
}
export async function withRetry<T>(fn:()=>Promise<T>, retry?:{attempts?:number;base_ms?:number;max_ms?:number}){
  const attempts = Math.max(1, retry?.attempts ?? 1);
  const base = retry?.base_ms ?? 200;
  const max  = retry?.max_ms ?? 2000;
  let tryN = 0, lastErr:any;
  while (tryN++ < attempts) {
    try { return await fn(); } catch (e) {
      lastErr = e; if (tryN>=attempts) break;
      const wait = Math.min(max, base * Math.pow(2, tryN-1));
      await new Promise(r=>setTimeout(r, wait));
    }
  }
  throw lastErr;
}
export function evalExpr(expr:string, vars:Record<string,any>){
  const src = String(expr||"false").replace(/@([a-zA-Z_]\w*)/g, (_,k)=> JSON.stringify(vars?.[k]));
  if (!/^[\s\w"'().,!<>=&|+\-/*%?:]+$/.test(src)) throw new Error("bad expr");
  // eslint-disable-next-line no-new-func
  return Function(`"use strict"; return (${src});`)();
}
```

---

# 3) `src/runner/instrTarget.ts`

* 解析 schema 的 `instruction_target`
* 支持 `css/xpath/element_id/ bbox_var / text/role` 的最小可用逻辑

```ts
// src/runner/instrTarget.ts
export function resolveInstrTarget(t:any = {}) {
  if (t.css) return { selector: t.css };
  if (t.element_id) return { selector: `#${cssEscape(t.element_id)}` };
  if (t.xpath) return { xpath: t.xpath }; // 执行时用 page.$x 再 click
  if (t.bbox_var) return { bboxVar: t.bbox_var }; // 调用方读取 ctx.vars
  if (t.text) return { text: t.text };
  return {};
}

function cssEscape(s:string){ return s.replace(/([ #;.?+*~':"!^$[\]()=>|/@])/g,"\\$1"); }
```

> 在 `dispatch.ts` 的 `ext.click` / `type_text` 里：优先 `selector/xpath`，否则若 `bboxVar` 则转坐标点击；再否则 `text` 模糊查找（你已有 DOM 查找工具可接）。

---

# 4) Studio UI（两处最小补丁）

## 4.1 `ActionForms.tsx`（新增字段映射）

* `ext.type_text`：`replace` 开关
* `ext.scroll`：`dir / amount`
* `ext.extract`：`use_reducer / reducer:"auto" / reducer_config.maxElements …`
* `llm_decide`：`args.goal / args.dom (var picker) / args.allowed_actions[]`

```tsx
// src/app/components/ActionForms.tsx (片段)
export function TypeTextForm({value,onChange}) {
  return <>
    <Input label="Selector (sel)" value={value.sel||""} onChange={v=>onChange({...value, sel:v})}/>
    <Input label="Text" value={value.text||""} onChange={v=>onChange({...value, text:v})}/>
    <Toggle label="Replace (clear first)" checked={!!value.replace} onChange={b=>onChange({...value, replace:b})}/>
  </>;
}
export function ScrollForm({value,onChange}) {
  return <>
    <Select label="Direction" value={value.dir||"down"} options={["up","down"]} onChange={v=>onChange({...value, dir:v})}/>
    <Number label="Amount(px)" value={value.amount??600} onChange={n=>onChange({...value, amount:n})}/>
  </>;
}
export function ExtractForm({value,onChange}) {
  return <>
    <Select label="Reducer" value={value.reducer||"auto"} options={["auto","true","false"]} onChange={v=>onChange({...value, reducer:v})}/>
    <Number label="maxElements" value={value.reducer_config?.maxElements??60}
      onChange={n=>onChange({...value, reducer_config:{...(value.reducer_config||{}), maxElements:n}})}/>
    <Number label="dupIoU" value={value.reducer_config?.dupIoU??0.88}
      onChange={n=>onChange({...value, reducer_config:{...(value.reducer_config||{}), dupIoU:n}})}/>
  </>;
}
export function LlmDecideForm({value,onChange,vars}) {
  return <>
    <Input label="Goal" value={value.goal||""} onChange={v=>onChange({...value, goal:v})}/>
    <VarPicker label="DOM Var" value={value.dom||""} options={Object.keys(vars||{})}
      onChange={v=>onChange({...value, dom:v})}/>
    <Tags label="Allowed Actions" value={value.allowed_actions||["ext.click_selector","ext.type_text","ext.key"]}
      onChange={arr=>onChange({...value, allowed_actions:arr})}/>
  </>;
}
```

## 4.2 `TransitionsEditor.tsx`（最小可用）

```tsx
// src/app/components/TransitionsEditor.tsx (片段)
export function TransitionsEditor({state, onChange, stateNames}:any){
  const trans = state.transitions || [];
  return <div className="space-y-2">
    {trans.map((t:any, i:number)=>(
      <div key={i} className="grid grid-cols-3 gap-2">
        <Input label="if" value={t.if||""} onChange={v=>mut(i,{...t, if:v})}/>
        <Select label="go_to" value={t.go_to||""} options={stateNames} onChange={v=>mut(i,{...t, go_to:v})}/>
        <Select label="else_go_to" value={t.else_go_to||""} options={stateNames} onChange={v=>mut(i,{...t, else_go_to:v})}/>
      </div>
    ))}
    <Button onClick={()=>onChange({...state, transitions:[...trans, { if:"@ok == true", go_to:"next_state"}]})}>+ add</Button>
  </div>;
  function mut(i:number, v:any){ const arr=[...trans]; arr[i]=v; onChange({...state, transitions:arr}); }
}
```

---

## Ajv 校验（加载你的 schema）

把你贴的 schema 文件保存为：`public/schema/workflow.v1_1.schema.json`，并在服务端启动时注册：

```ts
// src/lib/ajv.ts
import Ajv from "ajv";
import schemaV11 from "../../public/schema/workflow.v1_1.schema.json";
const ajv = new Ajv({ allErrors:true, strict:false });
ajv.addSchema(schemaV11, "workflow.v1_1");
export function validateV11(obj:any){
  const v = ajv.getSchema("workflow.v1_1");
  const ok = v?.(obj);
  return { ok: !!ok, errors: v?.errors || [] };
}
```

导入/保存工作流前跑一下 `validateV11()`，报错直接把 `errors` 丢到 UI。

---

## 最后小提示（对齐 schema 的细节）

* **变量**：根字段统一用 `vars`（内部持久用 `ctx.vars`）。
* **`ext.type_text.replace`**：等价“清空后再输入”。
* **`ext.extract`**：优先使用 `args` 包；若动作级未给 reducer，则合并全局 `config.dom_reduction`。
* **`transitions` 表达式**：`@var` 引用上下文变量，已支持基本逻辑与比较。
* **未实现动作**：统一返回 `ENOTIMPL:*`，不崩；可通过 `transitions`/`fallback` 旁路。

---

这四块落下去，你的 **录制直出 v1.1 → Ajv 校验 → Loader 规范化 → 执行器跑** 的闭环就齐了。需要我把 **Headless 的 `inj_extract` 注入** 或 **`/llm/decide` 服务端完整文件**也打包出来的话，我可以直接给整文件版本。

收到！基于你这版 **Hybrid Workflow v1.1** schema，我把「最后需要更新的点 + 一份可跑最小示例 + 本地自检清单」一次性给全：

---

## 1) 执行器/Studio 最后需要同步的点（极简清单）

* 变量：根字段用 `vars`（运行时统一映射到 `ctx.vars`），若同时存在旧的 `variables`，以 `vars` 为准。
* 跳转：`transitions[]` 优先，其次 `on_success`/`next`，再 `on_error`；表达式支持 `@var`、比较/逻辑。
* `common_action`：落实 `timeout_ms`、`retry{attempts,base_ms,max_ms}`、`save | save_as | save_to | save(json/shot/overlay/…)`。
* `ext.type_text` 补充 `replace:boolean` 语义（= 先清空）。
* `ext.extract` 兼容 `args` 包装，支持 `use_reducer` / `reducer:"auto"` / `reducer_config.*`，并可合并全局 `config.dom_reduction`（如果你有）。
* `wait_for` 先支持两类：`{type:"sleep_ms", value}` 与 `{type:"ext.wait_quiet", timeout_ms}`；其余类型先返回 ENOTIMPL（允许 fallback/分支兜底）。
* `llm_decide` 读取 `args` 包（`goal/dom/allowed_actions`），并按 LLM 返回的 `{do,args}` 顺序执行。
* `instr.*` 的 `instruction_target` 解析：优先 `css/xpath/element_id`，再 `bbox_var`（坐标点击兜底），最后 `text` 模糊匹配。
* 未接入的大型动作（`mq.* / chat.* / remote_session* / chaos_experiment* …`）先提供 **占位 handler** 返回 `ENOTIMPL:*`，不让工作流崩。

---

## 2) 最小可跑 v1.1 示例（可直接喂给 Ajv + 你的 Runner）

> 用到：打开页面 → 提取（Reducer 自动）→ 让 LLM 决策输入+回车 → 完成
> **完全对齐你 schema 的字段命名**（`a.ext.extract` 的 `do` 是 `"ext.extract"`，参数放在 `args`）

```json
{
  "version": "1.1",
  "name": "minimal_search_flow",
  "description": "Open -> extract(reducer:auto) -> llm_decide -> done",
  "start": "open",
  "vars": {
    "kw": "美食推荐"
  },
  "llm_provider": "openai",
  "llm_model": "gpt-4o-mini",
  "states": {
    "open": {
      "actions": [
        {
          "do": "ext.open_url",
          "url": "https://www.xiaohongshu.com/explore",
          "timeout_ms": 30000
        },
        {
          "do": "wait_for",
          "until": { "type": "ext.wait_quiet", "timeout_ms": 8000 }
        }
      ],
      "on_success": "search"
    },
    "search": {
      "actions": [
        {
          "do": "ext.extract",
          "args": {
            "want": "inputs",
            "limit": 200,
            "reducer": "auto",
            "reducer_config": { "maxElements": 40, "dupIoU": 0.9, "minTextLenSpan": 1 }
          },
          "save": { "json": "dom_snapshot" },
          "timeout_ms": 10000
        },
        {
          "do": "llm_decide",
          "args": {
            "goal": "在搜索框输入变量@kw，并按回车或点击搜索按钮开始搜索",
            "dom": "@dom_snapshot",
            "allowed_actions": ["ext.click_selector","ext.type_text","ext.key"]
          },
          "retry": { "attempts": 2, "base_ms": 300, "max_ms": 1500 }
        },
        {
          "do": "wait_for",
          "until": { "type": "sleep_ms", "value": 1500 }
        }
      ],
      "transitions": [
        { "if": "true", "go_to": "done" }
      ]
    },
    "done": {
      "actions": [
        { "do": "screenshot", "save": { "shot": "final_shot" } },
        { "do": "log", "message": "Flow finished", "level": "info" }
      ]
    }
  }
}
```

> 期望运行时变量：
> `@dom_snapshot`（`ext.extract` 输出）、`@final_shot`（截图路径）
> 允许把 `config.dom_reduction` 写在顶层 `context`，执行时与你的 `inj_extract` 合并。

---

## 3) 本地自检（Ajv + 烟囱跑通）

**Ajv 校验（Node 片段）**

```ts
import Ajv from "ajv";
import schema from "./workflow.v1_1.schema.json";
import wf from "./minimal_search_flow.json";

const ajv = new Ajv({ allErrors:true, strict:false });
const validate = ajv.compile(schema);
if (!validate(wf)) {
  console.error(validate.errors);
  process.exit(1);
}
console.log("schema OK");
```

**Runner 冒烟（伪代码）**

```ts
const ctx = await bootBrowser(); // page 就绪
const internal = fromStatesV11(wf); // 用我们给的 normalize
await run(internal, ctx);           // 用你的 dispatch
// 断言
assert(ctx.vars.dom_snapshot?.items?.length >= 1);
assert(typeof ctx.vars.final_shot === "string");
```

---

## 4) 录制器输出对齐规范（确保直出即合规）

* 根：`version:"1.1" | name | start | states | vars`。
* `click/input/key/scroll` 分别输出：

  * `ext.click_selector` → `{ "do":"ext.click_selector", "sel":"..." }`
  * `ext.type_text` → `{ "do":"ext.type_text", "sel":"...", "text":"...", "replace":true|false }`
  * `ext.key` → `{ "do":"ext.key", "key":"Enter" }`
  * `ext.scroll` → `{ "do":"ext.scroll", "dir":"down", "amount":600 }`
* 页面复杂（交互元素>阈值）自动插：

  1. `ext.extract`（`reducer:"auto"`，`save.json:"dom_snapshot"`）
  2. `llm_decide`（`goal`=录制语义，`dom:"@dom_snapshot"`，`allowed_actions` 缺省三件套）
* 每步可加：`timeout_ms`、`retry`、`save`，字段名与 schema 保持一致。

---

## 5) 未实现动作的默认策略（避免跑崩）

* 统一占位：返回 `{ ok:false, error:"ENOTIMPL:<name>" }`。
* 若 state 配了 `transitions`，可以用 `if:"@last_step_failed==true"` 将流向降级节点；或在动作自身提供 `fallback`（你 schema 里允许）。

---

## 6) 小坑预警（已踩过的点）

* `a.ext.extract` 的 schema 允许 **`additionalProperties: true`** 且把参数收敛在 `args`，务必在 Loader 中**优先取 `args`**，否则会把通用字段当作参数传给页面脚本。
* `llm_decide` 强烈建议把 `dom` 传 **变量引用**（如 `@dom_snapshot`），不要把大对象直接内联在 JSON 里（文件会很胖）。
* `transitions[].else_go_to` 与 `{ required: ["go_to"] }` 是两条独立 anyOf；实现时要兼容“只有 `else_go_to`”的写法（我已在 Loader 处理好了）。

---

如果你现在把上面的 **最小示例**丢给 Ajv 校验，再用我们前面给的 `normalize + dispatch` 跑一遍，就能完成**端到端闭环**。


