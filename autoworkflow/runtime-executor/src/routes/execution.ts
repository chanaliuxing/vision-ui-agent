// M3: Execution API Routes - RESTful endpoints for workflow execution

import express from 'express';
import type {
  ExecutionRequest,
  ExecutionResponse,
  ExecutionStatusResponse,
  WorkflowDefinition,
  ExecutionConfig
} from '../types/index.js';
import { WorkflowExecutionManager } from '../services/WorkflowExecutionManager.js';

const router = express.Router();
const executionManager = new WorkflowExecutionManager();

/**
 * Start a new workflow execution
 * POST /api/executions
 */
router.post('/', async (req, res) => {
  try {
    const { workflow, config, variables }: ExecutionRequest = req.body;

    // Validate workflow
    if (!workflow || !workflow.name || !workflow.start || !workflow.steps) {
      return res.status(400).json({
        error: 'Invalid workflow definition',
        details: 'Workflow must have name, start, and steps'
      });
    }

    // Start execution
    const executionId = await executionManager.startExecution(workflow, config, variables);

    const response: ExecutionResponse = {
      executionId,
      status: 'pending',
      message: 'Execution started successfully'
    };

    res.status(201).json(response);

  } catch (error) {
    res.status(500).json({
      error: 'Failed to start execution',
      details: error.message
    });
  }
});

/**
 * Get execution status
 * GET /api/executions/:id
 */
router.get('/:id', async (req, res) => {
  try {
    const executionId = req.params.id;
    const execution = executionManager.getExecution(executionId);

    if (!execution) {
      return res.status(404).json({
        error: 'Execution not found',
        executionId
      });
    }

    const response: ExecutionStatusResponse = {
      executionId: execution.id,
      status: execution.status,
      progress: execution.progress,
      currentStep: execution.currentStep,
      trace: req.query.includeTrace === 'true' ? execution.context.trace : undefined,
      error: execution.status === 'failed' ? execution.context.trace[execution.context.trace.length - 1]?.error : undefined
    };

    res.json(response);

  } catch (error) {
    res.status(500).json({
      error: 'Failed to get execution status',
      details: error.message
    });
  }
});

/**
 * Get all executions
 * GET /api/executions
 */
router.get('/', async (req, res) => {
  try {
    const executions = executionManager.getAllExecutions();

    // Filter by status if provided
    const statusFilter = req.query.status as string;
    const filteredExecutions = statusFilter
      ? executions.filter(e => e.status === statusFilter)
      : executions;

    // Limit results
    const limit = parseInt(req.query.limit as string) || 100;
    const limitedExecutions = filteredExecutions.slice(0, limit);

    res.json({
      executions: limitedExecutions.map(e => ({
        id: e.id,
        workflow: { name: e.workflow.name, version: e.workflow.version },
        status: e.status,
        progress: e.progress,
        currentStep: e.currentStep,
        createdAt: e.createdAt,
        startedAt: e.startedAt,
        completedAt: e.completedAt
      })),
      total: filteredExecutions.length
    });

  } catch (error) {
    res.status(500).json({
      error: 'Failed to get executions',
      details: error.message
    });
  }
});

/**
 * Cancel an execution
 * DELETE /api/executions/:id
 */
router.delete('/:id', async (req, res) => {
  try {
    const executionId = req.params.id;
    const cancelled = await executionManager.cancelExecution(executionId);

    if (!cancelled) {
      return res.status(404).json({
        error: 'Execution not found or cannot be cancelled',
        executionId
      });
    }

    res.json({
      message: 'Execution cancelled successfully',
      executionId
    });

  } catch (error) {
    res.status(500).json({
      error: 'Failed to cancel execution',
      details: error.message
    });
  }
});

/**
 * Pause an execution
 * POST /api/executions/:id/pause
 */
router.post('/:id/pause', async (req, res) => {
  try {
    const executionId = req.params.id;
    const paused = await executionManager.pauseExecution(executionId);

    if (!paused) {
      return res.status(404).json({
        error: 'Execution not found or cannot be paused',
        executionId
      });
    }

    res.json({
      message: 'Execution paused successfully',
      executionId
    });

  } catch (error) {
    res.status(500).json({
      error: 'Failed to pause execution',
      details: error.message
    });
  }
});

/**
 * Resume an execution
 * POST /api/executions/:id/resume
 */
router.post('/:id/resume', async (req, res) => {
  try {
    const executionId = req.params.id;
    const resumed = await executionManager.resumeExecution(executionId);

    if (!resumed) {
      return res.status(404).json({
        error: 'Execution not found or cannot be resumed',
        executionId
      });
    }

    res.json({
      message: 'Execution resumed successfully',
      executionId
    });

  } catch (error) {
    res.status(500).json({
      error: 'Failed to resume execution',
      details: error.message
    });
  }
});

/**
 * Get execution trace/logs
 * GET /api/executions/:id/trace
 */
router.get('/:id/trace', async (req, res) => {
  try {
    const executionId = req.params.id;
    const execution = executionManager.getExecution(executionId);

    if (!execution) {
      return res.status(404).json({
        error: 'Execution not found',
        executionId
      });
    }

    res.json({
      executionId,
      trace: execution.context.trace,
      totalSteps: execution.context.trace.length
    });

  } catch (error) {
    res.status(500).json({
      error: 'Failed to get execution trace',
      details: error.message
    });
  }
});

/**
 * Get execution screenshots
 * GET /api/executions/:id/screenshots
 */
router.get('/:id/screenshots', async (req, res) => {
  try {
    const executionId = req.params.id;
    const execution = executionManager.getExecution(executionId);

    if (!execution) {
      return res.status(404).json({
        error: 'Execution not found',
        executionId
      });
    }

    const screenshots = execution.context.trace
      .filter(t => t.screenshot)
      .map(t => ({
        stepId: t.stepId,
        timestamp: t.timestamp,
        screenshot: t.screenshot,
        action: t.action
      }));

    res.json({
      executionId,
      screenshots,
      count: screenshots.length
    });

  } catch (error) {
    res.status(500).json({
      error: 'Failed to get execution screenshots',
      details: error.message
    });
  }
});

/**
 * Health check endpoint
 * GET /api/executions/health
 */
router.get('/health', async (req, res) => {
  try {
    const health = await executionManager.healthCheck();

    res.json({
      status: 'ok',
      timestamp: new Date(),
      executionManager: health,
      uptime: process.uptime()
    });

  } catch (error) {
    res.status(500).json({
      status: 'error',
      error: error.message,
      timestamp: new Date()
    });
  }
});

// Export both router and execution manager for WebSocket integration
export { router as executionRouter, executionManager };