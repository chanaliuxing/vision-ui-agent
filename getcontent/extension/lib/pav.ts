// PAV (Plan-Act-Validate) Cycle Implementation
// Implements Phase 3 of the DOM reduction plan

// Core TypeScript interfaces for PAV cycle
export interface PlanStep {
  task_id: string;
  step_no: number;
  goal: string;
  action: "click" | "type" | "select" | "navigate";
  target: {
    by: "index" | "text" | "href" | "id";
    value: number | string;
    fallback?: Array<{ by: "text" | "href" | "id"; value: string }>;
  };
  input_text?: string;
  success_criteria: {
    url_contains?: string[];
    url_regex?: string[];
    title_includes?: string[];
    must_exist?: string[];
    must_not_exist?: string[];
    text_includes?: string[];
    timeout_ms?: number;
  };
}

export interface ReducedDom {
  url: string;
  title: string;
  vw: number;
  vh: number;
  dpr: number;
  elements: Array<{
    label: string;
    role: string;
    bbox: [number, number, number, number];
    center: [number, number];
    id?: string;
    href?: string;
    action?: string;
  }>;
  index: Record<string, number>;
  _reduced: true;
  _version: string;
}

export interface StepRuntime {
  ts_start: number;
  ts_end: number;
  duration_ms: number;
  nav_events: Array<{
    type: "committed" | "completed" | "error" | "redirect";
    url: string;
    time: number;
  }>;
  net_requests: number;
  screenshot?: string;
  error?: string;
}

export interface ExecutionReport {
  exec_id: string;
  task_id: string;
  step_no: number;
  goal: string;
  plan_step: PlanStep;
  history: Array<{
    step_no: number;
    action: string;
    target_label?: string;
    url_after: string;
    ok: boolean;
  }>;
  pre_context: ReducedDom;
  action_sent: {
    action: "click" | "type" | "select" | "navigate";
    target_resolved: {
      by: "index" | "text" | "href" | "id";
      value: number | string;
      label?: string;
    };
    input_text?: string;
  };
  runtime: StepRuntime;
  post_context: ReducedDom;
  diff: {
    url_changed: boolean;
    title_changed: boolean;
    appeared_labels: string[];
    disappeared_labels: string[];
  };
  local_validation: {
    status: "success" | "failure" | "uncertain";
    reasons: string[];
    matched_criteria: string[];
  };
  llm_validation?: ValidationVerdict;
}

export interface ValidationVerdict {
  status: "success" | "failure" | "uncertain";
  confidence: number;
  reasoning: string[];
  is_on_expected_page?: boolean;
  recommended_next_steps: Array<{
    action: "proceed" | "retry" | "wait" | "scroll" | "back" | "alt_target" | "abort";
    notes?: string;
    alt_target?: { by: "text" | "href" | "id"; value: string };
  }>;
  refined_success_criteria?: PlanStep["success_criteria"];
}

// Core PAV implementation
export class PAVController {
  private history: Array<{
    step_no: number;
    action: string;
    target_label?: string;
    url_after: string;
    ok: boolean;
  }> = [];

  private navEventLog: Array<{
    type: "committed" | "completed" | "error" | "redirect";
    url: string;
    time: number;
  }> = [];

  constructor() {
    this.initializeNavigationTracking();
  }

  private initializeNavigationTracking() {
    // Track navigation events for validation
    if (typeof chrome !== 'undefined' && chrome.webNavigation) {
      chrome.webNavigation.onCommitted.addListener((details) => {
        this.navEventLog.push({
          type: "committed",
          url: details.url,
          time: Date.now()
        });
      });

      chrome.webNavigation.onCompleted.addListener((details) => {
        this.navEventLog.push({
          type: "completed",
          url: details.url,
          time: Date.now()
        });
      });

      chrome.webNavigation.onErrorOccurred.addListener((details) => {
        this.navEventLog.push({
          type: "error",
          url: details.url,
          time: Date.now()
        });
      });
    }
  }

