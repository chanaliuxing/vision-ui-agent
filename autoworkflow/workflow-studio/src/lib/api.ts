// M2: Frontend Studio - API Client
// Connects to M1 Backend APIs

import {
  WorkflowDefinition,
  ValidationResult,
  LintResult,
  SimResult,
  ActionRegistry,
  WorkflowTemplate,
  LintIssue
} from './types';

const API_BASE_URL = 'http://localhost:8799';

class WorkflowAPI {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  // M1-S1: Validation API
  async validateWorkflow(workflow: WorkflowDefinition): Promise<ValidationResult> {
    const response = await fetch(`${this.baseUrl}/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(workflow)
    });

    if (!response.ok) {
      throw new Error(`Validation failed: ${response.statusText}`);
    }

    return response.json();
  }

  // M1-S2: Lint API
  async lintWorkflow(workflow: WorkflowDefinition, evidence?: any, device?: any): Promise<LintResult> {
    const payload = evidence || device ? { workflow, evidence, device } : workflow;

    const response = await fetch(`${this.baseUrl}/lint`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const result = await response.json();

    // Handle both success and error responses
    if (result.success === false && result.issues) {
      return {
        issues: result.issues,
        workflow_name: result.workflow_name,
        workflow_version: result.workflow_version,
        summary: result.summary
      };
    }

    return result;
  }

  // M1-S3: Simulation API
  async simulateWorkflow(workflow: WorkflowDefinition, options?: {
    provider?: string;
    debug?: boolean;
    device?: any;
  }): Promise<SimResult> {
    const response = await fetch(`${this.baseUrl}/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workflow, ...options })
    });

    if (!response.ok) {
      throw new Error(`Simulation failed: ${response.statusText}`);
    }

    return response.json();
  }

  // M1-S4: Generation API
  async generateWorkflow(prompt: string, options?: {
    complexity?: number;
    allow_actions?: string[];
    provider?: string;
  }): Promise<WorkflowDefinition> {
    const response = await fetch(`${this.baseUrl}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, ...options })
    });

    if (!response.ok) {
      throw new Error(`Generation failed: ${response.statusText}`);
    }

    const result = await response.json();
    return result.workflow;
  }

  // M1-S5: Auto-fix API
  async fixWorkflow(workflow: WorkflowDefinition, issues: LintIssue[]): Promise<{
    patched: WorkflowDefinition;
    patch: any[];
    notes: string[];
    appliedFixes: LintIssue[];
  }> {
    const response = await fetch(`${this.baseUrl}/fix`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workflow, issues })
    });

    if (!response.ok) {
      throw new Error(`Fix failed: ${response.statusText}`);
    }

    return response.json();
  }

  // M1-S6: Templates API
  async getTemplates(): Promise<Array<{ id: string; name: string; description: string; category: string }>> {
    const response = await fetch(`${this.baseUrl}/templates`);

    if (!response.ok) {
      throw new Error(`Failed to fetch templates: ${response.statusText}`);
    }

    return response.json();
  }

  async getTemplate(templateId: string): Promise<WorkflowTemplate> {
    const response = await fetch(`${this.baseUrl}/templates/${templateId}`);

    if (!response.ok) {
      throw new Error(`Failed to fetch template: ${response.statusText}`);
    }

    return response.json();
  }

  async generateFromTemplate(templateId: string, parameters: Record<string, any>): Promise<WorkflowDefinition> {
    const response = await fetch(`${this.baseUrl}/templates/${templateId}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parameters })
    });

    if (!response.ok) {
      throw new Error(`Template generation failed: ${response.statusText}`);
    }

    const result = await response.json();
    return result.workflow;
  }

  // Registry APIs
  async getActionRegistry(): Promise<ActionRegistry> {
    const response = await fetch(`${this.baseUrl}/registry/actions`);

    if (!response.ok) {
      throw new Error(`Failed to fetch registry: ${response.statusText}`);
    }

    return response.json();
  }

  async getActionSchema(actionId: string): Promise<any> {
    const response = await fetch(`${this.baseUrl}/registry/actions/${actionId}`);

    if (!response.ok) {
      throw new Error(`Failed to fetch action schema: ${response.statusText}`);
    }

    return response.json();
  }

  // Schema APIs
  async getWorkflowSchema(): Promise<any> {
    const response = await fetch(`${this.baseUrl}/schemas/workflow`);

    if (!response.ok) {
      throw new Error(`Failed to fetch workflow schema: ${response.statusText}`);
    }

    return response.json();
  }

  async getStepSchema(): Promise<any> {
    const response = await fetch(`${this.baseUrl}/schemas/step`);

    if (!response.ok) {
      throw new Error(`Failed to fetch step schema: ${response.statusText}`);
    }

    return response.json();
  }

  // Health check
  async healthCheck(): Promise<{ status: string; timestamp: string }> {
    const response = await fetch(`${this.baseUrl}/health`);

    if (!response.ok) {
      throw new Error(`Health check failed: ${response.statusText}`);
    }

    return response.json();
  }
}

// Singleton instance
export const workflowAPI = new WorkflowAPI();

// Export for testing with different base URLs
export { WorkflowAPI };