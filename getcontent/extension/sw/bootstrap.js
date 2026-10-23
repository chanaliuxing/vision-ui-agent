import { importPublicKeyB64, verifyEnvelope } from './verify.js';
import { kvGet, kvSet } from './db.js';
import { runEQP } from './eqp_runner.js';
import { runTask } from './task_runner.js';
import { startDaemon, stopDaemon } from './daemon.js';
import { reduceDomPayload } from '../lib/reducer.js';

let pubKey, keys, API_BASE, FEATURES = { network_sniff: true, vision_roi: false };
let ORCH_WS_URL = 'ws://127.0.0.1:8788/ws';
let ws = null; let wsConnected = false; let wsHeartbeat = null;
const TabReady = new Map(); // tabId -> true|false
const PendingMessages = new Map(); // tabId -> [{type, payload, resolve, reject}]

async function resolveAPIBase(strict = false) {
  const stored = await kvGet('api_base');
  const candidates = [stored, 'http://localhost:8787', 'http://127.0.0.1:8787'].filter(Boolean);

  for (const base of candidates) {
    try {
      const r = await fetch(`${base}/health`, { method: 'GET' });
      if (r.ok) {
        await kvSet('api_base', base);
        API_BASE = base;
        console.log('[BOOTSTRAP] API_BASE resolved to', base);
        return base;
      }
    } catch (_) {}
  }
  // Fallback: pick the first candidate so we can still try LOGIN; log a warning
  if (!strict && candidates.length) {
    API_BASE = candidates[0];
    await kvSet('api_base', API_BASE);
    console.warn('[BOOTSTRAP] Health check failed; falling back to', API_BASE);
    return API_BASE;
  }
  throw new Error('No reachable API_BASE (health check failed)');
}

async function initialize() {
  if (keys) return;
  const keysURL = chrome.runtime.getURL('keys.json');
  const response = await fetch(keysURL);
  if (!response.ok) throw new Error(`Failed to fetch keys.json: ${response.statusText}`);
  keys = await response.json();
  pubKey = await importPublicKeyB64(keys.publicKey_b64);

  // Try stored or detect
  try { await resolveAPIBase(false); } catch (e) { console.error('[BOOTSTRAP] API detection failed:', e.message); }
  console.log('Extension initialized successfully.');
  try {
    const stored = await chrome.storage.local.get(['orchestrator_ws_url']);
    if (stored?.orchestrator_ws_url) ORCH_WS_URL = stored.orchestrator_ws_url;
  } catch {}
  try { connectWS(); } catch (e) { console.warn('[BOOTSTRAP] WS connect failed', e?.message || e); }
}

async function api(path, body, method='POST') {
  await initialize();
  const sid = await kvGet('sid');
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(sid ? { 'Authorization': `Bearer ${sid}` } : {})
    },
    body: method === 'GET' ? undefined : JSON.stringify(body || {})
  });
  return res;
}

async function fetchSigned(path, body){
  await initialize();
  const res = await api(path, body, 'POST'); // includes Authorization if present
  if(!res.ok) throw new Error('HTTP '+res.status);
  const env = await res.json();
  if (!await verifyEnvelope(pubKey, env)) throw new Error('Bad signature');
  return env.payload;
}

