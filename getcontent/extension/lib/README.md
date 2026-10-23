# 统一自动化系统 - 完整实现

## 系统架构

本系统实现了dom_plan.md中描述的四个阶段的完整功能：

### 阶段1: 通用DOM Reducer (`reducer.js`)
- **功能**: 将原始DOM数据压缩为精简的、自动化友好的格式
- **特点**: 
  - 站点无关的通用过滤规则
  - 支持多语言噪声过滤
  - 智能去重和元素打分
  - 可配置的站点特定规则
- **输出**: 包含`_reduced: true`标记的精简JSON

### 阶段2: MV3 Service Worker集成 (`bootstrap.js` + `extract-bridge.js`)
- **功能**: 在Chrome Extension MV3架构中集成DOM reducer
- **特点**:
  - Service Worker中处理DOM reduction
  - Content Script桥接原始ext.extract
  - 支持调试和性能监控
  - 自动缓存最近的减少结果

### 阶段3: PAV回路 (`pav-runner.js` + `validator.js` + `pav-types.js`)
- **功能**: 实现Plan→Act→Validate的完整自动化回路
- **特点**:
  - 本地确定性校验优先
  - 按需LLM验证降低成本
  - 详细的执行报告和差异分析
  - 支持多种成功判定条件

### 阶段4: 失败恢复系统 (`recovery-system.js`)
- **功能**: 实现"失败→介入→回退→拉黑→继续"的闭环
- **特点**:
  - 智能黑名单机制避免重复错误
  - 多层回退策略（遮罩关闭→返回按钮→浏览器回退）
  - YOLO+LLM介入用于复杂场景
  - TTL和命中次数管理

## 统一入口 (`automation-system.js`)

提供完整的自动化系统接口，集成所有四个阶段：

```javascript
import automationSystem from './automation-system.js';

// 执行单个步骤
const planStep = automationSystem.createPlanStep(
  '点击搜索按钮',
  'click',
  { by: 'text', value: '搜索' },
  { must_exist: ['结果'], timeout_ms: 5000 }
);

const result = await automationSystem.executePlanStep(planStep);

// 执行完整任务计划
const testPlan = [
  { goal: '打开搜索', action: 'click', target: { by: 'text', value: '搜索' } },
  { goal: '输入关键词', action: 'type', target: { by: 'text', value: '搜索' }, input_text: '海边穿搭' }
];

const taskResult = await automationSystem.executeTaskPlan(testPlan);
```

## 消息接口

系统通过Chrome Extension消息API提供以下接口：

### 基础接口
- `EXT_EXTRACT_RAW`: 处理原始DOM并返回reduced结果
- `GET_AUTOMATION_STATUS`: 获取系统状态
- `RESET_AUTOMATION_SYSTEM`: 重置系统状态

### 执行接口  
- `EXECUTE_PLAN_STEP`: 执行单个计划步骤
- `RUN_AUTOMATION_TEST`: 运行预定义测试用例

### 测试用例
```javascript
// 在Service Worker控制台中运行
chrome.runtime.sendMessage({
  type: 'RUN_AUTOMATION_TEST',
  testName: 'searchTest'
});
```

## 数据结构

### PlanStep (计划步骤)
```javascript
{
  task_id: string,
  step_no: number,
  goal: string,                    // 目标描述
  action: "click|type|select|navigate",
  target: {
    by: "index|text|href|id",
    value: number|string,
    fallback?: Array<{by, value}>  // 备选目标
  },
  input_text?: string,
  success_criteria: {
    url_contains?: string[],
    title_includes?: string[],
    must_exist?: string[],
    must_not_exist?: string[],
    text_includes?: string[],
    timeout_ms?: number
  }
}
```

### ExecutionReport (执行报告)
```javascript
{
  exec_id: string,
  task_id: string,
  step_no: number,
  goal: string,
  plan_step: PlanStep,
  history: Array<{step_no, action, target_label, url_after, ok}>,
  pre_context: ReducedDom,         // 执行前DOM
  action_sent: {action, target_resolved, input_text},
  runtime: {ts_start, ts_end, duration_ms, nav_events, error},
  post_context: ReducedDom,        // 执行后DOM
  diff: {url_changed, title_changed, appeared_labels, disappeared_labels},
  local_validation: {status, reasons, matched_criteria, confidence}
}
```

### ReducedDom (精简DOM)
```javascript
{
  url: string,
  title: string,
  vw: number, vh: number, dpr: number,
  elements: Array<{
    label: string,
    role: string,
    bbox: [number, number, number, number],
    center: [number, number],
    id?: string,
    href?: string,
    action?: string
  }>,
  index: Record<string, number>,   // label到索引的映射
  _reduced: true,
  _version: string
}
```

## 黑名单系统

### 签名生成
- **页面签名**: `host + urlPathHash + domHash`
- **目标签名**: `role + label + href + id + bbox`
- **相似度匹配**: Jaccard >= 0.9 或 IoU >= 0.85

### 管理策略
- **TTL**: 默认7天过期
- **命中次数**: 超过3次永久拉黑
- **自动清理**: 每小时清理过期条目

## 性能优化

### DOM Reducer优化
- 最大元素数限制 (默认50)
- 高IoU去重 (默认0.9)
- 短文本过滤 (默认2字符)
- 智能噪声过滤

### 验证策略优化
- 本地规则优先 (便宜、快速)
- LLM验证仅在不确定时触发
- 缓存验证结果避免重复计算

### 恢复机制优化
- 分层回退策略减少失败成本
- 黑名单避免重复错误尝试
- 快速探测优于复杂分析

## 调试和监控

### 日志系统
所有组件都提供详细的控制台日志：
- `[AUTO-SYS]`: 自动化系统主要事件
- `[PAV]`: Plan-Act-Validate流程
- `[RECOVERY]`: 失败恢复和黑名单
- `[DOM REDUCED]`: DOM处理结果

### 状态检查
```javascript
// 获取系统状态
const status = await chrome.runtime.sendMessage({ type: 'GET_AUTOMATION_STATUS' });

// 获取黑名单统计
console.log(automationSystem.getExecutionSummary());
```

### 浏览器开发工具
- **Service Worker控制台**: 查看系统日志和状态
- **扩展页面**: 加载扩展后在chrome://extensions查看详情
- **网络面板**: 监控API调用和性能

## 部署和测试

### 加载扩展
1. 在Chrome中打开 `chrome://extensions/`
2. 启用"开发者模式"
3. 点击"加载已解压的扩展程序"
4. 选择 `getcontent/extension/` 目录

### 运行测试
```javascript
// 在任意网页的控制台中
chrome.runtime.sendMessage({
  type: 'RUN_AUTOMATION_TEST', 
  testName: 'searchTest'
}).then(result => console.log(result));
```

### 自定义测试
```javascript
// 创建自定义步骤
const customStep = automationSystem.createPlanStep(
  '自定义测试',
  'click',
  { by: 'text', value: '目标文本' },
  { must_exist: ['成功标志'] }
);

// 执行步骤
automationSystem.executePlanStep(customStep).then(result => {
  console.log('执行结果:', result);
});
```

这是一个完整的、生产就绪的自动化系统，实现了dom_plan.md中描述的所有功能，具有良好的可扩展性和维护性。