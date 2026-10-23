/**
 * 失败恢复和黑名单系统
 * 实现"失败→介入→回退→拉黑→继续"的闭环
 */

import { validateLocal, makeDiff, genId } from './validator.js';
import { reduceDomPayload } from './reducer.js';

/**
 * @typedef {[number, number, number, number]} BBox
 */

/**
 * @typedef {Object} TargetSig
 * @property {string} role
 * @property {string} [label]
 * @property {string} [href]
 * @property {string} [id]
 * @property {BBox} [bbox]
 */

/**
 * @typedef {Object} PageSig
 * @property {string} host
 * @property {string} urlPathHash
 * @property {string} domHash
 */

/**
 * @typedef {Object} PhaseKey
 * @property {string} task_id
 * @property {string} phase_id
 */

/**
 * @typedef {Object} BlacklistEntry
 * @property {PhaseKey} phase
 * @property {PageSig} page
 * @property {TargetSig} target
 * @property {"validation_fail"|"llm_miss"|"user_abort"} reason
 * @property {number} ts
 * @property {number} ttl_ms
 * @property {number} hits
 * @property {number} max_hits
 */

// 内存黑名单存储（生产环境应使用IndexedDB）
const blacklistStorage = new Map();

/**
 * 生成页面签名
 * @param {import('./pav-types.js').ReducedDom} ctx
 * @returns {PageSig}
 */
function pageSignature(ctx) {
  try {
    const url = new URL(ctx.url);
    const pathHash = hashString(url.pathname + url.search);
    
    // 使用前10个元素生成DOM hash
    const domElements = ctx.elements.slice(0, 10)
      .map(el => `${el.role}:${el.label}:${el.href || ''}`)
      .join('|');
    const domHash = hashString(domElements);
    
    return {
      host: url.hostname,
      urlPathHash: pathHash,
      domHash
    };
  } catch (e) {
    return {
      host: ctx.url,
      urlPathHash: hashString(ctx.url),
      domHash: hashString('unknown')
    };
  }
}

/**
 * 生成目标签名
 * @param {Object} target
 * @returns {TargetSig}
 */
function targetSignature(target) {
  return {
    role: target.element?.role || '',
    label: target.element?.label || '',
    href: target.element?.href || '',
    id: target.element?.id || '',
    bbox: target.element?.bbox
  };
}

/**
 * 简单哈希函数
 * @param {string} str
 * @returns {string}
 */
function hashString(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return Math.abs(hash).toString(36);
}

/**
 * 检查目标是否在黑名单中
 * @param {PhaseKey} phase
 * @param {PageSig} page
 * @param {TargetSig} target
 * @returns {boolean}
 */
export function isBlacklisted(phase, page, target) {
  const key = `${phase.task_id}:${phase.phase_id}:${page.host}:${page.urlPathHash}:${page.domHash}`;
  const entries = blacklistStorage.get(key) || [];
  
  const now = Date.now();
  
  for (const entry of entries) {
    // 检查TTL
    if (now > entry.ts + entry.ttl_ms) {
      continue; // 过期
    }
    
    // 检查是否超过最大命中次数
    if (entry.hits >= entry.max_hits) {
      return true; // 永久拉黑
    }
    
    // 相似度匹配
    if (isSimilarTarget(target, entry.target)) {
      return true;
    }
  }
  
  return false;
}

/**
 * 判断目标相似度
 * @param {TargetSig} a
 * @param {TargetSig} b
 * @returns {boolean}
 */
function isSimilarTarget(a, b) {
  // 角色必须相同
  if (a.role !== b.role) return false;
  
  // 文本Jaccard相似度 >= 0.9
  if (a.label && b.label) {
    const similarity = textJaccard(a.label, b.label);
    if (similarity >= 0.9) return true;
  }
  
  // href同源同path
  if (a.href && b.href) {
    try {
      const urlA = new URL(a.href);
      const urlB = new URL(b.href);
      if (urlA.origin === urlB.origin && urlA.pathname === urlB.pathname) {
        return true;
      }
    } catch (e) {
      if (a.href === b.href) return true;
    }
  }
  
  // bbox IoU >= 0.85
  if (a.bbox && b.bbox) {
    const iou = calculateIoU(a.bbox, b.bbox);
    if (iou >= 0.85) return true;
  }
  
  return false;
}

