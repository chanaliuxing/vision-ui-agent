import express from 'express';
import { v4 as uuidv4 } from 'uuid';

const router = express.Router();

// Store active runs in memory (could be moved to database later)
const activeRuns = new Map();

// Start a new run session
router.post('/runs/start', (req, res) => {
  try {
    const runId = uuidv4();
    const runData = {
      id: runId,
      startTime: Date.now(),
      status: 'active',
      clientConnected: false
    };

    activeRuns.set(runId, runData);

    res.json({
      success: true,
      run_id: runId,
      timestamp: runData.startTime
    });

    console.log(`[RUNS] Started new run: ${runId}`);
  } catch (error) {
    console.error('[RUNS] Failed to start run:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to start run'
    });
  }
});

// Get run status
router.get('/runs/:runId/status', (req, res) => {
  const runId = req.params.runId;
  const runData = activeRuns.get(runId);

  if (!runData) {
    return res.status(404).json({
      success: false,
      error: 'Run not found'
    });
  }

  res.json({
    success: true,
    run: runData
  });
});

// Stop a run
router.post('/runs/:runId/stop', (req, res) => {
  const runId = req.params.runId;
  const runData = activeRuns.get(runId);

  if (!runData) {
    return res.status(404).json({
      success: false,
      error: 'Run not found'
    });
  }

  runData.status = 'stopped';
  runData.stopTime = Date.now();

  res.json({
    success: true,
    run: runData
  });

  console.log(`[RUNS] Stopped run: ${runId}`);
});

// Page stability check endpoint
router.get('/page_stable', (req, res) => {
  // Simple mock implementation - returns stable after a short delay
  res.json({
    success: true,
    stable: true,
    timestamp: Date.now()
  });
});

// Wait for runs to be quiet/stable
router.post('/runs/wait_quiet', (req, res) => {
  // Mock implementation for wait_quiet
  res.json({
    success: true,
    quiet: true,
    timestamp: Date.now()
  });
});

export default router;