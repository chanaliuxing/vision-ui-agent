// Vision Bridge - Connects DOM-first extension with vision-first Python backend
// Implements Phase 3 PAV cycle with dual validation: DOM + Vision

import { PlanStep, ReducedDom, ExecutionReport, ValidationVerdict, PAVController } from './pav.js';
import { RecoveryController, PhaseKey, RecoveryResult } from './recovery.js';

// Bridge configuration
export interface VisionBridgeConfig {
  visionApiUrl: string;          // Python backend YOLO API (http://127.0.0.1:8000)
  workflowApiUrl: string;        // Workflow engine (http://127.0.0.1:8002)
  orchestratorUrl: string;       // Orchestrator (http://127.0.0.1:8788)
  useVisionFallback: boolean;    // Enable vision fallback when DOM fails
  useDualValidation: boolean;    // Use both DOM and vision validation
  hybridMode: boolean;           // Allow switching between DOM and vision
}

// Enhanced execution report with vision data
export interface HybridExecutionReport extends ExecutionReport {
  vision_data?: {
    screenshot_b64?: string;
    yolo_detections?: Array<{
      class: string;
      confidence: number;
      bbox: [number, number, number, number];
      label?: string;
    }>;
    ocr_results?: Array<{
      text: string;
      bbox: [number, number, number, number];
      confidence: number;
    }>;
  };
  validation_strategy: "dom_only" | "vision_only" | "dual_validation";
  fallback_triggered: boolean;
}

// Hybrid validation verdict combining DOM and vision
export interface HybridValidationVerdict extends ValidationVerdict {
  dom_verdict?: ValidationVerdict;
  vision_verdict?: ValidationVerdict;
  strategy_used: "dom_only" | "vision_only" | "dual_validation";
  confidence_sources: {
    dom_confidence?: number;
    vision_confidence?: number;
    combined_confidence: number;
  };
}

// Vision-Bridge PAV Controller
export class VisionBridgePAVController extends PAVController {
  private config: VisionBridgeConfig;
  private recoveryController: RecoveryController;

  constructor(config: VisionBridgeConfig) {
    super();
    this.config = config;
    this.recoveryController = new RecoveryController();
  }

  // Enhanced PAV execution with vision fallback
  async runStepWithVision(
    planStep: PlanStep,
    phase: PhaseKey
  ): Promise<HybridExecutionReport> {
    let fallback_triggered = false;
    let validation_strategy: "dom_only" | "vision_only" | "dual_validation" = "dom_only";

    try {
      // Phase 1: Try DOM-first approach
      const domReport = await this.runStep(planStep);

      // Check if DOM approach succeeded clearly
      const domValidation = domReport.llm_validation || domReport.local_validation;

      if (domValidation.status === "success" && domValidation.confidence && domValidation.confidence > 0.8) {
        // DOM approach succeeded with high confidence
        return this.enhanceWithVisionData(domReport, {
          validation_strategy: "dom_only",
          fallback_triggered: false
        });
      }

      // Phase 2: Use vision fallback or dual validation
      if (this.config.useVisionFallback || this.config.useDualValidation) {
        const visionData = await this.captureVisionData();

        if (domValidation.status === "failure" && this.config.useVisionFallback) {
          // DOM failed, try vision-based approach
          fallback_triggered = true;
          validation_strategy = "vision_only";

          const visionReport = await this.executeVisionBased(planStep, visionData);
          return this.enhanceWithVisionData(visionReport, {
            validation_strategy,
            fallback_triggered,
            vision_data: visionData
          });
        }

        if (this.config.useDualValidation) {
          // Use dual validation for better confidence
          validation_strategy = "dual_validation";

          const hybridVerdict = await this.performDualValidation(
            domReport,
            visionData,
            planStep
          );

          const enhancedReport = this.enhanceWithVisionData(domReport, {
            validation_strategy,
            fallback_triggered,
            vision_data: visionData
          });

          enhancedReport.llm_validation = hybridVerdict;
          return enhancedReport;
        }
      }

      // Return DOM-only result
      return this.enhanceWithVisionData(domReport, {
        validation_strategy: "dom_only",
        fallback_triggered: false
      });

    } catch (error) {
      // Ultimate fallback to vision-only approach
      if (this.config.useVisionFallback) {
        try {
          fallback_triggered = true;
          const visionData = await this.captureVisionData();
          const visionReport = await this.executeVisionBased(planStep, visionData);

          return this.enhanceWithVisionData(visionReport, {
            validation_strategy: "vision_only",
            fallback_triggered,
            vision_data: visionData
          });
        } catch (visionError) {
          throw new Error(`Both DOM and vision approaches failed: ${error}; ${visionError}`);
        }
      }

      throw error;
    }
  }

