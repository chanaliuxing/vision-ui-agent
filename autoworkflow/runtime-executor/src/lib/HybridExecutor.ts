// M3: Hybrid Execution Strategy - DOM-first with Vision fallback

import { EventEmitter } from 'events';
import type {
  WorkflowStep,
  HybridExecutionPlan,
  HybridExecutionResult,
  DOMAction,
  VisionAction,
  DOMExecutionResult,
  VisionExecutionResult,
  ExecutionContext,
  ChromeExtensionConnection,
  VisionEngineConnection,
  BrowserContext
} from '../types/index.js';
import { DOMExecutor } from './DOMExecutor.js';
import { VisionExecutor } from './VisionExecutor.js';
import { ChromeExtensionBridge } from './ChromeExtensionBridge.js';

export class HybridExecutor extends EventEmitter {
  private domExecutor: DOMExecutor;
  private visionExecutor: VisionExecutor;
  private chromeExtensionBridge: ChromeExtensionBridge;

  constructor(
    chromeExtension?: ChromeExtensionConnection,
    visionEngine?: VisionEngineConnection,
    browser?: BrowserContext
  ) {
    super();

    this.domExecutor = new DOMExecutor(chromeExtension, browser);
    this.visionExecutor = new VisionExecutor(visionEngine, browser);
    this.chromeExtensionBridge = new ChromeExtensionBridge();

    // Forward events from sub-executors
    this.domExecutor.on('dom_action', (data) => this.emit('dom_action', data));
    this.visionExecutor.on('vision_action', (data) => this.emit('vision_action', data));
  }

  /**
   * Execute a workflow step using hybrid DOM-first + Vision fallback strategy
   */
  async executeStep(
    step: WorkflowStep,
    context: ExecutionContext
  ): Promise<HybridExecutionResult> {
    const startTime = Date.now();
    let screenshots: string[] = [];

    try {
      // Create execution plan based on step type and context
      const plan = await this.createExecutionPlan(step, context);

      this.emit('execution_plan', { stepId: step.id, plan });

      // Primary execution attempt
      const primaryResult = await this.executePrimary(plan, context);
      screenshots.push(...(primaryResult.screenshot ? [primaryResult.screenshot] : []));

      // Check if primary execution succeeded
      if (primaryResult.success && !primaryResult.fallbackRequired) {
        return {
          success: true,
          methodUsed: plan.primaryMethod,
          primaryResult,
          totalDuration_ms: Date.now() - startTime,
          screenshots
        };
      }

      // Fallback execution if primary failed or requested fallback
      this.emit('fallback_triggered', {
        stepId: step.id,
        reason: primaryResult.error || 'Primary method requested fallback',
        primaryMethod: plan.primaryMethod
      });

      const fallbackResult = await this.executeFallback(plan, context, primaryResult);
      screenshots.push(...(fallbackResult.screenshot ? [fallbackResult.screenshot] : []));

      if (fallbackResult.success) {
        return {
          success: true,
          methodUsed: 'both',
          primaryResult,
          fallbackResult,
          totalDuration_ms: Date.now() - startTime,
          screenshots
        };
      }

      // Both methods failed
      return {
        success: false,
        methodUsed: 'both',
        primaryResult,
        fallbackResult,
        totalDuration_ms: Date.now() - startTime,
        screenshots
      };

    } catch (error) {
      this.emit('execution_error', { stepId: step.id, error: error.message });

      return {
        success: false,
        methodUsed: 'dom', // Default for error cases
        primaryResult: {
          success: false,
          method: 'dom',
          error: error.message
        },
        totalDuration_ms: Date.now() - startTime,
        screenshots
      };
    }
  }

  /**
   * Create an intelligent execution plan based on step analysis
   */
  private async createExecutionPlan(
    step: WorkflowStep,
    context: ExecutionContext
  ): Promise<HybridExecutionPlan> {
    const { params } = step;

    // Analyze step to determine best execution strategy
    const domViability = this.analyzeDOMViability(step, context);
    const visionComplexity = this.analyzeVisionComplexity(step, context);

    // Default to DOM-first for web targets
    let primaryMethod: 'dom' | 'vision' = 'dom';
    let fallbackMethod: 'dom' | 'vision' = 'vision';

    // Switch to vision-first for complex visual tasks
    if (visionComplexity > 0.7 || domViability < 0.3) {
      primaryMethod = 'vision';
      fallbackMethod = 'dom';
    }

    // Force vision-only for certain action types
    if (step.uses?.includes('vision.') || params?.force_vision) {
      primaryMethod = 'vision';
      fallbackMethod = 'vision';
    }

    // Force DOM-only for certain action types
    if (step.uses?.includes('dom.') || params?.force_dom) {
      primaryMethod = 'dom';
      fallbackMethod = 'dom';
    }

    return {
      stepId: step.id,
      primaryMethod,
      fallbackMethod,
      domAction: this.createDOMAction(step),
      visionAction: this.createVisionAction(step),
      fallbackThreshold: 0.3,
      maxRetries: step.retry?.times || 2
    };
  }

  /**
   * Analyze how suitable this step is for DOM execution
   */
  private analyzeDOMViability(step: WorkflowStep, context: ExecutionContext): number {
    let score = 0.8; // Default high score for DOM

    // Reduce score for dynamic content
    if (step.params?.dynamic_content) score -= 0.3;

    // Reduce score for complex selectors
    if (step.params?.selector?.includes(':nth-child')) score -= 0.2;

    // Increase score for simple actions
    if (['click', 'type', 'scroll'].includes(step.uses?.split('.')[1] || '')) score += 0.2;

    // Check if Chrome extension is available
    if (!context.chromeExtension?.isConnected) score -= 0.5;

    return Math.max(0, Math.min(1, score));
  }

