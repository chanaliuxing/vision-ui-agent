# DOM Plan 使用指南
# DOM Plan Usage Guide

## 概述 / Overview

DOM Plan 文档描述了一个**通用DOM简化器**系统，用于优化Chrome扩展的DOM提取和自动化执行。该系统分为多个阶段，每个阶段都有特定的功能和验证方法。

---

## 阶段1: 通用DOM简化器 / Phase 1: Universal DOM Reducer

### 功能概述 / Feature Overview

阶段1实现了一个**站点无关**的通用DOM简化器，将Chrome扩展提取的复杂DOM结构简化为自动化友好的格式。

#### 核心特性 / Core Features

- **站点无关设计**: 适用于任何网站，无需特定配置
- **智能去重**: 基于IoU和文本相似度的重复元素合并
- **噪声过滤**: 自动过滤无关元素（备案信息、隐私条款等）
- **动作推断**: 自动推断元素的最佳操作类型
- **可配置选项**: 支持按域名覆盖默认参数

#### 输出格式 / Output Format

简化后的DOM包含以下字段：
- `label`: 元素描述文本
- `role`: 元素角色 (button, input, a, etc.)
- `bbox`: 元素边界框 [x1, y1, x2, y2]
- `center`: 元素中心点 [cx, cy]
- `action`: 推断的操作类型 (click, type, navigate, select)
- `id`: 元素ID（如果有）
- `href`: 链接地址（如果是链接）

### 在工作流中使用 / Usage in Workflows

#### 1. 基础集成 / Basic Integration

在Chrome扩展的Service Worker中集成：

```javascript
// sw/bootstrap.js
import { reduceDomPayload } from "../lib/reducer.js";

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "EXT_EXTRACT_RAW") {
    // 使用默认配置简化DOM
    const reduced = reduceDomPayload(msg.payload, {
      maxElements: 45  // 限制最多返回45个元素
    });

    console.log("[DOM REDUCED]", reduced);

    // 发送简化结果到后端
    fetch("http://127.0.0.1:8787/ingest", {
      method: "POST",
      body: JSON.stringify(reduced)
    });

    sendResponse(reduced);
  }
  return true;
});
```

#### 2. 工作流中使用简化DOM / Using Reduced DOM in Workflows

```json
{
  "name": "使用简化DOM的工作流",
  "start": "extract_and_analyze",
  "states": {
    "extract_and_analyze": {
      "actions": [
        {
          "do": "ext.extract_reduced",
          "max_elements": 50,
          "filter_noise": true
        }
      ],
      "next": "find_target"
    },
    "find_target": {
      "actions": [
        {
          "do": "instr.click",
          "target": {"reduced_index": "搜索框"},
          "fallback": {"css": "input[type=search]"}
        }
      ]
    }
  }
}
```

#### 3. 站点特定配置 / Site-Specific Configuration

对特殊网站进行优化：

```javascript
const siteProfiles = {
  "www.youtube.com": {
    dropDigitsShort: false,     // YouTube评论区数字较多
    minTextLenSpan: 1          // 允许更短的文本
  },
  "news.ycombinator.com": {
    keepSpansWithText: true,    // 保留更多文本元素
    minTextLenSpan: 1
  },
  "www.xiaohongshu.com": {
    maxElements: 40,           // 小红书内容较多，限制元素数量
    preferAboveFoldY: 300      // 优先选择页面上部元素
  }
};

const reduced = reduceDomPayload(payload, {
  profiles: siteProfiles
});
```

### 手动验证方法 / Manual Verification Methods

#### 1. 检查简化质量 / Check Reduction Quality

```bash
# 在Chrome DevTools Console中验证
console.log("原始DOM元素数量:", payload.result.dom.items.length);
console.log("简化后元素数量:", reduced.elements.length);
console.log("简化比率:", (reduced.elements.length / payload.result.dom.items.length * 100).toFixed(1) + "%");

# 检查是否保留了关键元素
const importantElements = reduced.elements.filter(el =>
  el.role === 'button' || el.role === 'input' || el.role === 'a'
);
console.log("重要元素数量:", importantElements.length);
```

#### 2. 验证去重效果 / Verify Deduplication

