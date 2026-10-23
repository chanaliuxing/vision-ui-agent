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