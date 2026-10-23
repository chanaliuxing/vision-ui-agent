import express from 'express';
import { v4 as uuid } from 'uuid';

const router = express.Router();

// Dispatch action to extension via orchestrator WebSocket
router.post('/actions/dispatch', async (req, res) => {
  try {
    const { action, args, device_id = 'dev_device_001', tab_id = 1793631353 } = req.body;

    console.log(`[ACTIONS] Dispatching action: ${action}`, args);

    // Forward to orchestrator WebSocket system
    const exec_id = uuid();
    const header = { device_id, tab_id, ts: Date.now() };

    // Send to orchestrator via HTTP to enqueue WebSocket action
    const orchestratorRes = await fetch('http://127.0.0.1:8788/ws/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        header,
        exec_id,
        action,
        args
      })
    });

    if (!orchestratorRes.ok) {
      throw new Error(`Orchestrator returned ${orchestratorRes.status}`);
    }

    const result = await orchestratorRes.json();

    console.log(`[ACTIONS] Dispatched action ${action} with exec_id ${exec_id}`);

    res.json({
      success: true,
      action,
      exec_id,
      timestamp: Date.now(),
      result: 'dispatched_via_orchestrator'
    });
  } catch (error) {
    console.error('[ACTIONS] Failed to dispatch action:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to dispatch action'
    });
  }
});

export default router;