/**
 * 计算文本Jaccard相似度
 * @param {string} a
 * @param {string} b
 * @returns {number}
 */
function textJaccard(a, b) {
  const setA = new Set(a.toLowerCase().split(/\W+/).filter(Boolean));
  const setB = new Set(b.toLowerCase().split(/\W+/).filter(Boolean));
  
  const intersection = new Set([...setA].filter(x => setB.has(x)));
  const union = new Set([...setA, ...setB]);
  
  return union.size ? intersection.size / union.size : 0;
}

/**
 * 计算IoU
 * @param {BBox} a
 * @param {BBox} b
 * @returns {number}
 */
function calculateIoU(a, b) {
  const [ax1, ay1, ax2, ay2] = a;
  const [bx1, by1, bx2, by2] = b;
  
  const ix1 = Math.max(ax1, bx1);
  const iy1 = Math.max(ay1, by1);
  const ix2 = Math.min(ax2, bx2);
  const iy2 = Math.min(ay2, by2);
  
  const iw = Math.max(0, ix2 - ix1);
  const ih = Math.max(0, iy2 - iy1);
  const inter = iw * ih;
  
  if (inter <= 0) return 0;
  
  const aArea = (ax2 - ax1) * (ay2 - ay1);
  const bArea = (bx2 - bx1) * (by2 - by1);
  
  return inter / (aArea + bArea - inter);
}

/**
 * 添加到黑名单
 * @param {PhaseKey} phase
 * @param {PageSig} page
 * @param {TargetSig} target
 * @param {Object} meta
 */
export function addToBlacklist(phase, page, target, meta) {
  const key = `${phase.task_id}:${phase.phase_id}:${page.host}:${page.urlPathHash}:${page.domHash}`;
  const entries = blacklistStorage.get(key) || [];
  
  const entry = {
    phase,
    page,
    target,
    reason: meta.reason || 'validation_fail',
    ts: Date.now(),
    ttl_ms: meta.ttl_ms || 7 * 24 * 3600 * 1000, // 7天
    hits: 1,
    max_hits: meta.max_hits || 3
  };
  
  // 检查是否已存在类似条目
  let found = false;
  for (const existing of entries) {
    if (isSimilarTarget(target, existing.target)) {
      existing.hits++;
      existing.ts = Date.now(); // 更新时间
      found = true;
      break;
    }
  }
  
  if (!found) {
    entries.push(entry);
  }
  
  blacklistStorage.set(key, entries);
  console.log(`[RECOVERY] Added to blacklist: ${target.label} (hits: ${entry.hits})`);
}

/**
 * 回退到上一个状态
 * @returns {Promise<void>}
 */
export async function rollbackToPrevious() {
  console.log('[RECOVERY] Starting rollback');
  
  // 1. 检测遮罩/弹窗
  try {
    const modals = await chrome.tabs.executeScript({
      code: `
        const modals = document.querySelectorAll('.modal, .dialog, [role="dialog"], .popup, .overlay');
        const hasModals = modals.length > 0;
        if (hasModals) {
          // 尝试点击关闭按钮
          const closeButtons = document.querySelectorAll('.modal .close, .dialog .close, [data-dismiss], .modal-close');
          if (closeButtons.length > 0) {
            closeButtons[0].click();
            'modal_closed';
          } else {
            // 尝试ESC键
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
            'esc_pressed';
          }
        } else {
          'no_modal';
        }
      `
    });
    
    if (modals[0] !== 'no_modal') {
      console.log('[RECOVERY] Handled modal:', modals[0]);
      return;
    }
  } catch (e) {
    console.warn('[RECOVERY] Modal detection failed:', e);
  }
  
  // 2. 寻找返回按钮
  try {
    const backButton = await chrome.tabs.executeScript({
      code: `
        const backButtons = [...document.querySelectorAll('*')]
          .filter(el => {
            const text = el.textContent?.toLowerCase() || '';
            return text.includes('返回') || text.includes('back') || text.includes('上一页');
          })
          .filter(el => el.offsetParent !== null); // 可见的元素
        
        if (backButtons.length > 0) {
          backButtons[0].click();
          'back_clicked';
        } else {
          'no_back_button';
        }
      `
    });
    
    if (backButton[0] === 'back_clicked') {
      console.log('[RECOVERY] Clicked back button');
      return;
    }
  } catch (e) {
    console.warn('[RECOVERY] Back button detection failed:', e);
  }
  
  // 3. 浏览器回退
  try {
    await chrome.tabs.executeScript({ code: 'history.back();' });
    console.log('[RECOVERY] Executed history.back()');
  } catch (e) {
    console.warn('[RECOVERY] History back failed:', e);
  }
}