  // Main PAV execution method
  async runStep(planStep: PlanStep): Promise<ExecutionReport> {
    const exec_id = this.generateId();
    const ts_start = Date.now();

    try {
      // 1) Get pre-execution context
      const pre_context = await this.getReducedDom();

      // 2) Resolve target using reducer output
      const target_resolved = this.resolveTarget(planStep.target, pre_context);

      // 3) Execute the action
      const action_sent = {
        action: planStep.action,
        target_resolved,
        input_text: planStep.input_text
      };

      await this.performAction(action_sent, planStep);

      // 4) Wait for action to complete
      await this.waitForStability(planStep.success_criteria?.timeout_ms || 8000);

      const ts_end = Date.now();

      // 5) Get post-execution context
      const post_context = await this.getReducedDom();

      // 6) Calculate diff
      const diff = this.makeDiff(pre_context, post_context);

      // 7) Build runtime info
      const runtime: StepRuntime = {
        ts_start,
        ts_end,
        duration_ms: ts_end - ts_start,
        nav_events: this.getRecentNavEvents(ts_start),
        net_requests: 0, // TODO: Implement via CDP if needed
        screenshot: undefined, // TODO: Add screenshot capability
        error: undefined
      };

      // 8) Local validation
      const local_validation = this.validateLocal(
        planStep.success_criteria,
        post_context,
        diff,
        runtime
      );

      // 9) Build execution report
      const report: ExecutionReport = {
        exec_id,
        task_id: planStep.task_id,
        step_no: planStep.step_no,
        goal: planStep.goal,
        plan_step: planStep,
        history: [...this.history],
        pre_context,
        action_sent,
        runtime,
        post_context,
        diff,
        local_validation
      };

      // 10) LLM validation for uncertain cases
      if (local_validation.status === "uncertain") {
        const llm_validation = await this.callLLMValidator(report);
        report.llm_validation = llm_validation;
      }

      // 11) Update history
      this.history.push({
        step_no: planStep.step_no,
        action: planStep.action,
        target_label: target_resolved.label,
        url_after: post_context.url,
        ok: (report.llm_validation?.status || local_validation.status) === "success"
      });

      return report;

    } catch (error) {
      const ts_end = Date.now();
      const post_context = await this.getReducedDom().catch(() => ({} as ReducedDom));

      return {
        exec_id,
        task_id: planStep.task_id,
        step_no: planStep.step_no,
        goal: planStep.goal,
        plan_step: planStep,
        history: [...this.history],
        pre_context: {} as ReducedDom,
        action_sent: {
          action: planStep.action,
          target_resolved: { by: "index", value: -1 }
        },
        runtime: {
          ts_start,
          ts_end,
          duration_ms: ts_end - ts_start,
          nav_events: this.getRecentNavEvents(ts_start),
          net_requests: 0,
          error: error instanceof Error ? error.message : String(error)
        },
        post_context,
        diff: {
          url_changed: false,
          title_changed: false,
          appeared_labels: [],
          disappeared_labels: []
        },
        local_validation: {
          status: "failure",
          reasons: [`Execution error: ${error}`],
          matched_criteria: []
        }
      };
    }
  }

  // Get reduced DOM using existing reducer
  private async getReducedDom(): Promise<ReducedDom> {
    // This would call the reducer we implemented in Phase 1
    const response = await chrome.runtime.sendMessage({
      type: 'EXT_EXTRACT_RAW',
      args: { want: 'inputs', limit: 100 }
    });

    if (!response?.result) {
      throw new Error('Failed to get DOM snapshot');
    }

    // Transform to ReducedDom format
    const { dom, meta } = response.result;

    return {
      url: meta.url,
      title: meta.title || document.title,
      vw: dom.vw || window.innerWidth,
      vh: dom.vh || window.innerHeight,
      dpr: dom.dpr || window.devicePixelRatio,
      elements: dom.items || [],
      index: this.buildElementIndex(dom.items || []),
      _reduced: true,
      _version: "1.0.0"
    };
  }

