# Workflow JSON Configuration Guide

这是一个完整的Workflow JSON配置指南，涵盖所有可用的模块配置选项，包括DOM Reducer、RAG Memory、DPO Training、Skills & Macros、Vision Analysis等功能。

## 📖 概述

Workflow JSON是自动化执行引擎的核心配置文件，通过不同模块的组合配置，可以实现复杂的网页自动化任务。本指南将逐模块介绍每个功能的配置方法。

## 🏗️ 基础结构

### Workflow JSON基础格式
```json
{
  "version": "1.1",
  "name": "workflow_name",
  "description": "工作流描述",
  "task": "任务说明",
  "config": {
    // 全局配置项
  },
  "start": "initial_state",
  "states": {
    // 状态定义
  }
}
```

## 📋 模块配置目录

1. [DOM Reducer配置](#dom-reducer) - DOM数据精简
2. [RAG Memory配置](#rag-memory) - 记忆和反思系统
3. [LLM Provider配置](#llm-provider) - 大模型配置
4. [Vision Analysis配置](#vision-analysis) - 视觉分析
5. [Skills & Macros配置](#skills-macros) - 技能和宏
6. [Error Handling配置](#error-handling) - 错误处理
7. [Observability配置](#observability) - 可观测性

---

# 1. DOM Reducer配置 {#dom-reducer}

DOM Reducer是一个智能DOM数据精简工具，可以将复杂页面的大量DOM元素（几百个）精简为LLM友好的少量核心元素（几十个）。

### 方法1: 在extract动作中直接启用

#### 基础启用
```json
{
  "do": "ext.extract",
  "args": {
    "want": "inputs",
    "limit": 30,
    "use_reducer": true,     // 启用DOM reducer
    "save": "dom_snapshot"
  }
}
```

#### 自定义reducer配置
```json
{
  "do": "ext.extract",
  "args": {
    "want": "inputs",
    "limit": 200,
    "use_reducer": true,
    "reducer_config": {      // 自定义reducer参数
      "maxElements": 50,     // 最大保留元素数
      "dupIoU": 0.9,        // 重复检测阈值
      "minTextLenSpan": 2,  // 最小文本长度
      "profiles": {         // 站点特定配置
        "xiaohongshu.com": {
          "dropDigitsShort": false,
          "minTextLenSpan": 1
        }
      }
    }
  },
  "save": "reduced_dom"
}
```

#### 智能自动模式（推荐）
```json
{
  "do": "ext.extract",
  "args": {
    "want": "inputs",
    "limit": 200,
    "reducer": "auto"       // 根据元素数量自动决定是否启用
  },
  "save": "dom_snapshot"
}
```

### 方法2: Workflow级别全局配置

```json
{
  "version": "1.1",
  "name": "xhs_search_with_reducer",
  "description": "小红书搜索workflow，启用DOM精简功能",
  "config": {
    "dom_reduction": {
      "enabled": true,        // 全局启用DOM reduction
      "auto_threshold": 100,  // 超过100个元素自动启用
      "max_elements": 50,     // 最大保留元素数
      "dup_iou": 0.9,        // 重复检测阈值
      "noise_filtering": true // 启用噪声过滤
    }
  },
  "start": "search",
  "states": {
    "search": {
      "actions": [
        {
          "do": "ext.extract",
          "args": { "want": "inputs" }  // 会自动应用全局reducer配置
        }
      ]
    }
  }
}
```

### 方法3: 使用专门的reducer动作

```json
{
  "do": "ext.extract_reduced",  // 专门的reducer动作类型
  "args": {
    "want": "links",
    "limit": 200,
    "max_elements": 30
  },
  "save": "reduced_links"
}
```

## ⚙️ 配置参数详解

### 核心参数
```json
{
  "maxElements": 60,           // 最大保留元素数（默认60）
  "dupIoU": 0.88,             // 重复元素IoU阈值（默认0.88）
  "minTextLenSpan": 2,        // span最小文本长度（默认2）
  "minAreaPx": 64,            // 最小像素面积（默认64）
  "preferAboveFoldY": 200     // 优先保留页面顶部元素
}
```

### 过滤规则
```json
{
  "allowedRoles": ["a","button","input","textarea","select","span","p","label"],
  "dropDigitsShort": true,     // 丢弃短纯数字文本
  "keepSpansWithText": true,   // 保留有文本的span元素
  "inferAction": true          // 自动推断动作类型（click/type/select/navigate）
}
```

### 噪声过滤
```json
{
  "noiseRegexps": [
    "/ICP备|ICP\\b|公网安备|备案|许可证|资格证|平台备字/i",
    "/cookie|privacy|terms|免责声明|隐私|条款|协议|GDPR/i",
    "/subscribe|newsletter|关注我们|站点地图|site\\s*map/i",
    "/©|copyright|版权所有/i",
    "/客服|联系我们|联系\\s*我们|about\\s*us/i"
  ]
}
```

### 站点特定配置
```json
{
  "profiles": {
    "www.youtube.com": {
      "dropDigitsShort": false,  // YouTube评论区数字较多
      "minTextLenSpan": 1
    },
    "news.ycombinator.com": {
      "keepSpansWithText": true,  // 更偏文本链接
      "minTextLenSpan": 1
    },
    "xiaohongshu.com": {
      "maxElements": 40,         // 小红书专用配置
      "preferAboveFoldY": 300
    }
  }
}
```

## 📋 完整Workflow示例

### 示例1: 小红书搜索workflow

```json
{
  "version": "1.1",
  "name": "xiaohongshu_search_reduced",
  "description": "小红书搜索并打开第一个结果（启用DOM精简）",
  "config": {
    "dom_reduction": {
      "enabled": true,
      "auto_threshold": 80,
      "max_elements": 40
    }
  },
  "start": "open_home",
  "states": {
    "open_home": {
      "actions": [
        { "do": "ext.navigate", "url": "https://www.xiaohongshu.com/explore" },
        { "do": "ext.wait_quiet", "timeout_ms": 5000 }
      ],
      "on_success": "search"
    },
    "search": {
      "actions": [
        {
          "do": "ext.extract",
          "args": {
            "want": "inputs",
            "limit": 100,
            "use_reducer": true,
            "reducer_config": {
              "maxElements": 30,
              "profiles": {
                "xiaohongshu.com": {
                  "dropDigitsShort": false
                }
              }
            }
          },
          "save": "search_dom"
        },
        {
          "do": "llm_decide",
          "args": {
            "goal": "找到搜索输入框并输入'美食推荐'",
            "dom": "{{search_dom}}",
            "allowed_actions": ["ext.click_selector", "ext.type_text"]
          }
        }
      ],
      "on_success": "results"
    },
    "results": {
      "actions": [
        {
          "do": "ext.extract",
          "args": {
            "want": "links",
            "limit": 150,
            "reducer": "auto"  // 自动判断是否需要精简
          },
          "save": "results_dom"
        },
        {
          "do": "llm_decide",
          "args": {
            "goal": "点击第一个搜索结果帖子",
            "dom": "{{results_dom}}",
            "allowed_actions": ["ext.click_selector"]
          }
        }
      ],
      "on_success": "done"
    },
    "done": {
      "actions": [
        { "do": "ext.wait_quiet", "timeout_ms": 3000 }
      ]
    }
  }
}
```

### 示例2: Indeed求职workflow

```json
{
  "version": "1.1",
  "name": "indeed_job_search_reduced",
  "description": "Indeed求职申请（智能DOM精简）",
  "start": "open_indeed",
  "states": {
    "open_indeed": {
      "actions": [
        { "do": "ext.navigate", "url": "https://ca.indeed.com" },
        { "do": "ext.wait_quiet", "timeout_ms": 8000 }
      ],
      "on_success": "search_jobs"
    },
    "search_jobs": {
      "actions": [
        {
          "do": "ext.extract_reduced",  // 使用专门的reducer动作
          "args": {
            "want": "inputs",
            "limit": 200,
            "max_elements": 40
          },
          "save": "search_form"
        },
        {
          "do": "llm_decide",
          "args": {
            "goal": "在搜索框输入'software engineer'并搜索",
            "dom": "{{search_form}}",
            "allowed_actions": ["ext.click_selector", "ext.type_text", "ext.key"]
          }
        }
      ],
      "on_success": "select_job"
    },
    "select_job": {
      "actions": [
        {
          "do": "ext.extract",
          "args": {
            "want": "links",
            "limit": 300,
            "use_reducer": true,
            "reducer_config": {
              "maxElements": 50,
              "preferAboveFoldY": 400  // 优先选择页面顶部的职位
            }
          },
          "save": "job_listings"
        },
        {
          "do": "llm_decide",
          "args": {
            "goal": "点击第一个合适的软件工程师职位",
            "dom": "{{job_listings}}",
            "allowed_actions": ["ext.click_selector"]
          }
        }
      ],
      "on_success": "apply_job"
    },
    "apply_job": {
      "actions": [
        {
          "do": "ext.extract",
          "args": {
            "want": "buttons",
            "limit": 100,
            "reducer": "auto"
          },
          "save": "job_page"
        },
        {
          "do": "llm_decide",
          "args": {
            "goal": "点击Apply或Quick Apply按钮",
            "dom": "{{job_page}}",
            "allowed_actions": ["ext.click_selector"]
          }
        }
      ],
      "on_success": "done"
    },
    "done": {
      "actions": [
        { "do": "ext.wait_quiet", "timeout_ms": 5000 }
      ]
    }
  }
}
```

## 🎛️ 高级配置选项

### 性能优化配置
```json
{
  "config": {
    "dom_reduction": {
      "performance_mode": "balanced",  // "fast" | "balanced" | "quality"
      "cache_enabled": true,           // 启用DOM缓存
      "batch_processing": true         // 批量处理多个extract
    }
  }
}
```

### 调试配置
```json
{
  "config": {
    "dom_reduction": {
      "debug_mode": true,              // 启用详细日志
      "save_original": true,           // 保存原始DOM用于对比
      "log_reduction_stats": true      // 记录精简统计信息
    }
  }
}
```

## 📊 效果对比

| 场景 | 原始元素数 | 精简后元素数 | 数据减少 | LLM token减少 |
|------|------------|--------------|----------|---------------|
| 简单登录页 | 30 | 30 | 0% | 0% |
| 中等商城页 | 150 | 45 | 70% | 65% |
| 复杂社交媒体 | 400+ | 50 | 87% | 83% |
| 新闻聚合网站 | 800+ | 40 | 95% | 92% |

## 🔍 故障排查

### 常见问题

**1. DOM精简后找不到目标元素**
```json
{
  "reducer_config": {
    "maxElements": 80,        // 增加保留元素数
    "minAreaPx": 32,         // 降低最小面积要求
    "keepSpansWithText": true // 保留更多文本元素
  }
}
```

**2. 特定网站兼容性问题**
```json
{
  "profiles": {
    "problematic-site.com": {
      "maxElements": 100,      // 为特定网站增加元素限制
      "dropDigitsShort": false, // 禁用数字过滤
      "noiseRegexps": []       // 禁用噪声过滤
    }
  }
}
```

**3. 性能问题**
```json
{
  "reducer_config": {
    "maxElements": 30,        // 减少保留元素数
    "dupIoU": 0.95,          // 提高去重阈值
    "minTextLenSpan": 3      // 提高文本长度要求
  }
}
```

## 📚 最佳实践

1. **渐进式启用**: 先在复杂页面测试，确认效果后再全面启用
2. **站点定制**: 为重要网站创建专门的profiles配置
3. **监控效果**: 启用debug模式观察精简效果和成功率
4. **性能平衡**: 根据LLM token成本和执行速度调整maxElements
5. **回退机制**: 保留原始extract作为fallback选项

通过合理配置DOM Reducer，可以显著提升workflow在复杂网站上的执行效率和成功率！

---

# 2. RAG Memory配置 {#rag-memory}

RAG Memory系统提供记忆和反思功能，可以从历史执行中学习和改进。

## 基础配置

### Workflow级别启用RAG Memory
```json
{
  "config": {
    "memory": {
      "enabled": true,
      "provider": "openai",           // openai | sentence_transformers | mock
      "embedding_model": "text-embedding-3-small",
      "dimension": 1536,
      "recall_threshold": 0.7,        // 相似度阈值
      "max_recall_results": 5
    }
  }
}
```

### 使用mem.recall动作
```json
{
  "do": "mem.recall",
  "args": {
    "goal": "login to website",      // 查询目标
    "k": 5,                         // 返回结果数
    "threshold": 0.7,               // 相似度阈值
    "host_filter": "xiaohongshu.com" // 可选：按域名过滤
  },
  "save": "recalled_trajectories"
}
```

### 使用plan.reflect动作
```json
{
  "do": "plan.reflect",
  "args": {
    "focus": "error_analysis",       // reflection类型
    "context": "{{execution_log}}",  // 执行上下文
    "goal": "improve login success rate"
  },
  "save": "reflection_insights"
}
```

---

# 3. LLM Provider配置 {#llm-provider}

配置大语言模型提供商和参数。

## 全局LLM配置
```json
{
  "config": {
    "llm": {
      "provider": "gemini",           // gemini | openai | deepseek | nvidia
      "model": "gemini-1.5-flash",
      "temperature": 0.3,
      "max_tokens": 4096,
      "timeout_ms": 30000,
      "retry_attempts": 3
    }
  }
}
```

## 动作级别LLM覆盖
```json
{
  "do": "llm_decide",
  "args": {
    "goal": "find login button",
    "dom": "{{dom_snapshot}}",
    "llm_provider": "openai",        // 覆盖全局配置
    "llm_model": "gpt-4",
    "temperature": 0.1
  }
}
```

## 多模型配置
```json
{
  "config": {
    "llm": {
      "providers": {
        "vision": {
          "provider": "gemini",
          "model": "gemini-1.5-flash",
          "temperature": 0.2
        },
        "reasoning": {
          "provider": "openai",
          "model": "gpt-4",
          "temperature": 0.1
        },
        "fast": {
          "provider": "deepseek",
          "model": "deepseek-chat",
          "temperature": 0.3
        }
      }
    }
  }
}
```

---

# 4. Vision Analysis配置 {#vision-analysis}

视觉分析系统集成YOLO目标检测和OCR文字识别。

## 基础Vision配置
```json
{
  "config": {
    "vision": {
      "enabled": true,
      "yolo_endpoint": "http://127.0.0.1:8000",
      "ocr_endpoint": "http://127.0.0.1:8001",
      "confidence_threshold": 0.5,
      "use_overlay": true,
      "save_screenshots": true
    }
  }
}
```

## 使用Vision动作
```json
{
  "do": "vision.detect",
  "args": {
    "target": "button",              // 检测目标类型
    "confidence": 0.7,
    "text_contains": "登录",         // OCR文字过滤
    "region": "top_half"             // 检测区域
  },
  "save": "detected_elements"
}
```

## 混合Vision+DOM验证
```json
{
  "do": "autostep",
  "args": {
    "goal": "click login button",
    "verification": {
      "dom_check": true,             // DOM验证
      "vision_check": true,          // Vision验证
      "ocr_check": true,             // OCR验证
      "confidence_weight": {
        "dom": 0.4,
        "vision": 0.4,
        "ocr": 0.2
      }
    }
  }
}
```

---

# 5. Skills & Macros配置 {#skills-macros}

技能和宏系统允许复用常见的自动化序列。

## Macro配置
```json
{
  "config": {
    "macros": {
      "enabled": true,
      "registry_url": "http://127.0.0.1:8005",
      "auto_load": true,
      "skill_paths": ["./skills/", "./macros/"],
      "security_level": "medium"      // low | medium | high
    }
  }
}
```

## 使用macro.execute动作
```json
{
  "do": "macro.execute",
  "args": {
    "name": "login_sequence",        // 宏名称
    "params": {                      // 参数传递
      "username": "{{username}}",
      "password": "{{password}}",
      "remember_me": true
    },
    "timeout_ms": 30000
  },
  "save": "macro_result"
}
```

## 技能定义示例
```json
{
  "skill_name": "xiaohongshu_login",
  "version": "1.0.0",
  "description": "小红书登录技能",
  "parameters": {
    "username": "string",
    "password": "string"
  },
  "steps": [
    { "do": "ext.click_selector", "sel": ".login-btn" },
    { "do": "ext.type_text", "sel": "input[type=text]", "text": "{{username}}" },
    { "do": "ext.type_text", "sel": "input[type=password]", "text": "{{password}}" },
    { "do": "ext.click_selector", "sel": ".submit-btn" }
  ]
}
```

---

# 6. Error Handling配置 {#error-handling}

错误处理和重试机制配置。

## 全局错误处理
```json
{
  "config": {
    "error_handling": {
      "max_retries": 3,
      "retry_delay_ms": 2000,
      "recovery_strategies": ["retry", "fallback", "skip"],
      "blacklist_failed_elements": true,
      "auto_rollback": true
    }
  }
}
```

## 状态级错误处理
```json
{
  "states": {
    "login": {
      "actions": [
        { "do": "ext.click_selector", "sel": ".login-btn" }
      ],
      "on_error": "retry_login",     // 错误时跳转状态
      "error_config": {
        "max_attempts": 5,
        "backoff_factor": 1.5
      }
    },
    "retry_login": {
      "actions": [
        { "do": "wait", "ms": 5000 },
        { "do": "goto_state", "state": "login" }
      ]
    }
  }
}
```

## 动作级错误处理
```json
{
  "do": "ext.click_selector",
  "sel": ".submit-btn",
  "fallback": [                      // 回退策略
    { "do": "ext.click_selector", "sel": "button[type=submit]" },
    { "do": "ext.key", "key": "Enter" }
  ],
  "retry": {
    "max_attempts": 3,
    "delay_ms": 1000
  }
}
```

---

# 7. Observability配置 {#observability}

可观测性和日志配置。

## 日志配置
```json
{
  "config": {
    "observability": {
      "logging": {
        "enabled": true,
        "level": "info",              // debug | info | warn | error
        "destinations": ["console", "file", "remote"],
        "remote_endpoint": "http://127.0.0.1:8787/logs"
      },
      "metrics": {
        "enabled": true,
        "collect_timing": true,
        "collect_success_rate": true,
        "export_interval_ms": 60000
      }
    }
  }
}
```

## 事件追踪
```json
{
  "do": "ext.click_selector",
  "sel": ".login-btn",
  "telemetry": {
    "event_name": "login_attempt",
    "custom_fields": {
      "user_type": "premium",
      "login_method": "password"
    },
    "success_metric": "login_success_rate"
  }
}
```

---

# 🔧 完整配置示例

## 高级小红书workflow配置
```json
{
  "version": "1.1",
  "name": "xiaohongshu_advanced_workflow",
  "description": "小红书高级自动化workflow（全功能版）",
  "task": "搜索美食内容并进行互动",
  "config": {
    "dom_reduction": {
      "enabled": true,
      "auto_threshold": 80,
      "max_elements": 40,
      "profiles": {
        "xiaohongshu.com": {
          "dropDigitsShort": false,
          "minTextLenSpan": 1
        }
      }
    },
    "memory": {
      "enabled": true,
      "provider": "openai",
      "recall_threshold": 0.7,
      "max_recall_results": 5
    },
    "llm": {
      "provider": "gemini",
      "model": "gemini-1.5-flash",
      "temperature": 0.3,
      "timeout_ms": 30000
    },
    "vision": {
      "enabled": true,
      "confidence_threshold": 0.6,
      "use_overlay": true
    },
    "macros": {
      "enabled": true,
      "auto_load": true
    },
    "error_handling": {
      "max_retries": 3,
      "auto_rollback": true
    },
    "observability": {
      "logging": {
        "enabled": true,
        "level": "info"
      },
      "metrics": {
        "enabled": true,
        "collect_timing": true
      }
    }
  },
  "start": "recall_experience",
  "states": {
    "recall_experience": {
      "description": "回忆之前的成功经验",
      "actions": [
        {
          "do": "mem.recall",
          "args": {
            "goal": "xiaohongshu search and interaction",
            "k": 3,
            "host_filter": "xiaohongshu.com"
          },
          "save": "past_experience"
        }
      ],
      "on_success": "open_home"
    },
    "open_home": {
      "description": "打开小红书首页",
      "actions": [
        { "do": "ext.navigate", "url": "https://www.xiaohongshu.com/explore" },
        { "do": "ext.wait_quiet", "timeout_ms": 5000 }
      ],
      "on_success": "search",
      "on_error": "error_recovery"
    },
    "search": {
      "description": "搜索美食内容",
      "actions": [
        {
          "do": "ext.extract",
          "args": {
            "want": "inputs",
            "use_reducer": true
          },
          "save": "search_dom"
        },
        {
          "do": "llm_decide",
          "args": {
            "goal": "找到搜索框并输入'美食推荐'",
            "dom": "{{search_dom}}",
            "context": "{{past_experience}}",
            "allowed_actions": ["ext.click_selector", "ext.type_text"]
          }
        }
      ],
      "on_success": "interact_with_posts",
      "error_config": {
        "max_attempts": 3
      }
    },
    "interact_with_posts": {
      "description": "与搜索结果互动",
      "actions": [
        {
          "do": "ext.extract",
          "args": {
            "want": "links",
            "reducer": "auto"
          },
          "save": "posts_dom"
        },
        {
          "do": "macro.execute",
          "args": {
            "name": "xiaohongshu_like_posts",
            "params": {
              "post_count": 3,
              "dom_data": "{{posts_dom}}"
            }
          }
        }
      ],
      "on_success": "reflect_and_learn"
    },
    "reflect_and_learn": {
      "description": "反思和学习",
      "actions": [
        {
          "do": "plan.reflect",
          "args": {
            "focus": "success_patterns",
            "context": "{{execution_log}}",
            "goal": "improve xiaohongshu automation"
          },
          "save": "learning_insights"
        }
      ],
      "on_success": "done"
    },
    "error_recovery": {
      "description": "错误恢复",
      "actions": [
        { "do": "wait", "ms": 3000 },
        { "do": "ext.refresh" },
        { "do": "goto_state", "state": "open_home" }
      ]
    },
    "done": {
      "actions": [
        { "do": "ext.wait_quiet", "timeout_ms": 2000 }
      ]
    }
  }
}
```

## 🎯 配置最佳实践

1. **模块化配置**: 按功能分组配置，便于维护
2. **环境适配**: 为不同环境（开发/测试/生产）创建不同配置
3. **性能优化**: 根据任务复杂度调整各模块参数
4. **错误处理**: 为关键步骤配置充分的错误处理机制
5. **可观测性**: 启用详细日志和指标收集便于调试
6. **安全性**: 敏感信息使用环境变量或加密存储

通过组合使用这些配置模块，可以构建出功能强大、稳定可靠的自动化workflow！

---

# 8. 完整Action配置参考 {#complete-actions}

基于workflow.schema.json定义的所有可用动作类型的完整配置参考。

## 基础动作 (Basic Actions)

### a.sleep_ms - 等待延迟
```json
{
  "do": "sleep_ms",
  "args": {
    "duration": 2000,           // 等待毫秒数
    "reason": "page load"       // 可选：等待原因
  }
}
```

### a.open_url - 导航到URL
```json
{
  "do": "open_url",
  "args": {
    "url": "https://example.com",
    "wait_for_load": true,      // 等待页面加载完成
    "timeout_ms": 10000         // 超时时间
  }
}
```

### a.screenshot - 截图
```json
{
  "do": "screenshot",
  "args": {
    "save_path": "current_state.png",  // 保存路径
    "region": "full",                  // full | viewport | element
    "format": "png"                    // png | jpg | webp
  }
}
```

### a.wait_for - 等待条件
```json
{
  "do": "wait_for",
  "args": {
    "condition": "element_visible",    // 等待条件类型
    "selector": ".login-button",       // CSS选择器
    "timeout_ms": 15000,              // 超时时间
    "poll_interval_ms": 500           // 轮询间隔
  }
}
```

### a.goto_state - 状态跳转
```json
{
  "do": "goto_state",
  "args": {
    "state": "login_page",            // 目标状态名
    "reason": "login_required",       // 跳转原因
    "carry_variables": ["username"]   // 传递的变量
  }
}
```

## 检测动作 (Detection Actions)

### a.detect - 通用检测
```json
{
  "do": "detect",
  "args": {
    "type": "button",                 // 检测类型
    "confidence": 0.7,                // 置信度阈值
    "region": "viewport",             // 检测区域
    "max_results": 10                 // 最大结果数
  },
  "save": "detected_elements"
}
```

### a.locate - 元素定位
```json
{
  "do": "locate",
  "args": {
    "target": "login_button",         // 目标元素
    "method": "hybrid",               // 定位方法: vision | dom | hybrid
    "fallback": true                  // 启用回退策略
  },
  "save": "element_location"
}
```

### a.yolo_detect - YOLO目标检测
```json
{
  "do": "yolo_detect",
  "args": {
    "classes": ["button", "input"],   // 检测类别
    "confidence": 0.6,                // 置信度阈值
    "nms_threshold": 0.4,             // NMS阈值
    "model": "yolov8n"                // 模型版本
  },
  "save": "yolo_results"
}
```

## 浏览器交互动作 (Browser Actions)

### a.click - 点击
```json
{
  "do": "click",
  "args": {
    "selector": ".submit-btn",        // CSS选择器
    "coordinates": [100, 200],        // 可选：直接坐标
    "verify": true,                   // 验证点击效果
    "wait_after_ms": 1000            // 点击后等待时间
  }
}
```

### a.type_text - 输入文本
```json
{
  "do": "type_text",
  "args": {
    "selector": "input[name='username']",
    "text": "{{username}}",           // 支持变量替换
    "clear_first": true,             // 先清空输入框
    "simulate_typing": true,         // 模拟人类输入
    "typing_speed_ms": 100          // 输入速度
  }
}
```

### a.scroll - 滚动
```json
{
  "do": "scroll",
  "args": {
    "direction": "down",             // up | down | left | right
    "distance": 500,                 // 滚动距离（像素）
    "element": ".content",           // 可选：滚动容器
    "smooth": true                   // 平滑滚动
  }
}
```

### a.go_back - 浏览器后退
```json
{
  "do": "go_back",
  "args": {
    "steps": 1,                      // 后退步数
    "wait_for_load": true            // 等待页面加载
  }
}
```

### a.refresh - 刷新页面
```json
{
  "do": "refresh",
  "args": {
    "hard_refresh": false,           // 强制刷新
    "wait_for_load": true            // 等待加载完成
  }
}
```

## 扩展动作 (Extension Actions)

### a.ext.navigate - 扩展导航
```json
{
  "do": "ext.navigate",
  "args": {
    "url": "https://example.com",
    "new_tab": false,                // 是否新标签页
    "wait_for": "networkidle",       // 等待条件
    "timeout_ms": 30000
  }
}
```

### a.ext.click_selector - 扩展点击
```json
{
  "do": "ext.click_selector",
  "args": {
    "sel": ".login-button",
    "wait_for_element": true,        // 等待元素出现
    "scroll_into_view": true,        // 滚动到可视区域
    "force": false                   // 强制点击
  }
}
```

### a.ext.type_text - 扩展文本输入
```json
{
  "do": "ext.type_text",
  "args": {
    "sel": "input[type='password']",
    "text": "{{password}}",
    "mode": "type",                  // type | paste | simulate
    "clear": true,                   // 先清空
    "verify": true                   // 验证输入结果
  }
}
```

### a.ext.extract - 数据提取
```json
{
  "do": "ext.extract",
  "args": {
    "want": "inputs",                // inputs | buttons | links | text
    "limit": 50,                     // 最大提取数量
    "filters": {                     // 过滤条件
      "visible_only": true,
      "text_contains": "submit"
    },
    "use_reducer": true,             // 启用DOM精简
    "reducer_config": {
      "maxElements": 30
    }
  },
  "save": "extracted_data"
}
```

### a.ext.get_pagestate - 获取页面状态
```json
{
  "do": "ext.get_pagestate",
  "args": {
    "include_dom": true,             // 包含DOM信息
    "include_viewport": true,        // 包含视口信息
    "include_cookies": false,        // 包含Cookie
    "deep_scan": false              // 深度扫描
  },
  "save": "page_state"
}
```

### a.ext.wait_quiet - 等待页面安静
```json
{
  "do": "ext.wait_quiet",
  "args": {
    "timeout_ms": 10000,            // 超时时间
    "network_idle_ms": 2000,        // 网络空闲时间
    "no_mutations_ms": 1000,        // DOM无变化时间
    "ignore_images": true           // 忽略图片加载
  }
}
```

### a.ext.key - 按键操作
```json
{
  "do": "ext.key",
  "args": {
    "key": "Enter",                  // 按键名称
    "modifiers": ["Ctrl"],           // 修饰键
    "repeat": 1,                     // 重复次数
    "delay_ms": 100                 // 按键间隔
  }
}
```

## 指令动作 (Instruction Actions)

### a.instr.autostep - 自动步进
```json
{
  "do": "instr.autostep",
  "args": {
    "goal": "login to website",      // 执行目标
    "allowed_actions": [             // 允许的动作
      "ext.click_selector",
      "ext.type_text",
      "ext.key"
    ],
    "context": "{{page_context}}",   // 上下文信息
    "max_attempts": 3,               // 最大尝试次数
    "verification": {                // 验证配置
      "method": "dom_change",
      "timeout_ms": 5000
    }
  }
}
```

### a.instr.plan - 规划指令
```json
{
  "do": "instr.plan",
  "args": {
    "objective": "complete registration form",
    "constraints": {                 // 约束条件
      "max_steps": 10,
      "time_limit_ms": 60000,
      "allowed_domains": ["example.com"]
    },
    "context": "{{current_state}}",
    "strategy": "conservative"       // conservative | aggressive | balanced
  },
  "save": "execution_plan"
}
```

## LLM动作 (LLM Actions)

### a.llm_decide - LLM决策
```json
{
  "do": "llm_decide",
  "args": {
    "goal": "find and click submit button",
    "dom": "{{dom_snapshot}}",       // DOM数据
    "context": "{{context}}",        // 上下文
    "allowed_actions": [             // 允许的动作
      "ext.click_selector",
      "ext.type_text"
    ],
    "llm_provider": "gemini",        // 覆盖默认LLM
    "llm_model": "gemini-1.5-flash",
    "temperature": 0.3,
    "max_tokens": 1000,
    "strategy": {                    // 策略配置
      "approach": "step_by_step",
      "confidence_threshold": 0.8,
      "fallback_enabled": true
    }
  }
}
```

### a.llm.submit - LLM提交
```json
{
  "do": "llm.submit",
  "args": {
    "prompt": "Analyze this page and suggest next actions",
    "context": "{{page_data}}",
    "model": "gpt-4",
    "parameters": {
      "temperature": 0.1,
      "max_tokens": 2000,
      "top_p": 0.9
    },
    "format": "json",                // json | text | structured
    "schema": "action_plan"          // 输出格式约束
  },
  "save": "llm_response"
}
```

### a.llm.plan - LLM规划增强版
```json
{
  "do": "llm.plan",
  "args": {
    "strategy": "agentq",            // agentq | mcts | basic
    "planner_version_id": 3,         // 指定规划器版本
    "enable_ab_testing": true,       // 启用A/B测试
    "references": "{{recalled_memories}}", // RAG引用
    "constraints": {                 // 约束条件
      "max_steps": 8,
      "must_stay_in_host": "example.com",
      "no_dom_click": false
    },
    "inputs": {                      // 输入数据
      "page_state": "{{page_state}}",
      "user_goal": "{{goal}}"
    },
    "schema": "microplan_v2"         // 输出模式
  },
  "save": "enhanced_plan"
}
```

## 记忆动作 (Memory Actions)

### a.mem.recall - 记忆回调
```json
{
  "do": "mem.recall",
  "args": {
    "goal": "login to xiaohongshu",  // 查询目标
    "fingerprint": "{{page_fingerprint}}", // 页面指纹
    "k": 5,                          // 返回结果数
    "min_reward": 0.6,               // 最小奖励分数
    "since": "2024-01-01",           // 时间范围
    "filters": {                     // 过滤条件
      "host": "xiaohongshu.com",
      "success_only": true,
      "min_similarity": 0.7
    },
    "provider": "openai"             // 嵌入模型提供商
  },
  "save": "recalled_experiences"
}
```

### a.plan.reflect - 规划反思
```json
{
  "do": "plan.reflect",
  "args": {
    "when": "@step_count > 5 && @success_rate < 0.5", // 触发条件
    "focus": "error_analysis",       // 反思焦点
    "max_len": 500,                  // 最大长度
    "provider": "gpt-4",             // LLM提供商
    "context": {                     // 反思上下文
      "execution_log": "{{execution_log}}",
      "errors": "{{error_history}}",
      "goal": "{{original_goal}}"
    },
    "save": true                     // 保存反思结果
  },
  "save": "reflection_insights"
}
```

## 消息队列动作 (Message Queue Actions)

### a.mq.consume - 消费消息
```json
{
  "do": "mq.consume",
  "args": {
    "queue": "task_queue",           // 队列名称
    "timeout_ms": 30000,             // 超时时间
    "max_messages": 1,               // 最大消息数
    "auto_ack": false,               // 自动确认
    "message_format": "json"         // 消息格式
  },
  "save": "consumed_message"
}
```

### a.mq.ack - 确认消息
```json
{
  "do": "mq.ack",
  "args": {
    "message_id": "{{message.id}}",  // 消息ID
    "queue": "task_queue",           // 队列名称
    "success": true                  // 处理结果
  }
}
```

### a.mq.publish - 发布消息
```json
{
  "do": "mq.publish",
  "args": {
    "queue": "result_queue",         // 目标队列
    "message": {                     // 消息内容
      "type": "task_result",
      "data": "{{execution_result}}",
      "timestamp": "{{current_time}}"
    },
    "priority": 1,                   // 消息优先级
    "ttl_ms": 300000                // 消息TTL
  }
}
```

## OCR动作 (OCR Actions)

### a.ocr.run - OCR识别
```json
{
  "do": "ocr.run",
  "args": {
    "image": "{{screenshot}}",       // 图像数据
    "engine": "paddle",              // paddle | easy | tesseract
    "languages": ["en", "zh"],       // 识别语言
    "region": {                      // 识别区域
      "x": 0, "y": 0, "width": 800, "height": 600
    },
    "confidence_threshold": 0.7      // 置信度阈值
  },
  "save": "ocr_results"
}
```

### a.ocr_extract - OCR数据提取
```json
{
  "do": "ocr_extract",
  "args": {
    "target": "text_blocks",         // 提取目标
    "filters": {                     // 过滤条件
      "min_confidence": 0.8,
      "text_contains": "登录",
      "min_area": 100
    },
    "post_process": true,            // 后处理
    "merge_adjacent": true           // 合并相邻文本
  },
  "save": "extracted_text"
}
```

## 聊天动作 (Chat Actions)

### a.chat.send - 发送聊天消息
```json
{
  "do": "chat.send",
  "args": {
    "message": "Hello, how can I help?",
    "channel": "customer_support",   // 聊天频道
    "recipient": "{{user_id}}",      // 接收者
    "format": "text",                // text | markdown | html
    "attachments": []                // 附件列表
  }
}
```

### a.chat.receive - 接收聊天消息
```json
{
  "do": "chat.receive",
  "args": {
    "channel": "customer_support",
    "timeout_ms": 30000,            // 接收超时
    "filters": {                     // 消息过滤
      "from": "{{user_id}}",
      "type": "text"
    }
  },
  "save": "received_message"
}
```

## 系统动作 (System Actions)

### a.authenticate - 身份验证
```json
{
  "do": "authenticate",
  "args": {
    "method": "oauth2",              // 认证方法
    "provider": "google",            // 认证提供商
    "credentials": {                 // 认证凭据
      "client_id": "{{client_id}}",
      "client_secret": "{{client_secret}}"
    },
    "scope": ["read", "write"],      // 权限范围
    "redirect_uri": "{{callback_url}}"
  },
  "save": "auth_token"
}
```

### a.secure_operation - 安全操作
```json
{
  "do": "secure_operation",
  "args": {
    "operation": "sensitive_data_access",
    "security_level": "high",       // low | medium | high
    "verification": {                // 验证要求
      "mfa_required": true,
      "audit_log": true,
      "encryption": "aes256"
    },
    "timeout_ms": 60000             // 操作超时
  }
}
```

### a.platform_detect - 平台检测
```json
{
  "do": "platform_detect",
  "args": {
    "check_browser": true,           // 检测浏览器
    "check_os": true,                // 检测操作系统
    "check_device": true,            // 检测设备类型
    "check_capabilities": true       // 检测能力支持
  },
  "save": "platform_info"
}
```

## 测试动作 (Testing Actions)

### a.mock_service_setup - 模拟服务设置
```json
{
  "do": "mock_service_setup",
  "args": {
    "service": "payment_api",        // 服务名称
    "endpoints": [                   // 模拟端点
      {
        "path": "/charge",
        "method": "POST",
        "response": {"status": "success"},
        "delay_ms": 500
      }
    ],
    "failure_rate": 0.1              // 失败率
  }
}
```

### a.chaos_experiment - 混沌实验
```json
{
  "do": "chaos_experiment",
  "args": {
    "type": "network_delay",         // 实验类型
    "parameters": {                  // 实验参数
      "delay_ms": 2000,
      "jitter_ms": 500,
      "target_hosts": ["api.example.com"]
    },
    "duration_ms": 30000,           // 实验持续时间
    "rollback_on_failure": true     // 失败时回滚
  }
}
```

## 宏动作 (Macro Actions)

### a.macro.run - 执行宏
```json
{
  "do": "macro.run",
  "args": {
    "name": "login_sequence",        // 宏名称
    "args": {                        // 宏参数
      "username": "{{username}}",
      "password": "{{password}}",
      "remember_me": true,
      "index_offset": 0,
      "scroll_amount": -600
    },
    "constraints": {                 // 执行约束
      "max_steps": 10,
      "timeout_ms": 30000,
      "must_stay_in_host": "example.com"
    },
    "policy": {                      // 执行策略
      "allowed": ["click_coordinates", "ext.extract"],
      "per_step_timeout_ms": 5000
    }
  },
  "save": "macro_result"
}
```

### a.macro.validate - 验证宏
```json
{
  "do": "macro.validate",
  "args": {
    "name": "login_sequence",        // 宏名称
    "check_params": true,            // 检查参数
    "check_constraints": true,       // 检查约束
    "check_dependencies": true       // 检查依赖
  },
  "save": "validation_result"
}
```

### a.macro.list - 列出宏
```json
{
  "do": "macro.list",
  "args": {
    "host": "xiaohongshu.com",      // 可选：按域名过滤
    "category": "social_media",      // 可选：按类别过滤
    "include_metadata": true         // 包含元数据
  },
  "save": "available_macros"
}
```

## 坐标动作 (Coordinate Actions)

### a.click_coordinates - 坐标点击
```json
{
  "do": "click_coordinates",
  "args": {
    "bbox": "@ps.lists[0].itemRects[@i]",  // 目标矩形框
    "trace_tag": "click_job_item",         // 追踪标签
    "guard": {                             // 安全防护
      "source_vars_only": true            // 仅允许来自变量的坐标
    },
    "humanize": true                       // 人类化鼠标移动
  }
}
```

### a.wheel_coordinates - 坐标滚动
```json
{
  "do": "wheel_coordinates",
  "args": {
    "at_bbox": "@ps.panes.left.rect",     // 滚动容器
    "amount": -600,                       // 滚动量（负数向上）
    "trace_tag": "scroll_job_list"        // 追踪标签
  }
}
```

## 增强动作示例

### 复合动作组合
```json
{
  "do": "instr.autostep",
  "args": {
    "goal": "complete login with memory assistance",
    "pre_actions": [                      // 预处理动作
      {
        "do": "mem.recall",
        "args": {
          "goal": "login",
          "k": 3
        }
      }
    ],
    "main_action": {                      // 主要动作
      "do": "llm_decide",
      "args": {
        "goal": "login using recalled patterns",
        "context": "{{recalled_experiences}}"
      }
    },
    "post_actions": [                     // 后处理动作
      {
        "do": "plan.reflect",
        "args": {
          "focus": "login_success"
        }
      }
    ],
    "verification": {                     // 验证步骤
      "method": "multi_modal",
      "checks": ["dom_change", "url_change", "vision_confirm"]
    }
  }
}
```

### 错误处理增强
```json
{
  "do": "ext.click_selector",
  "args": {
    "sel": ".submit-button"
  },
  "error_handling": {                     // 错误处理配置
    "on_not_found": {                     // 元素未找到时
      "fallback": [
        {"do": "ext.click_selector", "sel": "button[type=submit]"},
        {"do": "ext.key", "key": "Enter"}
      ]
    },
    "on_click_failed": {                  // 点击失败时
      "retry": {
        "max_attempts": 3,
        "delay_ms": 1000,
        "backoff_factor": 1.5
      }
    },
    "on_timeout": {                       // 超时时
      "action": "goto_state",
      "state": "error_recovery"
    }
  }
}
```

---

# 9. 高级配置模式 {#advanced-patterns}

## 条件执行模式
```json
{
  "do": "llm_decide",
  "args": {
    "goal": "handle dynamic page state"
  },
  "conditions": {                         // 执行条件
    "if": "@page_state.login_required",  // 条件表达式
    "then": {                           // 满足条件时执行
      "do": "macro.run",
      "args": {"name": "login_sequence"}
    },
    "else": {                           // 不满足条件时执行
      "do": "goto_state",
      "state": "main_task"
    }
  }
}
```

## 并行执行模式
```json
{
  "do": "parallel_execute",
  "args": {
    "actions": [                          // 并行执行的动作列表
      {
        "do": "mem.recall",
        "args": {"goal": "pattern_A"}
      },
      {
        "do": "ext.extract",
        "args": {"want": "buttons"}
      },
      {
        "do": "vision.detect",
        "args": {"target": "submit_button"}
      }
    ],
    "wait_for": "all",                    // all | any | first_success
    "timeout_ms": 30000                   // 总体超时
  },
  "save": "parallel_results"
}
```

## 动态配置模式
```json
{
  "do": "ext.extract",
  "args": {
    "want": "{{extract_type}}",           // 动态参数
    "limit": "@config.performance_mode == 'fast' ? 20 : 50",
    "use_reducer": "@dom_element_count > 100",
    "reducer_config": {
      "maxElements": "@performance_budget"
    }
  }
}
```

## 链式验证模式
```json
{
  "do": "ext.click_selector",
  "args": {
    "sel": ".login-button"
  },
  "verification_chain": [                 // 验证链
    {
      "type": "dom_change",
      "timeout_ms": 2000,
      "required": true
    },
    {
      "type": "network_activity",
      "timeout_ms": 5000,
      "required": false
    },
    {
      "type": "visual_change",
      "timeout_ms": 3000,
      "required": true
    }
  ]
}
```

## 自适应重试模式
```json
{
  "do": "llm_decide",
  "args": {
    "goal": "submit form"
  },
  "adaptive_retry": {                     // 自适应重试
    "strategy": "exponential_backoff",
    "initial_delay_ms": 1000,
    "max_delay_ms": 10000,
    "max_attempts": 5,
    "success_criteria": [                 // 成功标准
      {"type": "dom_change", "weight": 0.6},
      {"type": "url_change", "weight": 0.4}
    ],
    "failure_adaptation": {               // 失败适应
      "increase_timeout": true,
      "reduce_confidence": true,
      "enable_fallback": true
    }
  }
}
```

## Task积木化动作 (Task Component Actions)

Task积木化系统提供可重用的工作流组件，支持模块化的复杂自动化任务构建。

### task.run - 执行任务组件
```json
{
  "do": "task.run",
  "name": "login_sequence",           // 任务名称
  "args": {                          // 任务参数
    "username": "@username",
    "password": "@password",
    "remember_me": true,
    "site_url": "https://example.com"
  },
  "version": "1.0",                  // 可选：指定版本
  "timeout_ms": 30000,               // 可选：任务超时
  "retry": {                         // 可选：重试配置
    "attempts": 3,
    "base_ms": 1000,
    "max_ms": 5000
  },
  "save": "task_result"              // 保存任务结果
}
```

### task.validate - 验证任务定义
```json
{
  "do": "task.validate",
  "name": "login_sequence",           // 要验证的任务名称
  "version": "1.0",                  // 可选：指定版本
  "strict": true,                    // 可选：严格验证模式
  "save": "validation_result"
}
```

### task.list - 列出可用任务
```json
{
  "do": "task.list",
  "category": "authentication",       // 可选：按类别筛选
  "host": "api.example.com",         // 可选：指定主机
  "tags": ["web", "login"],          // 可选：按标签筛选
  "version_filter": ">=1.0",        // 可选：版本过滤
  "save": "available_tasks"
}
```

### task.sync - 同步任务注册表
```json
{
  "do": "task.sync",
  "host": "registry.company.com",    // 注册表主机
  "auth": {                          // 可选：认证配置
    "type": "api_key",
    "token": "@api_token"
  },
  "categories": ["core", "custom"],  // 可选：同步特定类别
  "force_update": false,             // 可选：强制更新
  "save": "sync_status"
}
```

### task.install - 安装任务包
```json
{
  "do": "task.install",
  "name": "advanced_login",           // 任务包名称
  "version": "2.0",                  // 安装版本
  "source": "internal_registry",     // 可选：安装源
  "dependencies": "auto",            // 可选：依赖处理 (auto/skip/force)
  "overwrite": false,                // 可选：覆盖现有版本
  "verify_signature": true,          // 可选：验证数字签名
  "save": "install_result"
}
```

### Task组件定义示例
```json
{
  "task_definition": {
    "name": "enterprise_login",
    "version": "1.0",
    "description": "企业级登录流程组件",
    "category": "authentication",
    "tags": ["web", "enterprise", "2fa"],
    "parameters": {
      "username": {"type": "string", "required": true},
      "password": {"type": "string", "required": true, "sensitive": true},
      "site_url": {"type": "string", "required": true},
      "enable_2fa": {"type": "boolean", "default": false},
      "remember_me": {"type": "boolean", "default": true}
    },
    "preconditions": [                // 执行前置条件
      {"check": "network_available"},
      {"check": "browser_ready"}
    ],
    "postconditions": [               // 执行后置条件
      {"check": "login_successful"},
      {"check": "dashboard_loaded"}
    ],
    "implementation": {
      "type": "workflow",
      "path": "tasks/enterprise_login.json"
    },
    "estimated_duration_ms": 15000,   // 预估执行时间
    "success_rate": 0.95,            // 历史成功率
    "dependencies": ["basic_web_actions"] // 依赖的其他任务组件
  }
}
```

### Task执行上下文配置
```json
{
  "task_context": {
    "execution_mode": "isolated",     // isolated/shared/inherit
    "variable_scope": "local",        // local/global/hybrid
    "error_handling": {
      "on_failure": "rollback",       // rollback/continue/abort
      "max_retries": 3,
      "retry_delay_ms": 2000
    },
    "resource_limits": {
      "max_execution_time_ms": 60000,
      "max_memory_mb": 256,
      "max_network_calls": 50
    },
    "monitoring": {
      "track_performance": true,
      "log_level": "info",
      "capture_screenshots": false
    }
  }
}
```

### 复合任务流水线示例
```json
{
  "states": {
    "authentication_pipeline": {
      "actions": [
        {
          "do": "task.run",
          "name": "detect_login_form",
          "args": {"page_url": "@target_url"},
          "save": "form_info"
        },
        {
          "do": "task.run",
          "name": "fill_credentials",
          "args": {
            "form_data": "@form_info",
            "username": "@username",
            "password": "@password"
          },
          "save": "fill_result"
        },
        {
          "do": "task.run",
          "name": "handle_captcha",
          "args": {"form_context": "@fill_result"},
          "save": "captcha_result"
        },
        {
          "do": "task.run",
          "name": "submit_and_verify",
          "args": {
            "captcha_data": "@captcha_result",
            "expected_redirect": "/dashboard"
          },
          "save": "login_result"
        }
      ],
      "on_success": "post_login_tasks",
      "on_error": "login_recovery"
    }
  }
}
```

这个完整的Action配置参考涵盖了workflow.schema.json中定义的所有动作类型，包括最新的Task积木化系统，为构建复杂自动化workflow提供了全面的配置指导。
