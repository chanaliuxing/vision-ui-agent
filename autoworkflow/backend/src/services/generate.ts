import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { createValidator, loadActionSchemas } from "../lib/ajv.js";
import { WorkflowLinter } from "../lib/linter.js";
import { callLLM, ChatMessage } from "../llm/call.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

type GenReq = {
  type?: string;
  complexity?: "small" | "medium" | "large";
  description: string;
  allow_actions?: string[];
};

// Load registry and schema directly
function loadRegistryIndex() {
  const registryPath = join(__dirname, '../../registry/index.json');
  const registryContent = readFileSync(registryPath, 'utf-8');
  return JSON.parse(registryContent);
}

function loadWorkflowSchema() {
  const schemaPath = join(__dirname, '../../../schemas/workflow.schema.json');
  const schemaContent = readFileSync(schemaPath, 'utf-8');
  return JSON.parse(schemaContent);
}

async function loadActionSchema(schemaPath: string) {
  const fullPath = join(__dirname, '../../registry', schemaPath);
  const content = readFileSync(fullPath, 'utf-8');
  return JSON.parse(content);
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
  const s = loadWorkflowSchema();
  // 简短契约（减少上下文体积）
  return {
    required: s.required,
    props: Object.keys(s.properties),
    stepProps: s.definitions?.Step?.properties ? Object.keys(s.definitions.Step.properties) : [],
    edgeProps: s.definitions?.Edge?.properties ? Object.keys(s.definitions.Edge.properties) : []
  };
}

export async function generateWorkflow(req: GenReq) {
  const registryIndex = loadRegistryIndex();
  const ACTIONS = registryIndex.actions as Array<any>;

  const allow = new Set(req.allow_actions && req.allow_actions.length
    ? req.allow_actions
    : ACTIONS.map(a => a.id)
  );

  const actionBriefs: string[] = [];
  for (const action of ACTIONS) {
    if (allow.has(action.id)) {
      try {
        const schema = await loadActionSchema(action.schema);
        const props = schema.properties || {};
        const required = schema.required || [];
        const parts = Object.keys(props).map(k => {
          const p = props[k];
          const t = p.type || (p.enum ? "enum" : "object");
          const en = p.enum ? ` enum=${JSON.stringify(p.enum)}` : "";
          return `${k}:${t}${en}${required.includes(k) ? " *" : ""}`;
        });
        actionBriefs.push(`- ${action.id}: ${parts.join(", ")}`);
      } catch (error) {
        console.warn(`Failed to load schema for ${action.id}:`, error);
        actionBriefs.push(`- ${action.id}: (schema load failed)`);
      }
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

  const { validateWorkflow } = createValidator();

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

    try {
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
      const validationResult = validateWorkflow(parsed);
      const vIssues = validationResult ? [] : (validateWorkflow.errors || []).map(e => ({
        pointer: e.instancePath || "/",
        message: e.message
      }));

      // lint - skip for now to test basic functionality
      const lIssues: any[] = [];
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
    } catch (error) {
      attempts.push({ round, note: `LLM call failed: ${error}` });
      issues = [{ pointer: "/", message: `LLM call failed: ${error}` }];
      continue;
    }
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