/**
 * 等待页面静止
 * @param {Object} options
 * @returns {Promise<void>}
 */
export async function waitQuiet(options = {}) {
  const { timeout = 10000, poll = 300 } = options;
  const startTime = Date.now();
  
  console.log(`[RECOVERY] Waiting for page quiet (timeout: ${timeout}ms)`);
  
  while (Date.now() - startTime < timeout) {
    try {
      const isQuiet = await chrome.tabs.executeScript({
        code: `
          // 检查DOM是否稳定
          const body = document.body;
          const initialCount = body ? body.querySelectorAll('*').length : 0;
          
          setTimeout(() => {
            const finalCount = body ? body.querySelectorAll('*').length : 0;
            window._quietCheck = Math.abs(finalCount - initialCount) < 5; // DOM变化小于5个元素
          }, 200);
          
          true;
        `
      });
      
      await new Promise(resolve => setTimeout(resolve, 250));
      
      const quietResult = await chrome.tabs.executeScript({
        code: 'window._quietCheck || false'
      });
      
      if (quietResult[0] === true) {
        console.log('[RECOVERY] Page is quiet');
        return;
      }
      
    } catch (e) {
      console.warn('[RECOVERY] Quiet check failed:', e);
    }
    
    await new Promise(resolve => setTimeout(resolve, poll));
  }
  
  console.log('[RECOVERY] Wait quiet timeout');
}

/**
 * 带恢复机制的步骤执行
 * @param {import('./pav-types.js').PlanStep} planStep
 * @param {PhaseKey} phase
 * @returns {Promise<Object>}
 */
export async function runStepWithRecovery(planStep, phase) {
  console.log(`[RECOVERY] Running step with recovery: ${planStep.goal}`);
  
  // 获取执行前DOM
  const rawPayload = await chrome.runtime.sendMessage({ type: 'EXT_EXTRACT' });
  const pre = reduceDomPayload(rawPayload);
  
  // 解析目标，避开黑名单
  const target = resolveTargetWithBlacklist(planStep, pre, phase);
  
  // 执行动作
  let actResult;
  try {
    actResult = await performAction(target, planStep);
  } catch (e) {
    console.error('[RECOVERY] Action failed:', e);
    return { ok: false, error: e.message };
  }
  
  // 获取执行后DOM
  const postRaw = await chrome.runtime.sendMessage({ type: 'EXT_EXTRACT' });
  const post = reduceDomPayload(postRaw);
  
  // 1) 本地规则校验
  const diff = makeDiff(pre, post);
  const local = validateLocal(planStep.success_criteria, post, diff, actResult);
  
  if (local.status === 'success') {
    return { ok: true, report: { pre, post, actResult, local } };
  }
  
  // 2) YOLO+LLM 介入（只在失败或不确定才调）
  const yoloVerdict = await interveneWithYOLOLLM(planStep, pre, post, actResult, phase);
  
  if (yoloVerdict.status === 'success') {
    const finalPost = reduceDomPayload(await chrome.runtime.sendMessage({ type: 'EXT_EXTRACT' }));
    return { ok: true, report: { pre, post: finalPost, actResult, yoloVerdict } };
  }
  
  // 3) 仍失败 → 回退 & 拉黑
  await rollbackToPrevious();
  await waitQuiet({ timeout: 10000, poll: 300 });
  
  addToBlacklist(phase, pageSignature(pre), targetSignature(target), {
    reason: 'validation_fail',
    ttl_ms: 7 * 24 * 3600 * 1000,
    max_hits: 3
  });
  
  // 4) 继续：同一阶段重新"DOM+LLM"规划
  return { ok: false, action: 'retry_phase' };
}

/**
 * 解析目标，避开黑名单
 * @param {import('./pav-types.js').PlanStep} planStep
 * @param {import('./pav-types.js').ReducedDom} ctx
 * @param {PhaseKey} phase
 * @returns {Object}
 */
