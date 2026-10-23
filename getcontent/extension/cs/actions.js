// Content Script: DOM Actions + SAVE_TEXT integration
// Handles DOM manipulation, scraping, and artifact saving for workflow execution

// Import logger functions (async import for content script compatibility)
let logActionPerformed, logError;
(async () => {
  try {
    const logger = await import('../lib/logger.js');
    logActionPerformed = logger.logActionPerformed;
    logError = logger.logError;
  } catch (e) {
    console.warn('[CS] Logger import failed:', e);
    // Fallback: no-op functions
    logActionPerformed = () => {};
    logError = () => {};
  }
})();

// Global variables for scraped content
window.__LAST_SCRAPED_TEXT__ = '';
window.__SCRAPE_HISTORY__ = [];

// Configuration - will be updated by service worker with proper URLs
let ORCHESTRATOR_BASE = 'http://127.0.0.1:8788';
let VISION_API_BASE = 'http://127.0.0.1:8000';

// Update configuration from environment
chrome.runtime.sendMessage({type: 'GET_CONFIG'}, (config) => {
  if (config) {
    ORCHESTRATOR_BASE = config.orchestratorUrl || ORCHESTRATOR_BASE;
    VISION_API_BASE = config.visionApiUrl || VISION_API_BASE;
  }
});

// Utility functions
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function safeSelector(selector) {
  try {
    return document.querySelector(selector);
  } catch (e) {
    console.warn('[CS] Invalid selector:', selector, e.message);
    return null;
  }
}

function safeSelectorAll(selector) {
  try {
    return document.querySelectorAll(selector);
  } catch (e) {
    console.warn('[CS] Invalid selector:', selector, e.message);
    return [];
  }
}

// DOM action implementations
async function handleWaitFor(args, verify = {}) {
  const { selector, timeout = 8000 } = args;
  const startTime = Date.now();
  
  while (Date.now() - startTime < timeout) {
    const element = safeSelector(selector);
    if (element && element.offsetParent !== null) {
      // Element found and visible
      return { ok: true, found: true, elapsed: Date.now() - startTime };
    }
    await sleep(100);
  }
  
  return { ok: false, error: 'Element not found within timeout', selector, timeout };
}

// ext.* standardized actions (MVP wrappers)
async function handleExtWaitQuiet(args = {}) {
  const timeout = Math.max(0, args.timeout_ms || args.timeout || 8000);
  const quietMs = Math.max(200, args.quiet_ms || 650);
  const start = Date.now();

  let lastMut = Date.now();
  const mo = new MutationObserver(() => { lastMut = Date.now(); });
  try { mo.observe(document.documentElement || document.body, { subtree: true, childList: true, attributes: true, characterData: true }); } catch {}

  try {
    while (Date.now() - start < timeout) {
      const idle = (Date.now() - lastMut) >= quietMs;
      if (idle) {
        // notify SW for compatibility with orchestrator /page_stable if desired
        try { chrome.runtime.sendMessage({ type: 'PAGE_STABLE', url: location.href, route_change: false }, ()=>{}); } catch {}
        return { ok: true, detail: { dom_idle: true, quiet_ms: quietMs } };
      }
      await sleep(100);
    }
    return { ok: false, error: 'wait_quiet timeout', timeout_ms: timeout };
  } finally {
    try { mo.disconnect(); } catch {}
  }
}

