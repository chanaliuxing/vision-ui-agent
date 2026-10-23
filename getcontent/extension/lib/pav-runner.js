/**
 * PAV (Plan → Act → Validate) 主执行器
 * 站点无关的通用执行系统
 */

import { validateLocal, makeDiff, genId } from './validator.js';
import { reduceDomPayload } from './reducer.js';

/**
 * 解析目标元素
 * @param {import('./pav-types.js').PlanStep['target']} target
 * @param {import('./pav-types.js').ReducedDom} context
 * @returns {Object} 解析后的目标
 */
function resolveTarget(target, context) {
  const { by, value, fallback = [] } = target;
  
  // 尝试主要目标
  const candidates = [{ by, value }, ...fallback];
  
  for (const candidate of candidates) {
    let element = null;
    let index = -1;
    
    switch (candidate.by) {
      case 'index':
        index = typeof candidate.value === 'number' ? candidate.value : parseInt(candidate.value);
        if (index >= 0 && index < context.elements.length) {
          element = context.elements[index];
        }
        break;
        
      case 'text':
        index = context.index[String(candidate.value).toLowerCase()];
        if (index !== undefined && index >= 0) {
          element = context.elements[index];
        } else {
          // 模糊匹配
          for (let i = 0; i < context.elements.length; i++) {
            if (context.elements[i].label.toLowerCase().includes(String(candidate.value).toLowerCase())) {
              element = context.elements[i];
              index = i;
              break;
            }
          }
        }
        break;
        
      case 'href':
        for (let i = 0; i < context.elements.length; i++) {
          if (context.elements[i].href && context.elements[i].href.includes(String(candidate.value))) {
            element = context.elements[i];
            index = i;
            break;
          }
        }
        break;
        
      case 'id':
        for (let i = 0; i < context.elements.length; i++) {
          if (context.elements[i].id === String(candidate.value)) {
            element = context.elements[i];
            index = i;
            break;
          }
        }
        break;
    }
    
    if (element) {
      return {
        by: candidate.by,
        value: candidate.value,
        label: element.label,
        element,
        index
      };
    }
  }
  
  throw new Error(`Target not found: ${JSON.stringify(target)}`);
}

/**
 * 执行动作并观察
 * @param {Object} targetResolved - 解析后的目标
 * @param {import('./pav-types.js').PlanStep} planStep
 * @param {Object} options - 选项
 * @returns {Promise<import('./pav-types.js').StepRuntime>}
 */
async function performActionAndObserve(targetResolved, planStep, options = {}) {
  const { timeout = 8000 } = options;
  const tsStart = Date.now();
  const navEvents = [];
  
  // 监听导航事件
  const navListener = (details) => {
    navEvents.push({
      type: details.transitionType || 'committed',
      url: details.url,
      time: Date.now()
    });
  };
  
  chrome.webNavigation.onCommitted.addListener(navListener);
  chrome.webNavigation.onCompleted.addListener(navListener);
  
  try {
    // 发送动作到content script
    let result;
    switch (planStep.action) {
      case 'click':
        result = await chrome.runtime.sendMessage({
          type: 'EXT_CLICK_INDEX',
          index: targetResolved.index
        });
        break;
        
      case 'type':
        result = await chrome.runtime.sendMessage({
          type: 'EXT_TYPE_INDEX',
          index: targetResolved.index,
          text: planStep.input_text || ''
        });
        break;
        
      case 'select':
        result = await chrome.runtime.sendMessage({
          type: 'EXT_SELECT_INDEX',
          index: targetResolved.index,
          value: planStep.input_text || ''
        });
        break;
        
      case 'navigate':
        if (targetResolved.element.href) {
          result = await chrome.runtime.sendMessage({
            type: 'EXT_NAVIGATE',
            url: targetResolved.element.href
          });
        } else {
          throw new Error('Cannot navigate: no href in target element');
        }
        break;
        
      default:
        throw new Error(`Unknown action: ${planStep.action}`);
    }
    
    // 等待页面稳定
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    const tsEnd = Date.now();
    
    return {
      ts_start: tsStart,
      ts_end: tsEnd,
      duration_ms: tsEnd - tsStart,
      nav_events: navEvents,
      net_requests: 0, // TODO: 通过CDP统计网络请求
      error: result?.ok === false ? result.error : undefined
    };
    
  } finally {
    chrome.webNavigation.onCommitted.removeListener(navListener);
    chrome.webNavigation.onCompleted.removeListener(navListener);
  }
}

