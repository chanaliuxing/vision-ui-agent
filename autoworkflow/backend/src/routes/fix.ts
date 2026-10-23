import express from 'express';
import { loadActionSchemas } from '../lib/ajv';
import { WorkflowLinter } from '../lib/linter';
import { enhancedAutoFix } from '../lib/autoFix';
import type { WorkflowDefinition, LintIssue } from '../types';

const router = express.Router();

router.post('/fix', async (req, res) => {
  try {
    const workflow: WorkflowDefinition = req.body;

    if (!workflow) {
      return res.status(400).json({
        success: false,
        error: 'No workflow provided'
      });
    }

    // Load action schemas/registry
    const actionSchemas = loadActionSchemas();
    const linter = new WorkflowLinter(actionSchemas);

    // Run lint first to identify issues
    const issues = linter.lint(workflow);

    // Apply enhanced auto-fixes
    const fixResult = enhancedAutoFix(workflow, issues);

    // Re-lint to check for remaining issues
    const remainingIssues = linter.lint(fixResult.patched);

    res.json({
      success: true,
      originalIssues: issues.length,
      fixedIssues: fixResult.appliedFixes.length,
      remainingIssues: remainingIssues.length,
      workflow: fixResult.patched,
      appliedFixes: fixResult.appliedFixes,
      patch: fixResult.patch,
      notes: fixResult.notes
    });

  } catch (error) {
    console.error('Fix error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fix workflow',
      details: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});

export { router as fixRouter };