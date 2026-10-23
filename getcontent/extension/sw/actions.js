// DOM action helpers executed via chrome.scripting in MAIN world

async function runInPage(tabId, fn, args=[]) {
  const res = await chrome.scripting.executeScript({
    target: { tabId, allFrames: false },
    world: 'MAIN',
    func: fn,
    args
  });
  return res?.[0]?.result;
}

export async function clickSelector(tabId, selector) {
  return runInPage(tabId, (sel) => {
    try {
      const el = document.querySelector(sel);
      if (!el) return { ok:false, reason:'not_found' };
      el.scrollIntoView({ block:'center', inline:'center' });
      const r = el.getBoundingClientRect();
      (el instanceof HTMLElement) && el.click();
      return { ok:true, bbox:{ x:r.x, y:r.y, w:r.width, h:r.height } };
    } catch (e) {
      return { ok:false, reason: String(e) };
    }
  }, [selector]);
}

export async function typeSelector(tabId, selector, text, { replace=true } = {}) {
  return runInPage(tabId, (sel, txt, replace) => {
    try {
      const el = document.querySelector(sel);
      if (!el) return { ok:false, reason:'not_found' };
      el.scrollIntoView({ block:'center', inline:'center' });
      (el instanceof HTMLElement) && el.focus();
      if ('value' in el) {
        if (replace) el.value = '';
        el.value += txt;
        el.dispatchEvent(new Event('input', { bubbles:true }));
        el.dispatchEvent(new Event('change', { bubbles:true }));
      } else {
        // contenteditable
        el.textContent = (replace ? '' : (el.textContent || '')) + txt;
        el.dispatchEvent(new Event('input', { bubbles:true }));
      }
      return { ok:true };
    } catch (e) {
      return { ok:false, reason:String(e) };
    }
  }, [selector, text, replace]);
}

export async function waitForSelector(tabId, selector, timeoutMs=2000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const ok = await runInPage(tabId, sel => !!document.querySelector(sel), [selector]);
    if (ok) return { ok:true };
    await new Promise(r => setTimeout(r, 120));
  }
  return { ok:false, reason:'timeout' };
}