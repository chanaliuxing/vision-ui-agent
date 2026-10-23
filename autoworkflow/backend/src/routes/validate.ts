import { Router } from 'express';
import { createValidator } from '../lib/ajv.js';
import type { WorkflowDefinition, ValidationResult, ValidationError } from '../types.js';

const router = Router();

// POST /validate - Validate a workflow definition
router.post('/validate', (req, res) => {
  try {
    const workflow: WorkflowDefinition = req.body;

    if (!workflow) {
      return res.status(400).json({
        success: false,
        error: 'No workflow data provided'
      });
    }

    const { validateWorkflow, actionSchemas } = createValidator();

    // Step 1: Basic JSON Schema validation
    const isValid = validateWorkflow(workflow);
    const errors: ValidationError[] = [];

    if (!isValid && validateWorkflow.errors) {
      for (const error of validateWorkflow.errors) {
        errors.push({
          path: error.instancePath || '/',
          message: error.message || 'Validation error',
          value: error.data,
          schema: error.schema
        });
      }
    }

    // Step 2: Semantic validation
    if (isValid) {
      const semanticErrors = validateSemantics(workflow, actionSchemas);
      errors.push(...semanticErrors);
    }

    const result: ValidationResult = {
      valid: errors.length === 0,
      errors
    };

    // Return appropriate status code
    const statusCode = result.valid ? 200 : 400;

    res.status(statusCode).json({
      success: result.valid,
      ...result,
      workflow_name: workflow.name,
      workflow_version: workflow.version
    });

  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Validation service error',
      details: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});

// Semantic validation logic
function validateSemantics(workflow: WorkflowDefinition, actionSchemas: Record<string, any>): ValidationError[] {
  const errors: ValidationError[] = [];

  // Check if start step exists
  const startStep = workflow.steps.find(step => step.id === workflow.start);
  if (!startStep) {
    errors.push({
      path: '/start',
      message: `Start step '${workflow.start}' not found in steps array`
    });
  }

  // Check step IDs are unique
  const stepIds = new Set<string>();
  workflow.steps.forEach((step, index) => {
    if (stepIds.has(step.id)) {
      errors.push({
        path: `/steps/${index}/id`,
        message: `Duplicate step ID: '${step.id}'`
      });
    }
    stepIds.add(step.id);
  });

  // Validate action usage
  workflow.steps.forEach((step, index) => {
    if (step.type === 'action' && step.uses) {
      if (!actionSchemas[step.uses]) {
        errors.push({
          path: `/steps/${index}/uses`,
          message: `Action '${step.uses}' not found in registry`
        });
      } else {
        // Validate action parameters against action schema (simplified for M1-S1)
        const actionDef = actionSchemas[step.uses];
        if (actionDef && actionDef.schema && step.params) {
          try {
            // Basic parameter validation - just check required fields exist
            const requiredParams = actionDef.schema.required || [];
            for (const requiredParam of requiredParams) {
              if (!(requiredParam in step.params)) {
                errors.push({
                  path: `/steps/${index}/params/${requiredParam}`,
                  message: `Missing required parameter: '${requiredParam}'`
                });
              }
            }
          } catch (error) {
            // Skip parameter validation errors for now
            console.warn(`Parameter validation skipped for ${step.uses}:`, error);
          }
        }
      }
    }
  });

  // Validate edges reference existing steps
  if (workflow.edges) {
    workflow.edges.forEach((edge, index) => {
      if (!stepIds.has(edge.from)) {
        errors.push({
          path: `/edges/${index}/from`,
          message: `Edge references non-existent step: '${edge.from}'`
        });
      }
      if (!stepIds.has(edge.to)) {
        errors.push({
          path: `/edges/${index}/to`,
          message: `Edge references non-existent step: '${edge.to}'`
        });
      }
    });
  }

  // Check goto references
  workflow.steps.forEach((step, index) => {
    if (step.on_error === 'goto' && step.goto) {
      if (!stepIds.has(step.goto)) {
        errors.push({
          path: `/steps/${index}/goto`,
          message: `Goto references non-existent step: '${step.goto}'`
        });
      }
    }
  });

  return errors;
}

export default router;