// extension/sw/cdp.js
// CDP helpers: DOM/AX snapshots + JSON network sniff

export async function withCDP(tabId, fn) {
  await chrome.debugger.attach({ tabId }, '1.3');
  const send = (method, params = {}) =>
    chrome.debugger.sendCommand({ tabId }, method, params);
  try {
    return await fn(send);
  } finally {
    try { await chrome.debugger.detach({ tabId }); } catch {}
  }
}

export async function captureDOMSnapshot(tabId) {
  return withCDP(tabId, send =>
    send('DOMSnapshot.captureSnapshot', {
      computedStyles: ['display', 'visibility', 'font-size', 'z-index'],
      includeDOMRects: true,
      includePaintOrder: false
    })
  );
}

export async function getAXTree(tabId) {
  return withCDP(tabId, send => send('Accessibility.getFullAXTree', {}));
}

/**
 * Sniff JSON responses for a short period.
 * @param {number} tabId
 * @param {RegExp|string} urlOrKeyPattern - URL substring or JSON key regex
 * @param {number} timeoutMs - window to listen
 * @param {number} maxBodies - cap number of bodies to fetch
 * @returns {Promise<Array<{url, mimeType, body, requestId}>>}
 */
export async function sniffJSON(tabId, urlOrKeyPattern = 'json', timeoutMs = 1500, maxBodies = 4) {
  return withCDP(tabId, async send => {
    await send('Network.enable', { maxTotalBufferSize: 8 * 1024 * 1024 });
    const responses = new Map(); // requestId -> {url, mimeType}
    const hits = [];

    function onEvent(debuggeeId, method, params) {
      if (debuggeeId.tabId !== tabId) return;
      if (method === 'Network.responseReceived') {
        const { requestId, response } = params || {};
        const url = response?.url || '';
        const mime = (response?.mimeType || '').toLowerCase();
        if (mime.includes('json') || /application\/.*json/.test(mime)) {
          responses.set(requestId, { url, mimeType: mime });
        }
      }
    }

    chrome.debugger.onEvent.addListener(onEvent);
    await new Promise(r => setTimeout(r, timeoutMs));
    chrome.debugger.onEvent.removeListener(onEvent);

    const reqIds = Array.from(responses.keys()).slice(0, maxBodies);
    for (const requestId of reqIds) {
      try {
        const bodyRes = await send('Network.getResponseBody', { requestId });
        const meta = responses.get(requestId);
        const text = bodyRes.base64Encoded
          ? atob(bodyRes.body)
          : bodyRes.body;

        // Optional: quick filter by URL substring
        let pass = true;
        if (typeof urlOrKeyPattern === 'string') {
          pass = meta.url.includes(urlOrKeyPattern);
        }

        // If string filter didn't pass, try key regex on JSON keys
        if (!pass) {
          try {
            const obj = JSON.parse(text);
            const regex = new RegExp(urlOrKeyPattern, 'i');
            pass = jsonHasKeyMatch(obj, regex);
          } catch {}
        }

        if (pass) hits.push({ url: meta.url, mimeType: meta.mimeType, body: text, requestId });
      } catch {}
    }
    return hits;
  });
}

// shallow+deep key match
function jsonHasKeyMatch(obj, regex) {
  const stack = [obj];
  while (stack.length) {
    const cur = stack.pop();
    if (cur && typeof cur === 'object') {
      for (const k of Object.keys(cur)) {
        if (regex.test(k)) return true;
        const v = cur[k];
        if (v && typeof v === 'object') stack.push(v);
      }
    }
  }
  return false;
}

export async function waitForNetworkMatch(tabId, {
  pattern = 'json',        // string URL substr or JSON key regex
  timeoutMs = 4000,
  windowMs = 1000,
  maxBodies = 3
} = {}) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const hits = await sniffJSON(tabId, pattern, windowMs, maxBodies);
    if (hits && hits.length) return { ok: true, hits };
    await new Promise(r => setTimeout(r, 200));
  }
  return { ok: false, reason: 'network_timeout' };
}