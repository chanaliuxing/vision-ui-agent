import type { WorkflowDefinition, LintIssue, LintFix, ActionRegistry, LintContext, DeviceProfile } from '../types.js';

const DEFAULT_DEVICE: DeviceProfile = { width: 1440, height: 900, scale: 1, name: "web-1440x900" };

export class WorkflowLinter {
  private actionRegistry: ActionRegistry;

  constructor(actionRegistry: ActionRegistry) {
    this.actionRegistry = actionRegistry;
  }

  lint(workflow: WorkflowDefinition, context?: LintContext): LintIssue[] {
    const issues: LintIssue[] = [];

    // 1. Graph consistency checks
    issues.push(...this.checkGraphConsistency(workflow));

    // 2. Action validity checks
    issues.push(...this.checkActionValidity(workflow));

    // 3. Prerequisites checks
    issues.push(...this.checkPrerequisites(workflow));

    // 4. Variable reference checks
    issues.push(...this.checkVariableReferences(workflow));

    // 5. Budget estimation checks
    issues.push(...this.checkBudgetEstimation(workflow));

    // 6. Platform compatibility checks
    issues.push(...this.checkPlatformCompatibility(workflow));

    // 7. Edge presence checks
    issues.push(...this.checkEdgePresence(workflow));

    // 8. Enhanced checks with context (M1-S7)
    if (context) {
      issues.push(...this.checkEvidenceBasedLint(workflow, context));
    }

    return issues;
  }

  private checkGraphConsistency(workflow: WorkflowDefinition): LintIssue[] {
    const issues: LintIssue[] = [];

    if (!workflow.steps || !Array.isArray(workflow.steps)) {
      issues.push({
        code: 'GRAPH_NO_STEPS',
        level: 'error',
        message: 'Workflow must have steps array',
        pointer: '/steps'
      });
      return issues;
    }

    const stepIds = new Set(workflow.steps.map(s => s.id));

    // Check start step exists
    if (!stepIds.has(workflow.start)) {
      issues.push({
        code: 'GRAPH_INVALID_START',
        level: 'error',
        message: `Start step '${workflow.start}' not found`,
        pointer: '/start',
        fix: {
          type: 'suggestion',
          description: `Change start to one of: ${Array.from(stepIds).join(', ')}`
        }
      });
    }

    // Check edge references
    if (workflow.edges) {
      workflow.edges.forEach((edge, index) => {
        if (!stepIds.has(edge.from)) {
          issues.push({
            code: 'GRAPH_INVALID_EDGE_FROM',
            level: 'error',
            message: `Edge 'from' references non-existent step: ${edge.from}`,
            pointer: `/edges/${index}/from`
          });
        }
        if (!stepIds.has(edge.to)) {
          issues.push({
            code: 'GRAPH_INVALID_EDGE_TO',
            level: 'error',
            message: `Edge 'to' references non-existent step: ${edge.to}`,
            pointer: `/edges/${index}/to`
          });
        }
      });
    }

    // Check for unreachable steps
    const reachableSteps = this.findReachableSteps(workflow);
    stepIds.forEach(stepId => {
      if (!reachableSteps.has(stepId)) {
        const stepIndex = workflow.steps.findIndex(s => s.id === stepId);
        issues.push({
          code: 'GRAPH_UNREACHABLE_STEP',
          level: 'warn',
          message: `Step '${stepId}' is unreachable`,
          pointer: `/steps/${stepIndex}`,
          fix: {
            type: 'suggestion',
            description: 'Add an edge leading to this step or remove it'
          }
        });
      }
    });

    return issues;
  }