// --- Minimal WS client (MVP) ---
async function connectWS(){
  if (ws && wsConnected) return;
  // Probe WS health to avoid noisy 404 handshake errors when WS is disabled
  try {
    const probeUrl = ORCH_WS_URL.replace('ws://', 'http://').replace('/ws', '/ws/health');
    const ctrl = new AbortController();
    const to = setTimeout(() => ctrl.abort(), 1200);
    const r = await fetch(probeUrl, { method:'GET', signal: ctrl.signal });
    clearTimeout(to);
    if (!r.ok) throw new Error('ws health http ' + r.status);
    const j = await r.json();
    if (!j || !j.ws) {
      console.warn('[WS] health says ws disabled; skipping connect');
      return;
    }
  } catch (e) {
    console.warn('[WS] probe failed; skipping connect:', e?.message || e);
    return;
  }
  try {
    ws = new WebSocket(ORCH_WS_URL);
  } catch (e) {
    console.warn('[WS] cannot create client', e?.message || e);
    return;
  }
  ws.onopen = async () => {
    wsConnected = true;
    const device_id = (await kvGet('device_id')) || null;
    const [tab] = await chrome.tabs.query({ active:true, currentWindow:true });
    let tab_id = tab?.id || null;
    // Ensure tab_id is a number
    if (typeof tab_id === 'string') tab_id = parseInt(tab_id, 10);
    if (typeof tab_id !== 'number' || tab_id <= 0) tab_id = null;
    ws.send(JSON.stringify({ type:'register', header:{ device_id, tab_id, ts: Date.now() }, ua: navigator.userAgent }));
    if (wsHeartbeat) clearInterval(wsHeartbeat);
    wsHeartbeat = setInterval(() => {
      try { ws?.readyState === 1 && ws.send(JSON.stringify({ type:'heartbeat', ts: Date.now() })); } catch {}
    }, 15000);
    console.log('[WS] connected');
  };
  ws.onclose = () => {
    wsConnected = false;
    try { if (wsHeartbeat) clearInterval(wsHeartbeat); } catch {}
    wsHeartbeat = null; ws = null;
    setTimeout(connectWS, 3000);
  };
  ws.onerror = (e) => {
    console.warn('[WS] error', e);
  };
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (!msg || typeof msg !== 'object') return;
      if (msg.type === 'action') {
        runExtAction(msg).catch(e => {
          try { ws?.send(JSON.stringify({ type:'action_result', ok:false, exec_id: msg.exec_id, action: msg.action, error: e?.message || String(e), header: msg.header || {} })); } catch {}
        });
      }
    } catch {}
  };
}

async function runExtAction(msg) {
  const header = msg.header || {};
  const exec_id = msg.exec_id;
  const action = msg.action;
  const args = msg.args || {};
  let tabId = header.tab_id || (await (async ()=>{ const [t] = await chrome.tabs.query({ active:true, currentWindow:true }); return t?.id; })());
  // Ensure tabId is a number
  if (typeof tabId === 'string') tabId = parseInt(tabId, 10);
  if (typeof tabId !== 'number' || tabId <= 0) tabId = null;
  if (!tabId) throw new Error('no_tab');

  function awaitReady(timeoutMs = 6000){
    return new Promise((resolve) => {
      const start = Date.now();
      const tick = () => {
        const ready = !!TabReady.get(tabId);
        if (ready) return resolve(true);
        if (Date.now() - start >= timeoutMs) return resolve(false);
        setTimeout(tick, 100);
      };
      tick();
    });
  }
  async function sendToCS(type, payload){
    const ready = await awaitReady(2000);
    if (!ready) {
      // Queue message and wait for CS_READY
      return new Promise((resolve, reject) => {
        const pending = PendingMessages.get(tabId) || [];
        pending.push({ type, payload, resolve, reject });
        PendingMessages.set(tabId, pending);
        
        // Set timeout for queued message
        setTimeout(() => {
          const stillPending = PendingMessages.get(tabId) || [];
          const index = stillPending.findIndex(p => p.resolve === resolve);
          if (index >= 0) {
            stillPending.splice(index, 1);
            if (stillPending.length === 0) PendingMessages.delete(tabId);
            else PendingMessages.set(tabId, stillPending);
            reject(new Error('cs_not_ready_timeout'));
          }
        }, 8000);
      });
    }
    
    const resp = await new Promise((resolve, reject) => {
      chrome.tabs.sendMessage(tabId, Object.assign({ type }, payload || {}), (resp) => {
        const err = chrome.runtime.lastError; if (err) return reject(new Error(err.message));
        resolve(resp);
      });
    });
    return resp;
  }
  
  function processPendingMessages(tabId) {
    const pending = PendingMessages.get(tabId);
    if (!pending || pending.length === 0) return;
    
    console.log(`[SW] Processing ${pending.length} pending messages for tab ${tabId}`);
    PendingMessages.delete(tabId);
    
    for (const msg of pending) {
      chrome.tabs.sendMessage(tabId, Object.assign({ type: msg.type }, msg.payload || {}), (resp) => {
        const err = chrome.runtime.lastError;
        if (err) msg.reject(new Error(err.message));
        else msg.resolve(resp);
      });
    }
  }

  let result = null;
  async function withDebugger(tabId, fn) {
    const target = { tabId };
    try {
      await chrome.debugger.attach(target, '1.3');
      const send = (method, params={}) => new Promise((resolve, reject) => {
        chrome.debugger.sendCommand(target, method, params, (res) => {
          const err = chrome.runtime.lastError; if (err) reject(new Error(err.message)); else resolve(res);
        });
      });
      const out = await fn(send);
      await chrome.debugger.detach(target);
      return out;
    } catch (e) {
      try { await chrome.debugger.detach(target); } catch {}
      throw e;
    }
  }
  switch (action) {
    case 'open_url': {
      const url = args?.url || null;
      if (!url) throw new Error('open_url requires url');
      const wantActive = !!args?.active;
      let tabId = header.tab_id || null;
      if (tabId) {
        await chrome.tabs.update(tabId, { url, active: wantActive });
      } else {
        const created = await chrome.tabs.create({ url, active: true });
        tabId = created.id;
      }
      try { if (tabId != null) TabReady.set(tabId, false); } catch {}
      result = { ok: true, tab_id: tabId };
      break;
    }
    case 'ext.wait_quiet':
      result = await sendToCS('EXT_WAIT_QUIET', { args });
      break;
    case 'ext.resolve':
      result = await sendToCS('EXT_RESOLVE', { args });
      break;
    case 'ext.extract':
      result = await sendToCS('EXT_EXTRACT', { args });
      break;
    case 'ext.click_selector':
      result = await sendToCS('EXT_CLICK_SELECTOR', { args });
      break;
    case 'ext.type_text':
      result = await sendToCS('EXT_TYPE_TEXT', { args });
      break;
    case 'ext.scroll':
      result = await sendToCS('EXT_SCROLL', { args });
      break;
    case 'ext.key':
      result = await sendToCS('EXT_KEY', { args });
      break;
    case 'ext.hover':
      result = await sendToCS('EXT_HOVER', { args });
      break;
    case 'ext.select_option':
      result = await sendToCS('EXT_SELECT_OPTION', { args });
      break;
    case 'ext.upload_file':
      // Best-effort CDP bridge: DOM.setFileInputFiles
      // args: { sel|selector, file|files }
      try {
        const files = Array.isArray(args.files) ? args.files : (args.file ? [args.file] : []);
        const selector = args.sel || args.selector;
        if (!selector || files.length === 0) throw new Error('missing selector or files');
        result = await withDebugger(tabId, async (send) => {
          // Ensure DOM domain enabled
          await send('DOM.enable');
          await send('Runtime.enable');
          const doc = await send('DOM.getDocument', { depth: 1 });
          const rootId = doc?.root?.nodeId;
          if (!rootId) throw new Error('no_root');
          const q = await send('DOM.querySelector', { nodeId: rootId, selector });
          const nodeId = q?.nodeId;
          if (!nodeId || nodeId === 0) throw new Error('not_found');
          await send('DOM.setFileInputFiles', { nodeId, files });
          return { ok: true, nodeId };
        });
      } catch (e) {
        result = { ok: false, error: String(e && e.message || e) };
      }
      break;
    case 'ext.history':
      result = await sendToCS('EXT_HISTORY', { args });
      break;
    default:
      throw new Error('unknown_action: ' + action);
  }

  try { ws?.readyState === 1 && ws.send(JSON.stringify({ type:'action_result', ok: !!(result && result.ok !== false), exec_id, action, result, header })); } catch {}
}