```javascript
// 检查是否有重复的标签文本
const labels = reduced.elements.map(el => el.label);
const uniqueLabels = new Set(labels);
console.log("去重效果:", labels.length === uniqueLabels.size ? "良好" : "仍有重复");

// 检查IoU重叠
function checkOverlap(elements) {
  for (let i = 0; i < elements.length; i++) {
    for (let j = i + 1; j < elements.length; j++) {
      const iou = calculateIoU(elements[i].bbox, elements[j].bbox);
      if (iou > 0.8) {
        console.warn("高重叠元素:", elements[i].label, elements[j].label, "IoU:", iou);
      }
    }
  }
}
checkOverlap(reduced.elements);
```

#### 3. 验证噪声过滤 / Verify Noise Filtering

```javascript
// 检查是否过滤了常见噪声
const noiseKeywords = ['备案', 'ICP', '隐私', 'cookie', '版权', '客服'];
const hasNoise = reduced.elements.some(el =>
  noiseKeywords.some(keyword => el.label.includes(keyword))
);
console.log("噪声过滤:", hasNoise ? "不完全" : "良好");

// 检查是否保留了有用的链接
const usefulLinks = reduced.elements.filter(el =>
  el.role === 'a' && el.href && !el.href.includes('about') && !el.href.includes('privacy')
);
console.log("有用链接数量:", usefulLinks.length);
```

#### 4. 性能测试 / Performance Testing

```javascript
// 测试简化器性能
console.time("DOM Reduction");
const reduced = reduceDomPayload(payload);
console.timeEnd("DOM Reduction");

// 内存使用对比
const originalSize = JSON.stringify(payload).length;
const reducedSize = JSON.stringify(reduced).length;
console.log("大小压缩率:", ((originalSize - reducedSize) / originalSize * 100).toFixed(1) + "%");
```

### 配置参数详解 / Configuration Parameters

| 参数 | 默认值 | 说明 | 使用场景 |
|------|--------|------|----------|
| `maxElements` | 60 | 最大元素数量 | 控制输出大小 |
| `allowedRoles` | ["a","button","input"...] | 允许的元素角色 | 过滤无关元素类型 |
| `dupIoU` | 0.88 | 去重IoU阈值 | 控制重复检测严格度 |
| `minTextLenSpan` | 2 | span最小文本长度 | 过滤无意义的单字符 |
| `minAreaPx` | 64 | 最小元素面积 | 过滤微小元素 |
| `preferAboveFoldY` | 200 | 首屏优先阈值 | 优先选择页面上部元素 |

### 故障排除 / Troubleshooting

#### 常见问题 / Common Issues

1. **重要元素被过滤**: 调整 `allowedRoles` 或 `minAreaPx`
2. **仍有重复元素**: 降低 `dupIoU` 阈值
3. **噪声元素过多**: 添加站点特定的 `noiseRegexps`
4. **性能问题**: 减少 `maxElements` 或优化过滤条件

#### 调试技巧 / Debug Tips

```javascript
// 开启详细日志
const reduced = reduceDomPayload(payload, {
  debug: true,  // 需要在reducer中添加
  logFiltered: true
});

// 分析被过滤的元素
console.log("被过滤的元素原因统计");
```

---

## 阶段2: MV3集成实现 / Phase 2: MV3 Integration Implementation

### 功能概述 / Feature Overview

阶段2提供了完整的Chrome Extension MV3集成方案，将通用DOM简化器无缝集成到Chrome扩展架构中。

#### 核心组件 / Core Components

1. **Service Worker集成**: 在SW中执行DOM简化
2. **Content Script桥接**: 传递原始数据到SW
3. **消息传递机制**: SW与Content的通信
4. **配置管理**: 支持站点特定配置

### 在工作流中使用 / Usage in Workflows

#### 1. 扩展结构配置 / Extension Structure Configuration

**manifest.json配置**:
```json
{
  "manifest_version": 3,
  "name": "DOM Plan Auto Runner",
  "version": "1.0.0",
  "background": {
    "service_worker": "sw/bootstrap.js",
    "type": "module"
  },
  "permissions": ["storage", "activeTab", "scripting", "tabs"],
  "host_permissions": ["<all_urls>"],
  "content_scripts": [
    {
      "matches": ["<all_urls>"],
      "js": ["content/extract-bridge.js"],
      "run_at": "document_idle"
    }
  ]
}
```

