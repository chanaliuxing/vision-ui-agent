/**
 * 本地确定性校验系统
 * 优先本地规则，按需LLM，可控成本、稳定行为
 */

/**
 * 本地校验逻辑
 * @param {import('./pav-types.js').PlanStep['success_criteria']} criteria - 成功判定条件
 * @param {import('./pav-types.js').ReducedDom} postContext - 执行后DOM
 * @param {Object} diff - DOM差异
 * @param {import('./pav-types.js').StepRuntime} runtime - 运行时信息
 * @returns {Object} 验证结果
 */
export function validateLocal(criteria, postContext, diff, runtime) {
  let score = 0;
  const reasons = [];
  const matchedCriteria = [];

  // 1. URL检查 (+0.4)
  if (criteria.url_contains || criteria.url_regex) {
    let urlMatched = false;
    
    if (criteria.url_contains) {
      for (const pattern of criteria.url_contains) {
        if (postContext.url.includes(pattern)) {
          urlMatched = true;
          matchedCriteria.push(`url_contains:${pattern}`);
          break;
        }
      }
    }
    
    if (!urlMatched && criteria.url_regex) {
      for (const pattern of criteria.url_regex) {
        try {
          const regex = new RegExp(pattern, 'i');
          if (regex.test(postContext.url)) {
            urlMatched = true;
            matchedCriteria.push(`url_regex:${pattern}`);
            break;
          }
        } catch (e) {
          console.warn('[VALIDATOR] Invalid regex:', pattern);
        }
      }
    }
    
    if (urlMatched) {
      score += 0.4;
      reasons.push('URL匹配成功');
    }
  }

  // 2. 标题检查 (+0.2)
  if (criteria.title_includes) {
    for (const text of criteria.title_includes) {
      if (postContext.title.includes(text)) {
        score += 0.2;
        reasons.push(`标题包含: ${text}`);
        matchedCriteria.push(`title_includes:${text}`);
        break;
      }
    }
  }

  // 3. 必须存在的元素 (+0.2全部满足, +0.1部分满足)
  if (criteria.must_exist) {
    const existingElements = postContext.elements.map(el => el.label.toLowerCase());
    let foundCount = 0;
    
    for (const required of criteria.must_exist) {
      const found = existingElements.some(label => 
        label.includes(required.toLowerCase()) || 
        postContext.index[required.toLowerCase()] !== undefined
      );
      if (found) {
        foundCount++;
        matchedCriteria.push(`must_exist:${required}`);
      }
    }
    
    if (foundCount === criteria.must_exist.length) {
      score += 0.2;
      reasons.push('所有必需元素都存在');
    } else if (foundCount > 0) {
      score += 0.1;
      reasons.push(`部分必需元素存在 (${foundCount}/${criteria.must_exist.length})`);
    }
  }

  // 4. 不应存在的元素 (-0.3)
  if (criteria.must_not_exist) {
    const existingElements = postContext.elements.map(el => el.label.toLowerCase());
    
    for (const forbidden of criteria.must_not_exist) {
      const found = existingElements.some(label => 
        label.includes(forbidden.toLowerCase()) || 
        postContext.index[forbidden.toLowerCase()] !== undefined
      );
      if (found) {
        score -= 0.3;
        reasons.push(`发现不应存在的元素: ${forbidden}`);
        break;
      }
    }
  }

  // 5. 文本包含检查 (+0.1)
  if (criteria.text_includes) {
    const allText = postContext.elements.map(el => el.label).join(' ').toLowerCase();
    
    for (const text of criteria.text_includes) {
      if (allText.includes(text.toLowerCase())) {
        score += 0.1;
        reasons.push(`页面包含文本: ${text}`);
        matchedCriteria.push(`text_includes:${text}`);
        break;
      }
    }
  }

  // 6. 导航事件检查 (+0.1)
  const hasNavigation = runtime.nav_events && runtime.nav_events.some(
    event => event.type === 'committed' || event.type === 'completed'
  );
  if (hasNavigation) {
    score += 0.1;
    reasons.push('检测到页面导航');
    matchedCriteria.push('navigation_detected');
  }

  // 7. 超时检查 (-0.2)
  if (criteria.timeout_ms && runtime.duration_ms > criteria.timeout_ms) {
    score -= 0.2;
    reasons.push(`执行超时 (${runtime.duration_ms}ms > ${criteria.timeout_ms}ms)`);
  }

  // 8. 结构变化加分
  if (diff.appeared_labels && diff.appeared_labels.length > 0) {
    score += 0.05;
    reasons.push(`新增了${diff.appeared_labels.length}个UI元素`);
  }
  
  if (diff.url_changed) {
    score += 0.05;
    reasons.push('页面URL发生变化');
  }

  // 决定最终状态
  let status;
  if (score >= 0.6) {
    status = 'success';
  } else if (score <= 0.2) {
    status = 'failure';
  } else {
    status = 'uncertain';
  }

  return {
    status,
    reasons,
    matched_criteria: matchedCriteria,
    confidence: Math.max(0, Math.min(1, score))
  };
}

/**
 * 创建DOM差异对比
 * @param {import('./pav-types.js').ReducedDom} pre - 执行前DOM
 * @param {import('./pav-types.js').ReducedDom} post - 执行后DOM  
 * @returns {Object} 差异结果
 */
export function makeDiff(pre, post) {
  const preLabels = new Set(pre.elements.map(el => el.label));
  const postLabels = new Set(post.elements.map(el => el.label));
  
  const appeared = [];
  const disappeared = [];
  
  for (const label of postLabels) {
    if (!preLabels.has(label)) {
      appeared.push(label);
    }
  }
  
  for (const label of preLabels) {
    if (!postLabels.has(label)) {
      disappeared.push(label);
    }
  }
  
  return {
    url_changed: pre.url !== post.url,
    title_changed: pre.title !== post.title,
    appeared_labels: appeared,
    disappeared_labels: disappeared
  };
}

/**
 * 生成唯一ID
 * @returns {string}
 */
export function genId() {
  return crypto.randomUUID();
}