async function refreshEntitlement(){
  const device_id = (await kvGet('device_id')) || crypto.randomUUID();
  await kvSet('device_id', device_id);
  
  let domain = '';
  try {
    const tabs = await chrome.tabs.query({ active:true, currentWindow:true });
    if (tabs && tabs.length > 0) {
      const tab = tabs[0];
      domain = tab?.url ? new URL(tab.url).host : '';
    }
  } catch (error) {
    console.error('[BOOTSTRAP] Error getting active tab:', error);
  }
  
  const account_id = (await kvGet('account_id')) || null;
  if (!account_id) throw new Error('Not logged in');
  
  const payload = await fetchSigned('/entitlement/issue', { account_id, device_id, product_id:'yolo-llm-automation', domain });
  await kvSet('entitlement', payload);
  FEATURES = Object.assign(FEATURES, payload?.features || {});
  console.log('[BOOTSTRAP] Entitlement refreshed');
  return payload;
}

async function runPlan() {
  const t0 = Date.now();
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) throw new Error('No active tab');
  await refreshEntitlement();
  const host = new URL(tab.url).host;
  const scope = 'default';
  const plan = await fetchSigned('/plans/fetch', { page_signature:{ host }, scope });

  const result = await runEQP(plan.eqp);

  try {
    await api('/events/ingest', {
      type: 'eqp_run',
      host,
      ms: Date.now() - t0,
      counts: result.results.map(r => ({ id: r.id, ok: r.ok, count: r.count || 0 })),
    });
  } catch {}
  console.log('EQP result', result);
}