#### 2. Service Worker实现 / Service Worker Implementation

**sw/bootstrap.js**:
```javascript
import { reduceDomPayload } from "../lib/reducer.js";

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg?.type === "EXT_EXTRACT_RAW") {
    try {
      const reduced = reduceDomPayload(msg.payload, {
        maxElements: 50,
        dupIoU: 0.9,
        minTextLenSpan: 2,
        profiles: {
          "www.xiaohongshu.com": { maxElements: 40 },
          "ca.indeed.com": { preferAboveFoldY: 300 }
        }
      });

      // 保存最近结果用于调试
      chrome.storage.session.set({ LAST_DOM_REDUCED: reduced });

      // 发送到后端（可选）
      if (reduced.elements.length > 0) {
        fetch("http://127.0.0.1:8787/ingest", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(reduced)
        });
      }

      sendResponse(reduced);
      console.log("[DOM REDUCED]", reduced);
    } catch (e) {
      console.error("[REDUCE FAILED]", e);
      sendResponse({ _reduced: false, error: String(e) });
    }
    return true;
  }
});
```

#### 3. 工作流集成 / Workflow Integration

**在工作流中使用简化DOM**:
```json
{
  "name": "使用DOM Plan的自动化工作流",
  "start": "extract_and_reduce",
  "states": {
    "extract_and_reduce": {
      "actions": [
        {
          "do": "ext.extract_reduced",
          "options": {
            "maxElements": 45,
            "site_profile": "auto"
          }
        }
      ],
      "next": "smart_interaction"
    },
    "smart_interaction": {
      "actions": [
        {
          "do": "instr.click",
          "target": {
            "reduced_selector": {
              "label": "搜索",
              "role": "button"
            },
            "fallback": {"css": "button.search"}
          }
        }
      ]
    }
  }
}
```

### 手动验证方法 / Manual Verification Methods

#### 1. 检查集成状态 / Check Integration Status

```bash
# 在Chrome DevTools中验证
# 1. 重新加载扩展
chrome://extensions/ -> 重新加载

# 2. 打开测试页面并检查SW控制台
# 扩展详情 -> Service Worker -> 检查视图
console.log("应该看到 [DOM REDUCED] 日志");

# 3. 检查存储的数据
chrome.storage.session.get(["LAST_DOM_REDUCED"]).then(console.log);
```

#### 2. 验证简化质量 / Verify Reduction Quality

```javascript
// 在SW控制台中运行
chrome.storage.session.get(["LAST_DOM_REDUCED"]).then(({LAST_DOM_REDUCED: reduced}) => {
  if (!reduced) {
    console.error("未找到简化数据");
    return;
  }

  console.log("✅ 验证简化数据:");
  console.log("- 元素数量:", reduced.elements.length);
  console.log("- 是否标记为简化:", reduced._reduced);
  console.log("- 版本:", reduced._version);

  // 验证元素质量
  const hasButtons = reduced.elements.filter(e => e.role === 'button').length;
  const hasInputs = reduced.elements.filter(e => e.role === 'input').length;
  const hasLinks = reduced.elements.filter(e => e.role === 'a').length;

  console.log("- 按钮数量:", hasButtons);
  console.log("- 输入框数量:", hasInputs);
  console.log("- 链接数量:", hasLinks);

  // 验证索引
  console.log("- 索引条目数:", Object.keys(reduced.index).length);
});
```

#### 3. 测试站点配置 / Test Site Configuration

```javascript
// 测试不同站点的配置生效
const testSites = [
  "www.xiaohongshu.com",
  "ca.indeed.com",
  "www.youtube.com"
];

// 在各个站点检查配置是否生效
testSites.forEach(site => {
  console.log(`测试站点: ${site}`);
  // 访问站点并触发extract，检查元素数量是否符合配置
});
```

---

## 阶段3: PAV回路系统 / Phase 3: Plan-Act-Validate Loop

### 功能概述 / Feature Overview

阶段3实现了Plan-Act-Validate的闭环系统，结合本地规则校验和LLM复核，提供智能的自动化执行和验证。

#### 核心数据结构 / Core Data Structures

