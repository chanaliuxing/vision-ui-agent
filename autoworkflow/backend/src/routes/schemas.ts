import { Router } from 'express';
import { loadWorkflowSchema, loadActionSchemas } from '../lib/ajv.js';
import type { ActionRegistry } from '../types.js';

const router = Router();

// GET /schemas - Return the workflow schema
router.get('/schemas', (req, res) => {
  try {
    const workflowSchema = loadWorkflowSchema();
    res.json({
      success: true,
      schema: workflowSchema
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Failed to load workflow schema',
      details: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});

// GET /schemas/workflow - Same as above, more specific
router.get('/schemas/workflow', (req, res) => {
  try {
    const workflowSchema = loadWorkflowSchema();
    res.json(workflowSchema);
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Failed to load workflow schema',
      details: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});

// GET /registry/actions - Return action registry
router.get('/registry/actions', (req, res) => {
  try {
    const actionSchemas = loadActionSchemas();

    // Convert to registry format
    const registry: ActionRegistry = {};
    for (const [actionId, actionDef] of Object.entries(actionSchemas)) {
      registry[actionId] = actionDef as any;
    }

    res.json({
      success: true,
      registry,
      count: Object.keys(registry).length
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Failed to load action registry',
      details: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});

// GET /registry/actions/:actionId - Get specific action schema
router.get('/registry/actions/:actionId', (req, res) => {
  try {
    const { actionId } = req.params;
    const actionSchemas = loadActionSchemas();

    if (!actionSchemas[actionId]) {
      return res.status(404).json({
        success: false,
        error: `Action '${actionId}' not found in registry`
      });
    }

    res.json({
      success: true,
      action: actionSchemas[actionId]
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Failed to load action',
      details: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});

export default router;