function gatherBasicDom(maxItems = 400) {
  const vw = window.innerWidth, vh = window.innerHeight, dpr = window.devicePixelRatio || 1;
  const items = [];
  const nodes = document.querySelectorAll('a,button,input,textarea,[role],h1,h2,h3,p,span');
  for (const el of nodes) {
    if (items.length >= maxItems) break;
    const rect = el.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) continue;
    if (rect.bottom < 0 || rect.top > vh) continue; // viewport-ish
    const text = (el.innerText || el.value || '').trim();
    const href = el.getAttribute && el.getAttribute('href');
    const role = el.getAttribute && (el.getAttribute('role') || el.tagName.toLowerCase());
    items.push({
      id: el.id || null,
      sel: undefined,
      role,
      text: text ? text.slice(0, 160) : '',
      href: href || undefined,
      bbox: [Math.round(rect.left), Math.round(rect.top), Math.round(rect.right), Math.round(rect.bottom)],
      region: 'viewport',
      visible: true,
      z: (parseInt(getComputedStyle(el).zIndex) || 0)
    });
  }
  return { vw, vh, dpr, items };
}

async function handleExtExtract(args = {}) {
  const want = args.want || 'default';
  const limit = Math.max(50, Math.min(1000, args.limit || 400));
  // MVP: only default structure, return basic dom snapshot plus meta
  const dom = gatherBasicDom(limit);
  const meta = { url: location.href, title: document.title };
  return { ok: true, dom, meta };
}

// Resolve a target definition to selector and bbox
async function handleExtResolve(args = {}) {
  const target = args.target || {};
  function findByXPath(xpath) {
    try {
      const r = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
      return r.singleNodeValue || null;
    } catch (_) { return null; }
  }
  function norm(s) { return (s || '').toString().replace(/\s+/g, ' ').trim().toLowerCase(); }
  function findByRoleText(role, text) {
    const roleSel = role ? `[role="${role}"] , ${role}` : '*';
    const cands = Array.from(document.querySelectorAll(roleSel));
    if (!text) return cands[0] || null;
    const t = norm(text);
    for (const el of cands) {
      const name = norm((el.innerText || el.getAttribute?.('aria-label') || '').toString());
      if (name.includes(t)) return el;
    }
    return Array.from(document.querySelectorAll('button,a,[role],div,span,input,textarea,select'))
      .find(el => norm(el.innerText || el.getAttribute?.('aria-label') || '').includes(t)) || null;
  }
  let el = null;
  if (target.element_id) el = document.getElementById(target.element_id);
  if (!el && target.css) { try { el = document.querySelector(target.css); } catch(_){} }
  if (!el && target.xpath) el = findByXPath(target.xpath);
  if (!el && (target.role || target.text)) el = findByRoleText(target.role, target.text);
  if (!el) return { ok: false, error: 'not_found' };
  const r = el.getBoundingClientRect();
  const bbox = { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height), dpr: window.devicePixelRatio || 1 };
  const selector = target.css || (el.id ? `#${el.id}` : undefined);
  return { ok: true, selector, bbox };
}

async function handleExtClickSelector(args = {}) {
  if (!args.sel && !args.selector) throw new Error('ext.click_selector requires sel');
  const selector = args.sel || args.selector;
  const res = await handleClick({ selector });
  return Object.assign({ ok: true }, res, { after: { url: location.href } });
}

