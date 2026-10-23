// Working service worker - no imports, just direct HTTP calls
console.log('[WORKING] Service worker starting...');

const API_BASE = 'http://localhost:8787';

// Simple in-memory storage (no IndexedDB to avoid import issues)
let storage = {};

async function loginPassword(username, password) {
  console.log('[WORKING] Login attempt:', username);
  const device_id = crypto.randomUUID();
  console.log('[WORKING] Device ID:', device_id);
  
  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST', 
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, device_id })
    });
    
    console.log('[WORKING] Login response status:', res.status);
    
    if (!res.ok) {
      const errorText = await res.text();
      console.error('[WORKING] Login failed:', errorText);
      throw new Error(`Login failed: ${errorText}`);
    }
    
    const data = await res.json();
    console.log('[WORKING] Login successful:', data);
    
    // Store in memory
    storage.jwt = data.token;
    storage.account_id = data.account_id;
    storage.device_id = device_id;
    
    return data;
  } catch (error) {
    console.error('[WORKING] Login error:', error);
    throw error;
  }
}

chrome.runtime.onInstalled.addListener(() => { 
  console.log('[WORKING] Extension installed');
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('[WORKING] Message received:', message.type);
  
  (async () => {
    try {
      switch (message.type) {
        case 'GET_STATUS': {
          console.log('[WORKING] GET_STATUS request');
          const hasAuth = storage.jwt && storage.account_id;
          console.log('[WORKING] Has auth:', hasAuth);
          sendResponse({ 
            entitlement: hasAuth ? { account_id: storage.account_id } : null 
          });
          break;
        }
        case 'LOGIN': {
          console.log('[WORKING] LOGIN request:', message.username);
          const { username, password } = message;
          if (!username || !password) {
            throw new Error('username/password required');
          }
          const result = await loginPassword(username, password);
          console.log('[WORKING] Sending success response');
          sendResponse({ ok: true, result });
          break;
        }
        case 'RUN_PLAN': {
          console.log('[WORKING] RUN_PLAN request (not implemented)');
          sendResponse({ ok: false, error: 'Not implemented' });
          break;
        }
        default:
          console.log('[WORKING] Unknown message type:', message.type);
          sendResponse({ ok: false, error: 'unknown message' });
      }
    } catch (e) {
      console.error('[WORKING] Message handler failed:', e);
      sendResponse({ ok: false, error: e.message });
    }
  })();
  
  return true; // Keep message channel open for async response
});