// Task Runner v3: vars + retries + post-verify + await network + emit outputs + resume upload support

import { getCard, putCard, ensureCandidates, chooseUCB, recordOutcome } from './skill_store.js';
import { clickSelector, typeSelector, waitForSelector } from './actions.js';
import { renderDeep } from './interp.js';
import { waitForNetworkMatch } from './cdp.js';
import { extractList, extractOne } from './output.js';
import { dropFileFromDataUrl, focusFileInput } from './actions_upload.js';
import { visionFallback } from './vision.js';

// Verify rules
function verifyRule(rule, contextTxt='') {
  if (!rule) return { pass:true };
  if (rule.sample_contains_any?.length) {
    const t = String(contextTxt||'').toLowerCase();
    const ok = rule.sample_contains_any.some(x => t.includes(String(x).toLowerCase()));
    if (!ok) return { pass:false, reason:'sample_not_contains' };
  }
  if (rule.min_length) {
    if ((contextTxt || '').length < rule.min_length) return { pass:false, reason:'min_length' };
  }
  return { pass:true };
}

async function sampleSelector(tabId, css) {
  const res = await chrome.scripting.executeScript({
    target: { tabId, allFrames: false },
    world:'MAIN',
    func: sel => {
      const n = document.querySelector(sel);
      return n ? (n.innerText || n.textContent || '').slice(0, 2000) : '';
    },
    args: [css]
  });
  return res?.[0]?.result || '';
}

async function postVerify(tabId, spec) {
  if (!spec) return { ok:true };
  const sample = spec.selector ? await sampleSelector(tabId, spec.selector) : '';
  const v = verifyRule(spec, sample);
  return { ok: v.pass, reason: v.reason || null, sample };
}

function* backoffSeq(attempts = 2, base = 300) {
  for (let i=0;i<attempts;i++) yield base * Math.pow(2, i); // 300, 600, 1200...
}

async function runAction(tabId, type, selector, actionSpec) {
  if (type === 'click') return clickSelector(tabId, selector);
  if (type === 'type') return typeSelector(tabId, selector, actionSpec.text || '', { replace: actionSpec.replace !== false });
  if (type === 'waitFor') return waitForSelector(tabId, selector, actionSpec.ms || 2000);
  if (type === 'uploadResumeDrop') return dropFileFromDataUrl(tabId, selector, actionSpec.data_url, actionSpec.filename || 'resume.pdf');
  if (type === 'uploadResumePrompt') return focusFileInput(tabId, selector);
  return { ok:false, reason:'unsupported_action' };
}

async function runWithRetries({ tabId, step, selector, actionSpec, postVerifySpec }) {
  const attempts = Math.max(1, step.retry?.attempts ?? 1);
  const base = Math.max(50, step.retry?.base_ms ?? 300);
  let lastRes = { ok:false, reason:'no_attempt' };
  let lastPV  = { ok:false };

  let i = 0;
  for (const ms of backoffSeq(attempts, base)) {
    i++;
    lastRes = await runAction(tabId, actionSpec.type, selector, actionSpec);
    if (!lastRes.ok) { await sleep(ms); continue; }
    // optional immediate wait
    if (step.wait_after_ms) await sleep(step.wait_after_ms);
    // post-verify
    lastPV = await postVerify(tabId, postVerifySpec);
    if (lastPV.ok) return { ok:true, res:lastRes, pv:lastPV, attempts:i };
    await sleep(ms);
  }
  return { ok:false, res:lastRes, pv:lastPV, attempts:i };
}

function sleep(ms){ return new Promise(r => setTimeout(r, ms)); }

/**
 * TQP v3:
 * steps: array of:
 *  - { wait:{selector?, ms?} }
 *  - { await_network:{pattern, timeoutMs, windowMs, maxBodies} }
 *  - { slot, candidates:[css...], action:{type:'click'|'type'|'waitFor'|'uploadResumeDrop'|'uploadResumePrompt', ...}, retry?, wait_after_ms?, post_verify? }
 *  - { verify:{selector, sample_contains_any?, min_length?} }
 *  - { emit:{ name, list?:{within?,item_css,fields[],take?}, props?:[{name,selector,type,attr?}] } }
 */
