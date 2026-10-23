// Unified logging system for Chrome Extension MV3
// Tracks full-chain: DOM extraction → LLM → Action → Validation → Recovery

import { sha256Hex, objectSignature } from "./hash.js";
import { redactUrl, redactText, createPageContext } from "./redact.js";

// Configuration
const CFG = {
  consoleLevel: "info",                // "debug" | "info" | "warn" | "error"
  flushIntervalMs: 3000,               // Auto-flush interval
  maxBuffer: 200,                      // Max events before forced flush
  maxBytesPerEvent: 64 * 1024,         // 64KB protection per event
  backendUrl: "http://127.0.0.1:8787/logs", // Backend log collection endpoint
  storageKey: "DOM_LOGS_V1",           // Chrome storage key for offline logs
  enabled: true                        // Global logging enable/disable
};

const LEVELS = ["debug", "info", "warn", "error"];
let buffer = [];
let flushTimer = null;

/**
 * Set logging configuration
 * @param {object} partial - Partial config to merge
 */
export function setLogConfig(partial) {
  Object.assign(CFG, partial || {});
}

/**
 * Check if log level should be output to console
 * @param {string} level - Log level
 * @returns {boolean}
 */
function shouldLog(level) {
  return LEVELS.indexOf(level) >= LEVELS.indexOf(CFG.consoleLevel);
}

/**
 * Generate unique execution ID
 * @returns {string}
 */
function generateId() {
  return Math.random().toString(36).substr(2, 9) + Date.now().toString(36);
}

/**
 * Core logging function - adds common fields and buffers events
 * @param {object} event - Event data
 */
export function logEvent(event = {}) {
  if (!CFG.enabled) return;

  const evt = {
    ts: Date.now(),
    level: event.level || "info",
    env: event.env || "ext-sw",
    run_id: event.run_id || generateId(),
    ...event
  };

  // Console output (filtered by level)
  if (shouldLog(evt.level)) {
    const { payload_sample, resp_sample, ...lite } = evt;
    console.log(`[DOM_LOG:${evt.level.toUpperCase()}]`, lite);
  }

  // Buffer for batch upload
  buffer.push(evt);

  // Auto-flush triggers
  if (buffer.length >= CFG.maxBuffer) {
    flushLogs();
  }

  if (!flushTimer) {
    flushTimer = setInterval(flushLogs, CFG.flushIntervalMs);
  }
}

// =============================================================================
// PHASE 1: DOM EXTRACTION LOGGING
// =============================================================================

/**
 * Log raw ext.extract payload (with hash for security)
 */
export async function logExtractRaw({ exec_id, task_id, phase_id, step_no, url, payload }) {
  const sig = await objectSignature(payload);

  logEvent({
    evt: "EXTRACTED_RAW",
    exec_id, task_id, phase_id, step_no,
    level: "debug",
    page: createPageContext(url, payload?.result?.meta?.title || ""),
    payload_size: sig.size,
    payload_sha256: sig.hash,
    items_count: payload?.result?.dom?.items?.length || 0
  });
}

/**
 * Log DOM reduction results
 */
export async function logDomReduced({ exec_id, task_id, phase_id, step_no, url, reduced }) {
  // Safe sample: only first 5 elements with label/role
  const sample = reduced.elements.slice(0, 5).map(e => ({
    label: redactText(e.label),
    role: e.role
  }));

  const sig = await objectSignature(reduced);

  logEvent({
    evt: "DOM_REDUCED",
    level: "info",
    exec_id, task_id, phase_id, step_no,
    page: createPageContext(url, reduced.title),
    el_count: reduced.elements.length,
    reduction_ratio: reduced.elements.length / (reduced._originalCount || reduced.elements.length),
    payload_size: sig.size,
    payload_sha256: sig.hash,
    payload_sample: sample,
    version: reduced._version
  });
}

// =============================================================================
// PHASE 2: LLM INTERACTION LOGGING
// =============================================================================

/**
 * Log LLM request (before sending)
 */
export async function logLLMRequest({ exec_id, task_id, phase_id, step_no, model, body, purpose }) {
  const sig = await objectSignature(body);

  logEvent({
    evt: "LLM_REQUEST",
    level: "info",
    exec_id, task_id, phase_id, step_no,
    llm: { model, purpose: purpose || "dom_picker" },
    payload_size: sig.size,
    payload_sha256: sig.hash,
    message_count: Array.isArray(body.messages) ? body.messages.length : 0
  });
}

/**
 * Log LLM response (after receiving)
 */
export async function logLLMResponse({
  exec_id, task_id, phase_id, step_no,
  model, status, latency_ms, tokens, response
}) {
  const responseData = {
    evt: "LLM_RESPONSE",
    level: status === "ok" ? "info" : "warn",
    exec_id, task_id, phase_id, step_no,
    llm: { model },
    latency_ms,
    status
  };

  // Add token usage if available
  if (tokens) {
    responseData.token_in = tokens.in;
    responseData.token_out = tokens.out;
    responseData.token_total = (tokens.in || 0) + (tokens.out || 0);
  }

  // Add response summary for successful DOM picker results
  if (status === "ok" && response) {
    responseData.response_summary = {
      has_selector: !!response.sel,
      confidence: response.confidence,
      selector_type: response.sel ? (response.sel.startsWith('#') ? 'id' : 'other') : null
    };
  }

  logEvent(responseData);
}

// =============================================================================
// PHASE 3: ACTION EXECUTION LOGGING
// =============================================================================

/**
 * Log DOM action execution
 */
export function logActionPerformed({
  exec_id, task_id, phase_id, step_no,
  action, target, input_text, success
}) {
  logEvent({
    evt: "ACTION_PERFORMED",
    level: success ? "info" : "warn",
    exec_id, task_id, phase_id, step_no,
    action,
    target: {
      role: target.role,
      label: redactText(target.label || ""),
      has_href: !!target.href,
      has_id: !!target.id
    },
    input_text: input_text ? "[text_input]" : undefined,
    success
  });
}

