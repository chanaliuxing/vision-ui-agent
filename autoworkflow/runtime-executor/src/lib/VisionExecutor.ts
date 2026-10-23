// M3: Vision Executor - YOLO + LLM based visual automation

import { EventEmitter } from 'events';
import axios from 'axios';
import sharp from 'sharp';
import type {
  VisionAction,
  VisionExecutionResult,
  ExecutionContext,
  VisionEngineConnection,
  BrowserContext,
  YOLODetection,
  OCRResult,
  LLMDecision
} from '../types/index.js';

export class VisionExecutor extends EventEmitter {
  private visionEngine?: VisionEngineConnection;
  private browser?: BrowserContext;

  // Vision engine URLs (from CLAUDE.md)
  private readonly yoloApiUrl: string;
  private readonly ocrApiUrl: string;
  private readonly workflowApiUrl: string;

  constructor(
    visionEngine?: VisionEngineConnection,
    browser?: BrowserContext
  ) {
    super();

    this.visionEngine = visionEngine;
    this.browser = browser;

    // Default vision engine URLs
    this.yoloApiUrl = 'http://localhost:8000';
    this.ocrApiUrl = 'http://localhost:8001';
    this.workflowApiUrl = 'http://localhost:8002';

    // Initialize vision engine connection
    this.initializeVisionEngine();
  }

  /**
   * Initialize vision engine connection
   */
  private async initializeVisionEngine(): Promise<void> {
    try {
      // Check YOLO API health
      const yoloHealth = await axios.get(`${this.yoloApiUrl}/health`, { timeout: 5000 });

      // Check OCR API health
      const ocrHealth = await axios.get(`${this.ocrApiUrl}/health`, { timeout: 5000 });

      this.visionEngine = {
        baseUrl: this.yoloApiUrl,
        isHealthy: yoloHealth.status === 200 && ocrHealth.status === 200,
        lastHealthCheck: new Date(),
        capabilities: ['yolo_detect', 'ocr_extract', 'llm_decide', 'vision_click'],
        models: {
          yolo: 'yolov8',
          ocr: 'paddleocr',
          llm: 'gemini-1.5-flash'
        }
      };

      this.emit('vision_engine_connected', this.visionEngine);

    } catch (error) {
      this.visionEngine = {
        baseUrl: this.yoloApiUrl,
        isHealthy: false,
        lastHealthCheck: new Date(),
        capabilities: [],
        models: {}
      };

      this.emit('vision_engine_error', error);
      console.error('Failed to initialize vision engine:', error.message);
    }
  }

  /**
   * Execute vision action
   */
  async execute(
    action: VisionAction,
    context: ExecutionContext
  ): Promise<VisionExecutionResult> {
    this.emit('vision_action', { action, context });

    try {
      // Validate action
      this.validateAction(action);

      // Check vision engine health
      if (!this.visionEngine?.isHealthy) {
        await this.initializeVisionEngine();
        if (!this.visionEngine?.isHealthy) {
          return {
            success: false,
            method: 'vision',
            error: 'Vision engine not available'
          };
        }
      }

      // Take screenshot if needed
      const screenshot = action.image || await this.captureScreenshot();
      if (!screenshot) {
        return {
          success: false,
          method: 'vision',
          error: 'Failed to capture screenshot'
        };
      }

      // Execute specific vision action
      switch (action.type) {
        case 'yolo_detect':
          return await this.executeYOLODetection(screenshot, action, context);

        case 'ocr_extract':
          return await this.executeOCRExtraction(screenshot, action, context);

        case 'llm_decide':
          return await this.executeLLMDecision(screenshot, action, context);

        case 'click_vision':
          return await this.executeVisionClick(screenshot, action, context);

        case 'type_vision':
          return await this.executeVisionType(screenshot, action, context);

        default:
          return {
            success: false,
            method: 'vision',
            error: `Unsupported vision action type: ${action.type}`
          };
      }

    } catch (error) {
      return {
        success: false,
        method: 'vision',
        error: error.message,
        screenshot: action.image
      };
    }
  }

