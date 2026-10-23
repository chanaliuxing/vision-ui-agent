import express from 'express';
import { q } from '../lib/db.js';

const router = express.Router();

function fuzzyScore(name, candidateText){
  name = String(name||'').toLowerCase();
  const t = String(candidateText||'').toLowerCase();
  if (!name || !t) return 0;
  let s = 0;
  if (t.includes(name)) s += 5;
  if (/\d{1,2}:\d{2}|今天|昨天/.test(t)) s += 1;
  return s;
}

async function llmPickOpenAI(apiKey, targetName, snapshot){
  if (!apiKey) return null;
  try {
    const system = `You pick UI selectors from candidate lists. Return JSON: {"thread_selector":"","input_selector":"","send_selector":""}.`;
    const user = {
      target_name: targetName,
      candidates: {
        threads: (snapshot?.list||[]).slice(0,50).map(x => ({ selector:x.selector, text:x.text, score:x.score })),
        inputs: snapshot?.inputs || [],
        sends:  snapshot?.sends  || []
      }
    };
    const r = await fetch('https://api.openai.com/v1/chat/completions',{
      method:'POST',
      headers:{'Content-Type':'application/json','Authorization':`Bearer ${apiKey}`},
      body: JSON.stringify({
        model: 'gpt-4o-mini',
        temperature: 0,
        response_format: { type:'json_object' },
        messages: [
          { role:'system', content: system },
          { role:'user', content: JSON.stringify(user) }
        ]
      })
    });
    if (!r.ok) throw new Error('LLM HTTP '+r.status);
    const j = await r.json();
    const text = j.choices?.[0]?.message?.content || '{}';
    return JSON.parse(text);
  } catch (e) {
    console.warn('[resolve] LLM failed:', e.message);
    return null;
  }
}

router.post('/resolve/xhs_reply', async (req, res) => {
  const { target_name, reply_text, snapshot } = req.body || {};
  if (!target_name || !reply_text) return res.status(400).json({ error:'missing params' });

  // Heuristic candidates from snapshot (if present)
  const candidates = (snapshot?.list || [])
    .map(c => ({ ...c, _score: fuzzyScore(target_name, c.text) + (c.score||0) }))
    .sort((a,b)=> b._score - a._score);

  const llm = await llmPickOpenAI(process.env.OPENAI_API_KEY, target_name, snapshot || { list:[], inputs:[], sends:[] });

  const threadSel = llm?.thread_selector || candidates[0]?.selector || 'a, [role=listitem]';
  const inputSel  = llm?.input_selector  || (snapshot?.inputs?.[0]?.selector || 'textarea, div[contenteditable="true"]');
  const sendSel   = llm?.send_selector   || (snapshot?.sends?.find(s=>/send|发|回复/i.test(s.text))?.selector || 'button');

  const tqp = {
    page_signature: { host: 'xhs.com', path_hint: '/im' },
    vars: { reply_text },
    steps: [
      { wait: { selector: 'main, #root, [role="main"]', ms: 2500 } },
      { slot:'open_thread', candidates: [threadSel], action:{ type:'click' }, retry:{ attempts:2, base_ms:300 }, wait_after_ms: 300 },
      { slot:'input', candidates: [inputSel, 'textarea', 'div[contenteditable="true"]'], action:{ type:'type', text:'{{reply_text}}', replace:true }, retry:{ attempts:2, base_ms:300 }, post_verify:{ selector: `${inputSel}, textarea, div[contenteditable="true"]`, min_length: 2 } },
      { slot:'send',  candidates: [sendSel, "button:has(svg[aria-label*='send'])", "button[aria-label*='发送']", "button.send", ".btn-send"], action:{ type:'click' }, retry:{ attempts:2, base_ms:300 }, await_network_after:{ pattern:'message|conversation', timeoutMs: 3000, windowMs: 600 } },
      { wait: { ms: 500 } },
      { emit: { name:'messages', list: { within: "main, #root, [role='main']", item_css: "div.message, li.msg, [data-role='message']", fields:[ {name:'dir', type:'queryAttr', css:':scope', attr:'class'}, {name:'text', type:'innerText'} ], take:{ last_n:5 } } } },
      { verify: { selector: ".message.outgoing:last-child, .msg.right:last-child, [data-role='message'].outgoing:last-child", sample_contains_any: [reply_text.slice(0, Math.min(6, reply_text.length))] } }
    ]
  };

  try {
    await q(
      `INSERT INTO events(account_id, type, host, payload)
       VALUES ($1,$2,$3,$4)`,
      [req.session?.account_id || null, 'resolve_xhs', snapshot?.host || 'xhs.com', { target_name, threadSel, inputSel, sendSel }]
    );
  } catch {}

  res.json({ tqp, debug: { picked: { threadSel, inputSel, sendSel }, topCandidates: candidates.slice(0,5) } });
});

export default router;