chrome.runtime.onInstalled.addListener(()=>{ console.log('Extension onInstalled'); initialize(); });

chrome.action.onClicked.addListener(async ()=>{
  try { await runPlan(); } catch(e){ console.error('Run failed', e); }
});

// Popup messages
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  (async () => {
    try {
      console.log('[BOOTSTRAP] Received message:', message.type);
      await initialize();
      switch (message.type) {
        case 'CS_READY': {
          try {
            const tabId = _sender?.tab?.id || null;
            if (tabId != null) {
              TabReady.set(tabId, true);
              console.log('[SW] CS_READY from tab', tabId);
              // Process any pending messages for this tab
              processPendingMessages(tabId);
            }
            sendResponse({ ok: true });
          } catch (e) {
            sendResponse({ ok: false, error: String(e?.message || e) });
          }
          break;
        }
        case 'GET_CONFIG': {
          sendResponse({
            orchestratorUrl: 'http://127.0.0.1:8788',
            visionApiUrl: 'http://127.0.0.1:8000',
            backendUrl: API_BASE
          });
          break;
        }
        case 'GET_STATUS': {
          try{
            const res = await api('/auth/me', null, 'GET');
            if (res.ok){ const me = await res.json(); sendResponse({ me }); }
            else sendResponse({ me: null });
          }catch{ sendResponse({ me: null }); }
          break;
        }
        case 'LOGIN': {
          const { username, password } = message;
          try { await resolveAPIBase(false); } catch (e) { /* ignore, we’ll try anyway */ }

          let res;
          try {
            res = await api('/auth/login', { username, password }); // no sid yet, but CORS/PNA OK
          } catch (e) {
            sendResponse({ ok:false, error: 'Network error: ' + e.message });
            break;
          }

          if (!res.ok) {
            sendResponse({ ok:false, error: `Login failed: HTTP ${res.status}` });
            break;
          }
          const me = await res.json();
          await kvSet('account_id', me.account_id);
          if (me.sid) await kvSet('sid', me.sid); // <- important
          await refreshEntitlement();
          sendResponse({ ok:true, me });
          break;
        }
        case 'RUN_PLAN': {
          console.log('[BOOTSTRAP] Running plan...');
          await runPlan(); 
          sendResponse({ ok: true }); 
          break;
        }
        case 'RUN_TASK': {
          const [tab] = await chrome.tabs.query({ active:true, currentWindow:true });
          const host = new URL(tab.url).host;
          await refreshEntitlement();
          const scope = message.name || 'task:auto';
          const payload = await fetchSigned('/plans/fetch', { page_signature:{ host }, scope });
          if (!payload.tasks?.tqp) throw new Error('No task plan available');

          const overrideVars = message.vars || {};
          const res = await runTask(payload.tasks.tqp, overrideVars);

          try {
            await api('/events/ingest', { type:'task_run', host, ok:res.ok, keys: Object.keys(res.outputs||{}) });
          } catch {}

          sendResponse({ ok: res.ok, reason: res.reason || null, outputs: res.outputs || null });
          break;
        }
        case 'SET_AUTO_MODE': {
          const { enabled } = message;
          await kvSet('auto_mode', enabled);
          if (enabled) {
            await startDaemon();
            console.log('[BOOTSTRAP] Auto-mode enabled, daemon started');
    } else {
      stopDaemon();
      console.log('[BOOTSTRAP] Auto-mode disabled, daemon stopped');
    }
    sendResponse({ ok: true });
    break;
  }
  case 'PAGE_STABLE': {
    try {
      const url = await getSignalUrl();
      const targetUrl = message?.url || null;
      const device_id = (await kvGet('device_id')) || null;
      let tab_id = _sender?.tab?.id || null;
      // Ensure tab_id is a number
      if (typeof tab_id === 'string') tab_id = parseInt(tab_id, 10);
      if (typeof tab_id !== 'number' || tab_id <= 0) tab_id = null;
      const ts = Date.now();
      await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ready: true, url: targetUrl, route_change: !!message?.route_change, header: { device_id, tab_id, ts } })
      });
      console.log('[SW] forwarded PAGE_STABLE to', url, 'for', targetUrl, 'hdr', { device_id, tab_id });
      // Also send over WS if available
      try { if (ws && wsConnected) ws.send(JSON.stringify({ type:'page_event', url: targetUrl, route_change: !!message?.route_change, ready: true, header: { device_id, tab_id, ts } })); } catch {}
      sendResponse({ ok: true });
    } catch (e) {
      console.warn('[SW] PAGE_STABLE forward failed:', e?.message || e);
      sendResponse({ ok: false, error: String(e?.message || e) });
    }
    break;
  }
        case 'GET_AUTO_MODE': {
          const enabled = (await kvGet('auto_mode')) || false;
          sendResponse({ enabled });
          break;
        }
        case 'TEST_VISION_API': {
          const { testVisionConnectivity } = await import('./test_integration.js');
          const result = await testVisionConnectivity();
          sendResponse(result);
          break;
        }
        case 'RUN_INTEGRATION_TEST': {
          const { runAllIntegrationTests } = await import('./test_integration.js');
          const result = await runAllIntegrationTests();
          sendResponse(result);
          break;
        }
        case 'EXT_EXTRACT_RAW': {
          try {
            const reduced = reduceDomPayload(message.payload, {
              maxElements: 50,
              dupIoU: 0.9,
              minTextLenSpan: 2,
              // profiles: { "xiaohongshu.com": { dropDigitsShort:false } } // 需要时再加
            });
            // 可选：保存最近一次，方便调试/回放
            try {
              await chrome.storage.session.set({ LAST_DOM_REDUCED: reduced });
            } catch (storageErr) {
              console.warn('[DOM REDUCER] Storage failed:', storageErr);
            }
            sendResponse(reduced);
            console.log('[DOM REDUCED]', reduced);
          } catch (e) {
            console.error('[REDUCE FAILED]', e);
            sendResponse({ _reduced: false, error: String(e) });
          }
          break;
        }
      }
    } catch(e){ 
      console.error('[BOOTSTRAP] Message handler failed:', e.message, e.stack); 
      sendResponse({ ok:false, error:e.message }); 
    }
  })();
  return true; // Async response
});

