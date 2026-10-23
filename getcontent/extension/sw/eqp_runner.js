// extension/sw/eqp_runner.js
// Read-only EQP runner v1.5: css, by_anchor, relative_to, iterate, verify, network fallback

import { sniffJSON } from './cdp.js';
import {
  logExtractRaw, logDomReduced, logLLMRequest, logLLMResponse,
  logActionPerformed, logValidationLocal, logError, logSystem
} from '../lib/logger.js';

function arr(v) { return Array.isArray(v) ? v : (v ? [v] : []); }
function cssAll(root, sel) { try { return [...root.querySelectorAll(sel)]; } catch { return []; } }
function hasAnyClass(el, names=[]) { if (!names?.length) return false; const set = new Set((el.className||'').split(/\s+/)); return names.some(n => set.has(n)); }
function notHasAnyClass(el, names=[]) { if (!names?.length) return true; const set = new Set((el.className||'').split(/\s+/)); return names.every(n => !set.has(n)); }

function verify(rule, nodes, textSample) {
  if (!rule) return { pass: true };
  if (rule.min_count && nodes.length < rule.min_count) return { pass:false, reason:'min_count' };
  if (rule.min_length) {
    const txt = textSample ?? nodes[0]?.innerText ?? nodes[0]?.textContent ?? '';
    if ((txt || '').length < rule.min_length) return { pass:false, reason:'min_length' };
  }
  if (rule.sample_contains_any && rule.sample_contains_any.length) {
    const txt = (textSample ?? '').toLowerCase();
    const ok = rule.sample_contains_any.some(t => txt.includes(String(t).toLowerCase()));
    if (!ok) return { pass:false, reason:'sample_not_contains' };
  }
  return { pass: true };
}

function extractField(node, f) {
  if (!node) return null;
  if (f.type === 'innerText') return (node.innerText || '').trim();
  if (f.type === 'innerHTML') return (node.innerHTML || '');
  if (f.type === 'attr') return node.getAttribute(f.attr) || null;
  if (f.type === 'queryAttrAll') return cssAll(node, f.css || 'img').map(n => n.getAttribute(f.attr)).filter(Boolean);
  if (f.type === 'closestText') {
    const own = (node.innerText || '').trim();
    if (own) return own;
    const prev = node.previousElementSibling;
    return prev ? (prev.innerText || '').trim() : null;
  }
  return null;
}

function uniqueBy(arr, keyFn) {
  const seen = new Set(); const out = [];
  for (const x of arr) { const k = keyFn(x); if (seen.has(k)) continue; seen.add(k); out.push(x); }
  return out;
}

/** Anchor-based selector: find anchor text in container, then return first descendant */
function selectByAnchor(doc, by_anchor) {
  const anchors = arr(by_anchor.anchor_text);
  const containers = cssAll(doc, by_anchor.container_css || 'body');
  const out = [];
  for (const c of containers) {
    // find any descendant whose innerText includes anchor text
    const candidates = cssAll(c, by_anchor.descendant_css || '*');
    for (const n of candidates) {
      const t = (n.innerText || '').trim();
      if (!t) continue;
      for (const a of anchors) {
        if (t.toLowerCase().includes(String(a).toLowerCase())) {
          out.push(n);
          break;
        }
      }
      if (out.length) break;
    }
    if (out.length) break;
  }
  return out;
}

async function execSelectorInPage(tabId, selector, relativeMap) {
  // Runs in MAIN world; supports css | by_anchor | relative_to
  const res = await chrome.scripting.executeScript({
    target: { tabId, allFrames: true }, // collect across frames
    world: 'MAIN',
    func: (selector, rel) => {
      const arr = v => Array.isArray(v) ? v : (v ? [v] : []);
      function cssAll(root, sel) { try { return [...root.querySelectorAll(sel)]; } catch { return []; } }
      function hasAnyClass(el, names=[]) { if (!names?.length) return false; const set = new Set((el.className||'').split(/\s+/)); return names.some(n => set.has(n)); }
      function notHasAnyClass(el, names=[]) { if (!names?.length) return true; const set = new Set((el.className||'').split(/\s+/)); return names.every(n => !set.has(n)); }
      function selectByAnchor(doc, by_anchor) {
        const anchors = arr(by_anchor.anchor_text);
        const containers = cssAll(doc, by_anchor.container_css || 'body');
        const out = [];
        for (const c of containers) {
          const candidates = cssAll(c, by_anchor.descendant_css || '*');
          for (const n of candidates) {
            const t = (n.innerText || '').trim();
            if (!t) continue;
            for (const a of anchors) {
              if (t.toLowerCase().includes(String(a).toLowerCase())) { out.push(n); break; }
            }
            if (out.length) break;
          }
          if (out.length) break;
        }
        return out;
      }

      const scopeRoots = [document];
      let nodes = [];
      if (selector?.css) {
        for (const root of scopeRoots) nodes.push(...cssAll(root, selector.css));
      } else if (selector?.by_anchor) {
        nodes = selectByAnchor(document, selector.by_anchor);
      } else if (selector?.relative_to) {
        const prevId = selector.relative_to;
        const prevHTMLs = rel?.[prevId] || [];
        for (const html of prevHTMLs) {
          const guess = document.querySelector(`[data-eqp-ref="${CSS.escape(prevId)}"]`);
          // If previous step marked nodes, try relative selection within their parents
          const bases = guess ? [guess] : [document];
          for (const base of bases) {
            if (selector.css) nodes.push(...cssAll(base, selector.css));
          }
        }
      }

      // De-dupe & serialize minimal info
      nodes = nodes.filter(Boolean);
      const out = nodes.map((n, i) => ({
        _eqp_ref: `${Date.now()}_${i}`,
        _html: n.outerHTML ? n.outerHTML.slice(0, 300) : (n.nodeName || 'NODE'),
        _text: (n.innerText || '').slice(0, 300)
      }));
      return out;
    },
    args: [selector, relativeMap || {}]
  });

  // Flatten results from frames
  const flat = (res || []).flatMap(r => r.result || []);
  return flat;
}

