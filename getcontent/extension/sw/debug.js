// Static imports must be at the very top
import { importPublicKeyB64, verifyEnvelope } from './verify.js';
import { kvGet, kvSet } from './db.js';

// Debug service worker to test imports step by step
console.log('[DEBUG] Service worker starting...');
console.log('[DEBUG] Static imports completed successfully');
console.log('[DEBUG] Available from verify.js:', typeof importPublicKeyB64, typeof verifyEnvelope);
console.log('[DEBUG] Available from db.js:', typeof kvGet, typeof kvSet);

// Test 1: Basic service worker functionality
self.addEventListener('install', () => {
  console.log('[DEBUG] Service worker installed');
});

self.addEventListener('activate', () => {
  console.log('[DEBUG] Service worker activated');
});

console.log('[DEBUG] Debug service worker setup complete');