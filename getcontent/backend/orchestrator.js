// Orchestrator MVP: Workflow execution engine using existing /commands queue
// Converts workflow JSON to commands, aggregates results, manages artifacts

import express from 'express';
import { v4 as uuid } from 'uuid';
import pkg from 'pg';
const { Pool } = pkg;

const app = express();
app.use(express.json({ limit: '4mb' }));
app.use(express.urlencoded({ extended: true }));

// Database connection (reuse existing config from main backend)
const pool = new Pool({
  connectionString: process.env.DATABASE_URL || process.env.DATABASE || 'postgresql://user:pass@localhost/db'
});

// Helper functions for database operations
async function q(sql, params = []) {
  const client = await pool.connect();
  try {
    const result = await client.query(sql, params);
    return result.rows;
  } finally {
    client.release();
  }
}

async function q_one(sql, params = []) {
  const rows = await q(sql, params);
  return rows[0] || null;
}

/**
 * Start workflow execution
 * POST /runs/start
 * Body: { workflow: {...}, params: {...} }
 */
app.post('/runs/start', async (req, res) => {
  try {
    const { workflow, params = {}, user_id = null, site = null, start_url = null, bind = null } = req.body;
    
    if (!workflow || !workflow.states || !workflow.start) {
      return res.status(400).json({ ok: false, error: 'Invalid workflow format' });
    }
    
    const runId = uuid();
    const workflowName = workflow.name || 'unnamed_workflow';
    
    // Create workflow run record (best-effort; allow memory-only runs if DB unavailable)
    try {
      await q(
        "INSERT INTO workflow_runs(id, workflow_name, status, created_at) VALUES ($1, $2, 'running', NOW())",
        [runId, workflowName]
      );
    } catch (e) {
      console.warn('[ORCH] DB insert workflow_runs failed, continuing in memory:', e.message || e);
    }
    
    // Get starting state
    const startState = workflow.states[workflow.start];
    if (!startState || !startState.actions) {
      await q("UPDATE workflow_runs SET status='failed', finished_at=NOW() WHERE id=$1", [runId]);
      return res.status(400).json({ ok: false, error: 'Invalid start state' });
    }
    
    // Create run steps for each action
    let stepIdx = 0;
    for (const action of startState.actions) {
      stepIdx++;
      const stepId = uuid();
      try {
        await q(
          "INSERT INTO run_steps(id, run_id, idx, action, status, started_at) VALUES ($1, $2, $3, $4, 'pending', NOW())",
          [stepId, runId, stepIdx, JSON.stringify(action)]
        );
        const commandPayload = {
          id: stepId,
          run_id: runId,
          step_idx: stepIdx,
          type: 'ACTION',
          action: action,
          timestamp: new Date().toISOString()
        };
        await q(
          "INSERT INTO commands(id, queue, payload, created_at, status) VALUES ($1, $2, $3, NOW(), 'pending')",
          [uuid(), 'agent', JSON.stringify(commandPayload)]
        );
      } catch (e) {
        // If DB is unavailable, skip DB-backed steps; engine will drive via /actions/dispatch
        console.warn('[ORCH] DB step enqueue failed, skipping DB-backed queue:', e.message || e);
      }
    }
    
    console.log(`[ORCHESTRATOR] Started workflow run ${runId} with ${stepIdx} steps`);

    // Optional auto-binding (server-push)
    let bound = false; let bDevice = null; let bTab = null;
    try {
      const wantDomain = (bind && bind.domain) || (start_url ? new URL(start_url).host : null);
      const keys = Array.from(ConnRegistry.keys());
      // Prefer a ready tab matching domain
      let chosenKey = null;
      if (wantDomain) {
        for (const k of keys) {
          const meta = (typeof TabRegistry !== 'undefined') ? (TabRegistry.get(k) || {}) : {};
          if (meta && meta.ready && meta.host && meta.host.includes(wantDomain)) { chosenKey = k; break; }
        }
      }
      if (!chosenKey && keys.length) chosenKey = keys[0];
      if (chosenKey) {
        const [device_id, tab_id_raw] = chosenKey.split(':');
        let tab_id = parseInt(tab_id_raw, 10);
        // Ensure we have a real tab_id; if not or no domain matched, open start_url and await tab_id
        if (!(tab_id > 0) && start_url) {
          const ws = ConnRegistry.get(chosenKey);
          if (ws) {
            const exec_id = uuid();
            const waiter = awaitActionResult(exec_id, 12000);
            try { ws.send(JSON.stringify({ type:'action', header:{ device_id, tab_id: null }, exec_id, action:'open_url', args:{ url: start_url, active: true } })); } catch {}
            try {
              const out = await waiter;
              if (out && out.ok && out.result && typeof out.result.tab_id === 'number') {
                tab_id = out.result.tab_id;
              }
            } catch {}
          }
        }
        if (tab_id > 0) {
          RunBindings.set(runId, { device_id, tab_id });
          bound = true; bDevice = device_id; bTab = tab_id;
          // Best-effort: ensure page is quiet and mark ready to satisfy immediate waits
          try {
            const key = `${device_id}:${tab_id}`;
            const ws2 = ConnRegistry.get(key);
            if (ws2) {
              const exec2 = uuid();
              const waiter2 = awaitActionResult(exec2, 4000);
              try { ws2.send(JSON.stringify({ type:'action', header:{ device_id, tab_id }, exec_id: exec2, action:'ext.wait_quiet', args:{ timeout_ms: 3000 } })); } catch {}
              try { await waiter2; } catch {}
              // Mark ready in TabRegistry so /runs/wait_quiet can return immediately
              try {
                const meta = TabRegistry.get(key) || {};
                meta.ready = true; meta.ts = Date.now();
                TabRegistry.set(key, meta);
              } catch {}
            }
          } catch {}
        }
      }
    } catch (e) {
      console.warn('[ORCH] auto-bind failed:', e?.message || e);
    }

    res.json({
      ok: true,
      run_id: runId,
      workflow_name: workflowName,
      steps: stepIdx,
      status: 'running',
      bound,
      device_id: bDevice,
      tab_id: bTab
    });
    
  } catch (error) {
    console.error('[ORCHESTRATOR] Error starting workflow:', error);
    res.status(500).json({ ok: false, error: error.message });
  }
});