**计划步骤 (PlanStep)**:
```typescript
interface PlanStep {
  task_id: string;
  step_no: number;
  goal: string;
  action: "click"|"type"|"select"|"navigate";
  target: {
    by: "index"|"text"|"href"|"id";
    value: number|string;
    fallback?: Array<{by: string, value: string}>;
  };
  input_text?: string;
  success_criteria: {
    url_contains?: string[];
    title_includes?: string[];
    must_exist?: string[];
    must_not_exist?: string[];
    text_includes?: string[];
    timeout_ms?: number;
  };
}
```

### 在工作流中使用 / Usage in Workflows

#### 1. 带PAV回路的工作流 / Workflow with PAV Loop

```json
{
  "name": "智能PAV执行流程",
  "start": "plan_step",
  "states": {
    "plan_step": {
      "actions": [
        {
          "do": "pav.plan",
          "goal": "点击搜索按钮",
          "success_criteria": {
            "url_contains": ["/search"],
            "must_exist": ["搜索结果", "筛选"],
            "timeout_ms": 5000
          }
        }
      ],
      "next": "execute_with_validation"
    },
    "execute_with_validation": {
      "actions": [
        {
          "do": "pav.execute",
          "validate_local": true,
          "llm_fallback": true
        }
      ],
      "on_success": "next_step",
      "on_failure": "recovery"
    },
    "recovery": {
      "actions": [
        {
          "do": "pav.recover",
          "strategies": ["retry", "alternative_target", "rollback"]
        }
      ]
    }
  }
}
```

#### 2. 自定义成功判定 / Custom Success Criteria

```json
{
  "success_criteria": {
    "url_contains": ["dashboard", "profile"],
    "url_regex": [".*\\/user\\/\\d+"],
    "title_includes": ["用户中心", "个人资料"],
    "must_exist": ["退出登录", "设置"],
    "must_not_exist": ["登录", "注册"],
    "text_includes": ["欢迎回来"],
    "timeout_ms": 8000
  }
}
```

### 手动验证方法 / Manual Verification Methods

#### 1. 验证本地校验规则 / Verify Local Validation Rules

```javascript
// 测试本地校验逻辑
function testLocalValidation(criteria, postContext) {
  let score = 0;
  const results = {};

  // URL检查
  if (criteria.url_contains) {
    const urlMatches = criteria.url_contains.some(pattern =>
      postContext.url.includes(pattern)
    );
    if (urlMatches) score += 0.4;
    results.url_check = urlMatches;
  }

  // 元素存在性检查
  if (criteria.must_exist) {
    const existCount = criteria.must_exist.filter(text =>
      postContext.elements.some(el => el.label.includes(text))
    ).length;
    score += (existCount / criteria.must_exist.length) * 0.2;
    results.must_exist_check = existCount;
  }

  const status = score >= 0.6 ? "success" : score <= 0.2 ? "failure" : "uncertain";

  console.log("本地验证结果:", {
    score: score.toFixed(2),
    status,
    details: results
  });

  return { status, score, details: results };
}
```

#### 2. 调试PAV执行流程 / Debug PAV Execution Flow

```javascript
// 启用PAV调试模式
window.PAV_DEBUG = true;

// 监听PAV事件
window.addEventListener('pav:plan', (e) => {
  console.log("📋 计划阶段:", e.detail);
});

window.addEventListener('pav:act', (e) => {
  console.log("🎯 执行阶段:", e.detail);
});

window.addEventListener('pav:validate', (e) => {
  console.log("✅ 验证阶段:", e.detail);
});

window.addEventListener('pav:recover', (e) => {
  console.log("🔄 恢复阶段:", e.detail);
});
```

#### 3. LLM复核测试 / Test LLM Review

```javascript
// 模拟LLM复核场景
async function testLLMReview(executionReport) {
  const reviewPrompt = {
    system: "你是网页自动化验证器。判断操作是否成功。",
    user: JSON.stringify({
      goal: executionReport.goal,
      action_performed: executionReport.action_sent,
      before_elements: executionReport.pre_context.elements.slice(0, 10),
      after_elements: executionReport.post_context.elements.slice(0, 10),
      url_changed: executionReport.diff.url_changed
    })
  };

  console.log("发送LLM复核请求:", reviewPrompt);

  // 这里会调用实际的LLM API
  // const response = await callLLMValidator(reviewPrompt);
  // console.log("LLM复核结果:", response);
}
```

