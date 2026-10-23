// Minimal bootstrap - only basic login functionality
import { importPublicKeyB64, verifyEnvelope } from './verify.js';
import { kvGet, kvSet } from './db.js';

console.log('[MINIMAL] Service worker starting...');

let pubKey, keys, API_BASE;

async function initialize(){
  console.log('[MINIMAL] Initialize called');
  if (keys) return;
  console.log('[MINIMAL] Fetching keys.json...');
  const keysURL = chrome.runtime.getURL('keys.json');
  const response = await fetch(keysURL);
  if (!response.ok) throw new Error('Failed to fetch keys.json');
  keys = await response.json();
  console.log('[MINIMAL] Keys loaded, importing public key...');
  pubKey = await importPublicKeyB64(keys.publicKey_b64);
  API_BASE = (await kvGet('api_base')) || 'http://localhost:8787';
  console.log('[MINIMAL] Initialize complete, API_BASE:', API_BASE);
}

async function loginPassword(username, password){
  console.log('[MINIMAL] Login attempt:', username);
  const device_id = (await kvGet('device_id')) || crypto.randomUUID();
  await kvSet('device_id', device_id);
  console.log('[MINIMAL] Device ID:', device_id);
  
  const res = await fetch(`${API_BASE}/auth/login`, {
    method:'POST', 
    headers:{ 'Content-Type':'application/json' },
    body: JSON.stringify({ username, password, device_id })
  });
  
  console.log('[MINIMAL] Login response status:', res.status);
  
  if (!res.ok) {
    const errorText = await res.text();
    console.error('[MINIMAL] Login failed:', errorText);
    throw new Error('Login failed');
  }
  
  const data = await res.json();
  console.log('[MINIMAL] Login successful:', data);
  await kvSet('jwt', data.token);
  await kvSet('account_id', data.account_id);
  return data;
}

chrome.runtime.onInstalled.addListener(()=>{ 
  console.log('[MINIMAL] Extension installed, initializing...');
  initialize().catch(err => {
    console.error('[MINIMAL] Initialize failed:', err);
  }); 
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('[MINIMAL] Message received:', message.type);
  (async () => {
    try {
      await initialize();
      switch (message.type) {
        case 'GET_STATUS': {
          console.log('[MINIMAL] GET_STATUS request');
          const entitlement = await kvGet('entitlement');
          sendResponse({ entitlement });
          break;
        }
        case 'LOGIN': {
          console.log('[MINIMAL] LOGIN request:', message.username);
          const { username, password } = message;
          if (!username || !password) throw new Error('username/password required');
          await loginPassword(username, password);
          sendResponse({ ok: true });
          break;
        }
        case 'RUN_PLAN': {
          console.log('[MINIMAL] RUN_PLAN request (not implemented)');
          sendResponse({ ok: false, error: 'Not implemented in minimal version' });
          break;
        }
        default:
          console.log('[MINIMAL] Unknown message type:', message.type);
          sendResponse({ ok:false, error:'unknown message' });
      }
    } catch(e){
      console.error('[MINIMAL] Message handler failed:', e);
      sendResponse({ ok:false, error:e.message });
    }
  })();
  return true;
});