async function handleExtTypeText(args = {}) {
  const { sel, selector, text, replace = true } = args;
  if (!text) throw new Error('ext.type_text requires text');

  const element = safeSelector(sel || selector);
  if (!element) {
    throw new Error(`Element not found: ${sel || selector}`);
  }

  // Focus the element
  element.focus();
  await sleep(50);

  // Clear existing content if requested
  if (replace) {
    element.value = '';
    element.dispatchEvent(new Event('input', { bubbles: true }));
  }

  // Process text for special characters
  let processedText = text;
  let shouldTriggerEnter = false;
  let shouldTriggerTab = false;

  // Handle special escape sequences
  if (text.includes('\\n')) {
    processedText = text.replace(/\\n/g, '');  // Remove \n from text
    shouldTriggerEnter = true;
  }
  if (text.includes('\\t')) {
    processedText = processedText.replace(/\\t/g, '\t');  // Convert to actual tab
    shouldTriggerTab = true;
  }
  if (text.includes('\\b')) {
    processedText = processedText.replace(/\\b/g, '');  // Backspace removes chars
  }

  // Type the processed text
  if (processedText) {
    for (const char of processedText) {
      element.value += char;
      element.dispatchEvent(new Event('input', { bubbles: true }));
      await sleep(20 + Math.random() * 30); // Human-like typing speed
    }
  }

  // Handle special character triggers with robust event dispatch
  if (shouldTriggerEnter) {
    // Double insurance: text input satisfaction + real Enter events
    ["keydown", "keypress", "keyup"].forEach(type => {
      const ev = new KeyboardEvent(type, {
        key: "Enter",
        code: "Enter",
        keyCode: 13,
        bubbles: true,
        cancelable: true
      });
      element.dispatchEvent(ev);
    });

    // Also trigger form submission if element is in a form
    const form = element.closest('form');
    if (form) {
      form.dispatchEvent(new Event('submit', { bubbles: true }));
    }
  }

  if (shouldTriggerTab) {
    ["keydown", "keypress", "keyup"].forEach(type => {
      const ev = new KeyboardEvent(type, {
        key: "Tab",
        code: "Tab",
        keyCode: 9,
        bubbles: true,
        cancelable: true
      });
      element.dispatchEvent(ev);
    });
  }

  // Final change event
  element.dispatchEvent(new Event('change', { bubbles: true }));

  // Ensure element stays focused
  element.focus();

  return {
    ok: true,
    typed: text.length,
    processed: processedText,
    special_chars: { enter: shouldTriggerEnter, tab: shouldTriggerTab },
    focused: true
  };
}

async function handleExtKey(args = {}) {
  const el = document.activeElement;
  if (!el) {
    return { ok: false, error: "no active element" };
  }

  const key = args.key || "Enter";

  // 确保元素仍然focused
  el.focus();

  // 派发完整的键盘事件序列，确保框架能捕捉
  ["keydown", "keypress", "keyup"].forEach(type => {
    const ev = new KeyboardEvent(type, {
      key,
      code: key === "Enter" ? "Enter" : key,
      bubbles: true,
      cancelable: true
    });
    el.dispatchEvent(ev);
  });

  // 对于表单元素，额外触发input/change事件（必要时）
  if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  return { ok: true, key, element: el.tagName };
}

async function handleExtScroll(args = {}) {
  const dir = args.dir || 'down';
  const amount = typeof args.amount === 'number' ? args.amount : window.innerHeight * 0.8;
  const dy = dir === 'up' ? -Math.abs(amount) : Math.abs(amount);
  window.scrollBy({ top: dy, behavior: 'smooth' });
  await sleep(200);
  return { ok: true, y: window.scrollY };
}

async function handleExtHover(args = {}) {
  const { sel, selector } = args;
  const el = safeSelector(sel || selector);
  if (!el) return { ok: false, error: 'not_found' };
  const rect = el.getBoundingClientRect();
  const evtOpts = { bubbles: true, cancelable: true, clientX: rect.left + 5, clientY: rect.top + 5 };
  el.dispatchEvent(new MouseEvent('mouseover', evtOpts));
  el.dispatchEvent(new MouseEvent('mouseenter', evtOpts));
  return { ok: true, tag: el.tagName };
}

async function handleExtSelectOption(args = {}) {
  function norm(s) { return (s || '').toString().replace(/\s+/g, ' ').trim().toLowerCase(); }
  const { sel, selector, value } = args;
  const el = safeSelector(sel || selector);
  if (!el || el.tagName !== 'SELECT') return { ok: false, error: 'not_select' };
  const selectEl = el;
  const opts = Array.from(selectEl.options);
  let matched = false;
  if (typeof value === 'number') {
    const idx = Math.max(0, Math.min(opts.length - 1, value));
    selectEl.selectedIndex = idx; matched = true;
  } else if (typeof value === 'string') {
    const byVal = opts.findIndex(o => o.value === value);
    const byTxt = byVal < 0 ? opts.findIndex(o => norm(o.text) === norm(value)) : byVal;
    if (byTxt >= 0) { selectEl.selectedIndex = byTxt; matched = true; }
  }
  if (matched) {
    selectEl.dispatchEvent(new Event('input', { bubbles: true }));
    selectEl.dispatchEvent(new Event('change', { bubbles: true }));
    return { ok: true, selectedIndex: selectEl.selectedIndex };
  }
  return { ok: false, error: 'no_match' };
}