// --- Lightweight page-stable signal for local Python workflow integration ---
// When a navigation completes on target domains, ping local signal server so
// the Python workflow (wait_for: {type: 'ext_page_stable'}) can proceed.
// Configure via chrome.storage.local key 'ext_signal_url'; default to 127.0.0.1:8789.
const DEFAULT_SIGNAL_URL = 'http://127.0.0.1:8788/page_stable';
async function getSignalUrl() {
  try {
    const stored = await chrome.storage.local.get(['ext_signal_url']);
    return stored?.ext_signal_url || DEFAULT_SIGNAL_URL;
  } catch { return DEFAULT_SIGNAL_URL; }
}

chrome.webNavigation.onCompleted.addListener(async (details) => {
  try {
    const u = new URL(details.url || '');
    // limit to whitelisted domains to avoid noise
    if (!(u.host.includes('xiaohongshu.com') || u.host.includes('xhs.com'))) return;
    const url = await getSignalUrl();
    const device_id = (await kvGet('device_id')) || null;
    const ts = Date.now();
    await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ready: true, url: details.url, header: { device_id, tab_id: details.tabId || null, ts } })
    });
    console.log('[EXT] signaled page_stable to', url, 'hdr', { device_id, tab_id: details.tabId });
    try { if (ws && wsConnected) ws.send(JSON.stringify({ type:'page_event', url: details.url, ready: true, header: { device_id, tab_id: details.tabId || null, ts } })); } catch {}
  } catch (e) {
    console.warn('[EXT] page_stable signal failed:', e?.message || e);
  }
}, { url: [{ schemes: ['http', 'https'] }] });

// SPA route changes (History API) — signal readiness on route updates too
chrome.webNavigation.onHistoryStateUpdated.addListener(async (details) => {
  try {
    const u = new URL(details.url || '');
    if (!(u.host.includes('xiaohongshu.com') || u.host.includes('xhs.com'))) return;
    const url = await getSignalUrl();
    const device_id = (await kvGet('device_id')) || null;
    const ts = Date.now();
    await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ready: true, url: details.url, route_change: true, header: { device_id, tab_id: details.tabId || null, ts } })
    });
    console.log('[EXT] signaled page_stable (history) to', url, 'hdr', { device_id, tab_id: details.tabId });
    try { if (ws && wsConnected) ws.send(JSON.stringify({ type:'page_event', url: details.url, route_change: true, ready: true, header: { device_id, tab_id: details.tabId || null, ts } })); } catch {}
  } catch (e) {
    console.warn('[EXT] page_stable (history) failed:', e?.message || e);
  }
}, { url: [{ schemes: ['http', 'https'] }] });
