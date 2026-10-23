// M3: Workflow Execution Manager - Core orchestrator for workflow execution

import { EventEmitter } from 'events';
import type {
  WorkflowDefinition,
  WorkflowStep,
  WorkflowExecution,
  ExecutionContext,
  ExecutionConfig,
  ExecutionStatus,
  ExecutionTrace,
  ExecutionMode,
  HybridExecutionResult,
  ChromeExtensionConnection,
  VisionEngineConnection,
  BrowserContext,
  WSMessage
} from '../types/index.js';
import { HybridExecutor } from '../lib/HybridExecutor.js';
import { ChromeExtensionBridge } from '../lib/ChromeExtensionBridge.js';

export class WorkflowExecutionManager extends EventEmitter {
  private executions = new Map<string, WorkflowExecution>();
  private hybridExecutor: HybridExecutor;
  private chromeExtensionBridge: ChromeExtensionBridge;
  private browser?: BrowserContext;

  constructor() {
    super();

    this.chromeExtensionBridge = new ChromeExtensionBridge();
    this.hybridExecutor = new HybridExecutor();

    // Forward events from sub-components
    this.hybridExecutor.on('execution_plan', (data) => this.emit('execution_plan', data));
    this.hybridExecutor.on('fallback_triggered', (data) => this.emit('fallback_triggered', data));
    this.hybridExecutor.on('dom_action', (data) => this.emit('dom_action', data));
    this.hybridExecutor.on('vision_action', (data) => this.emit('vision_action', data));
  }