  /**
   * Validate vision action
   */
  private validateAction(action: VisionAction): void {
    if (!action.type) {
      throw new Error('Vision action type is required');
    }

    switch (action.type) {
      case 'llm_decide':
        if (!action.prompt) {
          throw new Error('LLM decision action requires prompt');
        }
        break;

      case 'click_vision':
        if (!action.prompt && !action.coordinates) {
          throw new Error('Vision click action requires prompt or coordinates');
        }
        break;

      case 'type_vision':
        if (!action.text) {
          throw new Error('Vision type action requires text');
        }
        break;

      // yolo_detect and ocr_extract have optional parameters
    }
  }

  /**
   * Execute YOLO object detection
   */
  private async executeYOLODetection(
    screenshot: string,
    action: VisionAction,
    context: ExecutionContext
  ): Promise<VisionExecutionResult> {
    try {
      // Convert base64 image to buffer
      const imageBuffer = this.base64ToBuffer(screenshot);

      // Create form data for YOLO API
      const formData = new FormData();
      formData.append('image', new Blob([imageBuffer]), 'screenshot.png');

      // Call YOLO API
      const response = await axios.post(`${this.yoloApiUrl}/predict`, formData, {
        params: { return_image: false },
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 30000
      });

      const detections: YOLODetection[] = response.data.detections || [];

      this.emit('yolo_detections', { detections, count: detections.length });

      return {
        success: true,
        method: 'vision',
        detections,
        output: { detections, count: detections.length },
        screenshot
      };

    } catch (error) {
      return {
        success: false,
        method: 'vision',
        error: `YOLO detection failed: ${error.message}`,
        screenshot
      };
    }
  }

