// Test imports one by one
console.log('[TEST] Starting import test...');

try {
  console.log('[TEST] Importing verify.js...');
  import('./verify.js').then(module => {
    console.log('[TEST] verify.js loaded:', Object.keys(module));
  }).catch(err => {
    console.error('[TEST] verify.js failed:', err);
  });
} catch (err) {
  console.error('[TEST] verify.js import error:', err);
}

try {
  console.log('[TEST] Importing db.js...');
  import('./db.js').then(module => {
    console.log('[TEST] db.js loaded:', Object.keys(module));
  }).catch(err => {
    console.error('[TEST] db.js failed:', err);
  });
} catch (err) {
  console.error('[TEST] db.js import error:', err);
}

chrome.runtime.onInstalled.addListener(() => {
  console.log('[TEST] Extension installed');
});