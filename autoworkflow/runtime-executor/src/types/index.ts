// M3: Runtime Executor + Chrome Extension Bridge - Core Types

// Import workflow types from M1/M2
export interface WorkflowDefinition {
  name: string;
  description?: string;
  version: string;
  globals?: {
    device_target?: 'windows' | 'mac' | 'android' | 'ios' | 'web';
    defaults?: Record<string, any>;
    env?: Record<string, string>;
    permissions?: Array<'camera' | 'clipboard' | 'screenread' | 'filesystem' | 'network' | 'microphone'>;
    llm_budget?: {
      max_calls?: number;
      max_tokens?: number;
    };
    auto_promote_on_success?: boolean;
  };
  variables?: Record<string, any>;
  start: string;
  steps: WorkflowStep[];
  edges?: WorkflowEdge[];
  metadata?: Record<string, any>;
}

export interface WorkflowStep {
  id: string;
  name?: string;
  type: 'action' | 'branch' | 'loop' | 'parallel' | 'wait' | 'subflow' | 'human_input';
  uses?: string;
  params?: Record<string, any>;
  when?: string;
  retry?: {
    times?: number;
    backoff_ms?: number;
  };
  timeout_ms?: number;
  on_error?: 'fail' | 'skip' | 'goto';
  goto?: string;
  outputs?: Record<string, any>;
}

export interface WorkflowEdge {
  from: string;
  to: string;
  condition?: string;
  label?: string;
}

// M3 Execution Types
export interface ExecutionContext {
  executionId: string;
  workflow: WorkflowDefinition;
  currentStepId: string;
  variables: Record<string, any>;
  executionMode: ExecutionMode;
  browser?: BrowserContext;
  chromeExtension?: ChromeExtensionConnection;
  visionEngine?: VisionEngineConnection;
  startTime: Date;
  status: ExecutionStatus;
  trace: ExecutionTrace[];
}

export type ExecutionMode = 'hybrid' | 'dom-only' | 'vision-only' | 'debug';

export type ExecutionStatus = 'pending' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';

export interface ExecutionTrace {
  stepId: string;
  timestamp: Date;
  action: string;
  method: 'dom' | 'vision' | 'hybrid';
  input?: any;
  output?: any;
  screenshot?: string;
  error?: string;
  duration_ms: number;
}

// DOM-first Strategy Types
export interface DOMAction {
  type: 'click' | 'type' | 'scroll' | 'wait' | 'navigate' | 'extract' | 'context_click' | 'mouse_down' | 'mouse_up' | 'mouse_move' | 'mouse_drag' | 'key_combo' | 'key_sequence' |
        // New basic actions
        'clipboard_push' | 'clipboard_pop' | 'clipboard_clear' | 'clipboard_get' | 'clipboard_set' | 'clipboard_copy_selection' |
        'mouse_triple_click' | 'mouse_right_click' | 'mouse_middle_click' | 'mouse_wheel' | 'mouse_move_only' |
        'key_down' | 'key_up' | 'key_select_all' | 'key_copy' | 'key_cut' | 'key_paste' | 'key_toggle_ime' |
        'window_focus' | 'window_minimize' | 'window_close' | 'os_shell' | 'os_activate_app' | 'os_launch_app' |
        'file_read' | 'file_write' | 'file_mkdir' | 'file_remove' | 'file_copy' | 'file_move' | 'file_list';
  selector?: string;
  xpath?: string;
  text?: string;
  coordinates?: { x: number; y: number };
  options?: Record<string, any>;
  // Enhanced mouse options
  button?: 'left' | 'right' | 'middle';
  times?: number;
  clicks?: number;
  interval_ms?: number;
  // Enhanced movement options
  to?: [number, number];
  by?: [number, number];
  duration_ms?: number;
  // Enhanced keyboard options
  combo?: string;
  sequence?: string[];
  down?: string;
  up?: string;
  key?: string;
  keys?: string[];
  // Clipboard options
  content?: string;
  save?: string;
  trim?: boolean;
  max_len?: number;
  regex?: string;
  restore_on_fail?: boolean;
  // Window options
  title?: string;
  window_id?: string;
  // File options
  path?: string;
  data?: any;
  encoding?: string;
  recursive?: boolean;
  // Shell options
  command?: string;
  timeout?: number;
  shell?: boolean;
  // App options
  app_name?: string;
  app_names?: string[];
  app_path?: string;
}

export interface DOMExecutionResult {
  success: boolean;
  method: 'dom';
  output?: any;
  error?: string;
  fallbackRequired?: boolean;
  screenshot?: string;
}