  /**
   * Analyze complexity for vision-based execution
   */
  private analyzeVisionComplexity(step: WorkflowStep, context: ExecutionContext): number {
    let complexity = 0.4; // Default moderate complexity

    // Increase complexity for OCR tasks
    if (step.uses?.includes('ocr') || step.params?.extract_text) complexity += 0.3;

    // Increase complexity for LLM decision making
    if (step.params?.llm_prompt) complexity += 0.4;

    // Reduce complexity for simple clicks
    if (step.uses === 'ext.click') complexity -= 0.2;

    return Math.max(0, Math.min(1, complexity));
  }

  /**
   * Create DOM action from workflow step
   */
  private createDOMAction(step: WorkflowStep): DOMAction | undefined {
    const { uses, params } = step;

    if (!uses) return undefined;

    const [domain, action] = uses.split('.');

    if (domain !== 'ext') return undefined;

    switch (action) {
      case 'click':
        return {
          type: 'click',
          selector: params?.selector,
          xpath: params?.xpath,
          coordinates: params?.coordinates
        };

      case 'type':
        return {
          type: 'type',
          selector: params?.selector,
          xpath: params?.xpath,
          text: params?.text || params?.value
        };

      case 'scroll':
        return {
          type: 'scroll',
          selector: params?.selector,
          coordinates: params?.coordinates,
          options: {
            direction: params?.direction || 'down',
            amount: params?.amount || 3
          }
        };

      case 'wait':
        return {
          type: 'wait',
          selector: params?.selector,
          options: {
            timeout: params?.timeout || 5000,
            visible: params?.visible !== false
          }
        };

      case 'navigate':
        return {
          type: 'navigate',
          options: { url: params?.url }
        };

      case 'extract':
        return {
          type: 'extract',
          selector: params?.selector,
          options: {
            attribute: params?.attribute,
            multiple: params?.multiple
          }
        };

      default:
        return undefined;
    }
  }

  /**
   * Create vision action from workflow step
   */
  private createVisionAction(step: WorkflowStep): VisionAction | undefined {
    const { uses, params } = step;

    if (!uses) return undefined;

    // Handle vision-specific actions
    if (uses.startsWith('vision.')) {
      const action = uses.split('.')[1];

      switch (action) {
        case 'detect':
          return {
            type: 'yolo_detect',
            confidence_threshold: params?.confidence || 0.5
          };

        case 'ocr':
          return {
            type: 'ocr_extract',
            confidence_threshold: params?.confidence || 0.7
          };

        case 'decide':
          return {
            type: 'llm_decide',
            prompt: params?.prompt || params?.instruction
          };

        case 'click':
          return {
            type: 'click_vision',
            prompt: params?.target_description,
            confidence_threshold: params?.confidence || 0.6
          };

        case 'type':
          return {
            type: 'type_vision',
            text: params?.text || params?.value,
            prompt: params?.target_description
          };
      }
    }

    // Convert regular actions to vision equivalents
    const [domain, action] = uses.split('.');

    if (domain === 'ext') {
      switch (action) {
        case 'click':
          return {
            type: 'click_vision',
            prompt: params?.target_description || `Click on ${params?.selector}`,
            coordinates: params?.coordinates
          };

        case 'type':
          return {
            type: 'type_vision',
            text: params?.text || params?.value,
            prompt: params?.target_description || `Type in ${params?.selector}`
          };

        default:
          return {
            type: 'llm_decide',
            prompt: `Execute action: ${action} with parameters: ${JSON.stringify(params)}`
          };
      }
    }

    return undefined;
  }

  /**
   * Execute primary method
   */
  private async executePrimary(
    plan: HybridExecutionPlan,
    context: ExecutionContext
  ): Promise<DOMExecutionResult | VisionExecutionResult> {
    if (plan.primaryMethod === 'dom' && plan.domAction) {
      return await this.domExecutor.execute(plan.domAction, context);
    } else if (plan.primaryMethod === 'vision' && plan.visionAction) {
      return await this.visionExecutor.execute(plan.visionAction, context);
    }

    throw new Error(`Invalid primary execution plan: ${plan.primaryMethod}`);
  }

  /**
   * Execute fallback method
   */
  private async executeFallback(
    plan: HybridExecutionPlan,
    context: ExecutionContext,
    primaryResult: DOMExecutionResult | VisionExecutionResult
  ): Promise<DOMExecutionResult | VisionExecutionResult> {
    // Add delay before fallback
    await new Promise(resolve => setTimeout(resolve, 1000));

    if (plan.fallbackMethod === 'dom' && plan.domAction) {
      return await this.domExecutor.execute(plan.domAction, context);
    } else if (plan.fallbackMethod === 'vision' && plan.visionAction) {
      return await this.visionExecutor.execute(plan.visionAction, context);
    }

    throw new Error(`Invalid fallback execution plan: ${plan.fallbackMethod}`);
  }

  /**
   * Health check for hybrid executor
   */
  async healthCheck(): Promise<{
    dom: boolean;
    vision: boolean;
    chromeExtension: boolean;
  }> {
    const [dom, vision, chromeExtension] = await Promise.allSettled([
      this.domExecutor.healthCheck(),
      this.visionExecutor.healthCheck(),
      this.chromeExtensionBridge.healthCheck()
    ]);

    return {
      dom: dom.status === 'fulfilled' && dom.value,
      vision: vision.status === 'fulfilled' && vision.value,
      chromeExtension: chromeExtension.status === 'fulfilled' && chromeExtension.value
    };
  }
}