/**
 * Report step execution result
 * POST /runs/step_result  
 * Body: { id: step_id, run_id: run_id, ok: true/false, data: {...}, error: "...", artifacts: [...] }
 */
app.post('/runs/step_result', async (req, res) => {
  try {
    const { id, run_id, ok, data, error, artifacts = [] } = req.body;
    
    if (!id || !run_id) {
      return res.status(400).json({ ok: false, error: 'Missing id or run_id' });
    }
    
    // Find the pending step
    const step = await q_one(
      "SELECT id, run_id, idx FROM run_steps WHERE id=$1 AND run_id=$2 AND status='pending'",
      [id, run_id]
    );
    
    if (!step) {
      return res.json({ ok: true, note: 'Step not found or not pending', id, run_id });
    }
    
    // Update step status
    await q(
      "UPDATE run_steps SET status=$1, output=$2, error=$3, finished_at=NOW() WHERE id=$4",
      [
        ok ? 'success' : 'failed',
        JSON.stringify(data || null),
        error || null,
        id
      ]
    );
    
    // Save artifacts
    for (const artifact of artifacts) {
      await q(
        "INSERT INTO artifacts(run_id, kind, path, payload, created_at) VALUES ($1, $2, $3, $4, NOW())",
        [run_id, artifact.kind || 'unknown', artifact.path || null, artifact.payload || null]
      );
    }
    
    console.log(`[ORCHESTRATOR] Step ${id} completed: ${ok ? 'success' : 'failed'}`);
    
    // Check if workflow is complete
    const pendingCount = await q_one(
      "SELECT COUNT(*)::int AS count FROM run_steps WHERE run_id=$1 AND status='pending'",
      [run_id]
    );
    
    if (pendingCount.count === 0) {
      // All steps completed, mark workflow as finished
      const failedCount = await q_one(
        "SELECT COUNT(*)::int AS count FROM run_steps WHERE run_id=$1 AND status='failed'",
        [run_id]
      );
      
      const finalStatus = failedCount.count > 0 ? 'failed' : 'completed';
      await q(
        "UPDATE workflow_runs SET status=$1, finished_at=NOW() WHERE id=$2",
        [finalStatus, run_id]
      );
      
      console.log(`[ORCHESTRATOR] Workflow ${run_id} finished with status: ${finalStatus}`);
    }
    
    res.json({ ok: true, step_id: id, workflow_complete: pendingCount.count === 0 });
    
  } catch (error) {
    console.error('[ORCHESTRATOR] Error processing step result:', error);
    res.status(500).json({ ok: false, error: error.message });
  }
});

