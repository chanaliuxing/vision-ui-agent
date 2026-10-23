// Unified Orchestrator - Complete PAV + Recovery System
// Integrates all phases: DOM reduction, PAV cycle, vision bridge, and recovery

import {
  PlanStep,
  ReducedDom,
  ExecutionReport,
  ValidationVerdict,
  PAVController,
  createPAVController
} from './pav.js';

import {
  RecoveryController,
  PhaseKey,
  RecoveryResult,
  UnifiedAutomationController
} from './recovery.js';

import {
  VisionBridgePAVController,
  HybridExecutionReport,
  HybridValidationVerdict,
  createVisionBridgePAV,
  defaultVisionBridgeConfig,
  VisionBridgeConfig
} from './vision-bridge.js';

import { reduceDomPayload } from './reducer.js';

// Master configuration for the complete system
export interface UnifiedOrchestratorConfig {
  // Core PAV settings
  enablePAVCycle: boolean;
  enableRecoverySystem: boolean;

  // Vision integration
  enableVisionBridge: boolean;
  visionBridgeConfig: VisionBridgeConfig;

  // DOM reduction settings
  domReductionConfig: {
    maxElements: number;
    dupIoU: number;
    minTextLenSpan: number;
    profiles?: Record<string, any>;
  };

  // Recovery settings
  maxRetryAttempts: number;
  enablePythonBackendSync: boolean;
  pythonBackendUrl: string;

  // Logging and debugging
  enableDetailedLogging: boolean;
  logLevel: "debug" | "info" | "warn" | "error";
}

// Execution result for the complete system
export interface UnifiedExecutionResult {
  success: boolean;
  execution_strategy: "dom_only" | "vision_only" | "dual_validation" | "hybrid_recovery";
  steps_completed: number;
  total_steps: number;

  // Detailed results
  step_results: Array<{
    step_no: number;
    goal: string;
    result: HybridExecutionReport | RecoveryResult;
    validation: HybridValidationVerdict | ValidationVerdict;
    recovery_triggered: boolean;
    vision_fallback_used: boolean;
  }>;

  // Summary metrics
  metrics: {
    total_duration_ms: number;
    dom_success_rate: number;
    vision_fallback_rate: number;
    recovery_trigger_rate: number;
    blacklist_additions: number;
  };

  // Error handling
  final_status: "completed" | "partial_success" | "failed" | "manual_intervention_required";
  error_summary?: string;
  recovery_log: string[];
}

// The master orchestrator class
export class UnifiedOrchestrator {
  private config: UnifiedOrchestratorConfig;
  private pavController: PAVController;
  private visionBridgeController: VisionBridgePAVController;
  private recoveryController: RecoveryController;

  // Runtime state
  private currentPhase: PhaseKey;
  private executionLog: string[] = [];
  private metrics: UnifiedExecutionResult["metrics"];

  constructor(config: Partial<UnifiedOrchestratorConfig> = {}) {
    this.config = {
      enablePAVCycle: true,
      enableRecoverySystem: true,
      enableVisionBridge: true,
      visionBridgeConfig: defaultVisionBridgeConfig,
      domReductionConfig: {
        maxElements: 50,
        dupIoU: 0.9,
        minTextLenSpan: 2
      },
      maxRetryAttempts: 3,
      enablePythonBackendSync: true,
      pythonBackendUrl: "http://127.0.0.1:8000",
      enableDetailedLogging: true,
      logLevel: "info",
      ...config
    };

    this.initializeControllers();
    this.resetMetrics();
  }

  private initializeControllers(): void {
    // Initialize core PAV controller
    this.pavController = createPAVController();

    // Initialize vision bridge if enabled
    if (this.config.enableVisionBridge) {
      this.visionBridgeController = createVisionBridgePAV(this.config.visionBridgeConfig);
    }

    // Initialize recovery controller
    this.recoveryController = new RecoveryController(this.config.pythonBackendUrl);
  }

  private resetMetrics(): void {
    this.metrics = {
      total_duration_ms: 0,
      dom_success_rate: 0,
      vision_fallback_rate: 0,
      recovery_trigger_rate: 0,
      blacklist_additions: 0
    };
  }