export async function runTask(tqp, overrideVars = {}) {
  const [tab] = await chrome.tabs.query({ active:true, currentWindow:true });
  if (!tab) throw new Error('No active tab');

  const sig = tqp.page_signature || { host: new URL(tab.url).host };
  const vars = Object.assign({}, tqp.vars || {}, overrideVars || {});
  const outputs = {}; // name -> object/array

  for (const rawStep of (tqp.steps || [])) {
    const step = renderDeep(rawStep, vars); // interpolate strings with {{var}}

    // WAIT block
    if (step.wait) {
      if (step.wait.selector) {
        const w = await waitForSelector(tab.id, step.wait.selector, step.wait.ms || 2000);
        if (!w.ok) return { ok:false, reason:'wait_timeout', step };
      } else if (step.wait.ms) {
        await sleep(step.wait.ms);
      }
      continue;
    }

    // AWAIT NETWORK block (can be separate or after action)
    if (step.await_network) {
      const net = await waitForNetworkMatch(tab.id, {
        pattern: step.await_network.pattern || 'json',
        timeoutMs: step.await_network.timeoutMs || 4000,
        windowMs: step.await_network.windowMs || 1000,
        maxBodies: step.await_network.maxBodies || 3
      });
      if (!net.ok) return { ok:false, reason:'network_timeout', step };
      continue;
    }

    // PURE VERIFY block
    if (step.verify && !step.slot && !step.action) {
      const pv = await postVerify(tab.id, step.verify);
      if (!pv.ok) return { ok:false, reason:'verify_fail', step, sample: pv.sample };
      continue;
    }

    // EMIT block
    if (step.emit) {
      const name = step.emit.name || 'result';
      if (step.emit.list) {
        outputs[name] = await extractList(tab.id, step.emit.list);
      }
      if (Array.isArray(step.emit.props)) {
        const obj = {};
        for (const p of step.emit.props) {
          obj[p.name] = await extractOne(tab.id, { selector: p.selector, type: p.type || 'innerText', attr: p.attr });
        }
        outputs[name] = Object.assign({}, outputs[name] || {}, obj);
      }
      continue;
    }

    // ACTION block
    if (step.slot && step.action) {
      const slot = step.slot;
      let card = await getCard(sig, slot);
      card = ensureCandidates(card, step.candidates || []);
      await putCard(sig, slot, card);

      const pick = chooseUCB(card);
      if (!pick) return { ok:false, reason:'no_candidates', step };

      // ensure actionSpec (rendered already by renderDeep)
      const actionSpec = step.action;
      // quick greedy over candidates with retries + post-verify
      let success = false, lastReason = 'action_failed', chosen = pick.expr;

      const tryOne = async (expr) => {
        const out = await runWithRetries({
          tabId: tab.id,
          step,
          selector: expr,
          actionSpec,
          postVerifySpec: step.post_verify
        });
        await recordOutcome(sig, slot, expr, out.ok);
        return out;
      };

      // 1st candidate (UCB pick)
      let out = await tryOne(pick.expr);
      success = out.ok;
      lastReason = out.ok ? null : (out.pv?.reason || out.res?.reason || 'post_verify_failed');

      // fallback to others if failed
      if (!success) {
        const rest = (card.candidates || []).filter(c => c.expr !== pick.expr);
        for (const c of rest) {
          chosen = c.expr;
          out = await tryOne(c.expr);
          success = out.ok;
          lastReason = out.ok ? null : (out.pv?.reason || out.res?.reason || 'post_verify_failed');
          if (success) break;
        }
      }

      // Vision fallback if all DOM candidates failed
      if (!success && step.allow_vision_fallback !== false) {
        console.log('[TQP] DOM candidates failed, trying vision fallback...');
        try {
          const visionOut = await visionFallback(tab.id, step, actionSpec);
          if (visionOut.ok) {
            // Post-verify vision fallback result
            if (step.post_verify) {
              const pv = await postVerify(tab.id, step.post_verify);
              if (pv.ok) {
                console.log('[TQP] Vision fallback succeeded with post-verify');
                success = true;
                chosen = 'vision_fallback';
                lastReason = null;
              } else {
                console.log('[TQP] Vision fallback succeeded but post-verify failed:', pv.reason);
                lastReason = 'vision_post_verify_failed';
              }
            } else {
              console.log('[TQP] Vision fallback succeeded');
              success = true;
              chosen = 'vision_fallback';
              lastReason = null;
            }
          } else {
            console.log('[TQP] Vision fallback also failed:', visionOut.reason);
            lastReason = visionOut.reason || 'vision_fallback_failed';
          }
        } catch (visionError) {
          console.error('[TQP] Vision fallback error:', visionError);
          lastReason = 'vision_fallback_error';
        }
      }

      if (!success) return { ok:false, reason:lastReason || 'action_failed', step, chosen };

      // AFTER-ACTION AWAIT NETWORK (optional)
      if (step.await_network_after) {
        const net = await waitForNetworkMatch(tab.id, {
          pattern: step.await_network_after.pattern || 'json',
          timeoutMs: step.await_network_after.timeoutMs || 4000,
          windowMs: step.await_network_after.windowMs || 1000,
          maxBodies: step.await_network_after.maxBodies || 3
        });
        if (!net.ok) return { ok:false, reason:'network_timeout_after', step, chosen };
      }

      continue;
    }

    // Unknown step
    return { ok:false, reason:'unknown_step', step };
  }

  return { ok:true, outputs };
}