/**
 * Save text artifact (called by extension content script)
 * POST /artifacts/save_text
 * Body: { run_id: "...", path: "...", text: "..." }
 */
app.post('/artifacts/save_text', async (req, res) => {
  try {
    const { run_id, path, text } = req.body;
    
    if (!run_id || !path) {
      return res.status(400).json({ ok: false, error: 'Missing run_id or path' });
    }
    
    // Verify run exists
    const run = await q_one("SELECT id FROM workflow_runs WHERE id=$1", [run_id]);
    if (!run) {
      return res.status(404).json({ ok: false, error: 'Workflow run not found' });
    }
    
    // Redact PII (MVP): emails and phone-like numbers
    function redactPII(s = ''){
      try {
        let out = String(s);
        // emails
        out = out.replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, '[redacted_email]');
        // phone numbers (7-16 digits possibly separated by spaces or dashes)
        out = out.replace(/(?<!\d)(?:\+?\d[\s-]?){7,16}(?!\d)/g, '[redacted_phone]');
        return out;
      } catch { return s; }
    }
    const safeText = redactPII(text || '');

    // Save text artifact
    await q(
      "INSERT INTO artifacts(run_id, kind, path, payload, created_at) VALUES ($1, 'text', $2, $3, NOW())",
      [run_id, path, safeText]
    );
    
    console.log(`[ORCHESTRATOR] Saved text artifact: ${path} (${text?.length || 0} chars)`);
    
    res.json({ ok: true, path, size: safeText?.length || 0 });
    
  } catch (error) {
    console.error('[ORCHESTRATOR] Error saving text artifact:', error);
    res.status(500).json({ ok: false, error: error.message });
  }
});

/**
 * Get next command for extension execution
 * POST /commands/next
 * Body: { device_id: "..." }
 */
app.post('/commands/next', async (req, res) => {
  try {
    const { device_id } = req.body;
    
    // Get next pending command
    const command = await q_one(
      "SELECT * FROM commands WHERE status='pending' ORDER BY created_at ASC LIMIT 1"
    );
    
    if (!command) {
      return res.json({ cmd: null });
    }
    
    // Mark command as processing
    await q(
      "UPDATE commands SET status='processing', processed_at=NOW() WHERE id=$1",
      [command.id]
    );
    
    console.log(`[ORCHESTRATOR] Command claimed by device ${device_id}: ${command.id}`);
    
    // Return command in expected format
    const payload = typeof command.payload === 'string' ? JSON.parse(command.payload) : command.payload;
    
    res.json({
      cmd: {
        id: payload.id || command.id,
        run_id: payload.run_id,
        type: payload.type,
        action: payload.action,
        timestamp: command.created_at
      }
    });
    
  } catch (error) {
    console.error('[ORCHESTRATOR] Error getting next command:', error);
    res.status(500).json({ ok: false, error: error.message });
  }
});

/**
 * Acknowledge command execution result
 * POST /commands/ack  
 * Body: { id: "...", status: "succeeded|failed", result: {...}, error: "..." }
 */