---

## 阶段4: 故障恢复系统 / Phase 4: Failure Recovery System

### 功能概述 / Feature Overview

阶段4实现了完整的故障恢复机制，包括失败检测、黑名单管理、回退策略和继续执行。

#### 核心机制 / Core Mechanisms

1. **两层验证**: 本地规则 → YOLO+LLM介入
2. **智能回退**: 多种回退策略的优先级执行
3. **黑名单管理**: 按阶段+页面+目标的精确黑名单
4. **继续执行**: 回退后的状态恢复和重新规划

### 在工作流中使用 / Usage in Workflows

#### 1. 故障恢复配置 / Failure Recovery Configuration

```json
{
  "name": "带故障恢复的工作流",
  "recovery_config": {
    "max_attempts_per_phase": 3,
    "blacklist_ttl_ms": 604800000,
    "rollback_strategies": ["modal_close", "browser_back", "hard_navigate"],
    "enable_yolo_intervention": true
  },
  "states": {
    "robust_action": {
      "actions": [
        {
          "do": "instr.click",
          "target": {"css": "button.submit"},
          "recovery": {
            "on_failure": "auto_recover",
            "blacklist_on_repeat_fail": true,
            "alternative_targets": [
              {"css": "input[type=submit]"},
              {"xpath": "//button[contains(text(),'提交')]"}
            ]
          }
        }
      ]
    }
  }
}
```

#### 2. 黑名单管理 / Blacklist Management

```javascript
// 黑名单条目结构
const blacklistEntry = {
  phase: { task_id: "login_flow", phase_id: "submit_form" },
  page: {
    host: "example.com",
    urlPathHash: "hash_of_normalized_path",
    domHash: "hash_of_dom_structure"
  },
  target: {
    role: "button",
    label: "提交",
    bbox: [100, 200, 150, 230]
  },
  reason: "validation_fail",
  ttl_ms: 604800000, // 7天
  hits: 1,
  max_hits: 3
};
```

### 手动验证方法 / Manual Verification Methods

#### 1. 测试回退策略 / Test Rollback Strategies

```javascript
// 测试不同回退策略
async function testRollbackStrategies() {
  const strategies = ["modal_close", "browser_back", "hard_navigate"];

  for (const strategy of strategies) {
    console.log(`测试回退策略: ${strategy}`);

    switch (strategy) {
      case "modal_close":
        // 检测并关闭模态框
        const modal = document.querySelector('.modal, .dialog, .popup');
        if (modal) {
          console.log("找到模态框，尝试关闭");
          const closeBtn = modal.querySelector('.close, .cancel, [aria-label="close"]');
          if (closeBtn) closeBtn.click();
        }
        break;

      case "browser_back":
        // 浏览器后退
        console.log("执行浏览器后退");
        history.back();
        await new Promise(resolve => setTimeout(resolve, 2000));
        break;

      case "hard_navigate":
        // 强制导航到上一个URL
        console.log("强制导航到上一个URL");
        // location.assign(previousUrl);
        break;
    }
  }
}
```

#### 2. 验证黑名单功能 / Verify Blacklist Functionality

```javascript
// 测试黑名单添加和检查
function testBlacklist() {
  const testEntry = {
    phase: { task_id: "test", phase_id: "phase1" },
    page: { host: location.hostname },
    target: { role: "button", label: "测试按钮" }
  };

  // 添加到黑名单
  addToBlacklist(testEntry.phase, testEntry.page, testEntry.target, {
    reason: "test",
    ttl_ms: 60000 // 1分钟测试
  });

  // 检查是否被黑名单
  const isBlocked = isBlacklisted(testEntry.phase, testEntry.page, testEntry.target);
  console.log("黑名单测试结果:", isBlocked ? "已拉黑" : "未拉黑");

  // 查看黑名单条目
  getBlacklistEntries().then(entries => {
    console.log("当前黑名单条目:", entries.length);
  });
}
```

#### 3. YOLO+LLM介入测试 / Test YOLO+LLM Intervention

