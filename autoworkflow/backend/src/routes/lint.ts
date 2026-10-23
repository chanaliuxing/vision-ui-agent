import { Router } from 'express';
import { WorkflowLinter } from '../lib/linter.js';
import { loadActionSchemas } from '../lib/ajv.js';
import type { WorkflowDefinition, LintResult, LintContext } from '../types.js';

const router = Router();

// POST /lint - Lint a workflow for semantic issues
router.post('/lint', (req, res) => {
  try {
    const { workflow, device, evidence } = req.body || {};
    const wf = workflow || req.body; // 兼容老用法：直接传 workflow 对象

    if (!wf) {
      return res.status(400).json({
        success: false,
        error: 'No workflow data provided'
      });
    }

    // Load action schemas/registry
    const actionSchemas = loadActionSchemas();

    // Create linter instance
    const linter = new WorkflowLinter(actionSchemas);

    // 构建上下文
    const context: LintContext = { device, evidence };

    // Run lint checks with context
    const issues = linter.lint(wf, context);

    const result: LintResult = {
      issues,
      workflow_name: wf.name,
      workflow_version: wf.version
    };

    // Return issues with appropriate status
    const hasErrors = issues.some(issue => issue.level === 'error');
    const statusCode = hasErrors ? 400 : 200;

    res.status(statusCode).json({
      success: !hasErrors,
      ...result,
      summary: {
        errors: issues.filter(i => i.level === 'error').length,
        warnings: issues.filter(i => i.level === 'warn').length,
        info: issues.filter(i => i.level === 'info').length,
        total: issues.length
      }
    });

  } catch (error) {
    console.error('Lint service error:', error);
    res.status(500).json({
      success: false,
      error: 'Lint service error',
      details: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});

export default router;