async function handleExtUploadFile(_args = {}) {
  // Placeholder: True upload requires CDP DOM.setFileInputFiles from SW
  return { ok: false, error: 'upload_file not_implemented_in_content_script' };
}

async function handleExtHistory(args = {}) {
  const op = (args.op || 'back').toLowerCase();
  try {
    if (op === 'back') window.history.back();
    else if (op === 'forward') window.history.forward();
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

async function handleExtScreenshot(_args = {}) {
  // Not implemented in CS without capture permission; stub for contract
  return { ok: false, error: 'ext.screenshot not implemented in CS' };
}

async function handleType(args, verify = {}) {
  const { selector, text, enter = false, clear = true } = args;
  const element = safeSelector(selector);
  
  if (!element) {
    throw new Error(`Element not found: ${selector}`);
  }
  
  // Focus the element
  element.focus();
  await sleep(50);
  
  // Clear existing content if requested
  if (clear) {
    element.value = '';
    element.dispatchEvent(new Event('input', { bubbles: true }));
  }
  
  // Type the text
  for (const char of text) {
    element.value += char;
    element.dispatchEvent(new Event('input', { bubbles: true }));
    await sleep(20 + Math.random() * 30); // Human-like typing speed
  }
  
  // Press Enter if requested
  if (enter) {
    const enterEvent = new KeyboardEvent('keydown', {
      key: 'Enter',
      code: 'Enter',
      keyCode: 13,
      bubbles: true
    });
    element.dispatchEvent(enterEvent);
    
    // Also trigger form submission if element is in a form
    const form = element.closest('form');
    if (form) {
      form.dispatchEvent(new Event('submit', { bubbles: true }));
    }
  }
  
  element.dispatchEvent(new Event('change', { bubbles: true }));
  return { ok: true, typed: text.length, entered: enter };
}

async function handleClick(args, verify = {}) {
  const { selector } = args;
  const element = safeSelector(selector);
  
  if (!element) {
    throw new Error(`Element not found: ${selector}`);
  }
  
  // Scroll element into view
  element.scrollIntoView({ behavior: 'smooth', block: 'center' });
  await sleep(200);
  
  // Simulate realistic click sequence
  const rect = element.getBoundingClientRect();
  const x = rect.left + rect.width / 2;
  const y = rect.top + rect.height / 2;
  
  const eventOptions = { clientX: x, clientY: y, bubbles: true, cancelable: true };
  
  element.dispatchEvent(new MouseEvent('mouseover', eventOptions));
  element.dispatchEvent(new MouseEvent('mousedown', eventOptions));
  await sleep(50);
  element.dispatchEvent(new MouseEvent('mouseup', eventOptions));
  element.click();
  
  return { ok: true, clicked: true, tag: element.tagName, text: element.innerText?.slice(0, 50) };
}

async function handleOpenNthItem(args, verify = {}) {
  const { list_selector, index = 1 } = args;
  const items = safeSelectorAll(list_selector);
  
  if (items.length === 0) {
    throw new Error(`No items found: ${list_selector}`);
  }
  
  const targetIndex = Math.max(1, Math.min(index, items.length)) - 1; // Convert to 0-based
  const targetItem = items[targetIndex];
  
  if (!targetItem) {
    throw new Error(`Item ${index} not found (total: ${items.length})`);
  }
  
  // Click the item (with realistic interaction)
  await handleClick({ selector: `${list_selector}:nth-child(${targetIndex + 1})` });
  
  return { ok: true, opened: targetIndex + 1, total: items.length };
}

async function handleScrapeComments(args, verify = {}) {
  const { 
    container = 'body', 
    max_scrolls = 30, 
    scroll_pause_ms = 800,
    comment_selectors = [
      '[class*="comment"]',
      '[data-comment-id]', 
      '.comment',
      'section:has([class*="comment"]) *',
      '[class*="Content"] p',
      '[class*="text"] span'
    ]
  } = args;
  
  let allComments = [];
  let previousCount = 0;
  let stableCount = 0;
  
  for (let scroll = 0; scroll < max_scrolls; scroll++) {
    // Try each selector pattern
    for (const selector of comment_selectors) {
      const elements = safeSelectorAll(selector);
      
      for (const el of elements) {
        const text = (el.innerText || el.textContent || '').trim();
        if (text.length > 10 && !allComments.includes(text)) {
          allComments.push(text);
        }
      }
    }
    
    // Check if we're getting new content
    if (allComments.length === previousCount) {
      stableCount++;
      if (stableCount >= 3) {
        console.log(`[CS] Content stable after ${scroll} scrolls, stopping`);
        break;
      }
    } else {
      stableCount = 0;
      previousCount = allComments.length;
    }
    
    // Scroll down
    const scrollHeight = document.documentElement.scrollHeight;
    window.scrollBy(0, window.innerHeight * 0.8);
    await sleep(scroll_pause_ms);
    
    // Check if we reached the bottom
    if (window.scrollY + window.innerHeight >= scrollHeight - 100) {
      console.log(`[CS] Reached bottom after ${scroll} scrolls`);
      break;
    }
  }
  
  // Deduplicate and clean up comments
  const uniqueComments = [...new Set(allComments)].filter(text => 
    text.length > 10 && 
    !text.match(/^(�^|6�|�|ĺ|s�|�|{U|�)$/)
  );
  
  // Store in global variable for SAVE_TEXT
  const commentsText = uniqueComments.join('\n---\n');
  window.__LAST_SCRAPED_TEXT__ = commentsText;
  window.__SCRAPE_HISTORY__.push({
    timestamp: Date.now(),
    type: 'comments',
    count: uniqueComments.length,
    text: commentsText
  });
  
  console.log(`[CS] Scraped ${uniqueComments.length} comments`);
  
  return { 
    ok: true, 
    count: uniqueComments.length, 
    total_scrolls: Math.min(scroll, max_scrolls),
    preview: uniqueComments.slice(0, 3)
  };
}

async function handleSaveText(args, verify = {}) {
  const { path, run_id } = args;
  const text = window.__LAST_SCRAPED_TEXT__ || '';
  
  if (!run_id) {
    throw new Error('run_id is required for SAVE_TEXT');
  }
  
  if (!path) {
    throw new Error('path is required for SAVE_TEXT');
  }
  
  try {
    const response = await fetch(`${ORCHESTRATOR_BASE}/artifacts/save_text`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        run_id: run_id,
        path: path,
        text: text
      })
    });
    
    if (!response.ok) {
      throw new Error(`Save text failed: HTTP ${response.status}`);
    }
    
    const result = await response.json();
    
    return { 
      ok: true, 
      saved: true, 
      path: result.path,
      size: result.size || text.length,
      preview: text.slice(0, 100) + (text.length > 100 ? '...' : '')
    };
    
  } catch (error) {
    console.error('[CS] Save text error:', error);
    throw new Error(`Failed to save text: ${error.message}`);
  }
}

