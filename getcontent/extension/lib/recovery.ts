// Recovery System Implementation
// Implements Phase 4 of the DOM reduction plan: rollback, blacklist, retry logic
// Enhanced to work with existing Python backend blacklist system

import { PlanStep, ReducedDom, ExecutionReport, ValidationVerdict } from './pav.js';

// Phase 4 data structures
export type BBox = [number, number, number, number];

export interface TargetSig {
  role: string;
  label?: string;
  href?: string;
  id?: string;
  bbox?: BBox;
}

export interface PageSig {
  host: string;
  urlPathHash: string;
  domHash: string;
}

export interface PhaseKey {
  task_id: string;
  phase_id: string;
}

export interface BlacklistEntry {
  phase: PhaseKey;
  page: PageSig;
  target: TargetSig;
  reason: "validation_fail" | "llm_miss" | "user_abort";
  ts: number;
  ttl_ms: number;
  hits: number;
  max_hits: number;
}

export interface RecoveryResult {
  ok: boolean;
  action: "next" | "retry_phase" | "abort" | "manual_intervention";
  report?: ExecutionReport;
  recovery_log: string[];
}

// Enhanced recovery system with Python backend integration
export class RecoveryController {
  private blacklist: Map<string, BlacklistEntry> = new Map();
  private rollbackUrls: string[] = [];
  private maxAttempts = 3;
  private currentAttempts = 0;
  private pythonBackendUrl: string;

  constructor(pythonBackendUrl = "http://127.0.0.1:8000") {
    this.pythonBackendUrl = pythonBackendUrl;
    this.loadBlacklist();
    this.syncWithPythonBackend();
  }

  // Main recovery method called when PAV step fails
  async runStepWithRecovery(
    planStep: PlanStep,
    phase: PhaseKey,
    pavController: any // PAVController instance
  ): Promise<RecoveryResult> {
    const recovery_log: string[] = [];
    this.currentAttempts++;

    try {
      // 1) Get pre-execution context
      const pre = await this.getReducedDom();
      this.rollbackUrls.push(pre.url);
      recovery_log.push(`[${new Date().toISOString()}] Starting step ${planStep.step_no}: ${planStep.goal}`);

      // 2) Resolve target avoiding blacklist
      const target = this.resolveTarget(planStep, pre, phase);
      if (!target) {
        recovery_log.push(`All candidates blacklisted for phase ${phase.task_id}:${phase.phase_id}`);
        return {
          ok: false,
          action: "abort",
          recovery_log: [...recovery_log, "No valid targets remain after blacklist filtering"]
        };
      }

      // 3) Execute action via PAV
      const report = await pavController.runStep(planStep);
      recovery_log.push(`Executed ${planStep.action} on target: ${target.label || target.value}`);

      // 4) Check PAV validation results
      const validation = report.llm_validation || report.local_validation;

      if (validation.status === "success") {
        recovery_log.push(`Step ${planStep.step_no} completed successfully`);
        this.currentAttempts = 0; // Reset counter on success
        return { ok: true, action: "next", report, recovery_log };
      }

      // 5) YOLO+LLM intervention for failures
      recovery_log.push(`Local validation failed: ${validation.reasons.join(', ')}`);
      const intervention = await this.interveneWithYOLOLLM(planStep, report, phase);

      if (intervention.status === "success") {
        recovery_log.push(`YOLO+LLM intervention succeeded`);
        this.currentAttempts = 0;
        return { ok: true, action: "next", report, recovery_log };
      }

      // 6) Still failed - initiate recovery sequence
      recovery_log.push(`YOLO+LLM intervention failed: ${intervention.reasoning.join(', ')}`);

      if (this.currentAttempts >= this.maxAttempts) {
        recovery_log.push(`Max attempts (${this.maxAttempts}) reached for current phase`);
        return {
          ok: false,
          action: "manual_intervention",
          report,
          recovery_log: [...recovery_log, "Manual intervention required"]
        };
      }

      // 7) Rollback and blacklist
      await this.rollbackToPrevious(recovery_log);
      await this.waitQuiet({ timeout: 10000, poll: 300 }, recovery_log);

      this.addToBlacklist(phase, this.pageSignature(pre), this.targetSignature(target), {
        reason: "validation_fail",
        ttl_ms: 7 * 24 * 3600 * 1000, // 7 days
        max_hits: 3
      });
      recovery_log.push(`Blacklisted target: ${target.label || target.value}`);

      // 8) Continue with retry
      recovery_log.push(`Retrying phase ${phase.phase_id} (attempt ${this.currentAttempts}/${this.maxAttempts})`);
      return { ok: false, action: "retry_phase", report, recovery_log };

    } catch (error) {
      recovery_log.push(`Recovery error: ${error instanceof Error ? error.message : String(error)}`);
      return {
        ok: false,
        action: "abort",
        recovery_log: [...recovery_log, "Recovery system encountered fatal error"]
      };
    }
  }