  private checkActionValidity(workflow: WorkflowDefinition): LintIssue[] {
    const issues: LintIssue[] = [];

    if (!workflow.steps || !Array.isArray(workflow.steps)) {
      return issues;
    }

    workflow.steps.forEach((step, index) => {
      if (step.type === 'action' && step.uses) {
        const actionDef = this.actionRegistry[step.uses];
        if (!actionDef) {
          issues.push({
            code: 'ACTION_NOT_FOUND',
            level: 'error',
            message: `Unknown action: ${step.uses}`,
            pointer: `/steps/${index}/uses`,
            fix: {
              type: 'suggestion',
              description: `Available actions: ${Object.keys(this.actionRegistry).join(', ')}`
            }
          });
        } else {
          // Check required parameters
          const requiredParams = actionDef.schema?.required || [];
          if (step.params) {
            for (const param of requiredParams) {
              if (!(param in step.params)) {
                issues.push({
                  code: 'ACTION_MISSING_PARAM',
                  level: 'error',
                  message: `Missing required parameter: ${param}`,
                  pointer: `/steps/${index}/params`,
                  fix: {
                    type: 'add',
                    description: `Add required parameter '${param}'`,
                    target: `/steps/${index}/params/${param}`,
                    value: this.getDefaultValueForParam(actionDef.schema, param)
                  }
                });
              }
            }
          } else if (requiredParams.length > 0) {
            issues.push({
              code: 'ACTION_NO_PARAMS',
              level: 'error',
              message: `Action requires parameters: ${requiredParams.join(', ')}`,
              pointer: `/steps/${index}/params`,
              fix: {
                type: 'add',
                description: 'Add required parameters',
                target: `/steps/${index}/params`,
                value: this.createDefaultParams(actionDef.schema)
              }
            });
          }
        }
      }
    });

    return issues;
  }

  private checkPrerequisites(workflow: WorkflowDefinition): LintIssue[] {
    const issues: LintIssue[] = [];

    if (!workflow.steps || !Array.isArray(workflow.steps)) {
      return issues;
    }

    const executedActions = new Set<string>();

    // Build execution order based on edges or step sequence
    const executionOrder = this.getExecutionOrder(workflow);

    for (const stepId of executionOrder) {
      const step = workflow.steps.find(s => s.id === stepId);
      if (!step || step.type !== 'action' || !step.uses) continue;

      const actionDef = this.actionRegistry[step.uses];
      if (!actionDef) continue;

      // Check prerequisites
      const prerequisites = actionDef.prerequisites || [];
      for (const prereq of prerequisites) {
        if (!executedActions.has(prereq)) {
          const stepIndex = workflow.steps.findIndex(s => s.id === stepId);
          issues.push({
            code: 'ACTION_MISSING_PREREQUISITE',
            level: 'error',
            message: `Action '${step.uses}' requires '${prereq}' to be executed first`,
            pointer: `/steps/${stepIndex}`,
            fix: {
              type: 'suggestion',
              description: `Ensure '${prereq}' action appears before this step`
            }
          });
        }
      }

      executedActions.add(step.uses);
    }

    return issues;
  }

  private checkVariableReferences(workflow: WorkflowDefinition): LintIssue[] {
    const issues: LintIssue[] = [];

    if (!workflow.steps || !Array.isArray(workflow.steps)) {
      return issues;
    }

    const definedVars = new Set(Object.keys(workflow.variables || {}));

    // Add globals to defined vars
    if (workflow.globals?.env) {
      Object.keys(workflow.globals.env).forEach(key => definedVars.add(`globals.env.${key}`));
    }

    // Check variable references in steps
    workflow.steps.forEach((step, stepIndex) => {
      this.checkObjectForVariableReferences(step, `/steps/${stepIndex}`, definedVars, issues);
    });

    // Check cross-step output references
    issues.push(...this.checkOutputReferences(workflow));

    return issues;
  }

  private checkOutputReferences(workflow: WorkflowDefinition): LintIssue[] {
    const issues: LintIssue[] = [];

    if (!workflow.steps || !Array.isArray(workflow.steps)) {
      return issues; // Skip if no steps
    }

    const stepIds = new Set(workflow.steps.map(s => s.id));

    // Check each step for output references
    workflow.steps.forEach((step, stepIndex) => {
      if (step.type === 'action') {
        this.validateOutputRefsInObject(
          step.params || {},
          stepIds,
          step.id,
          issues,
          `/steps/${stepIndex}/params`,
          workflow
        );
      } else if (step.type === 'branch') {
        this.validateOutputRefsInObject(
          step.condition || {},
          stepIds,
          step.id,
          issues,
          `/steps/${stepIndex}/condition`,
          workflow
        );
      }
    });

    return issues;
  }

