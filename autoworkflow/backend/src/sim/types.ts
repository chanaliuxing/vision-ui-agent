export type StepStatus = "ok" | "skipped" | "error";

export interface SimTraceEntry {
  id: string;
  name?: string;
  uses?: string;
  status: StepStatus;
  started_ms: number;
  duration_ms: number;
  outputs?: Record<string, any>;
  warning?: string;
  error?: string;
}

export interface SimEstimates {
  llm_tokens: number;
  llm_calls: number;
}

export interface SimResult {
  trace: SimTraceEntry[];
  estimates: SimEstimates;
  warnings: string[];
  final_outputs: Record<string, any>;
  workflow_name?: string;
  workflow_version?: string;
}

export interface SimContext {
  variables: Record<string, any>;
  globals: Record<string, any>;
  outputs: Record<string, any>; // stepId -> output
  started_at: number;
}

export interface ConditionResult {
  passed: boolean;
  error?: string;
}

export interface ActionResult {
  outputs: Record<string, any>;
  duration_ms: number;
  warning?: string;
  error?: string;
}