  // Resolve target avoiding blacklisted entries
  private resolveTarget(planStep: PlanStep, ctx: ReducedDom, phase: PhaseKey): any {
    const candidates = this.enumerateCandidates(planStep, ctx);
    const page = this.pageSignature(ctx);

    const filtered = candidates.filter(c =>
      !this.isBlacklisted(phase, page, this.targetSignature(c))
    );

    if (filtered.length === 0) {
      return null;
    }

    // Return the best candidate (first in priority order)
    return filtered[0];
  }

  private enumerateCandidates(planStep: PlanStep, ctx: ReducedDom): any[] {
    const candidates = [];

    // Primary target
    const primary = this.findTarget(planStep.target, ctx);
    if (primary) candidates.push(primary);

    // Fallback targets
    if (planStep.target.fallback) {
      for (const fb of planStep.target.fallback) {
        const fallback = this.findTarget(fb, ctx);
        if (fallback) candidates.push(fallback);
      }
    }

    return candidates;
  }

  private findTarget(target: any, ctx: ReducedDom): any {
    switch (target.by) {
      case "index":
        const idx = Number(target.value);
        return idx >= 0 && idx < ctx.elements.length ? ctx.elements[idx] : null;

      case "text":
        return ctx.elements.find(el =>
          el.label?.toLowerCase().includes(String(target.value).toLowerCase())
        );

      case "href":
        return ctx.elements.find(el =>
          el.href?.includes(String(target.value))
        );

      case "id":
        return ctx.elements.find(el => el.id === String(target.value));

      default:
        return null;
    }
  }

  // YOLO+LLM intervention for failed validations
  private async interveneWithYOLOLLM(
    planStep: PlanStep,
    report: ExecutionReport,
    phase: PhaseKey
  ): Promise<ValidationVerdict> {
    try {
      // 1) Call LLM validator to re-assess the situation
      const llmVerdict = await this.callLLMValidator(report);

      if (llmVerdict.status === "success") {
        return llmVerdict;
      }

      // 2) Look for alternative targets suggested by LLM
      const altTargets = llmVerdict.recommended_next_steps.filter(step =>
        step.action === "alt_target" && step.alt_target
      );

      for (const alt of altTargets) {
        if (!alt.alt_target) continue;

        // Try to find and execute alternative target
        const probe = await this.findWithYOLOOrHeuristic(
          alt.alt_target,
          await this.getScreenshot(),
          await this.getReducedDom()
        );

        if (probe) {
          // Execute action on alternative target
          await this.performActionOnTarget(probe, planStep);

          // Wait and re-validate
          await this.waitQuiet({ timeout: 5000, poll: 300 });
          const postContext = await this.getReducedDom();

          // Check if alternative action succeeded
          const altValidation = this.validateAlternative(planStep, postContext);
          if (altValidation.status === "success") {
            return altValidation;
          }
        }
      }

      return {
        status: "failure",
        confidence: 0.2,
        reasoning: ["LLM/YOLO intervention failed to find working alternative"],
        recommended_next_steps: [{ action: "back", notes: "Rollback required" }]
      };

    } catch (error) {
      return {
        status: "failure",
        confidence: 0.1,
        reasoning: [`YOLO+LLM intervention error: ${error}`],
        recommended_next_steps: [{ action: "abort", notes: "Intervention system failed" }]
      };
    }
  }