/**
 * 获取当前页面的reduced DOM
 * @returns {Promise<import('./pav-types.js').ReducedDom>}
 */
async function getReducedDom() {
  // 首先获取原始DOM
  const rawPayload = await chrome.runtime.sendMessage({ type: 'EXT_EXTRACT' });
  
  // 通过reducer处理
  const reduced = reduceDomPayload(rawPayload, {
    maxElements: 50,
    dupIoU: 0.9,
    minTextLenSpan: 2
  });
  
  return reduced;
}

/**
 * 运行单个步骤
 * @param {import('./pav-types.js').PlanStep} planStep
 * @param {import('./pav-types.js').ReducedDom} ctxBefore - 执行前上下文
 * @returns {Promise<import('./pav-types.js').ExecutionReport>}
 */
export async function runStep(planStep, ctxBefore) {
  console.log('[PAV] Running step:', planStep.goal);
  
  // 1) 解析目标
  const targetResolved = resolveTarget(planStep.target, ctxBefore);
  console.log('[PAV] Target resolved:', targetResolved);
  
  // 2) 执行动作并观察
  const runtime = await performActionAndObserve(targetResolved, planStep, {
    timeout: planStep.success_criteria?.timeout_ms || 8000
  });
  
  // 3) 获取执行后DOM
  const ctxAfter = await getReducedDom();
  
  // 4) 计算差异
  const diff = makeDiff(ctxBefore, ctxAfter);
  
  // 5) 本地校验
  const localValidation = validateLocal(planStep.success_criteria, ctxAfter, diff, runtime);
  
  // 6) 组装报告
  const report = {
    exec_id: genId(),
    task_id: planStep.task_id,
    step_no: planStep.step_no,
    goal: planStep.goal,
    plan_step: planStep,
    history: [], // TODO: 维护历史记录
    pre_context: ctxBefore,
    action_sent: {
      action: planStep.action,
      target_resolved: targetResolved,
      input_text: planStep.input_text
    },
    runtime,
    post_context: ctxAfter,
    diff,
    local_validation: localValidation
  };
  
  console.log('[PAV] Step result:', localValidation.status, localValidation.reasons);
  return report;
}

/**
 * 决策下一步动作
 * @param {import('./pav-types.js').ExecutionReport} report
 * @returns {Object} 决策结果
 */
export function decideNext(report) {
  const { local_validation } = report;
  
  if (local_validation.status === 'success') {
    return { do: 'next', reason: 'Local validation succeeded' };
  }
  
  if (local_validation.status === 'failure') {
    return { do: 'repair_or_abort', reason: 'Local validation failed' };
  }
  
  // uncertain
  return { do: 'llm_validate', reason: 'Local validation uncertain, need LLM review' };
}

/**
 * 调用LLM进行验证
 * @param {import('./pav-types.js').ExecutionReport} report
 * @returns {Promise<import('./pav-types.js').ValidationVerdict>}
 */
export async function callLLMValidator(report) {
  // TODO: 集成到现有的LLM调用系统
  // 这里返回一个示例响应
  console.warn('[PAV] LLM validation not implemented yet, returning mock result');
  
  return {
    status: 'uncertain',
    confidence: 0.5,
    reasoning: ['LLM validation not implemented'],
    recommended_next_steps: [
      { action: 'retry', notes: 'Try the action again' }
    ]
  };
}