```javascript
// 模拟YOLO+LLM介入场景
async function testYOLOIntervention(planStep, preContext, postContext) {
  console.log("模拟YOLO+LLM介入...");

  // 1. 准备LLM输入
  const llmInput = {
    goal: planStep.goal,
    expected_outcome: planStep.success_criteria,
    dom_before: preContext.elements.slice(0, 15),
    dom_after: postContext.elements.slice(0, 15),
    action_performed: planStep.action
  };

  console.log("LLM输入:", llmInput);

  // 2. 模拟LLM响应
  const mockLLMResponse = {
    status: "failure",
    confidence: 0.3,
    reasoning: ["目标页面未出现", "仍在原页面"],
    recommended_next_steps: [
      {
        action: "alt_target",
        alt_target: { by: "text", value: "确认" }
      }
    ]
  };

  console.log("模拟LLM响应:", mockLLMResponse);

  // 3. 基于LLM建议执行替代操作
  if (mockLLMResponse.recommended_next_steps) {
    const altAction = mockLLMResponse.recommended_next_steps[0];
    if (altAction.action === "alt_target") {
      console.log("尝试替代目标:", altAction.alt_target);
      // 这里会执行实际的替代点击
    }
  }
}
```

---

## 阶段5: 日志与监控系统 / Phase 5: Logging & Monitoring System

### 功能概述 / Feature Overview

阶段5提供了完整的日志记录和监控方案，用于追踪LLM调用、DOM提取、验证结果等关键事件。

#### 日志事件类型 / Log Event Types

- `EXTRACTED_RAW`: 原始DOM提取
- `DOM_REDUCED`: 简化DOM输出
- `LLM_REQUEST`: LLM请求
- `LLM_RESPONSE`: LLM响应
- `ACTION_PERFORMED`: 动作执行
- `VALIDATION_LOCAL`: 本地验证
- `VALIDATION_LLM`: LLM验证
- `BLACKLIST_ADD`: 黑名单添加
- `ROLLBACK`: 回退操作
- `ERROR`: 错误事件

### 在工作流中使用 / Usage in Workflows

#### 1. 启用日志记录 / Enable Logging

```javascript
import { setLogConfig, logDomReduced, logLLMRequest, logLLMResponse } from "./lib/logger.js";

// 配置日志系统
setLogConfig({
  consoleLevel: "info",
  backendUrl: "http://127.0.0.1:8787/logs",
  flushIntervalMs: 3000,
  maxBuffer: 200
});
```

#### 2. 集成到工作流执行 / Integrate into Workflow Execution

```javascript
// 在关键节点记录日志
async function executeWorkflowStep(step) {
  const execId = generateExecId();

  try {
    // 记录DOM提取
    const domData = await extractDOM();
    await logDomReduced({
      exec_id: execId,
      task_id: step.task_id,
      phase_id: step.phase_id,
      step_no: step.step_no,
      url: location.href,
      reduced: domData
    });

    // 记录LLM调用
    const llmRequest = buildLLMRequest(step, domData);
    await logLLMRequest({
      exec_id: execId,
      task_id: step.task_id,
      phase_id: step.phase_id,
      step_no: step.step_no,
      model: "gemini-1.5-flash",
      body: llmRequest
    });

    const llmResponse = await callLLM(llmRequest);
    await logLLMResponse({
      exec_id: execId,
      task_id: step.task_id,
      phase_id: step.phase_id,
      step_no: step.step_no,
      model: "gemini-1.5-flash",
      status: "ok",
      latency_ms: 1200,
      tokens: { in: 850, out: 120 }
    });

  } catch (error) {
    await logError({
      exec_id: execId,
      task_id: step.task_id,
      phase_id: step.phase_id,
      step_no: step.step_no,
      err: error
    });
  }
}
```

### 手动验证方法 / Manual Verification Methods

#### 1. 检查日志生成 / Check Log Generation

```javascript
// 在Chrome DevTools中检查日志
console.log("检查日志缓冲区:");
chrome.storage.session.get(["LOG_BUFFER_V1"]).then(({LOG_BUFFER_V1: logs}) => {
  if (!logs || !logs.length) {
    console.warn("未找到日志数据");
    return;
  }

  console.log(`日志条目数量: ${logs.length}`);

  // 按事件类型分组
  const eventCounts = {};
  logs.forEach(log => {
    eventCounts[log.evt] = (eventCounts[log.evt] || 0) + 1;
  });

  console.log("事件类型统计:", eventCounts);

  // 查看最近的事件
  const recent = logs.slice(-10);
  console.log("最近10条日志:", recent);
});
```