  // Rollback strategies in priority order
  private async rollbackToPrevious(recovery_log: string[]): Promise<void> {
    try {
      // 1) Check for modal/dialog overlays first
      if (await this.dismissModalOrDialog()) {
        recovery_log.push("Dismissed modal/dialog overlay");
        return;
      }

      // 2) Look for explicit back/return buttons
      if (await this.clickBackButton()) {
        recovery_log.push("Clicked back/return button");
        return;
      }

      // 3) Use browser history back
      if (await this.browserHistoryBack()) {
        recovery_log.push("Used browser history.back()");
        return;
      }

      // 4) Force navigation to previous URL
      if (this.rollbackUrls.length > 1) {
        const prevUrl = this.rollbackUrls[this.rollbackUrls.length - 2];
        window.location.assign(prevUrl);
        recovery_log.push(`Force navigated to: ${prevUrl}`);
        return;
      }

      recovery_log.push("No rollback method available");

    } catch (error) {
      recovery_log.push(`Rollback error: ${error}`);
    }
  }

  private async dismissModalOrDialog(): Promise<boolean> {
    try {
      // Look for common modal/dialog patterns
      const modals = document.querySelectorAll('.modal, .dialog, [role="dialog"], .popup');

      for (const modal of modals) {
        // Try to find close button
        const closeBtn = modal.querySelector('.close, [aria-label*="close"], .modal-close, .x');
        if (closeBtn && closeBtn instanceof HTMLElement) {
          closeBtn.click();
          await new Promise(resolve => setTimeout(resolve, 1000));
          return true;
        }
      }

      // Try ESC key
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', keyCode: 27 }));
      await new Promise(resolve => setTimeout(resolve, 500));

      return false;
    } catch {
      return false;
    }
  }

  private async clickBackButton(): Promise<boolean> {
    try {
      const backSelectors = [
        'button:contains("返回")',
        'button:contains("Back")',
        'a:contains("返回")',
        'a:contains("Back")',
        '[aria-label*="back"]',
        '.back-btn',
        '.return-btn'
      ];

      for (const selector of backSelectors) {
        const elements = document.querySelectorAll(selector);
        for (const el of elements) {
          if (el instanceof HTMLElement && el.offsetParent !== null) {
            el.click();
            await new Promise(resolve => setTimeout(resolve, 2000));
            return true;
          }
        }
      }

      return false;
    } catch {
      return false;
    }
  }

  private async browserHistoryBack(): Promise<boolean> {
    try {
      history.back();
      await new Promise(resolve => setTimeout(resolve, 2000));
      return true;
    } catch {
      return false;
    }
  }

  // Wait for page stability after rollback
  private async waitQuiet(
    options: { timeout: number; poll: number },
    recovery_log: string[]
  ): Promise<void> {
    const start = Date.now();
    recovery_log.push(`Waiting for page stability (${options.timeout}ms timeout)`);

    return new Promise((resolve) => {
      const check = () => {
        if (Date.now() - start > options.timeout) {
          recovery_log.push("Wait timeout reached");
          resolve();
          return;
        }

        if (document.readyState === 'complete') {
          recovery_log.push("Page stability achieved");
          resolve();
        } else {
          setTimeout(check, options.poll);
        }
      };

      check();
    });
  }