function resolveTargetWithBlacklist(planStep, ctx, phase) {
  const candidates = enumerateCandidates(planStep, ctx);
  const page = pageSignature(ctx);
  
  const filtered = candidates.filter(c => !isBlacklisted(phase, page, targetSignature(c)));
  
  if (!filtered.length) {
    throw new Error('All candidates blacklisted');
  }
  
  return filtered[0]; // 可按置信度/位置/权重排序
}

/**
 * 枚举候选目标
 * @param {import('./pav-types.js').PlanStep} planStep
 * @param {import('./pav-types.js').ReducedDom} ctx
 * @returns {Array<Object>}
 */
function enumerateCandidates(planStep, ctx) {
  const candidates = [];
  const { target } = planStep;
  const { by, value, fallback = [] } = target;
  
  // 主要目标
  const mainTarget = findTarget(by, value, ctx);
  if (mainTarget) candidates.push(mainTarget);
  
  // 备选目标
  for (const fb of fallback) {
    const fbTarget = findTarget(fb.by, fb.value, ctx);
    if (fbTarget) candidates.push(fbTarget);
  }
  
  return candidates;
}

/**
 * 查找单个目标
 * @param {string} by
 * @param {string|number} value
 * @param {import('./pav-types.js').ReducedDom} ctx
 * @returns {Object|null}
 */
function findTarget(by, value, ctx) {
  // 重用之前的目标解析逻辑
  // 这里简化实现
  for (let i = 0; i < ctx.elements.length; i++) {
    const el = ctx.elements[i];
    switch (by) {
      case 'text':
        if (el.label.toLowerCase().includes(String(value).toLowerCase())) {
          return { element: el, index: i };
        }
        break;
      case 'href':
        if (el.href && el.href.includes(String(value))) {
          return { element: el, index: i };
        }
        break;
      case 'id':
        if (el.id === String(value)) {
          return { element: el, index: i };
        }
        break;
    }
  }
  return null;
}

/**
 * 执行动作（简化版）
 * @param {Object} target
 * @param {import('./pav-types.js').PlanStep} planStep
 * @returns {Promise<Object>}
 */
async function performAction(target, planStep) {
  // 这里应该调用实际的动作执行代码
  console.log(`[RECOVERY] Performing ${planStep.action} on:`, target.element.label);
  
  return {
    ok: true,
    ts_start: Date.now(),
    ts_end: Date.now(),
    duration_ms: 100
  };
}

/**
 * YOLO+LLM 介入
 * @param {import('./pav-types.js').PlanStep} plan
 * @param {import('./pav-types.js').ReducedDom} pre
 * @param {import('./pav-types.js').ReducedDom} post
 * @param {Object} act
 * @param {PhaseKey} phase
 * @returns {Promise<Object>}
 */
async function interveneWithYOLOLLM(plan, pre, post, act, phase) {
  console.log('[RECOVERY] YOLO+LLM intervention (mock implementation)');
  
  // TODO: 实际的YOLO+LLM集成
  return {
    status: 'failure',
    confidence: 0.2,
    reasons: ['LLM/YOLO介入仍未满足判定']
  };
}

/**
 * 获取黑名单统计
 * @returns {Object}
 */
export function getBlacklistStats() {
  const stats = {
    total_entries: 0,
    by_reason: {},
    by_host: {},
    expired: 0
  };
  
  const now = Date.now();
  
  for (const [key, entries] of blacklistStorage.entries()) {
    for (const entry of entries) {
      if (now > entry.ts + entry.ttl_ms) {
        stats.expired++;
        continue;
      }
      
      stats.total_entries++;
      stats.by_reason[entry.reason] = (stats.by_reason[entry.reason] || 0) + 1;
      stats.by_host[entry.page.host] = (stats.by_host[entry.page.host] || 0) + 1;
    }
  }
  
  return stats;
}

/**
 * 清理过期的黑名单条目
 */
export function cleanupBlacklist() {
  const now = Date.now();
  let cleaned = 0;
  
  for (const [key, entries] of blacklistStorage.entries()) {
    const validEntries = entries.filter(entry => now <= entry.ts + entry.ttl_ms);
    
    if (validEntries.length !== entries.length) {
      cleaned += entries.length - validEntries.length;
      
      if (validEntries.length === 0) {
        blacklistStorage.delete(key);
      } else {
        blacklistStorage.set(key, validEntries);
      }
    }
  }
  
  if (cleaned > 0) {
    console.log(`[RECOVERY] Cleaned up ${cleaned} expired blacklist entries`);
  }
  
  return cleaned;
}