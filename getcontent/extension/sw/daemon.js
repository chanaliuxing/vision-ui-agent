import { kvGet, kvSet } from './db.js';
import { runTask } from './task_runner.js';

let API_BASE = null;
let running = false;
let current = null;

async function ensureAPI() {
  if (!API_BASE) API_BASE = (await kvGet('api_base')) || 'http://localhost:8787';
  return API_BASE;
}

async function api(path, body) {
  if (!API_BASE) API_BASE = (await kvGet('api_base')) || 'http://localhost:8787';
  const sid = await kvGet('sid'); // <-- read sid
  const res = await fetch(`${API_BASE}${path}`, {
    method:'POST',
    credentials:'include', // harmless; header is what authorizes us
    headers:{
      'Content-Type':'application/json',
      ...(sid ? { 'Authorization': `Bearer ${sid}` } : {})
    },
    body: JSON.stringify(body||{})
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} ${path}`);
  return res.json();
}

async function heartbeat() {
  const device_id = (await kvGet('device_id')) || crypto.randomUUID();
  await kvSet('device_id', device_id);
  const ua = navigator.userAgent;
  try { await api('/devices/heartbeat', { device_id, ua }); } catch {}
  return device_id;
}

async function claimNext() {
  const device_id = await heartbeat();
  const { cmd } = await api('/commands/next', { device_id });
  return cmd || null;
}

async function collectSnapshot(tabId) {
  const res = await chrome.scripting.executeScript({
    target: { tabId, allFrames: false }, world:'MAIN',
    func: () => {
      function getUniqueSelector(el){
        if (el.id) return `#${CSS.escape(el.id)}`;
        const parts=[]; let cur=el;
        while(cur && cur.nodeType===1 && parts.length<4){
          const name = cur.tagName.toLowerCase();
          const cls = (cur.className||'').split(/\s+/).filter(Boolean).slice(0,2).map(c=>'.'+CSS.escape(c)).join('');
          parts.unshift(name+cls);
          cur = cur.parentElement;
        }
        return parts.join(' > ');
      }
      const items = [];
      const root = document.body;
      const els = root.querySelectorAll('a, div, li, [role=listitem]');
      for (const el of els) {
        const txt = (el.innerText || '').trim();
        if (!txt) continue;
        const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue;
        const score = (/\d{1,2}:\d{2}|今天|昨天/.test(txt) ? 1 : 0) + (el.querySelector('img')?1:0);
        items.push({ tag: el.tagName, class: el.className, text: txt.slice(0, 200), selector: getUniqueSelector(el), score });
      }
      const inputs = [...document.querySelectorAll('textarea, div[contenteditable="true"]')].map(n=>({text:n.getAttribute('placeholder')||'', selector:getUniqueSelector(n)}));
      const sends  = [...document.querySelectorAll('button, [role=button], a')].map(n=>{
        const t = (n.innerText || n.getAttribute('aria-label') || '').trim();
        return { text: t, selector: getUniqueSelector(n) };
      });
      return { host: location.host, path: location.pathname, list: items.slice(0,200), inputs: inputs.slice(0,20), sends: sends.slice(0,50) };
    }
  });
  return res?.[0]?.result || null;
}

function onNavCompleted(cb) {
  chrome.webNavigation.onCompleted.addListener(cb, { url: [{ schemes: ['http','https'] }] });
}
function offNavCompleted(cb) {
  try { chrome.webNavigation.onCompleted.removeListener(cb); } catch {}
}

async function waitForTabLoad(tabId, matchUrl) {
  return new Promise((resolve) => {
    const listener = (details) => {
      if (details.tabId !== tabId) return;
      try {
        const want = new URL(matchUrl);
        const seen = new URL(details.url || '');
        if (seen.host.endsWith(want.host)) {
          offNavCompleted(listener); resolve(true);
        }
      } catch { offNavCompleted(listener); resolve(true); }
    };
    onNavCompleted(listener);
    setTimeout(() => { offNavCompleted(listener); resolve(true); }, 15000);
  });
}