  private buildElementIndex(elements: any[]): Record<string, number> {
    const index: Record<string, number> = {};
    elements.forEach((el, i) => {
      if (el.label) index[el.label] = i;
      if (el.id) index[el.id] = i;
      if (el.href) index[el.href] = i;
    });
    return index;
  }

  // Resolve target element from plan step
  private resolveTarget(target: PlanStep["target"], context: ReducedDom): ExecutionReport["action_sent"]["target_resolved"] {
    const { by, value, fallback } = target;

    // Try primary target first
    const resolved = this.findElement(by, value, context);
    if (resolved) return resolved;

    // Try fallback targets
    if (fallback) {
      for (const fb of fallback) {
        const resolved = this.findElement(fb.by, fb.value, context);
        if (resolved) return resolved;
      }
    }

    throw new Error(`Target not found: ${by}=${value}`);
  }

  private findElement(by: string, value: string | number, context: ReducedDom): ExecutionReport["action_sent"]["target_resolved"] | null {
    switch (by) {
      case "index":
        const idx = Number(value);
        if (idx >= 0 && idx < context.elements.length) {
          return {
            by: "index",
            value: idx,
            label: context.elements[idx].label
          };
        }
        break;

      case "text":
        const textMatch = context.elements.find(el =>
          el.label?.toLowerCase().includes(String(value).toLowerCase())
        );
        if (textMatch) {
          return {
            by: "text",
            value: String(value),
            label: textMatch.label
          };
        }
        break;

      case "href":
        const hrefMatch = context.elements.find(el =>
          el.href?.includes(String(value))
        );
        if (hrefMatch) {
          return {
            by: "href",
            value: String(value),
            label: hrefMatch.label
          };
        }
        break;

      case "id":
        const idMatch = context.elements.find(el => el.id === String(value));
        if (idMatch) {
          return {
            by: "id",
            value: String(value),
            label: idMatch.label
          };
        }
        break;
    }

    return null;
  }

  // Perform the actual action
  private async performAction(action_sent: ExecutionReport["action_sent"], planStep: PlanStep): Promise<void> {
    switch (action_sent.action) {
      case "click":
        await this.performClick(action_sent.target_resolved);
        break;

      case "type":
        await this.performType(action_sent.target_resolved, action_sent.input_text || "");
        break;

      case "select":
        await this.performSelect(action_sent.target_resolved, action_sent.input_text || "");
        break;

      case "navigate":
        await this.performNavigate(String(action_sent.target_resolved.value));
        break;

      default:
        throw new Error(`Unknown action: ${action_sent.action}`);
    }
  }

  private async performClick(target: ExecutionReport["action_sent"]["target_resolved"]): Promise<void> {
    // Use existing content script actions
    await chrome.runtime.sendMessage({
      type: 'EXT_CLICK_SELECTOR',
      args: { sel: this.getSelector(target) }
    });
  }

  private async performType(target: ExecutionReport["action_sent"]["target_resolved"], text: string): Promise<void> {
    await chrome.runtime.sendMessage({
      type: 'EXT_TYPE_TEXT',
      args: { sel: this.getSelector(target), text, replace: true }
    });
  }

  private async performSelect(target: ExecutionReport["action_sent"]["target_resolved"], value: string): Promise<void> {
    // For select elements, we'll use a simple approach
    const selector = this.getSelector(target);
    await chrome.runtime.sendMessage({
      type: 'DOM_SELECT',
      args: { selector, value }
    });
  }

  private async performNavigate(url: string): Promise<void> {
    window.location.href = url;
  }

  private getSelector(target: ExecutionReport["action_sent"]["target_resolved"]): string {
    switch (target.by) {
      case "id":
        return `#${target.value}`;
      case "href":
        return `a[href*="${target.value}"]`;
      case "text":
        return `*:contains("${target.value}")`;
      case "index":
        // For index-based selection, we'll need a more complex approach
        return `*:nth-child(${Number(target.value) + 1})`;
      default:
        throw new Error(`Cannot build selector for: ${target.by}`);
    }
  }

