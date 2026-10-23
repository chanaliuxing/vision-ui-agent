// Absolutely minimal service worker
console.log('[TEST-SW] Service worker started');

self.addEventListener('install', () => {
  console.log('[TEST-SW] Extension installed');
});

self.addEventListener('activate', () => {
  console.log('[TEST-SW] Extension activated');
});