  // Main execution method - processes a complete task with multiple steps
  async executeTask(
    taskId: string,
    phaseId: string,
    planSteps: PlanStep[]
  ): Promise<UnifiedExecutionResult> {
    const startTime = Date.now();
    this.currentPhase = { task_id: taskId, phase_id: phaseId };
    this.resetMetrics();
    this.executionLog = [];

    const step_results: UnifiedExecutionResult["step_results"] = [];
    let completed_steps = 0;

    this.log("info", `Starting task execution: ${taskId}:${phaseId} (${planSteps.length} steps)`);

    try {
      for (let i = 0; i < planSteps.length; i++) {
        const planStep = planSteps[i];
        this.log("info", `Executing step ${i + 1}/${planSteps.length}: ${planStep.goal}`);

        const stepResult = await this.executeStep(planStep);
        step_results.push(stepResult);

        if (stepResult.result && 'ok' in stepResult.result && stepResult.result.ok) {
          completed_steps++;
        } else if (stepResult.result && 'action' in stepResult.result) {
          // Handle recovery results
          if (stepResult.result.action === "abort" || stepResult.result.action === "manual_intervention") {
            this.log("error", `Step ${i + 1} requires manual intervention`);
            break;
          } else if (stepResult.result.action === "retry_phase") {
            this.log("warn", `Step ${i + 1} triggered phase retry`);
            // Continue with next step for now, but mark as needing attention
          }
        }
      }

      // Calculate final metrics
      this.metrics.total_duration_ms = Date.now() - startTime;
      this.calculateFinalMetrics(step_results);

      // Determine final status
      let final_status: UnifiedExecutionResult["final_status"];
      if (completed_steps === planSteps.length) {
        final_status = "completed";
      } else if (completed_steps > 0) {
        final_status = "partial_success";
      } else {
        final_status = "failed";
      }

      const result: UnifiedExecutionResult = {
        success: final_status === "completed",
        execution_strategy: this.determineExecutionStrategy(step_results),
        steps_completed: completed_steps,
        total_steps: planSteps.length,
        step_results,
        metrics: this.metrics,
        final_status,
        recovery_log: this.executionLog
      };

      this.log("info", `Task completed: ${final_status} (${completed_steps}/${planSteps.length} steps)`);
      return result;

    } catch (error) {
      this.log("error", `Task execution failed: ${error}`);

      return {
        success: false,
        execution_strategy: "hybrid_recovery",
        steps_completed: completed_steps,
        total_steps: planSteps.length,
        step_results,
        metrics: this.metrics,
        final_status: "failed",
        error_summary: String(error),
        recovery_log: this.executionLog
      };
    }
  }

  // Execute a single step with full PAV + Recovery + Vision integration
  private async executeStep(planStep: PlanStep): Promise<UnifiedExecutionResult["step_results"][0]> {
    const stepStartTime = Date.now();

    try {
      // Determine execution strategy based on configuration
      if (this.config.enableVisionBridge && this.visionBridgeController) {
        // Use vision bridge for hybrid execution
        const report = await this.visionBridgeController.runStepWithVision(planStep, this.currentPhase);
        const validation = report.llm_validation || report.local_validation;

        return {
          step_no: planStep.step_no,
          goal: planStep.goal,
          result: report,
          validation: validation as HybridValidationVerdict,
          recovery_triggered: false,
          vision_fallback_used: report.fallback_triggered || report.validation_strategy !== "dom_only"
        };

      } else if (this.config.enableRecoverySystem) {
        // Use recovery system with DOM-only execution
        const recoveryResult = await this.recoveryController.runStepWithRecovery(
          planStep,
          this.currentPhase,
          this.pavController
        );

        return {
          step_no: planStep.step_no,
          goal: planStep.goal,
          result: recoveryResult,
          validation: recoveryResult.report?.local_validation as ValidationVerdict,
          recovery_triggered: !recoveryResult.ok,
          vision_fallback_used: false
        };

      } else {
        // Basic PAV execution only
        const report = await this.pavController.runStep(planStep);
        const validation = report.llm_validation || report.local_validation;

        return {
          step_no: planStep.step_no,
          goal: planStep.goal,
          result: report,
          validation: validation,
          recovery_triggered: false,
          vision_fallback_used: false
        };
      }

    } catch (error) {
      this.log("error", `Step ${planStep.step_no} execution failed: ${error}`);

      return {
        step_no: planStep.step_no,
        goal: planStep.goal,
        result: {
          ok: false,
          action: "abort",
          recovery_log: [`Step execution failed: ${error}`]
        } as RecoveryResult,
        validation: {
          status: "failure",
          confidence: 0,
          reasoning: [`Execution error: ${error}`],
          recommended_next_steps: [{ action: "abort" }]
        },
        recovery_triggered: true,
        vision_fallback_used: false
      };
    }
  }

  // Utility methods
  private calculateFinalMetrics(step_results: UnifiedExecutionResult["step_results"]): void {
    if (step_results.length === 0) return;

    const domSuccesses = step_results.filter(r =>
      !r.vision_fallback_used && r.validation.status === "success"
    ).length;

    const visionFallbacks = step_results.filter(r => r.vision_fallback_used).length;
    const recoveryTriggers = step_results.filter(r => r.recovery_triggered).length;

    this.metrics.dom_success_rate = domSuccesses / step_results.length;
    this.metrics.vision_fallback_rate = visionFallbacks / step_results.length;
    this.metrics.recovery_trigger_rate = recoveryTriggers / step_results.length;
    this.metrics.blacklist_additions = this.recoveryController.getBlacklistStats().total;
  }