  /**
   * Start a new workflow execution
   */
  async startExecution(
    workflow: WorkflowDefinition,
    config: Partial<ExecutionConfig> = {},
    variables: Record<string, any> = {}
  ): Promise<string> {
    const executionId = `exec_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    // Create default execution config
    const defaultConfig: ExecutionConfig = {
      mode: 'hybrid',
      timeoutMs: 300000, // 5 minutes
      retryAttempts: 3,
      screenshotOnError: true,
      enableVisionFallback: true,
      visionConfidenceThreshold: 0.6,
      debugMode: false,
      saveTrace: true
    };

    const executionConfig = { ...defaultConfig, ...config };

    // Initialize execution context
    const context: ExecutionContext = {
      executionId,
      workflow,
      currentStepId: workflow.start,
      variables: { ...workflow.variables, ...variables },
      executionMode: executionConfig.mode,
      browser: this.browser,
      chromeExtension: this.chromeExtensionBridge.getConnection(),
      visionEngine: undefined, // Will be set by HybridExecutor
      startTime: new Date(),
      status: 'pending',
      trace: []
    };

    // Create workflow execution
    const execution: WorkflowExecution = {
      id: executionId,
      workflow,
      status: 'pending',
      context,
      config: executionConfig,
      createdAt: new Date(),
      currentStep: workflow.start,
      progress: {
        completed: 0,
        total: workflow.steps.length,
        percentage: 0
      }
    };

    this.executions.set(executionId, execution);

    // Emit execution start event
    this.emit('execution_start', {
      type: 'execution_start',
      executionId,
      data: { workflow: workflow.name, config: executionConfig },
      timestamp: new Date()
    } as WSMessage);

    // Start execution asynchronously
    this.executeWorkflow(executionId).catch(error => {
      this.handleExecutionError(executionId, error);
    });

    return executionId;
  }

  /**
   * Main workflow execution loop
   */
  private async executeWorkflow(executionId: string): Promise<void> {
    const execution = this.executions.get(executionId);
    if (!execution) {
      throw new Error(`Execution not found: ${executionId}`);
    }

    try {
      execution.status = 'running';
      execution.context.status = 'running';
      execution.startedAt = new Date();

      this.emitProgress(executionId);

      let currentStepId = execution.workflow.start;
      const visitedSteps = new Set<string>();

      while (currentStepId && execution.status === 'running') {
        // Prevent infinite loops
        if (visitedSteps.has(currentStepId)) {
          throw new Error(`Infinite loop detected at step: ${currentStepId}`);
        }
        visitedSteps.add(currentStepId);

        // Find current step
        const step = execution.workflow.steps.find(s => s.id === currentStepId);
        if (!step) {
          throw new Error(`Step not found: ${currentStepId}`);
        }

        // Update current step
        execution.currentStep = currentStepId;
        execution.context.currentStepId = currentStepId;

        // Execute step
        const stepResult = await this.executeStep(execution, step);

        // Update progress
        execution.progress.completed++;
        execution.progress.percentage = Math.round(
          (execution.progress.completed / execution.progress.total) * 100
        );

        this.emitProgress(executionId);

        // Determine next step
        if (stepResult.success) {
          currentStepId = this.getNextStep(execution.workflow, step, stepResult);
        } else {
          // Handle step failure
          if (step.on_error === 'fail') {
            throw new Error(`Step failed: ${step.id} - ${stepResult.primaryResult?.error}`);
          } else if (step.on_error === 'skip') {
            currentStepId = this.getNextStep(execution.workflow, step, stepResult);
          } else if (step.on_error === 'goto' && step.goto) {
            currentStepId = step.goto;
          } else {
            throw new Error(`Step failed with no error handling: ${step.id}`);
          }
        }

        // Check timeout
        if (Date.now() - execution.startedAt!.getTime() > execution.config.timeoutMs) {
          throw new Error('Execution timeout');
        }
      }

      // Execution completed successfully
      execution.status = 'completed';
      execution.context.status = 'completed';
      execution.completedAt = new Date();

      this.emit('execution_complete', {
        type: 'execution_complete',
        executionId,
        data: {
          duration: execution.completedAt.getTime() - execution.startedAt!.getTime(),
          steps: execution.progress.completed
        },
        timestamp: new Date()
      } as WSMessage);

    } catch (error) {
      this.handleExecutionError(executionId, error);
    }
  }

  /**
   * Execute a single workflow step
   */
  private async executeStep(
    execution: WorkflowExecution,
    step: WorkflowStep
  ): Promise<HybridExecutionResult> {
    const startTime = Date.now();

    try {
      // Evaluate step conditions
      if (step.when && !this.evaluateCondition(step.when, execution.context.variables)) {
        return {
          success: true,
          methodUsed: 'dom',
          totalDuration_ms: 0,
          screenshots: []
        };
      }

      // Execute step with retry logic
      let lastResult: HybridExecutionResult | null = null;
      const maxRetries = step.retry?.times || execution.config.retryAttempts;

      for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
          const result = await this.hybridExecutor.executeStep(step, execution.context);

          // Add to execution trace
          const trace: ExecutionTrace = {
            stepId: step.id,
            timestamp: new Date(),
            action: step.uses || 'unknown',
            method: result.methodUsed === 'both' ? 'hybrid' : result.methodUsed,
            input: step.params,
            output: result.primaryResult?.output || result.fallbackResult?.output,
            screenshot: result.screenshots[result.screenshots.length - 1],
            error: result.success ? undefined : result.primaryResult?.error,
            duration_ms: result.totalDuration_ms
          };

          execution.context.trace.push(trace);

          if (result.success) {
            // Update variables from step outputs
            if (step.outputs && result.primaryResult?.output) {
              Object.assign(execution.context.variables, {
                [step.id]: result.primaryResult.output,
                ...step.outputs
              });
            }

            this.emit('step_complete', {
              type: 'step_complete',
              executionId: execution.id,
              data: { stepId: step.id, result, attempt },
              timestamp: new Date()
            } as WSMessage);

            return result;
          }

          lastResult = result;

          // Wait before retry
          if (attempt < maxRetries && step.retry?.backoff_ms) {
            await new Promise(resolve => setTimeout(resolve, step.retry!.backoff_ms!));
          }

        } catch (error) {
          if (attempt === maxRetries) {
            throw error;
          }

          // Wait before retry
          if (step.retry?.backoff_ms) {
            await new Promise(resolve => setTimeout(resolve, step.retry!.backoff_ms!));
          }
        }
      }

      // All retries failed
      return lastResult || {
        success: false,
        methodUsed: 'dom',
        primaryResult: {
          success: false,
          method: 'dom',
          error: 'All retry attempts failed'
        },
        totalDuration_ms: Date.now() - startTime,
        screenshots: []
      };

    } catch (error) {
      return {
        success: false,
        methodUsed: 'dom',
        primaryResult: {
          success: false,
          method: 'dom',
          error: error.message
        },
        totalDuration_ms: Date.now() - startTime,
        screenshots: []
      };
    }
  }

  /**
   * Determine next step based on workflow edges and conditions
   */
  private getNextStep(
    workflow: WorkflowDefinition,
    currentStep: WorkflowStep,
    result: HybridExecutionResult
  ): string | null {
    // Check workflow edges
    if (workflow.edges) {
      for (const edge of workflow.edges) {
        if (edge.from === currentStep.id) {
          if (!edge.condition || this.evaluateCondition(edge.condition, result)) {
            return edge.to;
          }
        }
      }
    }

    // Find next step by position (fallback)
    const currentIndex = workflow.steps.findIndex(s => s.id === currentStep.id);
    if (currentIndex >= 0 && currentIndex < workflow.steps.length - 1) {
      return workflow.steps[currentIndex + 1].id;
    }

    return null; // End of workflow
  }

  /**
   * Simple condition evaluation
   */
  private evaluateCondition(condition: string, context: any): boolean {
    try {
      // Simple variable substitution and evaluation
      const expr = condition.replace(/\$\{([^}]+)\}/g, (match, varName) => {
        return JSON.stringify(context[varName]);
      });

      // Basic safety check - only allow simple comparisons
      if (!/^[a-zA-Z0-9\s"'.<>=!&|()]+$/.test(expr)) {
        return false;
      }

      return eval(expr);
    } catch (error) {
      console.error('Condition evaluation error:', error);
      return false;
    }
  }

  /**
   * Handle execution errors
   */
  private handleExecutionError(executionId: string, error: any): void {
    const execution = this.executions.get(executionId);
    if (execution) {
      execution.status = 'failed';
      execution.context.status = 'failed';
      execution.completedAt = new Date();
    }

    this.emit('execution_error', {
      type: 'execution_error',
      executionId,
      data: { error: error.message },
      timestamp: new Date()
    } as WSMessage);
  }

  /**
   * Emit progress update
   */
  private emitProgress(executionId: string): void {
    const execution = this.executions.get(executionId);
    if (execution) {
      this.emit('execution_progress', {
        type: 'execution_progress',
        executionId,
        data: {
          status: execution.status,
          progress: execution.progress,
          currentStep: execution.currentStep
        },
        timestamp: new Date()
      } as WSMessage);
    }
  }

  /**
   * Get execution status
   */
  getExecution(executionId: string): WorkflowExecution | undefined {
    return this.executions.get(executionId);
  }

  /**
   * Get all executions
   */
  getAllExecutions(): WorkflowExecution[] {
    return Array.from(this.executions.values());
  }

  /**
   * Cancel execution
   */
  async cancelExecution(executionId: string): Promise<boolean> {
    const execution = this.executions.get(executionId);
    if (execution && execution.status === 'running') {
      execution.status = 'cancelled';
      execution.context.status = 'cancelled';
      execution.completedAt = new Date();

      this.emit('execution_complete', {
        type: 'execution_complete',
        executionId,
        data: { cancelled: true },
        timestamp: new Date()
      } as WSMessage);

      return true;
    }
    return false;
  }

  /**
   * Pause execution
   */
  async pauseExecution(executionId: string): Promise<boolean> {
    const execution = this.executions.get(executionId);
    if (execution && execution.status === 'running') {
      execution.status = 'paused';
      execution.context.status = 'paused';
      return true;
    }
    return false;
  }

  /**
   * Resume execution
   */
  async resumeExecution(executionId: string): Promise<boolean> {
    const execution = this.executions.get(executionId);
    if (execution && execution.status === 'paused') {
      execution.status = 'running';
      execution.context.status = 'running';

      // Resume execution asynchronously
      this.executeWorkflow(executionId).catch(error => {
        this.handleExecutionError(executionId, error);
      });

      return true;
    }
    return false;
  }

  /**
   * Set browser context
   */
  setBrowserContext(browser: BrowserContext): void {
    this.browser = browser;
  }

  /**
   * Health check for execution manager
   */
  async healthCheck(): Promise<{
    status: 'healthy' | 'degraded' | 'unhealthy';
    services: {
      hybridExecutor: boolean;
      chromeExtension: boolean;
      browser: boolean;
    };
    activeExecutions: number;
  }> {
    const hybridHealth = await this.hybridExecutor.healthCheck();
    const browserHealthy = !!this.browser;

    const activeExecutions = Array.from(this.executions.values())
      .filter(e => e.status === 'running' || e.status === 'paused').length;

    const allHealthy = hybridHealth.dom && hybridHealth.vision && browserHealthy;
    const someHealthy = hybridHealth.dom || hybridHealth.vision || browserHealthy;

    return {
      status: allHealthy ? 'healthy' : (someHealthy ? 'degraded' : 'unhealthy'),
      services: {
        hybridExecutor: hybridHealth.dom || hybridHealth.vision,
        chromeExtension: hybridHealth.chromeExtension,
        browser: browserHealthy
      },
      activeExecutions
    };
  }

  /**
   * Clean up completed executions older than specified time
   */
  cleanupOldExecutions(maxAgeMs: number = 24 * 60 * 60 * 1000): number {
    const cutoff = new Date(Date.now() - maxAgeMs);
    let cleaned = 0;

    for (const [id, execution] of this.executions) {
      if (execution.status !== 'running' && execution.status !== 'paused') {
        if (execution.completedAt && execution.completedAt < cutoff) {
          this.executions.delete(id);
          cleaned++;
        }
      }
    }

    return cleaned;
  }
}