app.post('/commands/ack', async (req, res) => {
  try {
    const { id, status, result, error } = req.body;
    
    // Update command status
    await q(
      "UPDATE commands SET status=$1 WHERE id=$2 OR payload->>'id'=$3",
      [status === 'succeeded' ? 'completed' : 'failed', id, id]
    );
    
    // If this was a workflow step, update the run_steps table
    if (result || error) {
      try {
        await q(
          "UPDATE run_steps SET status=$1, output=$2, error=$3, finished_at=NOW() WHERE id=$4",
          [status === 'succeeded' ? 'success' : 'failed', JSON.stringify(result || null), error || null, id]
        );
      } catch (e) {
        console.warn(`[ORCHESTRATOR] Could not update run_steps for ${id}:`, e.message);
      }
    }
    
    console.log(`[ORCHESTRATOR] Command acknowledged: ${id} - ${status}`);
    
    res.json({ ok: true });
    
  } catch (error) {
    console.error('[ORCHESTRATOR] Error acknowledging command:', error);
    res.status(500).json({ ok: false, error: error.message });
  }
});

/**
 * Get workflow run status and results
 * GET /runs/:runId
 */
app.get('/runs/:runId', async (req, res) => {
  try {
    const runId = req.params.runId;
    
    const run = await q_one(
      "SELECT * FROM workflow_runs WHERE id=$1",
      [runId]
    );
    
    if (!run) {
      return res.status(404).json({ ok: false, error: 'Workflow run not found' });
    }
    
    const steps = await q(
      "SELECT * FROM run_steps WHERE run_id=$1 ORDER BY idx ASC",
      [runId]
    );
    
    const artifacts = await q(
      "SELECT * FROM artifacts WHERE run_id=$1 ORDER BY created_at ASC",
      [runId]
    );
    
    res.json({
      ok: true,
      run: run,
      steps: steps,
      artifacts: artifacts
    });
    
  } catch (error) {
    console.error('[ORCHESTRATOR] Error getting run status:', error);
    res.status(500).json({ ok: false, error: error.message });
  }
});

/**
 * List recent workflow runs
 * GET /runs?limit=10
 */
app.get('/runs', async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 10, 100);
    
    const runs = await q(
      "SELECT wr.*, COUNT(rs.id) AS step_count, COUNT(a.id) AS artifact_count FROM workflow_runs wr LEFT JOIN run_steps rs ON wr.id = rs.run_id LEFT JOIN artifacts a ON wr.id = a.run_id GROUP BY wr.id ORDER BY wr.created_at DESC LIMIT $1",
      [limit]
    );
    
    res.json({ ok: true, runs });
    
  } catch (error) {
    console.error('[ORCHESTRATOR] Error listing runs:', error);
    res.status(500).json({ ok: false, error: error.message });
  }
});

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ ok: true, service: 'orchestrator', timestamp: new Date().toISOString() });
});

// Lightweight page-stable signal for extension → Python workflow integration
let __pageStable = false;
let __pageStableAt = 0;
const __STABLE_WINDOW_MS = parseInt(process.env.SIGNAL_WINDOW_MS || '3000', 10);
function __isStableNow(){
  if (!__pageStable) return false;
  if (Date.now() - __pageStableAt > __STABLE_WINDOW_MS) { __pageStable = false; }
  return __pageStable;
}
app.get('/page_stable', (_req, res) => {
  res.json({ stable: __isStableNow() });
});
app.post('/page_stable', (req, res) => {
  try {
    const { ready, url, route_change, header } = req.body || {};
    const hdr = header || {};
    __pageStable = true; __pageStableAt = Date.now();
    console.log('[ORCH] page_stable:', {
      ready: !!ready, url: url || null, route_change: !!route_change,
      device_id: hdr.device_id || null, tab_id: hdr.tab_id || null, ts: hdr.ts || Date.now()
    });
    res.status(200).json({ ok: true });
  } catch (e) {
    __pageStable = true; __pageStableAt = Date.now();
    res.status(200).json({ ok: true });
  }
});

const PORT = process.env.ORCHESTRATOR_PORT || 8788;

// Optional WS server state (MVP)
const ConnRegistry = new Map(); // key: `${device_id}:${tab_id}` -> ws
const CommandQueue = new Map(); // key -> [{exec_id, action, args, header}]
const ActionWaiters = new Map(); // exec_id -> { resolve, reject, t }
let WSS_ENABLED = false;
const RunBindings = new Map(); // run_id -> { device_id, tab_id }
const RunWaiters = new Map(); // run_id -> [{ resolve, reject, t }]
const TabRegistry = new Map(); // key -> { last_url, host, ready, ts }

