// Zero imports - just test basic service worker functionality
console.log('[ZERO] Service worker starting...');

chrome.runtime.onInstalled.addListener(()=>{ 
  console.log('[ZERO] Extension installed');
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('[ZERO] Message received:', message.type);
  
  if (message.type === 'LOGIN') {
    console.log('[ZERO] LOGIN request - simulating success');
    sendResponse({ ok: true });
  } else {
    sendResponse({ ok: false, error: 'Not implemented' });
  }
  
  return true;
});