// =============================================================================
// PHASE 4: VALIDATION LOGGING
// =============================================================================

/**
 * Log local validation results
 */
export function logValidationLocal({
  exec_id, task_id, phase_id, step_no,
  verdict, criteria_matched, duration_ms
}) {
  logEvent({
    evt: "VALIDATION_LOCAL",
    level: verdict.status === "failure" ? "warn" : "info",
    exec_id, task_id, phase_id, step_no,
    verdict: {
      status: verdict.status,
      confidence: verdict.confidence,
      reasons_count: verdict.reasons?.length || 0
    },
    criteria_matched: criteria_matched || [],
    duration_ms
  });
}

/**
 * Log LLM validation results
 */
export function logValidationLLM({
  exec_id, task_id, phase_id, step_no,
  verdict, fallback_triggered
}) {
  logEvent({
    evt: "VALIDATION_LLM",
    level: verdict.status === "failure" ? "warn" : "info",
    exec_id, task_id, phase_id, step_no,
    fallback_triggered,
    verdict_summary: {
      status: verdict.status,
      confidence: verdict.confidence,
      recommended_actions: verdict.recommended_next_steps?.slice(0, 2).map(s => s.action) || []
    }
  });
}

// =============================================================================
// PHASE 5: RECOVERY & BLACKLIST LOGGING
// =============================================================================

/**
 * Log blacklist addition
 */
export function logBlacklistAdd({
  exec_id, task_id, phase_id, step_no,
  target, reason, ttl_ms
}) {
  logEvent({
    evt: "BLACKLIST_ADD",
    level: "warn",
    exec_id, task_id, phase_id, step_no,
    target: {
      role: target.role,
      label: redactText(target.label || ""),
      has_href: !!target.href
    },
    reason,
    ttl_hours: Math.round(ttl_ms / (1000 * 60 * 60))
  });
}

/**
 * Log rollback execution
 */
export function logRollback({
  exec_id, task_id, phase_id, step_no,
  mode, success, reason
}) {
  logEvent({
    evt: "ROLLBACK",
    level: success ? "warn" : "error",
    exec_id, task_id, phase_id, step_no,
    mode, // "history.back" | "hard-navigate" | "close-modal"
    success,
    reason
  });
}

// =============================================================================
// ERROR & SYSTEM LOGGING
// =============================================================================

/**
 * Log errors with context
 */
export function logError({
  exec_id, task_id, phase_id, step_no,
  err, context
}) {
  logEvent({
    evt: "ERROR",
    level: "error",
    exec_id, task_id, phase_id, step_no,
    error: {
      name: err?.name || "Unknown",
      message: String(err?.message || err || "Unknown error"),
      stack: err?.stack ? err.stack.split('\n').slice(0, 5).join('\n') : undefined
    },
    context: context || "unknown"
  });
}

/**
 * Log system events (startup, config changes, etc.)
 */
export function logSystem({ message, level = "info", data = {} }) {
  logEvent({
    evt: "SYSTEM",
    level,
    message,
    ...data
  });
}

// =============================================================================
// FLUSH & PERSISTENCE
// =============================================================================

/**
 * Flush logs to backend or storage
 */
async function flushLogs() {
  if (!buffer.length) return;

  const batch = buffer.splice(0, buffer.length);

  if (!CFG.backendUrl) {
    // Store in Chrome storage as fallback
    try {
      const { [CFG.storageKey]: existing = [] } = await chrome.storage.session.get([CFG.storageKey]);
      const merged = [...existing, ...batch].slice(-1000); // Keep last 1000 events
      await chrome.storage.session.set({ [CFG.storageKey]: merged });
      console.log(`[DOM_LOG] Stored ${batch.length} events in session storage`);
    } catch (e) {
      console.warn("[DOM_LOG] Failed to store in session:", e);
    }
    return;
  }

  // Upload to backend
  try {
    const body = batch.map(e => JSON.stringify(e)).join("\n");
    const response = await fetch(CFG.backendUrl, {
      method: "POST",
      headers: {
        "content-type": "application/x-ndjson",
        "user-agent": "DOM-Extension-Logger/1.0"
      },
      body
    });

    if (response.ok) {
      logEvent({
        evt: "FLUSH",
        level: "debug",
        sent: batch.length,
        success: true
      });
    } else {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (e) {
    console.warn("[DOM_LOG] Flush failed, re-buffering:", e);
    // Re-add failed events to buffer (with limit to prevent memory leak)
    buffer = [...batch.slice(-CFG.maxBuffer), ...buffer].slice(-CFG.maxBuffer * 2);

    logEvent({
      evt: "FLUSH",
      level: "error",
      sent: 0,
      failed: batch.length,
      error: String(e)
    });
  }
}

/**
 * Manually flush logs immediately
 */
export async function flushLogsNow() {
  if (flushTimer) {
    clearInterval(flushTimer);
    flushTimer = null;
  }
  await flushLogs();
}

/**
 * Get current log buffer for debugging
 */
export function getLogBuffer() {
  return [...buffer];
}

/**
 * Clear log buffer
 */
export function clearLogBuffer() {
  buffer = [];
}

// Initialize logging system
logSystem({
  message: "DOM logging system initialized",
  level: "info",
  data: {
    version: "1.0",
    backend_url: CFG.backendUrl,
    console_level: CFG.consoleLevel
  }
});

// Auto-flush on extension unload
if (typeof chrome !== "undefined" && chrome.runtime) {
  chrome.runtime.onSuspend.addListener(() => {
    flushLogsNow();
  });
}