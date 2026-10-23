import Ajv from "ajv";
import addFormats from "ajv-formats";
import fs from "fs";
import path from "path";
import { OpenAI } from "openai";
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

function loadSchema(name) {
  const p = path.join(__dirname, "schema", name + ".json");
  return JSON.parse(fs.readFileSync(p, "utf-8"));
}
function loadPrompt(name) {
  const p = path.join(__dirname, "prompts", name + ".txt");
  return fs.readFileSync(p, "utf-8");
}

function mustJSON(s) {
  // 粗暴提取第一段 JSON
  const start = s.indexOf("{");
  const end = s.lastIndexOf("}");
  if (start >= 0 && end > start) {
    const sub = s.slice(start, end + 1);
    try { return JSON.parse(sub); } catch(e) {}
  }
  // 退化：返回一个最小对象
  return { reply_text: String(s).trim() };
}

async function callMock(job) {
  const nm = job.inputs?.new_messages?.[0]?.contact || "客户";
  return { contact_name: nm, reply_text: `你好，${nm}，我在的哈～请问想了解哪款车？` };
}

async function callOpenAI(job, promptPack) {
  const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
  const tpl = loadPrompt(promptPack);
  const inputs_json = JSON.stringify(job.inputs, null, 2);
  const content = tpl.replace("{{inputs_json}}", inputs_json);

  const res = await client.chat.completions.create({
    model: process.env.OPENAI_MODEL || "gpt-4o-mini",
    messages: [
      { role: "system", content: "You output only JSON that matches the given schema." },
      { role: "user", content }
    ],
    temperature: 0.3
  });
  const text = res.choices?.[0]?.message?.content || "{}";
  return mustJSON(text);
}

function makeValidator(schemaName) {
  const ajv = new Ajv({ allErrors: true, strict: false });
  addFormats(ajv);
  const schema = loadSchema(schemaName);
  const validate = ajv.compile(schema);
  return { validate, schema };
}

async function routeAndValidate(job) {
  const { schema: schemaName, prompt_pack: promptPack, provider_hint } = job;
  const { validate } = makeValidator(schemaName);
  let out;

  if (process.env.MOCK_LLM === "1" || provider_hint === "mock") {
    out = await callMock(job);
  } else if ((provider_hint || "").toLowerCase() === "openai") {
    out = await callOpenAI(job, promptPack);
  } else {
    // 你可以在这里接入 deepseek/anthropic，暂时 fallback 到 mock
    out = await callMock(job);
  }

  // 一轮修复与重试
  if (!validate(out)) {
    // 简单自愈：如果只有 reply_text，补齐 contact_name
    if (out.reply_text && !out.contact_name) {
      const nm = job.inputs?.new_messages?.[0]?.contact || "客户";
      out.contact_name = nm;
    }
  }
  if (!validate(out)) {
    // 最终兜底
    const nm = job.inputs?.new_messages?.[0]?.contact || "客户";
    out = { contact_name: nm, reply_text: "好的，我已收到您的消息，稍后详细回复您～" };
  }
  return out;
}

export { routeAndValidate };