  /**
   * Execute OCR text extraction
   */
  private async executeOCRExtraction(
    screenshot: string,
    action: VisionAction,
    context: ExecutionContext
  ): Promise<VisionExecutionResult> {
    try {
      // Convert base64 image to buffer
      const imageBuffer = this.base64ToBuffer(screenshot);

      // Create form data for OCR API
      const formData = new FormData();
      formData.append('image', new Blob([imageBuffer]), 'screenshot.png');

      // Call OCR API
      const response = await axios.post(`${this.ocrApiUrl}/predict`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 30000
      });

      const ocrResults: OCRResult[] = response.data.ocr_results || [];

      this.emit('ocr_results', { results: ocrResults, count: ocrResults.length });

      return {
        success: true,
        method: 'vision',
        ocr_results: ocrResults,
        output: { ocr_results: ocrResults, text_count: ocrResults.length },
        screenshot
      };

    } catch (error) {
      return {
        success: false,
        method: 'vision',
        error: `OCR extraction failed: ${error.message}`,
        screenshot
      };
    }
  }

  /**
   * Execute LLM decision making
   */
  private async executeLLMDecision(
    screenshot: string,
    action: VisionAction,
    context: ExecutionContext
  ): Promise<VisionExecutionResult> {
    try {
      // First get YOLO detections
      const detectionsResult = await this.executeYOLODetection(screenshot, action, context);
      if (!detectionsResult.success) {
        return detectionsResult;
      }

      // Get OCR results
      const ocrResult = await this.executeOCRExtraction(screenshot, action, context);
      const ocrResults = ocrResult.success ? ocrResult.ocr_results || [] : [];

      // Prepare LLM prompt with visual context
      const visualContext = {
        detections: detectionsResult.detections || [],
        ocr_results: ocrResults,
        prompt: action.prompt,
        screenshot_width: 1920, // TODO: Get actual dimensions
        screenshot_height: 1080
      };

      // Call workflow generation API for LLM decision
      const response = await axios.post(`${this.workflowApiUrl}/generate`, {
        prompt: this.buildLLMPrompt(action.prompt!, visualContext),
        complexity: 1,
        allow_actions: ['ext.click', 'ext.type', 'ext.scroll', 'ext.wait']
      }, {
        timeout: 60000
      });

      const llmDecision: LLMDecision = {
        action: response.data.workflow?.steps?.[0]?.uses || 'unknown',
        target: response.data.workflow?.steps?.[0]?.params?.selector,
        reasoning: response.data.reasoning || 'LLM decision made',
        confidence: 0.8, // TODO: Extract from response
        coordinates: response.data.workflow?.steps?.[0]?.params?.coordinates
      };

      this.emit('llm_decision', { decision: llmDecision, prompt: action.prompt });

      return {
        success: true,
        method: 'vision',
        detections: detectionsResult.detections,
        ocr_results: ocrResults,
        llm_decision: llmDecision,
        output: llmDecision,
        screenshot
      };

    } catch (error) {
      return {
        success: false,
        method: 'vision',
        error: `LLM decision failed: ${error.message}`,
        screenshot
      };
    }
  }

  /**
   * Execute vision-based click
   */
  private async executeVisionClick(
    screenshot: string,
    action: VisionAction,
    context: ExecutionContext
  ): Promise<VisionExecutionResult> {
    try {
      // If coordinates provided, use them directly
      if (action.coordinates) {
        await this.simulateClick(action.coordinates.x, action.coordinates.y);

        return {
          success: true,
          method: 'vision',
          output: {
            clicked: true,
            coordinates: action.coordinates,
            method: 'direct_coordinates'
          },
          screenshot
        };
      }

      // Use LLM to find click target
      const llmResult = await this.executeLLMDecision(screenshot, {
        type: 'llm_decide',
        prompt: `Find and click on: ${action.prompt}`
      }, context);

      if (!llmResult.success || !llmResult.llm_decision) {
        return {
          success: false,
          method: 'vision',
          error: 'Failed to find click target',
          screenshot
        };
      }

      const decision = llmResult.llm_decision;

      // Extract coordinates from LLM decision
      let clickCoordinates = decision.coordinates;

      if (!clickCoordinates && llmResult.detections) {
        // Find best detection match
        const targetDetection = this.findBestDetection(llmResult.detections, action.prompt || '');
        if (targetDetection) {
          clickCoordinates = targetDetection.center;
        }
      }

      if (!clickCoordinates) {
        return {
          success: false,
          method: 'vision',
          error: 'Could not determine click coordinates',
          screenshot
        };
      }

      // Perform click
      await this.simulateClick(clickCoordinates.x, clickCoordinates.y);

      this.emit('vision_click', { coordinates: clickCoordinates, prompt: action.prompt });

      return {
        success: true,
        method: 'vision',
        detections: llmResult.detections,
        llm_decision: decision,
        output: {
          clicked: true,
          coordinates: clickCoordinates,
          method: 'vision_guided'
        },
        screenshot
      };

    } catch (error) {
      return {
        success: false,
        method: 'vision',
        error: `Vision click failed: ${error.message}`,
        screenshot
      };
    }
  }

  /**
   * Execute vision-based typing
   */
  private async executeVisionType(
    screenshot: string,
    action: VisionAction,
    context: ExecutionContext
  ): Promise<VisionExecutionResult> {
    try {
      // First find the input field
      const clickResult = await this.executeVisionClick(screenshot, {
        type: 'click_vision',
        prompt: action.prompt || 'input field'
      }, context);

      if (!clickResult.success) {
        return {
          success: false,
          method: 'vision',
          error: 'Failed to find input field for typing',
          screenshot
        };
      }

      // Wait a moment for the field to focus
      await new Promise(resolve => setTimeout(resolve, 500));

      // Simulate typing
      await this.simulateTyping(action.text!);

      this.emit('vision_type', { text: action.text, prompt: action.prompt });

      return {
        success: true,
        method: 'vision',
        detections: clickResult.detections,
        llm_decision: clickResult.llm_decision,
        output: {
          typed: true,
          text: action.text,
          method: 'vision_guided'
        },
        screenshot
      };

    } catch (error) {
      return {
        success: false,
        method: 'vision',
        error: `Vision type failed: ${error.message}`,
        screenshot
      };
    }
  }

  /**
   * Capture screenshot using available method
   */
  private async captureScreenshot(): Promise<string | null> {
    try {
      // Try Puppeteer first
      if (this.browser?.page) {
        const screenshot = await this.browser.page.screenshot({ encoding: 'base64' });
        return `data:image/png;base64,${screenshot}`;
      }

      // TODO: Add other screenshot methods (native, Chrome Extension)
      return null;

    } catch (error) {
      console.error('Failed to capture screenshot:', error);
      return null;
    }
  }

  /**
   * Convert base64 to buffer
   */
  private base64ToBuffer(base64: string): Buffer {
    const data = base64.replace(/^data:image\/[a-z]+;base64,/, '');
    return Buffer.from(data, 'base64');
  }

  /**
   * Build comprehensive LLM prompt with visual context
   */
  private buildLLMPrompt(userPrompt: string, context: any): string {
    return `
Visual Context Analysis:
- Detected objects: ${context.detections.length} items
- Text elements: ${context.ocr_results.length} items
- Screen dimensions: ${context.screenshot_width}x${context.screenshot_height}

Detected Objects:
${context.detections.map((d: YOLODetection, i: number) =>
  `${i + 1}. ${d.class} (confidence: ${d.confidence.toFixed(2)}) at ${d.center.x},${d.center.y}`
).join('\n')}

Text Elements:
${context.ocr_results.map((ocr: OCRResult, i: number) =>
  `${i + 1}. "${ocr.text}" at ${ocr.center.x},${ocr.center.y}`
).join('\n')}

User Request: ${userPrompt}

Please create a workflow step that accomplishes this task using the available visual elements.
Focus on creating precise selectors or coordinates based on the detected objects and text.
`;
  }

  /**
   * Find best detection match for a given prompt
   */
  private findBestDetection(detections: YOLODetection[], prompt: string): YOLODetection | null {
    if (detections.length === 0) return null;

    const promptLower = prompt.toLowerCase();

    // Simple keyword matching for now
    const matches = detections.filter(d =>
      promptLower.includes(d.class.toLowerCase()) ||
      d.class.toLowerCase().includes(promptLower)
    );

    if (matches.length > 0) {
      // Return highest confidence match
      return matches.reduce((best, current) =>
        current.confidence > best.confidence ? current : best
      );
    }

    // Return highest confidence detection as fallback
    return detections.reduce((best, current) =>
      current.confidence > best.confidence ? current : best
    );
  }

  /**
   * Simulate mouse click at coordinates
   */
  private async simulateClick(x: number, y: number): Promise<void> {
    if (this.browser?.page) {
      await this.browser.page.mouse.click(x, y);
    } else {
      // TODO: Add native click simulation for non-browser contexts
      throw new Error('No click simulation method available');
    }
  }

  /**
   * Simulate keyboard typing
   */
  private async simulateTyping(text: string): Promise<void> {
    if (this.browser?.page) {
      await this.browser.page.keyboard.type(text);
    } else {
      // TODO: Add native typing simulation for non-browser contexts
      throw new Error('No typing simulation method available');
    }
  }

  /**
   * Health check for vision executor
   */
  async healthCheck(): Promise<boolean> {
    try {
      await this.initializeVisionEngine();
      return this.visionEngine?.isHealthy === true;
    } catch (error) {
      return false;
    }
  }

  /**
   * Get vision engine status
   */
  getVisionEngine(): VisionEngineConnection | undefined {
    return this.visionEngine;
  }
}