// Vision Fallback Types
export interface VisionAction {
  type: 'yolo_detect' | 'ocr_extract' | 'llm_decide' | 'click_vision' | 'type_vision' | 'mouse_down_vision' | 'mouse_up_vision' | 'mouse_move_vision' | 'mouse_drag_vision' | 'scroll_vision';
  image?: string;
  prompt?: string;
  coordinates?: { x: number; y: number };
  text?: string;
  confidence_threshold?: number;
  // Enhanced mouse options
  button?: 'left' | 'right' | 'middle';
  times?: number;
  clicks?: number;
  interval_ms?: number;
  // Enhanced movement options
  to?: [number, number];
  by?: [number, number];
  duration_ms?: number;
  // Scroll options
  delta_y?: number;
}

export interface VisionExecutionResult {
  success: boolean;
  method: 'vision';
  detections?: YOLODetection[];
  ocr_results?: OCRResult[];
  llm_decision?: LLMDecision;
  output?: any;
  error?: string;
  screenshot?: string;
}

export interface YOLODetection {
  class: string;
  confidence: number;
  bbox: { x: number; y: number; width: number; height: number };
  center: { x: number; y: number };
  id?: string;
}

export interface OCRResult {
  text: string;
  confidence: number;
  bbox: { x: number; y: number; width: number; height: number };
  center: { x: number; y: number };
}

export interface LLMDecision {
  action: string;
  target?: string;
  reasoning: string;
  confidence: number;
  coordinates?: { x: number; y: number };
}

// Chrome Extension Bridge Types
export interface ChromeExtensionConnection {
  tabId: number;
  url: string;
  isConnected: boolean;
  lastHeartbeat: Date;
  capabilities: string[];
}

export interface ChromeExtensionCommand {
  id: string;
  type: 'execute_action' | 'ping' | 'screenshot' | 'get_dom';
  payload: any;
  timestamp: Date;
  timeout_ms?: number;
}

export interface ChromeExtensionResponse {
  commandId: string;
  success: boolean;
  result?: any;
  error?: string;
  screenshot?: string;
  timestamp: Date;
}

// Vision Engine Connection Types
export interface VisionEngineConnection {
  baseUrl: string;
  isHealthy: boolean;
  lastHealthCheck: Date;
  capabilities: string[];
  models: {
    yolo?: string;
    ocr?: string;
    llm?: string;
  };
}

// Browser Context Types (Puppeteer)
export interface BrowserContext {
  browser: any; // Puppeteer Browser
  page: any; // Puppeteer Page
  viewport: { width: number; height: number };
  userAgent: string;
  isHeadless: boolean;
}

// Hybrid Execution Strategy Types
export interface HybridExecutionPlan {
  stepId: string;
  primaryMethod: 'dom' | 'vision';
  fallbackMethod: 'dom' | 'vision';
  domAction?: DOMAction;
  visionAction?: VisionAction;
  fallbackThreshold: number;
  maxRetries: number;
}

export interface HybridExecutionResult {
  success: boolean;
  methodUsed: 'dom' | 'vision' | 'both';
  primaryResult?: DOMExecutionResult | VisionExecutionResult;
  fallbackResult?: DOMExecutionResult | VisionExecutionResult;
  totalDuration_ms: number;
  screenshots: string[];
}

// Workflow Execution Manager Types
export interface WorkflowExecution {
  id: string;
  workflow: WorkflowDefinition;
  status: ExecutionStatus;
  context: ExecutionContext;
  config: ExecutionConfig;
  createdAt: Date;
  startedAt?: Date;
  completedAt?: Date;
  currentStep?: string;
  progress: {
    completed: number;
    total: number;
    percentage: number;
  };
}

export interface ExecutionConfig {
  mode: ExecutionMode;
  timeoutMs: number;
  retryAttempts: number;
  screenshotOnError: boolean;
  enableVisionFallback: boolean;
  visionConfidenceThreshold: number;
  debugMode: boolean;
  saveTrace: boolean;
}

// API Response Types
export interface ExecutionRequest {
  workflow: WorkflowDefinition;
  config?: Partial<ExecutionConfig>;
  variables?: Record<string, any>;
}

export interface ExecutionResponse {
  executionId: string;
  status: ExecutionStatus;
  message?: string;
}

export interface ExecutionStatusResponse {
  executionId: string;
  status: ExecutionStatus;
  progress: {
    completed: number;
    total: number;
    percentage: number;
  };
  currentStep?: string;
  trace?: ExecutionTrace[];
  error?: string;
}

// WebSocket Message Types
export interface WSMessage {
  type: 'execution_start' | 'execution_progress' | 'execution_complete' | 'execution_error' | 'step_complete';
  executionId: string;
  data: any;
  timestamp: Date;
}

// Health Check Types
export interface HealthCheckResult {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: Date;
  services: {
    chromeExtension: boolean;
    visionEngine: boolean;
    browser: boolean;
    m1Backend: boolean;
  };
  uptime: number;
}