  // Blacklist management
  private addToBlacklist(
    phase: PhaseKey,
    page: PageSig,
    target: TargetSig,
    meta: Partial<BlacklistEntry>
  ): void {
    const key = this.getBlacklistKey(phase, page, target);
    const existing = this.blacklist.get(key);

    const entry: BlacklistEntry = {
      phase,
      page,
      target,
      reason: meta.reason || "validation_fail",
      ts: Date.now(),
      ttl_ms: meta.ttl_ms || 7 * 24 * 3600 * 1000,
      hits: existing ? existing.hits + 1 : 1,
      max_hits: meta.max_hits || 3
    };

    this.blacklist.set(key, entry);
    this.saveBlacklist();
  }

  private isBlacklisted(phase: PhaseKey, page: PageSig, target: TargetSig): boolean {
    const key = this.getBlacklistKey(phase, page, target);
    const entry = this.blacklist.get(key);

    if (!entry) return false;

    // Check TTL
    if (Date.now() - entry.ts > entry.ttl_ms) {
      this.blacklist.delete(key);
      this.saveBlacklist();
      return false;
    }

    // Check hit count
    if (entry.hits >= entry.max_hits) {
      return true; // Permanently blacklisted
    }

    return entry.hits > 0;
  }

  private getBlacklistKey(phase: PhaseKey, page: PageSig, target: TargetSig): string {
    return `${phase.task_id}:${phase.phase_id}:${page.domHash}:${this.hashTarget(target)}`;
  }

  // Signature generation for page and target fingerprinting
  private pageSignature(ctx: ReducedDom): PageSig {
    const url = new URL(ctx.url);
    const urlPathHash = this.hashString(url.pathname + url.search);

    // Create DOM hash from first 10 elements
    const domFingerprint = ctx.elements.slice(0, 10)
      .map(el => `${el.role}:${el.label}:${el.href || ''}`)
      .join('|');
    const domHash = this.hashString(domFingerprint);

    return {
      host: url.host,
      urlPathHash,
      domHash
    };
  }

  private targetSignature(target: any): TargetSig {
    return {
      role: target.role || "",
      label: target.label,
      href: target.href,
      id: target.id,
      bbox: target.bbox
    };
  }

  private hashTarget(target: TargetSig): string {
    const parts = [
      target.role,
      target.label || "",
      target.href || "",
      target.id || "",
      target.bbox ? target.bbox.join(',') : ""
    ];
    return this.hashString(parts.join(':'));
  }

  private hashString(str: string): string {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    return Math.abs(hash).toString(36);
  }

  // Persistent blacklist storage
  private loadBlacklist(): void {
    try {
      const stored = localStorage.getItem('recovery_blacklist');
      if (stored) {
        const entries = JSON.parse(stored) as BlacklistEntry[];
        this.blacklist.clear();

        for (const entry of entries) {
          const key = this.getBlacklistKey(entry.phase, entry.page, entry.target);
          this.blacklist.set(key, entry);
        }
      }
    } catch (error) {
      console.warn('Failed to load blacklist:', error);
    }
  }

  private saveBlacklist(): void {
    try {
      const entries = Array.from(this.blacklist.values());
      localStorage.setItem('recovery_blacklist', JSON.stringify(entries));
    } catch (error) {
      console.warn('Failed to save blacklist:', error);
    }
  }