function keyOf(hdr = {}){
  return `${hdr.device_id || 'dev'}:${hdr.tab_id || 'tab'}`;
}

function enqueueAction(header, exec_id, action, args){
  const key = keyOf(header);
  const msg = { type:'action', header, exec_id, action, args };
  console.log(`[ORCH] enqueueAction ${action} for key=${key}, has_ws=${!!ConnRegistry.get(key)}`);
  const ws = ConnRegistry.get(key);
  if (ws && ws.readyState === 1) {
    console.log(`[ORCH] sending action ${action} directly via WS to ${key}`);
    try { ws.send(JSON.stringify(msg)); return true; } catch (e) { console.log(`[ORCH] WS send failed:`, e.message); }
  }
  console.log(`[ORCH] queueing action ${action} for ${key} (ws not ready)`);
  const q = CommandQueue.get(key) || [];
  q.push(msg);
  CommandQueue.set(key, q);
  return false;
}

function pumpQueueFor(key){
  const ws = ConnRegistry.get(key);
  if (!ws || ws.readyState !== 1) return;
  const q = CommandQueue.get(key) || [];
  while (q.length) {
    const m = q.shift();
    try { ws.send(JSON.stringify(m)); } catch { q.unshift(m); break; }
  }
  if (q.length === 0) CommandQueue.delete(key); else CommandQueue.set(key, q);
}

function awaitActionResult(exec_id, timeout_ms = 10000){
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => {
      ActionWaiters.delete(exec_id);
      resolve({ ok:false, error:'timeout' });
    }, timeout_ms);
    ActionWaiters.set(exec_id, { resolve, reject, t });
  });
}

async function initWS(server){
  let WebSocketServer;
  try {
    ({ WebSocketServer } = await import('ws'));
  } catch (e) {
    console.warn('[ORCH] WS not available (install "ws"): ', e?.message || e);
    return null;
  }
  const wss = new WebSocketServer({ server, path: '/ws' });
  WSS_ENABLED = true;
  wss.on('connection', (ws, req) => {
    ws._meta = { key: null };
    ws.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString());
        if (!msg || typeof msg !== 'object') return;
        if (msg.type === 'register') {
          const hdr = msg.header || {};
          const key = keyOf(hdr);
          ws._meta.key = key;
          ConnRegistry.set(key, ws);
          ws.send(JSON.stringify({ type:'registered', ok:true }));
          console.log('[WS] register', key);
          // pump pending actions for this bucket
          try { pumpQueueFor(key); } catch {}
          return;
        }
        if (msg.type === 'heartbeat') {
          ws.send(JSON.stringify({ type:'heartbeat_ack', ok:true, ts: Date.now() }));
          return;
        }
        if (msg.type === 'page_event') {
          const hdr = msg.header || {};
          const key = keyOf(hdr);
          if (msg.ready) { __pageStable = true; __pageStableAt = Date.now(); }
          console.log('[WS] page_event', { key, url: msg.url || null, ready: !!msg.ready, route_change: !!msg.route_change });
          // Wake any run waiters bound to this key
          try {
            for (const [runId, bind] of RunBindings.entries()) {
              if (bind && keyOf(bind) === key) {
                const arr = RunWaiters.get(runId) || [];
                while (arr.length) {
                  const w = arr.shift(); if (!w) break;
                  clearTimeout(w.t);
                  w.resolve({ ok: true, signals: { ready: !!msg.ready } });
                }
                if (arr.length) RunWaiters.set(runId, arr); else RunWaiters.delete(runId);
              }
            }
          } catch {}
          return;
        }
        if (msg.type === 'action_result') {
          const exec_id = msg.exec_id;
          const waiter = exec_id ? ActionWaiters.get(exec_id) : null;
          if (waiter) {
            clearTimeout(waiter.t);
            ActionWaiters.delete(exec_id);
            waiter.resolve({ ok: !!msg.ok, action: msg.action, result: msg.result, error: msg.error || null });
          }
          return;
        }
      } catch (e) {
        console.warn('[WS] message error', e?.message || e);
      }
    });
    ws.on('close', () => {
      const key = ws._meta?.key;
      if (key && ConnRegistry.get(key) === ws) ConnRegistry.delete(key);
    });
  });
  console.log('[ORCH] WS listening at /ws');
  return wss;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  // Direct execution
  const server = app.listen(PORT, async () => {
    console.log(`[ORCHESTRATOR] Server running on port ${PORT}`);
    console.log(`[ORCHESTRATOR] Health check: http://localhost:${PORT}/health`);
  });
  // Initialize WS (optional)
  try { await initWS(server); } catch {}
}

