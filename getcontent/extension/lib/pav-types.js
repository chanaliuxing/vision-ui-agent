/**
 * PAV (Plan → Act → Validate) 系统的TypeScript接口定义
 * 转换为JavaScript注释形式供ESM使用
 */

/**
 * @typedef {[number, number, number, number]} BBox
 */

/**
 * @typedef {Object} PlanStep
 * @property {string} task_id - 任务 id
 * @property {number} step_no - 步序
 * @property {string} goal - 目标描述，如"打开通知页"、"搜索'苹果手机'"
 * @property {"click"|"type"|"select"|"navigate"} action
 * @property {Object} target - 和 reducer 输出对齐
 * @property {"index"|"text"|"href"|"id"} target.by
 * @property {number|string} target.value
 * @property {Array<{by:"text"|"href"|"id", value:string}>} [target.fallback] - 备选目标
 * @property {string} [input_text] - type/select 时需要
 * @property {Object} success_criteria - 成功判定
 * @property {string[]} [success_criteria.url_contains]
 * @property {string[]} [success_criteria.url_regex]
 * @property {string[]} [success_criteria.title_includes]
 * @property {string[]} [success_criteria.must_exist] - 文字/按钮/标签
 * @property {string[]} [success_criteria.must_not_exist]
 * @property {string[]} [success_criteria.text_includes]
 * @property {number} [success_criteria.timeout_ms]
 */

/**
 * @typedef {Object} ReducedDom
 * @property {string} url
 * @property {string} title
 * @property {number} vw
 * @property {number} vh
 * @property {number} dpr
 * @property {Array<{label:string; role:string; bbox:BBox; center:[number,number]; id?:string; href?:string; action?:string}>} elements
 * @property {Record<string, number>} index
 * @property {true} _reduced
 * @property {string} _version
 */

/**
 * @typedef {Object} StepRuntime
 * @property {number} ts_start
 * @property {number} ts_end
 * @property {number} duration_ms
 * @property {Array<{type:"committed"|"completed"|"error"|"redirect"; url:string; time:number}>} nav_events
 * @property {number} net_requests
 * @property {string} [screenshot] - dataURL/base64
 * @property {string} [error] - 本地执行异常
 */

/**
 * @typedef {Object} ExecutionReport
 * @property {string} exec_id
 * @property {string} task_id
 * @property {number} step_no
 * @property {string} goal
 * @property {PlanStep} plan_step
 * @property {Array<{step_no:number; action:string; target_label?:string; url_after:string; ok:boolean}>} history
 * @property {ReducedDom} pre_context
 * @property {Object} action_sent
 * @property {"click"|"type"|"select"|"navigate"} action_sent.action
 * @property {{by:"index"|"text"|"href"|"id"; value:number|string; label?:string}} action_sent.target_resolved
 * @property {string} [action_sent.input_text]
 * @property {StepRuntime} runtime
 * @property {ReducedDom} post_context
 * @property {Object} diff
 * @property {boolean} diff.url_changed
 * @property {boolean} diff.title_changed
 * @property {string[]} diff.appeared_labels
 * @property {string[]} diff.disappeared_labels
 * @property {Object} local_validation
 * @property {"success"|"failure"|"uncertain"} local_validation.status
 * @property {string[]} local_validation.reasons
 * @property {string[]} local_validation.matched_criteria
 * @property {number} local_validation.confidence
 */

/**
 * @typedef {Object} ValidationVerdict
 * @property {"success"|"failure"|"uncertain"} status
 * @property {number} confidence
 * @property {string[]} reasoning
 * @property {boolean} [is_on_expected_page]
 * @property {Array<{action:"proceed"|"retry"|"wait"|"scroll"|"back"|"alt_target"|"abort"; notes?:string; alt_target?:{by:"text"|"href"|"id"; value:string}}>} recommended_next_steps
 * @property {Object} [refined_success_criteria]
 */

export { 
  // Export as JSDoc comments for type checking
};