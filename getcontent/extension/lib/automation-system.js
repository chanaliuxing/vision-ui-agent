/**
 * 统一自动化系统入口
 * 集成所有4个阶段：DOM Reducer + MV3 + PAV + Recovery
 */

import { reduceDomPayload } from './reducer.js';
import { runStep, decideNext, callLLMValidator } from './pav-runner.js';
import { runStepWithRecovery, addToBlacklist, getBlacklistStats, cleanupBlacklist } from './recovery-system.js';
import { validateLocal, makeDiff, genId } from './validator.js';

/**
 * 自动化系统主类
 */
export class AutomationSystem {
  constructor(options = {}) {
    this.options = {
      maxElements: 50,
      dupIoU: 0.9,
      minTextLenSpan: 2,
      enableRecovery: true,
      enableBlacklist: true,
      maxRetries: 3,
      ...options
    };
    
    this.history = [];
    this.currentTaskId = null;
    this.currentPhase = null;
    
    // 定期清理黑名单
    setInterval(() => {
      cleanupBlacklist();
    }, 60 * 60 * 1000); // 每小时清理一次
  }
  
  /**
   * 获取当前页面的reduced DOM
   * @returns {Promise<import('./pav-types.js').ReducedDom>}
   */
  async getCurrentDOM() {
    try {
      const rawPayload = await chrome.runtime.sendMessage({ type: 'EXT_EXTRACT' });
      if (!rawPayload) {
        throw new Error('Failed to extract DOM');
      }
      
      return reduceDomPayload(rawPayload, {
        maxElements: this.options.maxElements,
        dupIoU: this.options.dupIoU,
        minTextLenSpan: this.options.minTextLenSpan
      });
    } catch (error) {
      console.error('[AUTO-SYS] DOM extraction failed:', error);
      throw error;
    }
  }
  
  /**
   * 执行单个计划步骤
   * @param {import('./pav-types.js').PlanStep} planStep
   * @param {Object} options
   * @returns {Promise<Object>}
   */
  async executePlanStep(planStep, options = {}) {
    const { useRecovery = this.options.enableRecovery } = options;
    
    console.log(`[AUTO-SYS] Executing step: ${planStep.goal}`);
    
    // 设置当前上下文
    this.currentTaskId = planStep.task_id;
    this.currentPhase = { task_id: planStep.task_id, phase_id: `step_${planStep.step_no}` };
    
    let result;
    
    if (useRecovery) {
      // 使用恢复机制
      result = await runStepWithRecovery(planStep, this.currentPhase);
    } else {
      // 使用基本PAV执行
      const initialContext = await this.getCurrentDOM();
      const report = await runStep(planStep, initialContext);
      const decision = decideNext(report);
      
      result = {
        ok: decision.do === 'next',
        report,
        decision,
        final_status: report.local_validation.status
      };
    }
    
    // 记录历史
    this.history.push({
      step_no: planStep.step_no,
      goal: planStep.goal,
      action: planStep.action,
      result: result.ok,
      timestamp: Date.now(),
      details: result
    });
    
    return result;
  }
  
  /**
   * 执行完整的任务计划
   * @param {import('./pav-types.js').PlanStep[]} planSteps
   * @param {Object} options
   * @returns {Promise<Object>}
   */
  async executeTaskPlan(planSteps, options = {}) {
    const {
      stopOnFailure = true,
      maxRetries = this.options.maxRetries,
      useRecovery = this.options.enableRecovery
    } = options;
    
    console.log(`[AUTO-SYS] Starting task execution: ${planSteps.length} steps`);
    
    const results = [];
    let currentStep = 0;
    let retryCount = 0;
    
    while (currentStep < planSteps.length) {
      const planStep = planSteps[currentStep];
      
      try {
        const result = await this.executePlanStep(planStep, { useRecovery });
        results.push(result);
        
        if (result.ok) {
          console.log(`[AUTO-SYS] Step ${currentStep + 1} succeeded`);
          currentStep++;
          retryCount = 0; // 重置重试计数
        } else {
          console.warn(`[AUTO-SYS] Step ${currentStep + 1} failed:`, result.error || result.decision?.reason);
          
          if (retryCount < maxRetries) {
            retryCount++;
            console.log(`[AUTO-SYS] Retrying step ${currentStep + 1} (attempt ${retryCount}/${maxRetries})`);
            // 等待一段时间再重试
            await new Promise(resolve => setTimeout(resolve, 2000));
            continue;
          }
          
          if (stopOnFailure) {
            console.error(`[AUTO-SYS] Task execution stopped at step ${currentStep + 1}`);
            break;
          } else {
            console.warn(`[AUTO-SYS] Skipping failed step ${currentStep + 1}`);
            currentStep++;
            retryCount = 0;
          }
        }
      } catch (error) {
        console.error(`[AUTO-SYS] Step ${currentStep + 1} threw exception:`, error);
        results.push({ ok: false, error: error.message });
        
        if (stopOnFailure) break;
        currentStep++;
      }
    }
    
    const successful = results.filter(r => r.ok).length;
    const total = results.length;
    
    console.log(`[AUTO-SYS] Task execution completed: ${successful}/${total} steps succeeded`);
    
    return {
      success: successful === planSteps.length,
      completed_steps: successful,
      total_steps: planSteps.length,
      results,
      execution_summary: this.getExecutionSummary()
    };
  }
  
