// Query & extract structured data inside the page (MAIN world)
export async function extractList(tabId, spec) {
  // spec: { within?, item_css, fields:[{name,type,css?,attr?}], take? }
  const res = await chrome.scripting.executeScript({
    target: { tabId, allFrames:false }, world:'MAIN',
    func: (spec) => {
      function cssAll(root, sel){ try{ return [...root.querySelectorAll(sel)]; }catch{ return []; } }
      function text(n){ return (n?.innerText || n?.textContent || '').trim(); }
      function fieldFrom(node, f){
        if (f.type === 'innerText') return text(node);
        if (f.type === 'innerHTML') return node?.innerHTML || '';
        if (f.type === 'attr') return node?.getAttribute?.(f.attr) || null;
        if (f.type === 'queryText'){ const n = node?.querySelector?.(f.css); return text(n); }
        if (f.type === 'queryAttr'){ const n = node?.querySelector?.(f.css); return n?.getAttribute?.(f.attr) || null; }
        return null;
      }
      const root = spec.within ? document.querySelector(spec.within) : document;
      const items = [];
      for (const el of cssAll(root, spec.item_css || 'div')) {
        const rec = {};
        for (const f of (spec.fields||[])) rec[f.name] = fieldFrom(el, f);
        items.push(rec);
      }
      const take = spec.take?.last_n;
      return typeof take === 'number' && take>0 ? items.slice(-take) : items;
    },
    args: [spec]
  });
  return res?.[0]?.result || [];
}

export async function extractOne(tabId, spec) {
  // spec: { selector, type: 'innerText'|'innerHTML'|'attr', attr? }
  const res = await chrome.scripting.executeScript({
    target: { tabId, allFrames:false }, world:'MAIN',
    func: (spec) => {
      const n = document.querySelector(spec.selector);
      if (!n) return null;
      if (spec.type === 'innerText') return (n.innerText || n.textContent || '').trim();
      if (spec.type === 'innerHTML') return n.innerHTML || '';
      if (spec.type === 'attr') return n.getAttribute(spec.attr) || null;
      return null;
    },
    args: [spec]
  });
  return res?.[0]?.result ?? null;
}