  private determineExecutionStrategy(
    step_results: UnifiedExecutionResult["step_results"]
  ): UnifiedExecutionResult["execution_strategy"] {
    const hasVisionFallback = step_results.some(r => r.vision_fallback_used);
    const hasRecovery = step_results.some(r => r.recovery_triggered);
    const hasDualValidation = step_results.some(r =>
      'strategy_used' in r.validation && r.validation.strategy_used === "dual_validation"
    );

    if (hasRecovery) return "hybrid_recovery";
    if (hasDualValidation) return "dual_validation";
    if (hasVisionFallback) return "vision_only";
    return "dom_only";
  }

  private log(level: string, message: string): void {
    if (this.config.enableDetailedLogging) {
      const timestamp = new Date().toISOString();
      const logMessage = `[${timestamp}] [${level.toUpperCase()}] ${message}`;
      this.executionLog.push(logMessage);

      if (this.shouldLog(level)) {
        console.log(`[UNIFIED_ORCHESTRATOR] ${logMessage}`);
      }
    }
  }

  private shouldLog(level: string): boolean {
    const levels = ["debug", "info", "warn", "error"];
    const currentLevelIndex = levels.indexOf(this.config.logLevel);
    const messageLevel = levels.indexOf(level);
    return messageLevel >= currentLevelIndex;
  }

  // Public API methods
  public async getCurrentDomSnapshot(): Promise<ReducedDom> {
    // Use the DOM reducer to get current page state
    const rawDom = await chrome.runtime.sendMessage({
      type: 'EXT_EXTRACT',
      args: { want: 'inputs', limit: 200 }
    });

    return reduceDomPayload(rawDom, this.config.domReductionConfig);
  }

  public getExecutionLog(): string[] {
    return [...this.executionLog];
  }

  public getMetrics(): UnifiedExecutionResult["metrics"] {
    return { ...this.metrics };
  }

  public clearBlacklist(phase?: PhaseKey): void {
    this.recoveryController.clearBlacklist(phase);
  }

  public getBlacklistStats() {
    return this.recoveryController.getBlacklistStats();
  }

  // Configuration updates
  public updateConfig(config: Partial<UnifiedOrchestratorConfig>): void {
    Object.assign(this.config, config);
    this.initializeControllers(); // Reinitialize with new config
  }

  public getConfig(): UnifiedOrchestratorConfig {
    return { ...this.config };
  }
}

// Factory function and default export
export function createUnifiedOrchestrator(
  config?: Partial<UnifiedOrchestratorConfig>
): UnifiedOrchestrator {
  return new UnifiedOrchestrator(config);
}

// Example usage and testing utilities
export class OrchestratorTestSuite {
  private orchestrator: UnifiedOrchestrator;

  constructor(config?: Partial<UnifiedOrchestratorConfig>) {
    this.orchestrator = createUnifiedOrchestrator(config);
  }

  // Test basic DOM reduction
  async testDomReduction(): Promise<boolean> {
    try {
      const snapshot = await this.orchestrator.getCurrentDomSnapshot();
      console.log("DOM Reduction Test:", {
        elements_count: snapshot.elements.length,
        has_reduced_flag: snapshot._reduced,
        version: snapshot._version
      });
      return snapshot._reduced === true && snapshot.elements.length > 0;
    } catch (error) {
      console.error("DOM Reduction Test Failed:", error);
      return false;
    }
  }

  // Test a simple PAV step
  async testPAVStep(): Promise<boolean> {
    try {
      const testStep: PlanStep = {
        task_id: "test_task",
        step_no: 1,
        goal: "Test PAV cycle",
        action: "click",
        target: { by: "text", value: "search" },
        success_criteria: {
          url_contains: [window.location.hostname],
          timeout_ms: 5000
        }
      };

      const result = await this.orchestrator.executeTask("test_task", "test_phase", [testStep]);
      console.log("PAV Test Result:", {
        success: result.success,
        strategy: result.execution_strategy,
        steps_completed: result.steps_completed
      });

      return result.steps_completed > 0;
    } catch (error) {
      console.error("PAV Test Failed:", error);
      return false;
    }
  }

  // Run all tests
  async runAllTests(): Promise<{ passed: number; total: number; results: Record<string, boolean> }> {
    const tests = {
      dom_reduction: await this.testDomReduction(),
      pav_step: await this.testPAVStep()
    };

    const passed = Object.values(tests).filter(Boolean).length;
    const total = Object.keys(tests).length;

    console.log("Test Suite Results:", { passed, total, tests });
    return { passed, total, results: tests };
  }
}

// Export default configuration
export const defaultUnifiedConfig: UnifiedOrchestratorConfig = {
  enablePAVCycle: true,
  enableRecoverySystem: true,
  enableVisionBridge: true,
  visionBridgeConfig: defaultVisionBridgeConfig,
  domReductionConfig: {
    maxElements: 50,
    dupIoU: 0.9,
    minTextLenSpan: 2
  },
  maxRetryAttempts: 3,
  enablePythonBackendSync: true,
  pythonBackendUrl: "http://127.0.0.1:8000",
  enableDetailedLogging: true,
  logLevel: "info"
};