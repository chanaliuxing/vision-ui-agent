// SkillCard store with simple UCB1 over selector candidates
import { kvGet, kvSet } from './db.js';

const K = 'skill:cards';

async function loadAll() { return (await kvGet(K)) || {}; }
async function saveAll(data) { return kvSet(K, data); }

function keyFor(pageSig, slot) {
  // pageSig = { host, path_hint? } ; slot = logical target name (e.g., 'xhs.input')
  const host = (pageSig.host || '').toLowerCase();
  const hint = (pageSig.path_hint || '').toLowerCase();
  return `${host}::${hint}::${slot}`;
}

export async function getCard(pageSig, slot) {
  const all = await loadAll();
  return all[keyFor(pageSig, slot)] || null;
}

export async function putCard(pageSig, slot, card) {
  const all = await loadAll();
  all[keyFor(pageSig, slot)] = card;
  await saveAll(all);
}

export function ensureCandidates(card, candidates) {
  // card: { candidates:[{expr, success, fail}], meta:{} }
  if (!card) card = { candidates: [], meta: {} };
  const existing = new Map(card.candidates.map(c => [c.expr, c]));
  for (const expr of candidates || []) {
    if (!existing.has(expr)) {
      card.candidates.push({ expr, success: 0, fail: 0 });
    }
  }
  return card;
}

export function chooseUCB(card) {
  const cand = (card?.candidates || []);
  if (!cand.length) return null;
  const total = cand.reduce((s, c) => s + (c.success + c.fail || 0), 0) || 1;
  const cVal = Math.sqrt(2 * Math.log(total));
  return cand
    .map(c => {
      const n = (c.success + c.fail) || 1;
      const mean = (c.success || 0) / n;
      const ucb = mean + (cVal / Math.sqrt(n));
      return { ...c, ucb };
    })
    .sort((a, b) => b.ucb - a.ucb)[0];
}

export async function recordOutcome(pageSig, slot, expr, ok) {
  const all = await loadAll();
  const k = keyFor(pageSig, slot);
  const card = all[k];
  if (!card) return;
  const idx = card.candidates.findIndex(c => c.expr === expr);
  if (idx >= 0) {
    if (ok) card.candidates[idx].success = (card.candidates[idx].success || 0) + 1;
    else card.candidates[idx].fail = (card.candidates[idx].fail || 0) + 1;
  }
  await saveAll(all);
}