  private validateOutputRefsInObject(
    obj: any,
    stepIds: Set<string>,
    currentStepId: string,
    issues: LintIssue[],
    basePath: string,
    workflow: WorkflowDefinition
  ): void {
    if (typeof obj === 'string') {
      const refs = this.parseOutputsRef(obj);
      for (const ref of refs) {
        if (!stepIds.has(ref.stepId)) {
          issues.push({
            code: 'OUTPUT_REF_INVALID_STEP',
            level: 'error',
            message: `Reference to non-existent step: ${ref.stepId}`,
            pointer: basePath,
            fix: {
              type: 'suggestion',
              description: `Available steps: ${Array.from(stepIds).join(', ')}`
            }
          });
        } else if (!this.contractHasField(ref.stepId, ref.field, workflow)) {
          issues.push({
            code: 'OUTPUT_REF_INVALID_FIELD',
            level: 'warn',
            message: `Reference to potentially non-existent output field: ${ref.stepId}.${ref.field}`,
            pointer: basePath,
            fix: {
              type: 'suggestion',
              description: `Check if step ${ref.stepId} produces output field '${ref.field}'`
            }
          });
        }
      }
    } else if (Array.isArray(obj)) {
      obj.forEach((item, index) => {
        this.validateOutputRefsInObject(item, stepIds, currentStepId, issues, `${basePath}/${index}`, workflow);
      });
    } else if (obj && typeof obj === 'object') {
      Object.keys(obj).forEach(key => {
        this.validateOutputRefsInObject(obj[key], stepIds, currentStepId, issues, `${basePath}/${key}`, workflow);
      });
    }
  }