function applyIterate(docResults, iterateSpec) {
  // docResults: array of raw nodes serialized (we only have HTML/text; DOM ops executed in page)
  // For MVP: re-run a second pass in page that targets item_css within "within" id.
  // Here we just return the first batch info; richer iteration performed via executeScript again.
  return docResults; // placeholder (we handle iterate via page func below)
}

export async function runEQP(eqp) {
  const t0 = performance.now();
  const exec_id = `eqp_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
  const task_id = eqp.task_id || exec_id;
  const phase_id = eqp.phase_id || 'dom_extraction';

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) throw new Error('No active tab');

  // Log EQP execution start
  logSystem({
    message: 'EQP execution started',
    level: 'info',
    data: {
      exec_id,
      task_id,
      phase_id,
      eqp_id: eqp.id,
      url: tab.url,
      frames_count: (eqp.frames || []).length
    }
  });

  const frames = eqp.frames || [];
  const allResults = [];
  const relativeMap = {}; // id -> minimal serialization for relative_to

  for (const fr of frames) {
    for (const q of (fr.queries || [])) {
      const step_no = allResults.length + 1;
      let pageNodes = [];

      try {
        // 1) Primary selector execution
        if (q.selector) {
          pageNodes = await execSelectorInPage(tab.id, q.selector, relativeMap);

          // Log DOM extraction
          await logExtractRaw({
            exec_id,
            task_id,
            phase_id,
            step_no,
            url: tab.url,
            payload: {
              result: {
                meta: { query_id: q.id, selector: q.selector },
                dom: { items: pageNodes }
              }
            }
          });
        }

      // 2) Iterate support (second pass inside page for fields)
      if (q.iterate) {
        const withinId = q.iterate.within; // previous query id expected
        const itemCSS = q.iterate.item_css || '*';
        const fields = q.iterate.fields || [];
        const filters = q.iterate.filters || [];
        const order = q.iterate.order_by?.rule || 'dom_order';
        const take = q.iterate.take?.last_n || null;

        // for "within", reuse selection by previous query id
        let iterResults = [];
        const execRes = await chrome.scripting.executeScript({
          target: { tabId: tab.id, allFrames: true },
          world: 'MAIN',
          func: (withinId, itemCSS, fields, filters, order, take) => {
            function cssAll(root, sel){ try{ return [...root.querySelectorAll(sel)]; }catch{ return []; } }
            function hasAnyClass(el, names=[]) { if (!names?.length) return false; const set = new Set((el.className||'').split(/\s+/)); return names.some(n => set.has(n)); }
            function notHasAnyClass(el, names=[]) { if (!names?.length) return true; const set = new Set((el.className||'').split(/\s+/)); return names.every(n => !set.has(n)); }
            function extractField(node,f){
              if (!node) return null;
              if (f.type==='innerText') return (node.innerText||'').trim();
              if (f.type==='innerHTML') return (node.innerHTML||'');
              if (f.type==='attr') return node.getAttribute(f.attr)||null;
              if (f.type==='queryAttrAll') return cssAll(node, f.css||'img').map(n=> n.getAttribute(f.attr)).filter(Boolean);
              if (f.type==='closestText'){ const own=(node.innerText||'').trim(); if(own) return own; const prev=node.previousElementSibling; return prev?(prev.innerText||'').trim():null; }
              return null;
            }

            const roots = [document]; // MVP: whole doc if we didn't mark "within" nodes in DOM; extend by data-eqp-ref mapping in future
            const items = [];
            for (const r of roots) {
              for (const n of cssAll(r, itemCSS)) {
                // filters
                let pass = true;
                for (const f of filters) {
                  if (f.has_class_includes && !hasAnyClass(n, f.has_class_includes)) pass = false;
                  if (f.not_has_class && !notHasAnyClass(n, f.not_has_class)) pass = false;
                }
                if (!pass) continue;

                const rec = {};
                for (const fld of fields) rec[fld.name] = extractField(n, fld);
                items.push(rec);
              }
            }
            // order_by dom_order: keep natural order; take last_n if set
            let out = items;
            if (typeof take === 'number' && take > 0) out = out.slice(-take);
            return out;
          },
          args: [withinId, itemCSS, fields, filters, order, take]
        });
        iterResults = (execRes || []).flatMap(r => r.result || []);

        const v = verify(q.verify, iterResults, JSON.stringify(iterResults[0] || '').slice(0, 200));

        // Log validation results for iterate
        logValidationLocal({
          exec_id,
          task_id,
          phase_id,
          step_no,
          verdict: { status: v.pass ? 'success' : 'failure', confidence: 0.8, reasons: v.reason ? [v.reason] : [] },
          criteria_matched: v.pass ? ['item_count', 'data_format'] : [],
          duration_ms: 50
        });

        allResults.push({ id: q.id || 'iterate', ok: v.pass, reason: v.reason || null, count: iterResults.length, items: iterResults });

        // update relative map (lightweight)
        relativeMap[q.id] = iterResults.slice(0, 2).map(x => JSON.stringify(x).slice(0, 200));
        continue; // go next query
      }

        // 3) Non-iterate extraction
        const v = verify(q.verify, pageNodes, pageNodes[0]?._text);
        let count = pageNodes.length;
        let items = undefined;

        // Log validation results for selectors
        logValidationLocal({
          exec_id,
          task_id,
          phase_id,
          step_no,
          verdict: { status: v.pass ? 'success' : 'failure', confidence: 0.8, reasons: v.reason ? [v.reason] : [] },
          criteria_matched: v.pass ? ['selector_match', 'element_count'] : [],
          duration_ms: 30
        });

      if (q.extract) {
        // run extraction against first matched element via page
        const execRes = await chrome.scripting.executeScript({
          target: { tabId: tab.id, allFrames: true },
          world: 'MAIN',
          func: (selector, extract) => {
            function cssAll(root, sel){ try{ return [...root.querySelectorAll(sel)]; }catch{ return []; } }
            function extractField(node,f){
              if (!node) return null;
              if (f.type==='innerText') return (node.innerText||'').trim();
              if (f.type==='innerHTML') return (node.innerHTML||'');
              if (f.type==='attr') return node.getAttribute(f.attr)||null;
              return null;
            }
            let nodes = [];
            if (selector?.css) nodes = cssAll(document, selector.css);
            const node = nodes[0] || null;
            if (!node) return null;
            return extractField(node, extract);
          },
          args: [q.selector, q.extract]
        });
        items = [(execRes || []).find(Boolean)?.result || null];
      }

        allResults.push({ id: q.id || 'sel', ok: v.pass, reason: v.reason || null, count, samples: pageNodes.slice(0, 2) });
        relativeMap[q.id] = pageNodes.slice(0, 2).map(n => n._html);

      // 4) Fallbacks (network sniff) if verify failed
      if (!v.pass && Array.isArray(q.fallback)) {
        const fb = q.fallback.find(f => f.use === 'network_sniff');
        if (fb) {
          try {
            const pattern = fb.pattern || 'json';
            const hits = await sniffJSON(tab.id, pattern, 1500, 3);
            if (hits?.length) {
              // naive JSON mining: return top-level keys matching pattern
              const mined = [];
              for (const h of hits) {
                try {
                  const obj = JSON.parse(h.body);
                  const regex = new RegExp(pattern, 'i');
                  mined.push(...mineJson(obj, regex, 24));
                } catch {}
              }
              if (mined.length) {
                allResults.push({ id: q.id + ':network', ok: true, reason: null, count: mined.length, items: mined.slice(0, 5) });
              } else {
                allResults.push({ id: q.id + ':network', ok: false, reason: 'network_no_match', count: 0 });
              }
            } else {
              allResults.push({ id: q.id + ':network', ok: false, reason: 'network_no_hits', count: 0 });
            }
          } catch (e) {
            allResults.push({ id: q.id + ':network', ok: false, reason: 'network_error', error: String(e) });
          }
        }
      }

      } catch (error) {
        // Log errors during query execution
        logError({
          exec_id,
          task_id,
          phase_id,
          step_no,
          err: error,
          context: `query_execution:${q.id}`
        });
        throw error;
      }
    }
  }

  const ms = Math.round(performance.now() - t0);

  // Log EQP execution completion
  logSystem({
    message: 'EQP execution completed',
    level: 'info',
    data: {
      exec_id,
      task_id,
      phase_id,
      duration_ms: ms,
      results_count: allResults.length,
      success_count: allResults.filter(r => r.ok).length
    }
  });

  return { results: allResults, metrics: { ms }, exec_id };
}

function mineJson(obj, regex, max = 32) {
  const out = [];
  const stack = [{ k: '', v: obj }];
  while (stack.length && out.length < max) {
    const { k, v } = stack.pop();
    if (v && typeof v === 'object') {
      for (const key of Object.keys(v)) {
        const vv = v[key];
        if (regex.test(key)) {
          out.push({ key, value: typeof vv === 'string' ? vv.slice(0, 500) : vv });
        }
        if (vv && typeof vv === 'object') stack.push({ k: key, v: vv });
      }
    }
  }
  return out;
}