export default app;

// --- HTTP bridge to enqueue a WS action (MVP/testing) ---
app.post('/ws/action', async (req, res) => {
  try {
    const { header = {}, exec_id, action, args = {}, await_result = false, timeout_ms = 10000 } = req.body || {};
    if (!action) return res.status(400).json({ ok:false, error:'missing action' });
    const id = exec_id || uuid();
    const sent = enqueueAction(header, id, action, args);
    if (await_result) {
      const out = await awaitActionResult(id, timeout_ms);
      return res.json(Object.assign({ ok: out.ok, exec_id: id }, out));
    }
    res.json({ ok:true, exec_id: id, sent });
  } catch (e) {
    res.status(500).json({ ok:false, error: e?.message || String(e) });
  }
});

// WS health endpoint for clients to decide whether to connect
app.get('/ws/health', (_req, res) => {
  res.json({ ok: true, ws: !!WSS_ENABLED });
});

// List current WS connections (device_id:tab_id)
app.get('/ws/connections', (_req, res) => {
  try {
    const items = Array.from(ConnRegistry.keys()).map(k => ({ key: k }));
    res.json({ ok: true, items });
  } catch (e) {
    res.status(500).json({ ok: false, error: e?.message || String(e) });
  }
});

// --- Run-scoped dispatch: Engine only needs run_id ---
app.post('/actions/dispatch', async (req, res) => {
  try {
    const { run_id, step_id = null, exec_id = uuid(), action, args = {}, await_result = true, timeout_ms = 10000 } = req.body || {};
    if (!run_id || !action) return res.status(400).json({ ok:false, error:'missing run_id or action' });
    const bind = RunBindings.get(run_id);
    if (!bind) return res.json({ ok:false, error:'not_bound' });
    const sent = enqueueAction(bind, exec_id, action, args);
    if (!await_result) return res.json({ ok:true, sent, exec_id });
    const out = await awaitActionResult(exec_id, timeout_ms);
    return res.json(Object.assign({ exec_id }, out));
  } catch (e) {
    res.status(500).json({ ok:false, error: e?.message || String(e) });
  }
});

// Wait for page quiet for a bound run (maps to WS page_event)
app.post('/runs/wait_quiet', async (req, res) => {
  try {
    const { run_id, step_id = null, timeout_ms = 8000 } = req.body || {};
    if (!run_id) return res.status(400).json({ ok:false, error:'missing run_id' });
    const bind = RunBindings.get(run_id);
    if (!bind) return res.json({ ok:false, error:'not_bound' });
    // Immediate pass if current tab is already ready
    try {
      const key = `${bind.device_id}:${bind.tab_id}`;
      const meta = TabRegistry.get(key) || {};
      if (meta && meta.ready === true) {
        return res.json({ ok:true, signals:{ ready:true } });
      }
    } catch {}
    const p = new Promise((resolve) => {
      const t = setTimeout(() => {
        const arr = RunWaiters.get(run_id) || [];
        // remove this waiter if still in list
        RunWaiters.set(run_id, arr.filter(x => x.t !== t));
        resolve({ ok:false, error:'timeout' });
      }, timeout_ms);
      const arr = RunWaiters.get(run_id) || [];
      arr.push({ resolve, t });
      RunWaiters.set(run_id, arr);
    });
    const out = await p;
    res.json(out);
  } catch (e) {
    res.status(500).json({ ok:false, error: e?.message || String(e) });
  }
});