  // Wait for page/DOM stability
  private async waitForStability(timeout: number): Promise<void> {
    const start = Date.now();
    const checkInterval = 500;

    return new Promise((resolve) => {
      const check = () => {
        if (Date.now() - start > timeout) {
          resolve();
          return;
        }

        // Check for page readiness
        if (document.readyState === 'complete') {
          // Wait a bit more for dynamic content
          setTimeout(resolve, 1000);
        } else {
          setTimeout(check, checkInterval);
        }
      };

      check();
    });
  }

  // Create diff between pre and post contexts
  private makeDiff(pre: ReducedDom, post: ReducedDom): ExecutionReport["diff"] {
    const preLabels = new Set(pre.elements.map(el => el.label));
    const postLabels = new Set(post.elements.map(el => el.label));

    const appeared_labels = Array.from(postLabels).filter(label => !preLabels.has(label));
    const disappeared_labels = Array.from(preLabels).filter(label => !postLabels.has(label));

    return {
      url_changed: pre.url !== post.url,
      title_changed: pre.title !== post.title,
      appeared_labels,
      disappeared_labels
    };
  }

  // Local validation using deterministic rules
  private validateLocal(
    criteria: PlanStep["success_criteria"],
    context: ReducedDom,
    diff: ExecutionReport["diff"],
    runtime: StepRuntime
  ): ExecutionReport["local_validation"] {
    const reasons: string[] = [];
    const matched_criteria: string[] = [];
    let score = 0;
    let total = 0;

    // URL checks
    if (criteria.url_contains) {
      total++;
      const matches = criteria.url_contains.filter(fragment =>
        context.url.toLowerCase().includes(fragment.toLowerCase())
      );
      if (matches.length > 0) {
        score++;
        matched_criteria.push(`url_contains: ${matches.join(', ')}`);
        reasons.push(`URL contains expected fragments: ${matches.join(', ')}`);
      } else {
        reasons.push(`URL missing expected fragments: ${criteria.url_contains.join(', ')}`);
      }
    }

    if (criteria.url_regex) {
      total++;
      const matches = criteria.url_regex.filter(pattern => {
        try {
          return new RegExp(pattern).test(context.url);
        } catch {
          return false;
        }
      });
      if (matches.length > 0) {
        score++;
        matched_criteria.push(`url_regex: ${matches.join(', ')}`);
        reasons.push(`URL matches regex patterns: ${matches.join(', ')}`);
      } else {
        reasons.push(`URL doesn't match expected regex patterns: ${criteria.url_regex.join(', ')}`);
      }
    }

    // Title checks
    if (criteria.title_includes) {
      total++;
      const matches = criteria.title_includes.filter(fragment =>
        context.title.toLowerCase().includes(fragment.toLowerCase())
      );
      if (matches.length > 0) {
        score++;
        matched_criteria.push(`title_includes: ${matches.join(', ')}`);
        reasons.push(`Title contains expected text: ${matches.join(', ')}`);
      } else {
        reasons.push(`Title missing expected text: ${criteria.title_includes.join(', ')}`);
      }
    }

    // Element existence checks
    if (criteria.must_exist) {
      total++;
      const allLabels = context.elements.map(el => el.label.toLowerCase());
      const foundElements = criteria.must_exist.filter(required =>
        allLabels.some(label => label.includes(required.toLowerCase()))
      );
      if (foundElements.length === criteria.must_exist.length) {
        score++;
        matched_criteria.push(`must_exist: ${foundElements.join(', ')}`);
        reasons.push(`All required elements found: ${foundElements.join(', ')}`);
      } else {
        const missing = criteria.must_exist.filter(req =>
          !allLabels.some(label => label.includes(req.toLowerCase()))
        );
        reasons.push(`Missing required elements: ${missing.join(', ')}`);
      }
    }

    if (criteria.must_not_exist) {
      total++;
      const allLabels = context.elements.map(el => el.label.toLowerCase());
      const foundForbidden = criteria.must_not_exist.filter(forbidden =>
        allLabels.some(label => label.includes(forbidden.toLowerCase()))
      );
      if (foundForbidden.length === 0) {
        score++;
        matched_criteria.push(`must_not_exist: verified absent`);
        reasons.push(`No forbidden elements found`);
      } else {
        reasons.push(`Found forbidden elements: ${foundForbidden.join(', ')}`);
      }
    }

    // Text content checks
    if (criteria.text_includes) {
      total++;
      const allText = context.elements.map(el => el.label).join(' ').toLowerCase();
      const foundText = criteria.text_includes.filter(text =>
        allText.includes(text.toLowerCase())
      );
      if (foundText.length > 0) {
        score++;
        matched_criteria.push(`text_includes: ${foundText.join(', ')}`);
        reasons.push(`Found expected text: ${foundText.join(', ')}`);
      } else {
        reasons.push(`Missing expected text: ${criteria.text_includes.join(', ')}`);
      }
    }

    // Navigation events (bonus points)
    if (runtime.nav_events.length > 0) {
      matched_criteria.push(`navigation_events: ${runtime.nav_events.length}`);
      reasons.push(`Navigation events detected: ${runtime.nav_events.length}`);
    }

    // Determine status
    let status: "success" | "failure" | "uncertain";

    if (total === 0) {
      status = "uncertain";
      reasons.push("No validation criteria provided");
    } else {
      const successRate = score / total;
      if (successRate >= 0.8) {
        status = "success";
      } else if (successRate >= 0.4) {
        status = "uncertain";
      } else {
        status = "failure";
      }
    }

    return {
      status,
      reasons,
      matched_criteria
    };
  }

