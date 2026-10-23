// Ultra minimal - no crypto imports, just basic HTTP calls
import { kvGet, kvSet } from './db.js';

console.log('[ULTRA] Service worker starting...');

let API_BASE = 'http://localhost:8787';

async function loginPassword(username, password){
  console.log('[ULTRA] Login attempt:', username);
  const device_id = crypto.randomUUID();
  console.log('[ULTRA] Device ID:', device_id);
  
  const res = await fetch(`${API_BASE}/auth/login`, {
    method:'POST', 
    headers:{ 'Content-Type':'application/json' },
    body: JSON.stringify({ username, password, device_id })
  });
  
  console.log('[ULTRA] Login response status:', res.status);
  
  if (!res.ok) {
    const errorText = await res.text();
    console.error('[ULTRA] Login failed:', errorText);
    throw new Error('Login failed');
  }
  
  const data = await res.json();
  console.log('[ULTRA] Login successful:', data);
  await kvSet('jwt', data.token);
  await kvSet('account_id', data.account_id);
  return data;
}

chrome.runtime.onInstalled.addListener(()=>{ 
  console.log('[ULTRA] Extension installed');
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('[ULTRA] Message received:', message.type);
  (async () => {
    try {
      switch (message.type) {
        case 'GET_STATUS': {
          console.log('[ULTRA] GET_STATUS request');
          sendResponse({ entitlement: null });
          break;
        }
        case 'LOGIN': {
          console.log('[ULTRA] LOGIN request:', message.username);
          const { username, password } = message;
          if (!username || !password) throw new Error('username/password required');
          await loginPassword(username, password);
          sendResponse({ ok: true });
          break;
        }
        case 'RUN_PLAN': {
          console.log('[ULTRA] RUN_PLAN request (not implemented)');
          sendResponse({ ok: false, error: 'Not implemented' });
          break;
        }
        default:
          console.log('[ULTRA] Unknown message type:', message.type);
          sendResponse({ ok:false, error:'unknown message' });
      }
    } catch(e){
      console.error('[ULTRA] Message handler failed:', e);
      sendResponse({ ok:false, error:e.message });
    }
  })();
  return true;
});