  private parseOutputsRef(text: string): { stepId: string; field: string }[] {
    const refs: { stepId: string; field: string }[] = [];
    const pattern = /\$\{outputs\.([^.}]+)\.([^}]+)\}/g;
    let match;

    while ((match = pattern.exec(text)) !== null) {
      refs.push({
        stepId: match[1],
        field: match[2]
      });
    }

    return refs;
  }

  private contractHasField(stepId: string, field: string, workflow: WorkflowDefinition): boolean {
    // Look up step action and check its output contract
    const step = workflow.steps.find(s => s.id === stepId);
    if (!step || step.type !== 'action') return true; // Assume valid for non-action steps

    const actionDef = this.actionRegistry[step.uses!];
    if (!actionDef?.output_contract) return true; // Assume valid if no contract defined

    return field in actionDef.output_contract.properties;
  }

  private checkBudgetEstimation(workflow: WorkflowDefinition): LintIssue[] {
    const issues: LintIssue[] = [];

    if (!workflow.globals?.llm_budget) {
      return issues; // No budget constraints
    }

    if (!workflow.steps || !Array.isArray(workflow.steps)) {
      return issues;
    }

    let totalTokens = 0;
    let totalCalls = 0;

    workflow.steps.forEach((step, index) => {
      if (step.type === 'action' && step.uses) {
        const actionDef = this.actionRegistry[step.uses];
        if (actionDef?.cost_estimate) {
          totalTokens += actionDef.cost_estimate.llm_tokens || 0;
          totalCalls += actionDef.cost_estimate.api_calls || 0;
        }
      }
    });

    const budget = workflow.globals.llm_budget;

    if (budget.max_tokens && totalTokens > budget.max_tokens) {
      issues.push({
        code: 'BUDGET_TOKENS_EXCEEDED',
        level: 'warn',
        message: `Estimated tokens (${totalTokens}) exceed budget (${budget.max_tokens})`,
        pointer: '/globals/llm_budget/max_tokens',
        fix: {
          type: 'replace',
          description: `Increase budget to at least ${totalTokens}`,
          target: '/globals/llm_budget/max_tokens',
          value: totalTokens
        }
      });
    }

    if (budget.max_calls && totalCalls > budget.max_calls) {
      issues.push({
        code: 'BUDGET_CALLS_EXCEEDED',
        level: 'warn',
        message: `Estimated calls (${totalCalls}) exceed budget (${budget.max_calls})`,
        pointer: '/globals/llm_budget/max_calls',
        fix: {
          type: 'replace',
          description: `Increase budget to at least ${totalCalls}`,
          target: '/globals/llm_budget/max_calls',
          value: totalCalls
        }
      });
    }

    return issues;
  }

  private checkPlatformCompatibility(workflow: WorkflowDefinition): LintIssue[] {
    const issues: LintIssue[] = [];
    const targetPlatform = workflow.globals?.device_target;

    if (!targetPlatform) return issues;

    if (!workflow.steps || !Array.isArray(workflow.steps)) {
      return issues;
    }

    workflow.steps.forEach((step, index) => {
      if (step.type === 'action' && step.uses) {
        const actionDef = this.actionRegistry[step.uses];
        if (actionDef?.platforms && !actionDef.platforms.includes(targetPlatform)) {
          issues.push({
            code: 'PLATFORM_INCOMPATIBLE',
            level: 'error',
            message: `Action '${step.uses}' not supported on ${targetPlatform}`,
            pointer: `/steps/${index}/uses`,
            fix: {
              type: 'suggestion',
              description: `Available platforms: ${actionDef.platforms.join(', ')}`
            }
          });
        }
      }
    });

    return issues;
  }

  private checkEdgePresence(workflow: WorkflowDefinition): LintIssue[] {
    const issues: LintIssue[] = [];

    if (!workflow.steps || !Array.isArray(workflow.steps)) {
      return issues;
    }

    if (!workflow.edges || workflow.edges.length === 0) {
      if (workflow.steps.length > 1) {
        issues.push({
          code: 'WORKFLOW_NO_EDGES',
          level: 'info',
          message: 'No edges defined. Steps will execute in declaration order',
          pointer: '/edges',
          fix: {
            type: 'add',
            description: 'Add sequential edges between steps',
            target: '/edges',
            value: this.generateSequentialEdges(workflow.steps)
          }
        });
      }
    }

    return issues;
  }

  // Helper methods
  private findReachableSteps(workflow: WorkflowDefinition): Set<string> {
    const reachable = new Set<string>();
    const queue = [workflow.start];

    while (queue.length > 0) {
      const current = queue.shift()!;
      if (reachable.has(current)) continue;

      reachable.add(current);

      // Add connected steps
      if (workflow.edges) {
        workflow.edges
          .filter(edge => edge.from === current)
          .forEach(edge => queue.push(edge.to));
      }
    }

    return reachable;
  }

  private getExecutionOrder(workflow: WorkflowDefinition): string[] {
    if (!workflow.steps || !Array.isArray(workflow.steps)) {
      return [];
    }

    if (!workflow.edges || workflow.edges.length === 0) {
      return workflow.steps.map(s => s.id);
    }

    // Simple topological sort
    const order: string[] = [];
    const visited = new Set<string>();

    const visit = (stepId: string) => {
      if (visited.has(stepId)) return;
      visited.add(stepId);

      // Visit prerequisites first
      const incomingEdges = workflow.edges!.filter(e => e.to === stepId);
      for (const edge of incomingEdges) {
        visit(edge.from);
      }

      order.push(stepId);
    };

    // Start from root nodes
    const allTos = new Set(workflow.edges.map(e => e.to));
    const roots = workflow.steps
      .map(s => s.id)
      .filter(id => !allTos.has(id));

    for (const root of roots) {
      visit(root);
    }

    return order;
  }

  private checkObjectForVariableReferences(
    obj: any,
    basePath: string,
    definedVars: Set<string>,
    issues: LintIssue[]
  ): void {
    if (typeof obj === 'string') {
      const varRefs = obj.match(/\$\{([^}]+)\}/g);
      if (varRefs) {
        varRefs.forEach(ref => {
          const varName = ref.slice(2, -1); // Remove ${ and }

          // Skip output references - they're handled separately
          if (varName.startsWith('outputs.')) {
            return;
          }

          if (!definedVars.has(varName) && !varName.startsWith('vars.')) {
            issues.push({
              code: 'VARIABLE_UNDEFINED',
              level: 'error',
              message: `Undefined variable reference: ${varName}`,
              pointer: basePath,
              fix: {
                type: 'suggestion',
                description: `Define variable '${varName}' in workflow variables`
              }
            });
          }
        });
      }
    } else if (typeof obj === 'object' && obj !== null) {
      Object.entries(obj).forEach(([key, value]) => {
        this.checkObjectForVariableReferences(value, `${basePath}/${key}`, definedVars, issues);
      });
    }
  }

  private getDefaultValueForParam(schema: any, param: string): any {
    const property = schema?.properties?.[param];
    if (!property) return null;

    if (property.default !== undefined) return property.default;
    if (property.type === 'string') return '';
    if (property.type === 'number' || property.type === 'integer') return 0;
    if (property.type === 'boolean') return false;
    if (property.type === 'array') return [];
    if (property.type === 'object') return {};

    return null;
  }

  private createDefaultParams(schema: any): any {
    const params: any = {};
    const required = schema?.required || [];

    required.forEach((param: string) => {
      params[param] = this.getDefaultValueForParam(schema, param);
    });

    return params;
  }

  private generateSequentialEdges(steps: any[]): any[] {
    const edges = [];
    for (let i = 0; i < steps.length - 1; i++) {
      edges.push({
        from: steps[i].id,
        to: steps[i + 1].id
      });
    }
    return edges;
  }

  // M1-S7: Enhanced checks with evidence context
  private checkEvidenceBasedLint(workflow: WorkflowDefinition, context: LintContext): LintIssue[] {
    const issues: LintIssue[] = [];

    if (!workflow.steps || !Array.isArray(workflow.steps)) {
      return issues;
    }

    const device = context.device || DEFAULT_DEVICE;
    const evidence = context.evidence || {};

    // Utility functions
    const hasSelector = (selector?: string) => {
      if (!selector || !evidence.selectors) return true; // 无证据→不判为错
      return evidence.selectors.includes(selector);
    };

    const hasFingerprint = (id?: string) => {
      if (!id || !evidence.fingerprints) return true;
      return evidence.fingerprints.includes(id);
    };

    const isNumber = (n: any): n is number => typeof n === "number" && isFinite(n);

    const inBounds = (pt: {x:number; y:number}) => {
      return isNumber(pt.x) && isNumber(pt.y) && pt.x >= 0 && pt.y >= 0 && pt.x <= device.width && pt.y <= device.height;
    };

    const rectInBounds = (r: {x:number;y:number;w:number;h:number}) => {
      return isNumber(r.x) && isNumber(r.y) && isNumber(r.w) && isNumber(r.h) &&
             r.w >= 0 && r.h >= 0 &&
             r.x >= 0 && r.y >= 0 &&
             (r.x + r.w) <= device.width && (r.y + r.h) <= device.height;
    };

    // WF091: selector 不可达（基于 evidence）
    workflow.steps.forEach((s, i) => {
      if (s.type === "action" && s.uses === "ext.click") {
        const sel = s.params?.selector;
        if (typeof sel === "string" && sel.includes("${")) return; // 动态引用跳过
        if (typeof sel === "string" && !hasSelector(sel)) {
          issues.push({
            code: "WF091",
            level: "warn",
            message: `selector not found in evidence snapshot: "${sel}"`,
            pointer: `/steps/${i}/params/selector`,
            fix: {
              type: 'suggestion',
              description: "确认选择器来源（录制/回放），或改用 vision.find_element + ref"
            }
          });
        }
      }
    });

    // WF092: 坐标/区域越界（基于 device）
    workflow.steps.forEach((s, i) => {
      if (s.type !== "action") return;

      if (s.uses === "ext.click") {
        const p = s.params || {};
        if (isNumber(p.x) && isNumber(p.y) && !inBounds({x:p.x,y:p.y})) {
          issues.push({
            code: "WF092",
            level: "error",
            message: `click point (${p.x},${p.y}) out of device bounds ${device.width}x${device.height}`,
            pointer: `/steps/${i}/params`,
            fix: {
              type: 'suggestion',
              description: "调整坐标或切换 device"
            }
          });
        }
      }

      if (s.uses === "ocr.extract_region") {
        const r = s.params?.region;
        if (r && !rectInBounds(r)) {
          issues.push({
            code: "WF092",
            level: "error",
            message: `ocr region out of bounds: (${r.x},${r.y},${r.w},${r.h}) vs ${device.width}x${device.height}`,
            pointer: `/steps/${i}/params/region`,
            fix: {
              type: 'suggestion',
              description: "缩放/移动区域或切换 device"
            }
          });
        }
      }
    });

    // 指纹存在性（增强 WF08x）
    workflow.steps.forEach((s, i) => {
      if (s.type === "action" && s.uses === "vision.find_element_with_image_check") {
        const id = s.params?.anchor_image_id;
        if (typeof id === "string" && !hasFingerprint(id)) {
          issues.push({
            code: "WF091",
            level: "warn",
            message: `fingerprint id not found in evidence: "${id}"`,
            pointer: `/steps/${i}/params/anchor_image_id`,
            fix: {
              type: 'suggestion',
              description: "同步指纹库或检查 ID 拼写"
            }
          });
        }
      }
    });

    // WF093: LLM 预算精细化
    const budget = workflow.globals?.llm_budget;
    if (budget?.max_tokens != null) {
      const est = this.estimateLLM(workflow);
      if (est.tokens > budget.max_tokens * 1.15) {
        issues.push({
          code: "WF093",
          level: "error",
          message: `LLM token estimate ${est.tokens} exceeds budget ${budget.max_tokens}`,
          pointer: "/globals/llm_budget",
          fix: {
            type: 'suggestion',
            description: "减少 llm.* 调用或缩短 prompt，上调预算"
          }
        });
      } else if (est.tokens > budget.max_tokens * 0.85) {
        issues.push({
          code: "WF093",
          level: "warn",
          message: `LLM token estimate ${est.tokens} is close to budget ${budget.max_tokens}`,
          pointer: "/globals/llm_budget"
        });
      }
    }

    // WF095: 设备目标与浏览器 app 不匹配
    const deviceTarget = workflow.globals?.device_target;
    workflow.steps.forEach((s, i) => {
      if (s.type === "action" && s.uses === "ext.open_url") {
        const app = s.params?.app;
        if (deviceTarget === "web" && app && !["Google Chrome","Edge","Arc","Firefox"].includes(app)) {
          issues.push({
            code: "WF095",
            level: "warn",
            message: `device_target=web but app="${app}" may be unsupported`,
            pointer: `/steps/${i}/params/app`,
            fix: {
              type: 'suggestion',
              description: "改用 Chrome / Edge / Arc / Firefox"
            }
          });
        }
      }
    });

    return issues;
  }

  // LLM 预算精细化估算
  private estimateLLM(workflow: WorkflowDefinition): { tokens: number; calls: number } {
    let tokens = 0, calls = 0;

    for (const s of workflow.steps) {
      if (s.type !== "action") continue;

      const actionDef = this.actionRegistry[s.uses || ''];
      if (actionDef?.cost_estimate?.llm_tokens) {
        tokens += actionDef.cost_estimate.llm_tokens;
      }

      if (String(s.uses || "").startsWith("llm.")) {
        calls += 1;
        const sysOverhead = 80; // 经验常数
        const prompt = (typeof s.params?.prompt === "string") ? s.params.prompt : "";
        tokens += sysOverhead + Math.ceil(prompt.length / 4);
      }
    }

    return { tokens, calls };
  }
}