  // Capture vision data (screenshot + YOLO + OCR)
  private async captureVisionData(): Promise<HybridExecutionReport["vision_data"]> {
    try {
      // Take screenshot
      const screenshot = await this.takeScreenshot();

      // Call YOLO detection API
      const yoloResponse = await fetch(`${this.config.visionApiUrl}/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image: screenshot,
          return_image: false,
          conf_threshold: 0.3
        })
      });

      const yoloData = await yoloResponse.json();

      // Call OCR API if available
      let ocrResults = [];
      try {
        const ocrResponse = await fetch(`${this.config.visionApiUrl.replace('8000', '8001')}/predict`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image: screenshot })
        });
        const ocrData = await ocrResponse.json();
        ocrResults = ocrData.texts || [];
      } catch (ocrError) {
        console.warn('OCR API not available:', ocrError);
      }

      return {
        screenshot_b64: screenshot,
        yolo_detections: yoloData.detections || [],
        ocr_results: ocrResults
      };

    } catch (error) {
      console.error('Failed to capture vision data:', error);
      return {};
    }
  }

  // Execute action using vision-based approach (Python backend)
  private async executeVisionBased(
    planStep: PlanStep,
    visionData: HybridExecutionReport["vision_data"]
  ): Promise<ExecutionReport> {
    try {
      // Convert PlanStep to Python workflow format
      const pythonWorkflow = this.convertToWorkflowFormat(planStep);

      // Execute via workflow API
      const response = await fetch(`${this.config.workflowApiUrl}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workflow: pythonWorkflow,
          screenshot: visionData?.screenshot_b64,
          yolo_data: visionData?.yolo_detections,
          ocr_data: visionData?.ocr_results
        })
      });

      const result = await response.json();

      // Convert Python result back to ExecutionReport format
      return this.convertFromWorkflowResult(result, planStep);

    } catch (error) {
      throw new Error(`Vision-based execution failed: ${error}`);
    }
  }

  // Perform dual validation (DOM + Vision)
  private async performDualValidation(
    domReport: ExecutionReport,
    visionData: HybridExecutionReport["vision_data"],
    planStep: PlanStep
  ): Promise<HybridValidationVerdict> {
    try {
      // Get DOM validation
      const domVerdict = domReport.llm_validation || domReport.local_validation;

      // Perform vision-based validation
      const visionVerdict = await this.validateWithVision(
        planStep.success_criteria,
        visionData
      );

      // Combine verdicts using weighted confidence
      const domWeight = 0.6;  // DOM is primary
      const visionWeight = 0.4;  // Vision supplements

      const combinedConfidence =
        (domVerdict.confidence || 0.5) * domWeight +
        (visionVerdict.confidence || 0.5) * visionWeight;

      // Determine combined status
      let combinedStatus: "success" | "failure" | "uncertain";

      if (domVerdict.status === "success" && visionVerdict.status === "success") {
        combinedStatus = "success";
      } else if (domVerdict.status === "failure" && visionVerdict.status === "failure") {
        combinedStatus = "failure";
      } else if (combinedConfidence > 0.7) {
        combinedStatus = "success";
      } else if (combinedConfidence < 0.3) {
        combinedStatus = "failure";
      } else {
        combinedStatus = "uncertain";
      }

      return {
        status: combinedStatus,
        confidence: combinedConfidence,
        reasoning: [
          ...domVerdict.reasoning,
          ...visionVerdict.reasoning,
          `Combined DOM (${domWeight}) + Vision (${visionWeight}) validation`
        ],
        recommended_next_steps: this.mergeRecommendations(
          domVerdict.recommended_next_steps || [],
          visionVerdict.recommended_next_steps || []
        ),
        dom_verdict: domVerdict as ValidationVerdict,
        vision_verdict: visionVerdict,
        strategy_used: "dual_validation",
        confidence_sources: {
          dom_confidence: domVerdict.confidence,
          vision_confidence: visionVerdict.confidence,
          combined_confidence: combinedConfidence
        }
      };

    } catch (error) {
      console.error('Dual validation failed:', error);

      // Fallback to DOM-only verdict
      const domVerdict = domReport.llm_validation || domReport.local_validation;
      return {
        ...domVerdict,
        strategy_used: "dom_only",
        confidence_sources: {
          combined_confidence: domVerdict.confidence || 0.5
        },
        reasoning: [...domVerdict.reasoning, `Vision validation failed: ${error}`]
      } as HybridValidationVerdict;
    }
  }

  // Vision-based validation using YOLO/OCR results
  private async validateWithVision(
    criteria: PlanStep["success_criteria"],
    visionData: HybridExecutionReport["vision_data"]
  ): Promise<ValidationVerdict> {
    const reasons: string[] = [];
    let score = 0;
    let total = 0;

    // URL validation (not applicable for vision)

    // Text validation using OCR results
    if (criteria.text_includes) {
      total++;
      const ocrTexts = visionData?.ocr_results?.map(r => r.text.toLowerCase()) || [];
      const allOcrText = ocrTexts.join(' ');

      const foundTexts = criteria.text_includes.filter(text =>
        allOcrText.includes(text.toLowerCase())
      );

      if (foundTexts.length > 0) {
        score++;
        reasons.push(`Vision OCR found expected text: ${foundTexts.join(', ')}`);
      } else {
        reasons.push(`Vision OCR missing expected text: ${criteria.text_includes.join(', ')}`);
      }
    }

    // Element existence using YOLO detections
    if (criteria.must_exist) {
      total++;
      const yoloLabels = visionData?.yolo_detections?.map(d => d.label?.toLowerCase()) || [];

      const foundElements = criteria.must_exist.filter(required =>
        yoloLabels.some(label => label?.includes(required.toLowerCase()))
      );

      if (foundElements.length === criteria.must_exist.length) {
        score++;
        reasons.push(`Vision YOLO found all required elements: ${foundElements.join(', ')}`);
      } else {
        const missing = criteria.must_exist.filter(req =>
          !yoloLabels.some(label => label?.includes(req.toLowerCase()))
        );
        reasons.push(`Vision YOLO missing elements: ${missing.join(', ')}`);
      }
    }

    // Determine status
    const successRate = total > 0 ? score / total : 0.5;
    let status: "success" | "failure" | "uncertain";

    if (successRate >= 0.8) {
      status = "success";
    } else if (successRate >= 0.4) {
      status = "uncertain";
    } else {
      status = "failure";
    }

    return {
      status,
      confidence: successRate,
      reasoning: reasons,
      recommended_next_steps: [
        { action: status === "success" ? "proceed" : "retry" }
      ]
    };
  }

  // Helper methods
  private enhanceWithVisionData(
    report: ExecutionReport,
    enhancement: {
      validation_strategy: "dom_only" | "vision_only" | "dual_validation";
      fallback_triggered: boolean;
      vision_data?: HybridExecutionReport["vision_data"];
    }
  ): HybridExecutionReport {
    return {
      ...report,
      validation_strategy: enhancement.validation_strategy,
      fallback_triggered: enhancement.fallback_triggered,
      vision_data: enhancement.vision_data
    };
  }

  private async takeScreenshot(): Promise<string> {
    try {
      // Use Chrome API to take screenshot
      const dataUrl = await new Promise<string>((resolve, reject) => {
        chrome.tabs.captureVisibleTab((dataUrl) => {
          if (chrome.runtime.lastError) {
            reject(chrome.runtime.lastError);
          } else {
            resolve(dataUrl);
          }
        });
      });

      // Convert to base64 (remove data URL prefix)
      return dataUrl.split(',')[1];
    } catch (error) {
      throw new Error(`Screenshot failed: ${error}`);
    }
  }

  private convertToWorkflowFormat(planStep: PlanStep): any {
    // Convert PlanStep to Python workflow JSON format
    return {
      name: `step_${planStep.step_no}`,
      description: planStep.goal,
      start: "execute_action",
      states: {
        execute_action: {
          description: planStep.goal,
          actions: [
            {
              do: this.mapActionType(planStep.action),
              target: this.mapTargetFormat(planStep.target),
              text: planStep.input_text,
              save: `step_${planStep.step_no}_result`
            }
          ],
          on_success: null
        }
      }
    };
  }

  private mapActionType(action: string): string {
    const mapping: Record<string, string> = {
      "click": "click",
      "type": "type_text",
      "select": "select",
      "navigate": "navigate"
    };
    return mapping[action] || "click";
  }

  private mapTargetFormat(target: PlanStep["target"]): any {
    switch (target.by) {
      case "text":
        return { by_text: target.value };
      case "href":
        return { by_href: target.value };
      case "id":
        return { by_id: target.value };
      case "index":
        return { by_index: target.value };
      default:
        return { by_text: target.value };
    }
  }

  private convertFromWorkflowResult(result: any, planStep: PlanStep): ExecutionReport {
    // Convert Python workflow result back to ExecutionReport
    const exec_id = this.generateId();
    const now = Date.now();

    return {
      exec_id,
      task_id: planStep.task_id,
      step_no: planStep.step_no,
      goal: planStep.goal,
      plan_step: planStep,
      history: [],
      pre_context: {} as ReducedDom,
      action_sent: {
        action: planStep.action,
        target_resolved: { by: "vision", value: "detected" }
      },
      runtime: {
        ts_start: now,
        ts_end: now,
        duration_ms: result.duration_ms || 0,
        nav_events: [],
        net_requests: 0,
        error: result.error
      },
      post_context: {} as ReducedDom,
      diff: {
        url_changed: false,
        title_changed: false,
        appeared_labels: [],
        disappeared_labels: []
      },
      local_validation: {
        status: result.success ? "success" : "failure",
        reasons: [result.message || "Vision-based execution completed"],
        matched_criteria: []
      }
    };
  }

  private mergeRecommendations(
    domRecs: ValidationVerdict["recommended_next_steps"],
    visionRecs: ValidationVerdict["recommended_next_steps"]
  ): ValidationVerdict["recommended_next_steps"] {
    // Merge and prioritize recommendations
    const combined = [...domRecs, ...visionRecs];

    // Remove duplicates and prioritize
    const unique = combined.filter((rec, index, arr) =>
      arr.findIndex(r => r.action === rec.action) === index
    );

    // Sort by priority (proceed > retry > wait > abort)
    const priority = { proceed: 0, retry: 1, wait: 2, scroll: 3, back: 4, alt_target: 5, abort: 6 };
    return unique.sort((a, b) => (priority[a.action] || 99) - (priority[b.action] || 99));
  }

  private generateId(): string {
    return Date.now().toString(36) + Math.random().toString(36).substr(2);
  }

  // Recovery integration with vision fallback
  async executeStepWithRecoveryAndVision(
    planStep: PlanStep,
    phase: PhaseKey
  ): Promise<RecoveryResult> {
    try {
      const report = await this.runStepWithVision(planStep, phase);
      const validation = report.llm_validation || report.local_validation;

      if (validation.status === "success") {
        return {
          ok: true,
          action: "next",
          report,
          recovery_log: [`Step ${planStep.step_no} completed successfully with ${report.validation_strategy}`]
        };
      }

      // Use recovery system for failures
      return await this.recoveryController.runStepWithRecovery(planStep, phase, this);

    } catch (error) {
      return {
        ok: false,
        action: "abort",
        recovery_log: [`Vision-bridge execution failed: ${error}`]
      };
    }
  }
}

// Factory function for easy usage
export function createVisionBridgePAV(config: VisionBridgeConfig): VisionBridgePAVController {
  return new VisionBridgePAVController(config);
}

// Default configuration
export const defaultVisionBridgeConfig: VisionBridgeConfig = {
  visionApiUrl: "http://127.0.0.1:8000",
  workflowApiUrl: "http://127.0.0.1:8002",
  orchestratorUrl: "http://127.0.0.1:8788",
  useVisionFallback: true,
  useDualValidation: false,  // Start with fallback only
  hybridMode: true
};