async function handleSimClick(args) {
  const { x, y } = args;
  
  // Find element at coordinates
  const element = document.elementFromPoint(x, y);
  
  if (!element) {
    throw new Error(`No element found at coordinates (${x}, ${y})`);
  }
  
  // Simulate click
  const eventOptions = { clientX: x, clientY: y, bubbles: true, cancelable: true };
  element.dispatchEvent(new MouseEvent('mouseover', eventOptions));
  element.dispatchEvent(new MouseEvent('mousedown', eventOptions));
  element.dispatchEvent(new MouseEvent('mouseup', eventOptions));
  element.click();
  
  return { 
    ok: true, 
    clicked: true, 
    coords: { x, y },
    tag: element.tagName,
    text: element.innerText?.slice(0, 50)
  };
}

// Message handler
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    const exec_id = message.exec_id || `cs_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
    const task_id = message.task_id || exec_id;
    const phase_id = message.phase_id || 'action_execution';
    const step_no = message.step_no || 1;

    try {
      console.log('[CS] Received message:', message.type);
      
      switch (message.type) {
        case 'EXT_WAIT_QUIET':
          return await handleExtWaitQuiet(message.args || {});
        case 'EXT_RESOLVE':
          return await handleExtResolve(message.args || {});
        case 'EXT_EXTRACT':
          return await handleExtExtract(message.args || {});
        case 'EXT_CLICK_SELECTOR': {
          const result = await handleExtClickSelector(message.args || {});
          if (logActionPerformed) {
            logActionPerformed({
              exec_id, task_id, phase_id, step_no,
              action: 'click',
              target: { role: 'element', label: message.args?.sel || message.args?.selector || '', has_href: false, has_id: false },
              success: result.ok
            });
          }
          return result;
        }
        case 'EXT_TYPE_TEXT': {
          const result = await handleExtTypeText(message.args || {});
          if (logActionPerformed) {
            logActionPerformed({
              exec_id, task_id, phase_id, step_no,
              action: 'type',
              target: { role: 'input', label: message.args?.sel || message.args?.selector || '', has_href: false, has_id: false },
              input_text: message.args?.text || '',
              success: result.ok
            });
          }
          return result;
        }
        case 'EXT_KEY': {
          const result = await handleExtKey(message.args || {});
          if (logActionPerformed) {
            logActionPerformed({
              exec_id, task_id, phase_id, step_no,
              action: 'key',
              target: { role: 'input', label: message.args?.key || 'Enter', has_href: false, has_id: false },
              success: result.ok
            });
          }
          return result;
        }
        case 'EXT_SCROLL': {
          const result = await handleExtScroll(message.args || {});
          if (logActionPerformed) {
            logActionPerformed({
              exec_id, task_id, phase_id, step_no,
              action: 'scroll',
              target: { role: 'page', label: message.args?.dir || 'down', has_href: false, has_id: false },
              success: result.ok
            });
          }
          return result;
        }
        case 'EXT_HOVER': {
          const result = await handleExtHover(message.args || {});
          if (logActionPerformed) {
            logActionPerformed({ exec_id, task_id, phase_id, step_no, action: 'hover', target: { role: 'element', label: message.args?.sel || message.args?.selector || '' }, success: result.ok });
          }
          return result;
        }
        case 'EXT_SELECT_OPTION': {
          const result = await handleExtSelectOption(message.args || {});
          if (logActionPerformed) {
            logActionPerformed({ exec_id, task_id, phase_id, step_no, action: 'select_option', target: { role: 'select', label: message.args?.sel || message.args?.selector || '' }, success: result.ok });
          }
          return result;
        }
        case 'EXT_UPLOAD_FILE': {
          return await handleExtUploadFile(message.args || {});
        }
        case 'EXT_HISTORY': {
          return await handleExtHistory(message.args || {});
        }
        case 'EXT_SCREENSHOT':
          return await handleExtScreenshot(message.args || {});
        case 'DOM_WAIT_FOR':
          return await handleWaitFor(message.args || {}, message.verify);
          
        case 'DOM_TYPE':
          return await handleType({
            selector: message.selector,
            text: message.text,
            enter: message.enter
          }, message.verify);
          
        case 'DOM_CLICK':
          return await handleClick({ selector: message.selector }, message.verify);
          
        case 'DOM_OPEN_NTH':
          return await handleOpenNthItem({
            list_selector: message.list_selector,
            index: message.index
          }, message.verify);
          
        case 'DOM_SCRAPE_COMMENTS':
          return await handleScrapeComments({
            container: message.container,
            max_scrolls: message.max_scrolls,
            scroll_pause_ms: message.scroll_pause_ms
          }, message.verify);
          
        case 'SAVE_TEXT':
          return await handleSaveText({
            path: message.path,
            run_id: message.run_id
          }, message.verify);
          
        case 'SIM_CLICK':
          return await handleSimClick({ x: message.x, y: message.y });
          
        case 'GET_PAGE_INFO':
          return {
            ok: true,
            url: location.href,
            title: document.title,
            scraped_text_length: window.__LAST_SCRAPED_TEXT__.length,
            scrape_history_count: window.__SCRAPE_HISTORY__.length
          };
          
        default:
          throw new Error(`Unknown message type: ${message.type}`);
      }
      
    } catch (error) {
      console.error('[CS] Action failed:', error);

      // Log error
      if (logError) {
        logError({
          exec_id, task_id, phase_id, step_no,
          err: error,
          context: `content_script_action:${message.type}`
        });
      }

      return { ok: false, error: error.message };
    }
  })().then(result => {
    sendResponse(result);
  }).catch(error => {
    sendResponse({ ok: false, error: error.message });
  });
  
  return true; // Async response
});

// Initialize content script
console.log('[CS] Content script loaded for', location.hostname);

// Expose debugging functions
window.__CS_DEBUG__ = {
  getLastScrapedText: () => window.__LAST_SCRAPED_TEXT__,
  getScrapeHistory: () => window.__SCRAPE_HISTORY__,
  clearScrapeData: () => {
    window.__LAST_SCRAPED_TEXT__ = '';
    window.__SCRAPE_HISTORY__ = [];
  }
};

// --- Minimal SPA-ready quiet detector (MVP) ---
(() => {
  try {
    // Notify SW that CS is ready
    try { chrome.runtime.sendMessage({ type: 'CS_READY' }, () => {}); } catch {}
  } catch {}
  try {
    const TARGET_HOSTS = ['xiaohongshu.com', 'xhs.com'];
    const host = location.host || '';
    if (!TARGET_HOSTS.some(h => host.includes(h))) return;

    let lastMut = Date.now();
    let timer = null;
    let lastHref = location.href;

    // Observe DOM mutations
    const mo = new MutationObserver(() => {
      lastMut = Date.now();
    });
    try {
      mo.observe(document.documentElement || document.body, { subtree: true, childList: true, attributes: true, characterData: true });
    } catch {}

    function maybeSignal(routeChange = false) {
      const now = Date.now();
      const domIdle = (now - lastMut) >= 650; // ~600ms quiet
      if (!domIdle) return;
      try {
        chrome.runtime.sendMessage({ type: 'PAGE_STABLE', url: location.href, route_change: !!routeChange }, (resp) => {
          // ignore response
        });
      } catch (e) {
        console.warn('[CS] PAGE_STABLE send failed:', e?.message || e);
      }
    }

    function scheduleCheck(routeChange = false) {
      clearTimeout(timer);
      timer = setTimeout(() => maybeSignal(routeChange), 700);
    }

    // Periodic check
    setInterval(() => scheduleCheck(false), 800);

    // Route changes (SPA)
    window.addEventListener('popstate', () => {
      lastHref = location.href;
      lastMut = Date.now();
      scheduleCheck(true);
    });
    window.addEventListener('hashchange', () => {
      lastHref = location.href;
      lastMut = Date.now();
      scheduleCheck(true);
    });

  } catch (e) {
    console.warn('[CS] quiet detector init failed:', e?.message || e);
  }
})();