async function ensureTab(url) {
  const [active] = await chrome.tabs.query({ active:true, currentWindow:true });
  if (active && active.url) {
    const a = new URL(active.url); const u = new URL(url);
    if (a.host === u.host) {
      if (a.pathname !== u.pathname) await chrome.tabs.update(active.id, { url, active: true });
      await waitForTabLoad(active.id, url);
      return active.id;
    }
  }
  const tabId = (await chrome.tabs.create({ url })).id;
  await waitForTabLoad(tabId, url);
  return tabId;
}

async function ensureOffscreen(reason='run') {
  if (!chrome.offscreen?.createDocument) return;
  try {
    const has = await chrome.offscreen.hasDocument();
    if (!has) {
      await chrome.offscreen.createDocument({
        url: chrome.runtime.getURL('offscreen.html'),
        reasons: ['BLOBS'],
        justification: `Keepalive for ${reason}`
      });
    }
  } catch {}
}
async function closeOffscreen() {
  if (!chrome.offscreen?.closeDocument) return;
  try { await chrome.offscreen.closeDocument(); } catch {}
}

async function runCommand(cmd) {
  current = cmd;
  await ensureOffscreen('command');
  await api('/commands/ack', { id: cmd.id, status: 'running' });

  try {
    let tabId = null;
    if (cmd.url) tabId = await ensureTab(cmd.url);
    else {
      const [tab] = await chrome.tabs.query({ active:true, currentWindow:true });
      if (!tab) throw new Error('No active tab');
      tabId = tab.id;
    }

    // collect snapshot for resolver
    const snapshot = await collectSnapshot(tabId);

    let tqp = null;
    if (cmd.type === 'xhs_reply') {
      const payload = await api('/resolve/xhs_reply', {
        target_name: cmd.vars?.target_name,
        reply_text: cmd.vars?.reply_text,
        snapshot
      });
      tqp = payload?.tqp || null;
    } else if (cmd.scope?.startsWith('task:')) {
      // If you need direct task, fetch signed plan (already supported by your backend)
      const host = new URL((await chrome.tabs.get(tabId)).url).host;
      const res = await api('/plans/fetch', { page_signature:{ host }, scope: cmd.scope });
      tqp = res?.tasks?.tqp || null;
    }

    if (!tqp) throw new Error('no_task_plan');

    const out = await runTask(tqp, cmd.vars || {});
    if (out.ok) await api('/commands/ack', { id: cmd.id, status:'succeeded', result: out.outputs || {} });
    else        await api('/commands/ack', { id: cmd.id, status:'failed', error: out.reason || 'task_failed', result: out.outputs || {} });
  } catch (e) {
    await api('/commands/ack', { id: cmd.id, status:'failed', error: e.message });
  } finally {
    current = null;
    await closeOffscreen();
  }
}

let POLL_MS = 5000;
let pollTimer = null;

async function pollLoop() {
  if (!running) return;
  try {
    if (!current) {
      const cmd = await claimNext();
      if (cmd) await runCommand(cmd);
    }
  } catch (e) {
    console.warn('[daemon] poll error', e.message);
  } finally {
    pollTimer = setTimeout(pollLoop, POLL_MS);
  }
}

export async function startDaemon() {
  running = true;
  clearTimeout(pollTimer);
  await heartbeat();
  await ensureOffscreen('startup');
  pollLoop();
  chrome.alarms.create('daemon_heartbeat', { periodInMinutes: 1 });
}

export function stopDaemon() {
  running = false;
  clearTimeout(pollTimer);
  try { chrome.alarms.clear('daemon_heartbeat'); } catch {}
  closeOffscreen();
}

chrome.alarms.onAlarm.addListener(async (a)=>{
  if (a.name === 'daemon_heartbeat' && running) {
    await heartbeat();
    if (!current) pollLoop();
  }
});