  // LLM validation for uncertain cases
  private async callLLMValidator(report: ExecutionReport): Promise<ValidationVerdict> {
    // Prepare data for LLM
    const llmInput = {
      plan_step: report.plan_step,
      execution_report: {
        ...report,
        // Trim elements to first 30 for cost optimization
        pre_context: {
          ...report.pre_context,
          elements: report.pre_context.elements.slice(0, 30)
        },
        post_context: {
          ...report.post_context,
          elements: report.post_context.elements.slice(0, 30)
        }
      }
    };

    try {
      // This would call your LLM service
      // For now, return a simplified verdict
      const mockVerdict: ValidationVerdict = {
        status: "uncertain",
        confidence: 0.5,
        reasoning: ["LLM validation not yet implemented"],
        recommended_next_steps: [
          { action: "proceed", notes: "Continue with next step" }
        ]
      };

      return mockVerdict;

    } catch (error) {
      return {
        status: "failure",
        confidence: 0.1,
        reasoning: [`LLM validation failed: ${error}`],
        recommended_next_steps: [
          { action: "retry", notes: "Retry the current step" }
        ]
      };
    }
  }

  // Utility methods
  private generateId(): string {
    return Date.now().toString(36) + Math.random().toString(36).substr(2);
  }

  private getRecentNavEvents(since: number) {
    return this.navEventLog.filter(event => event.time >= since);
  }

  // Decision making based on validation results
  public decideNext(report: ExecutionReport): { do: string; reason: string } {
    const validation = report.llm_validation || report.local_validation;

    switch (validation.status) {
      case "success":
        return { do: "next", reason: "Step completed successfully" };

      case "failure":
        return { do: "repair_or_abort", reason: "Step failed validation" };

      case "uncertain":
        return { do: "probe", reason: "Validation uncertain, need more investigation" };

      default:
        return { do: "abort", reason: "Unknown validation status" };
    }
  }
}

// Export factory function for easy usage
export function createPAVController(): PAVController {
  return new PAVController();
}