  // Utility methods for integration
  private async getReducedDom(): Promise<ReducedDom> {
    // Reuse implementation from PAV controller
    const response = await chrome.runtime.sendMessage({
      type: 'EXT_EXTRACT_RAW',
      args: { want: 'inputs', limit: 100 }
    });

    if (!response?.result) {
      throw new Error('Failed to get DOM snapshot');
    }

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

  private async getScreenshot(): Promise<string> {
    // Placeholder for screenshot functionality
    return "";
  }

  private async findWithYOLOOrHeuristic(
    altTarget: { by: string; value: string },
    screenshot: string,
    context: ReducedDom
  ): Promise<any> {
    // Simple heuristic matching for now
    return this.findTarget(altTarget, context);
  }

  private async performActionOnTarget(target: any, planStep: PlanStep): Promise<void> {
    // Reuse action performance from PAV controller
    if (target.center) {
      // Simulate click at target center
      const [x, y] = target.center;
      await chrome.runtime.sendMessage({
        type: 'SIM_CLICK',
        x,
        y
      });
    }
  }

  private validateAlternative(planStep: PlanStep, context: ReducedDom): ValidationVerdict {
    // Simple validation for alternative actions
    return {
      status: "uncertain",
      confidence: 0.6,
      reasoning: ["Alternative target executed, uncertain of success"],
      recommended_next_steps: [{ action: "proceed" }]
    };
  }

  private async callLLMValidator(report: ExecutionReport): Promise<ValidationVerdict> {
    // Placeholder - would integrate with actual LLM service
    return {
      status: "failure",
      confidence: 0.3,
      reasoning: ["LLM validation not implemented"],
      recommended_next_steps: [
        { action: "alt_target", alt_target: { by: "text", value: "retry" } }
      ]
    };
  }

  // Public API for clearing blacklist (manual intervention)
  public clearBlacklist(phase?: PhaseKey): void {
    if (phase) {
      // Clear specific phase
      const toDelete = Array.from(this.blacklist.keys()).filter(key =>
        key.startsWith(`${phase.task_id}:${phase.phase_id}:`)
      );
      toDelete.forEach(key => this.blacklist.delete(key));
    } else {
      // Clear all
      this.blacklist.clear();
    }
    this.saveBlacklist();
  }

  public getBlacklistStats(): { total: number; byPhase: Record<string, number> } {
    const stats = { total: this.blacklist.size, byPhase: {} as Record<string, number> };

    for (const entry of this.blacklist.values()) {
      const phaseKey = `${entry.phase.task_id}:${entry.phase.phase_id}`;
      stats.byPhase[phaseKey] = (stats.byPhase[phaseKey] || 0) + 1;
    }

    return stats;
  }

  // Python backend integration methods
  private async syncWithPythonBackend(): Promise<void> {
    try {
      // Sync blacklist with Python backend memory system
      const response = await fetch(`${this.pythonBackendUrl}/memory/blacklist`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
      });

      if (response.ok) {
        const pythonBlacklist = await response.json();
        this.mergePythonBlacklist(pythonBlacklist);
      }
    } catch (error) {
      console.warn('Failed to sync with Python backend blacklist:', error);
    }
  }

  private mergePythonBlacklist(pythonBlacklist: any[]): void {
    // Convert Python backend blacklist format to our format
    for (const item of pythonBlacklist) {
      if (item.type === 'element_blacklist') {
        const entry: BlacklistEntry = {
          phase: { task_id: item.task_id || 'unknown', phase_id: item.phase_id || 'unknown' },
          page: {
            host: item.url ? new URL(item.url).host : 'unknown',
            urlPathHash: this.hashString(item.url || ''),
            domHash: this.hashString(item.element_signature || '')
          },
          target: {
            role: item.element_type || 'unknown',
            label: item.element_text,
            bbox: item.bbox
          },
          reason: 'validation_fail',
          ts: item.timestamp || Date.now(),
          ttl_ms: 7 * 24 * 3600 * 1000,
          hits: item.hit_count || 1,
          max_hits: 3
        };

        const key = this.getBlacklistKey(entry.phase, entry.page, entry.target);
        this.blacklist.set(key, entry);
      }
    }
  }

  private async reportToPythonBackend(
    action: 'blacklist_add' | 'rollback' | 'retry',
    data: any
  ): Promise<void> {
    try {
      await fetch(`${this.pythonBackendUrl}/memory/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          data,
          timestamp: Date.now(),
          source: 'chrome_extension'
        })
      });
    } catch (error) {
      console.warn('Failed to report to Python backend:', error);
    }
  }

  // Enhanced blacklist methods with Python backend sync
  private addToBlacklistWithSync(
    phase: PhaseKey,
    page: PageSig,
    target: TargetSig,
    meta: Partial<BlacklistEntry>
  ): void {
    // Add to local blacklist
    this.addToBlacklist(phase, page, target, meta);

    // Report to Python backend
    this.reportToPythonBackend('blacklist_add', {
      phase,
      page,
      target,
      reason: meta.reason,
      url: `https://${page.host}`,
      element_type: target.role,
      element_text: target.label,
      bbox: target.bbox
    });
  }