// Manual bind endpoint (optional): bind run to a tab
app.post('/runs/bind', (req, res) => {
  try {
    const { run_id, device_id, tab_id } = req.body || {};
    if (!run_id || !device_id || typeof tab_id !== 'number') return res.status(400).json({ ok:false, error:'missing params' });
    RunBindings.set(run_id, { device_id, tab_id });
    res.json({ ok:true });
  } catch (e) {
    res.status(500).json({ ok:false, error: e?.message || String(e) });
  }
});

// Rebind endpoint: handle tab disappearance/id change and rebind to domain-matching tab
app.post('/runs/rebind', async (req, res) => {
  try {
    const { run_id, policy = 'active_or_new', domain = null, start_url = null } = req.body || {};
    if (!run_id) return res.status(400).json({ ok:false, error:'missing run_id' });
    
    console.log(`[ORCH] rebind request for ${run_id}, policy=${policy}, domain=${domain}`);
    
    // Try to find a suitable tab
    const wantDomain = domain || (start_url ? new URL(start_url).host : null);
    const keys = Array.from(ConnRegistry.keys());
    let chosenKey = null;
    
    // Prefer ready tab matching domain
    if (wantDomain) {
      for (const k of keys) {
        const meta = TabRegistry.get(k) || {};
        if (meta && meta.ready && meta.host && meta.host.includes(wantDomain)) { 
          chosenKey = k; 
          break; 
        }
      }
    }
    
    // Fallback to any ready tab if policy allows
    if (!chosenKey && policy.includes('active')) {
      for (const k of keys) {
        const meta = TabRegistry.get(k) || {};
        if (meta && meta.ready) { 
          chosenKey = k; 
          break; 
        }
      }
    }
    
    // If no suitable tab and policy allows, create new one
    if (!chosenKey && policy.includes('new') && start_url && keys.length > 0) {
      const firstKey = keys[0];
      const [device_id] = firstKey.split(':');
      const ws = ConnRegistry.get(firstKey);
      if (ws) {
        const exec_id = uuid();
        const waiter = awaitActionResult(exec_id, 12000);
        try { 
          ws.send(JSON.stringify({ 
            type:'action', 
            header:{ device_id, tab_id: null }, 
            exec_id, 
            action:'open_url', 
            args:{ url: start_url, active: true } 
          })); 
        } catch {}
        
        try {
          const out = await waiter;
          if (out && out.ok && out.result && typeof out.result.tab_id === 'number') {
            chosenKey = `${device_id}:${out.result.tab_id}`;
          }
        } catch {}
      }
    }
    
    if (!chosenKey) {
      return res.json({ ok:false, error:'no_suitable_tab' });
    }
    
    // Parse chosen key and update binding
    const [device_id, tab_id_raw] = chosenKey.split(':');
    const tab_id = parseInt(tab_id_raw, 10);
    
    if (!(tab_id > 0)) {
      return res.json({ ok:false, error:'invalid_tab_id' });
    }
    
    // Update binding
    RunBindings.set(run_id, { device_id, tab_id });
    
    // Ensure page is quiet and ready
    try {
      const ws = ConnRegistry.get(chosenKey);
      if (ws) {
        const exec_id = uuid();
        const waiter = awaitActionResult(exec_id, 4000);
        try { 
          ws.send(JSON.stringify({ 
            type:'action', 
            header:{ device_id, tab_id }, 
            exec_id, 
            action:'ext.wait_quiet', 
            args:{ timeout_ms: 3000 } 
          })); 
        } catch {}
        try { await waiter; } catch {}
        
        // Mark ready in TabRegistry
        const meta = TabRegistry.get(chosenKey) || {};
        meta.ready = true; 
        meta.ts = Date.now();
        TabRegistry.set(chosenKey, meta);
      }
    } catch {}
    
    console.log(`[ORCH] rebind success: ${run_id} -> ${device_id}:${tab_id}`);
    res.json({ ok:true, device_id, tab_id, key: chosenKey });
    
  } catch (error) {
    console.error('[ORCH] rebind error:', error);
    res.status(500).json({ ok:false, error: error.message });
  }
});
