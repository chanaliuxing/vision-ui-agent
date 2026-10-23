/**
 * PAV系统测试工具
 * 提供简单的测试接口来验证PAV回路
 */

import { runStep, decideNext, callLLMValidator } from './pav-runner.js';
import { reduceDomPayload } from './reducer.js';

/**
 * 创建测试计划步骤
 * @param {string} goal - 目标描述
 * @param {string} action - 动作类型
 * @param {Object} target - 目标选择器
 * @param {Object} successCriteria - 成功条件
 * @returns {import('./pav-types.js').PlanStep}
 */
export function createTestStep(goal, action, target, successCriteria = {}) {
  return {
    task_id: 'test_task_' + Date.now(),
    step_no: 1,
    goal,
    action,
    target,
    success_criteria: successCriteria,
    input_text: target.input_text
  };
}

/**
 * 运行PAV测试
 * @param {import('./pav-types.js').PlanStep} planStep
 */
export async function runPAVTest(planStep) {
  console.log('[PAV-TEST] Starting PAV test for:', planStep.goal);
  
  try {
    // 1. Plan阶段 - 获取当前DOM上下文
    console.log('[PAV-TEST] Phase 1: Plan - Getting initial context');
    const rawPayload = await chrome.runtime.sendMessage({ type: 'EXT_EXTRACT' });
    const initialContext = reduceDomPayload(rawPayload, {
      maxElements: 50,
      dupIoU: 0.9,
      minTextLenSpan: 2
    });
    console.log('[PAV-TEST] Initial context:', initialContext);
    
    // 2. Act阶段 - 执行步骤
    console.log('[PAV-TEST] Phase 2: Act - Executing step');
    const report = await runStep(planStep, initialContext);
    console.log('[PAV-TEST] Execution report:', report);
    
    // 3. Validate阶段 - 决策下一步
    console.log('[PAV-TEST] Phase 3: Validate - Making decision');
    const decision = decideNext(report);
    console.log('[PAV-TEST] Decision:', decision);
    
    // 如果需要LLM验证
    if (decision.do === 'llm_validate') {
      console.log('[PAV-TEST] Calling LLM for validation');
      const llmVerdict = await callLLMValidator(report);
      console.log('[PAV-TEST] LLM verdict:', llmVerdict);
      
      return {
        success: true,
        report,
        decision,
        llm_verdict: llmVerdict,
        final_status: llmVerdict.status
      };
    }
    
    return {
      success: decision.do === 'next',
      report,
      decision,
      final_status: report.local_validation.status
    };
    
  } catch (error) {
    console.error('[PAV-TEST] Test failed:', error);
    return {
      success: false,
      error: error.message,
      report: null,
      decision: null
    };
  }
}

/**
 * 运行预定义的测试用例
 */
export async function runBuiltinTests() {
  console.log('[PAV-TEST] Running builtin PAV tests');
  
  const tests = [
    {
      name: 'Click search input',
      step: createTestStep(
        '点击搜索输入框',
        'click',
        { by: 'text', value: '搜索' },
        {
          must_exist: ['输入框', 'search'],
          timeout_ms: 5000
        }
      )
    },
    {
      name: 'Navigate to link',
      step: createTestStep(
        '点击导航链接',
        'click',
        { by: 'text', value: '首页', fallback: [{ by: 'text', value: 'home' }] },
        {
          url_contains: ['home', 'index'],
          title_includes: ['首页', 'Home'],
          timeout_ms: 10000
        }
      )
    }
  ];
  
  const results = [];
  
  for (const test of tests) {
    console.log(`[PAV-TEST] Running test: ${test.name}`);
    const result = await runPAVTest(test.step);
    results.push({
      name: test.name,
      ...result
    });
    
    // 等待一下避免过快执行
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  
  console.log('[PAV-TEST] All tests completed:', results);
  return results;
}

/**
 * 从content script调用的简化接口
 */
window.pavTest = {
  createStep: createTestStep,
  runTest: runPAVTest,
  runBuiltinTests
};