  /**
   * 创建简单的计划步骤
   * @param {string} goal
   * @param {string} action
   * @param {Object} target
   * @param {Object} successCriteria
   * @param {string} inputText
   * @returns {import('./pav-types.js').PlanStep}
   */
  createPlanStep(goal, action, target, successCriteria = {}, inputText = '') {
    return {
      task_id: this.currentTaskId || `task_${Date.now()}`,
      step_no: this.history.length + 1,
      goal,
      action,
      target,
      success_criteria: successCriteria,
      input_text: inputText
    };
  }
  
  /**
   * 获取执行摘要
   * @returns {Object}
   */
  getExecutionSummary() {
    const total = this.history.length;
    const successful = this.history.filter(h => h.result).length;
    const failed = total - successful;
    
    return {
      total_steps: total,
      successful_steps: successful,
      failed_steps: failed,
      success_rate: total > 0 ? (successful / total * 100).toFixed(1) + '%' : '0%',
      blacklist_stats: getBlacklistStats(),
      recent_history: this.history.slice(-5) // 最近5步
    };
  }
  
  /**
   * 重置系统状态
   */
  reset() {
    this.history = [];
    this.currentTaskId = null;
    this.currentPhase = null;
    console.log('[AUTO-SYS] System reset');
  }
  
  /**
   * 获取系统状态
   * @returns {Object}
   */
  getStatus() {
    return {
      ready: true,
      current_task: this.currentTaskId,
      current_phase: this.currentPhase,
      options: this.options,
      execution_summary: this.getExecutionSummary()
    };
  }
}

// 创建全局实例
const automationSystem = new AutomationSystem();

// 导出供外部使用
export default automationSystem;

// 为了方便在控制台调试
if (typeof window !== 'undefined') {
  window.automationSystem = automationSystem;
  window.AutomationSystem = AutomationSystem;
}

/**
 * 预定义的测试用例
 */
export const testCases = {
  /**
   * 搜索测试
   */
  searchTest: [
    {
      goal: '点击搜索输入框',
      action: 'click',
      target: { by: 'text', value: '搜索', fallback: [{ by: 'text', value: 'search' }] },
      success_criteria: {
        must_exist: ['输入框', 'search'],
        timeout_ms: 5000
      }
    },
    {
      goal: '输入搜索关键词',
      action: 'type',
      target: { by: 'text', value: '搜索' },
      input_text: '海边穿搭',
      success_criteria: {
        text_includes: ['海边穿搭'],
        timeout_ms: 3000
      }
    },
    {
      goal: '提交搜索',
      action: 'click',
      target: { by: 'text', value: '搜索', fallback: [{ by: 'text', value: '确认' }] },
      success_criteria: {
        url_contains: ['search', '搜索'],
        must_exist: ['结果', 'result'],
        timeout_ms: 10000
      }
    }
  ],
  
  /**
   * 导航测试
   */
  navigationTest: [
    {
      goal: '点击首页链接',
      action: 'click',
      target: { by: 'text', value: '首页', fallback: [{ by: 'text', value: 'home' }] },
      success_criteria: {
        url_contains: ['home', 'index', '/'],
        title_includes: ['首页', 'Home'],
        timeout_ms: 8000
      }
    }
  ]
};

console.log('[AUTO-SYS] Automation system initialized');
console.log('[AUTO-SYS] Available test cases:', Object.keys(testCases));
console.log('[AUTO-SYS] Access via window.automationSystem or window.AutomationSystem');