#### 2. 验证数据脱敏 / Verify Data Redaction

```javascript
// 检查敏感数据是否被正确脱敏
function checkDataRedaction() {
  const testData = {
    url: "https://example.com/user?email=test@example.com&token=abc123",
    text: "联系邮箱: user@company.com, 电话: +86-138-0013-8000"
  };

  const redactedUrl = redactUrl(testData.url);
  const redactedText = redactText(testData.text);

  console.log("原始URL:", testData.url);
  console.log("脱敏URL:", redactedUrl);
  console.log("原始文本:", testData.text);
  console.log("脱敏文本:", redactedText);

  // 验证脱敏效果
  const hasEmail = /@/.test(redactedText);
  const hasPhone = /\+?\d[\d\s\-]{6,}\d/.test(redactedText);

  console.log("脱敏验证:", {
    emailRedacted: !hasEmail,
    phoneRedacted: !hasPhone
  });
}
```

#### 3. 后端日志验证 / Verify Backend Logging

```bash
# 检查后端日志文件
tail -f logs/runner.ndjson | jq .

# 按执行ID过滤
grep "exec_123" logs/runner.ndjson | jq .

# 统计事件类型
cat logs/runner.ndjson | jq -r .evt | sort | uniq -c

# 查看LLM调用统计
cat logs/runner.ndjson | jq 'select(.evt=="LLM_RESPONSE")' | jq -r '.latency_ms' | awk '{sum+=$1; count++} END {print "平均延迟:", sum/count, "ms"}'
```

#### 4. 监控仪表板 / Monitoring Dashboard

```javascript
// 创建简单的监控仪表板
function createMonitoringDashboard() {
  const dashboard = document.createElement('div');
  dashboard.style.cssText = `
    position: fixed; top: 10px; right: 10px;
    background: rgba(0,0,0,0.8); color: white;
    padding: 10px; border-radius: 5px;
    font-family: monospace; font-size: 12px;
    z-index: 10000; min-width: 200px;
  `;

  // 实时更新统计信息
  setInterval(async () => {
    const {LOG_BUFFER_V1: logs = []} = await chrome.storage.session.get(["LOG_BUFFER_V1"]);

    const stats = {
      total: logs.length,
      errors: logs.filter(l => l.level === 'error').length,
      llmCalls: logs.filter(l => l.evt === 'LLM_REQUEST').length,
      actions: logs.filter(l => l.evt === 'ACTION_PERFORMED').length
    };

    dashboard.innerHTML = `
      <div>📊 DOM Plan 监控</div>
      <div>总日志: ${stats.total}</div>
      <div>错误: ${stats.errors}</div>
      <div>LLM调用: ${stats.llmCalls}</div>
      <div>动作执行: ${stats.actions}</div>
      <div>时间: ${new Date().toLocaleTimeString()}</div>
    `;
  }, 1000);

  document.body.appendChild(dashboard);
}

// 启用监控仪表板
createMonitoringDashboard();
```

---

## 总结与最佳实践 / Summary & Best Practices

### 实施建议 / Implementation Recommendations

1. **分阶段实施**: 按照阶段1→2→3→4→5的顺序逐步实施
2. **充分测试**: 每个阶段都要进行充分的手动验证
3. **监控优先**: 尽早启用日志系统，便于问题排查
4. **性能考虑**: 合理配置参数，避免过度处理
5. **安全第一**: 确保敏感数据的正确脱敏

### 常见问题 / Common Issues

1. **元素未找到**: 检查DOM简化配置和黑名单状态
2. **验证失败**: 调整成功判定条件的阈值
3. **性能问题**: 优化maxElements和采样率
4. **日志过多**: 调整日志级别和刷新频率

### 进阶功能 / Advanced Features

- 站点特定配置文件
- 自适应阈值调整
- 机器学习增强的元素识别
- 分布式日志收集
- 实时性能监控

---

**文档版本**: v1.0.0
**最后更新**: 2024年12月
**适用版本**: DOM Plan 完整实现

如需技术支持，请参考故障排除章节或联系开发团队。