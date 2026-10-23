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

export interface ActionDefinition {
  id: string;
  title: string;
  description?: string;
  schema: any; // JSON Schema object
  capabilities: string[];
  prerequisites?: string[];
  cost_estimate?: {
    llm_tokens?: number;
    api_calls?: number;
    execution_ms?: number;
  };
  platforms?: string[];
  version?: string;
  author?: string;
  tags?: string[];
}

export interface ValidationResult {
  valid: boolean;
  errors: ValidationError[];
}

export interface ValidationError {
  path: string;
  message: string;
  value?: any;
  schema?: any;
}

export interface ActionRegistry {
  [actionId: string]: ActionDefinition;
}

export interface LintIssue {
  code: string;
  level: 'error' | 'warn' | 'info';
  message: string;
  pointer?: string; // JSON Pointer
  fix?: LintFix;
}

export interface LintFix {
  type: 'replace' | 'add' | 'remove' | 'suggestion';
  description: string;
  target?: string; // JSON Pointer for the fix target
  value?: any; // New value for replace/add operations
}

export interface LintResult {
  issues: LintIssue[];
  workflow_name?: string;
  workflow_version?: string;
}

export interface SimResult {
  success: boolean;
  trace: any[];
  final_state?: any;
  error?: string;
  debug?: any[];
}

export interface DeviceProfile {
  width: number;
  height: number;
  scale?: number;
  name?: string;
}

export interface LintEvidence {
  // 从回放/快照收集到的可点击/存在的选择器（CSS/XPath 统一当字符串处理）
  selectors?: string[];
  // 可用的指纹 ID（anchor_image_id）
  fingerprints?: string[];
  // 上一次的模拟/真实轨迹（可选，用于未来更多推断）
  replay_trace?: any[];
}

export interface LintContext {
  device?: DeviceProfile;
  evidence?: LintEvidence;
}