  // Enhanced rollback with Python backend integration
  private async rollbackWithPythonBackend(recovery_log: string[]): Promise<void> {
    try {
      // Use existing rollback methods
      await this.rollbackToPrevious(recovery_log);

      // Report rollback to Python backend for learning
      await this.reportToPythonBackend('rollback', {
        url: window.location.href,
        method: 'browser_history_back',
        success: true
      });

    } catch (error) {
      recovery_log.push(`Rollback failed: ${error}`);

      // Report failed rollback
      await this.reportToPythonBackend('rollback', {
        url: window.location.href,
        method: 'browser_history_back',
        success: false,
        error: String(error)
      });
    }
  }

  // Enhanced recovery with Python backend coordination
  async runStepWithPythonBackendRecovery(
    planStep: PlanStep,
    phase: PhaseKey,
    pavController: any
  ): Promise<RecoveryResult> {
    const recovery_log: string[] = [];

    try {
      // 1) Check if Python backend suggests skipping this step
      const shouldSkip = await this.checkPythonBackendGuidance(planStep, phase);
      if (shouldSkip.skip) {
        recovery_log.push(`Python backend suggests skipping: ${shouldSkip.reason}`);
        return {
          ok: false,
          action: "retry_phase",
          recovery_log: [...recovery_log, "Skipped based on Python backend guidance"]
        };
      }

      // 2) Execute with existing recovery logic
      const result = await this.runStepWithRecovery(planStep, phase, pavController);

      // 3) Report results to Python backend
      await this.reportToPythonBackend('retry', {
        step_no: planStep.step_no,
        goal: planStep.goal,
        success: result.ok,
        action: result.action,
        recovery_log: result.recovery_log
      });

      return result;

    } catch (error) {
      recovery_log.push(`Python backend recovery failed: ${error}`);
      return {
        ok: false,
        action: "abort",
        recovery_log: [...recovery_log, "Python backend coordination failed"]
      };
    }
  }

  private async checkPythonBackendGuidance(
    planStep: PlanStep,
    phase: PhaseKey
  ): Promise<{ skip: boolean; reason?: string }> {
    try {
      const response = await fetch(`${this.pythonBackendUrl}/guidance/should_skip`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: phase.task_id,
          phase_id: phase.phase_id,
          step_no: planStep.step_no,
          goal: planStep.goal,
          url: window.location.href
        })
      });

      if (response.ok) {
        const guidance = await response.json();
        return {
          skip: guidance.should_skip || false,
          reason: guidance.reason
        };
      }

      return { skip: false };

    } catch (error) {
      console.warn('Failed to get Python backend guidance:', error);
      return { skip: false };
    }
  }
}

// Export factory function
export function createRecoveryController(): RecoveryController {
  return new RecoveryController();
}

// Unified PAV + Recovery system
export class UnifiedAutomationController {
  private pavController: any; // PAVController
  private recoveryController: RecoveryController;

  constructor(pavController: any) {
    this.pavController = pavController;
    this.recoveryController = new RecoveryController();
  }

  async executeStepWithRecovery(
    planStep: PlanStep,
    phase: PhaseKey
  ): Promise<RecoveryResult> {
    return this.recoveryController.runStepWithRecovery(
      planStep,
      phase,
      this.pavController
    );
  }

  public clearBlacklist(phase?: PhaseKey): void {
    this.recoveryController.clearBlacklist(phase);
  }

  public getBlacklistStats() {
    return this.recoveryController.getBlacklistStats();
  }
}