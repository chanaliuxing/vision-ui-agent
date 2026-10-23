/**
 * Enhanced Extension Actions for Action Space v2
 * 增强的扩展动作，支持Action Space v2的统一指令集
 */

/**
 * 目标解析器 - 解析统一目标格式到DOM元素
 * @param {Object} target - 目标描述 {element_id?, css?, xpath?, role?, text?, bbox_var?}
 * @returns {Promise<Object|null>} - {nodeId, selector, stableId, bbox} 或 null
 */
async function resolveTarget(target) {
    if (!target) return null;

    let el = null;
    let resolveMethod = null;

    try {
        // 优先级：element_id -> css -> xpath -> role+text
        if (target.element_id) {
            el = document.getElementById(target.element_id);
            resolveMethod = "element_id";
        }

        if (!el && target.css) {
            el = document.querySelector(target.css);
            resolveMethod = "css";
        }

        if (!el && target.xpath) {
            const result = document.evaluate(
                target.xpath,
                document,
                null,
                XPathResult.FIRST_ORDERED_NODE_TYPE,
                null
            );
            el = result.singleNodeValue;
            resolveMethod = "xpath";
        }

        if (!el && (target.role || target.text)) {
            el = findByRoleText(target.role, target.text);
            resolveMethod = "role_text";
        }

        if (!el) return null;

        // 获取元素信息
        const rect = el.getBoundingClientRect();
        const screenRect = toScreenRect(rect);
        const dpr = window.devicePixelRatio || 1;
        const zoom = getZoom();

        // 生成稳定选择器
        const stableId = el.id || el.getAttribute('data-testid');
        const selector = target.css || (stableId ? `#${stableId}` : generateSelector(el));

        return {
            nodeId: 0, // 如需CDP，可在此获取
            selector: selector,
            stableId: stableId,
            bbox: {
                x: screenRect.x,
                y: screenRect.y,
                w: screenRect.w,
                h: screenRect.h,
                dpr: dpr,
                zoom: zoom
            },
            element: el,
            resolveMethod: resolveMethod
        };

    } catch (error) {
        console.warn('Target resolution failed:', error);
        return null;
    }
}

/**
 * 基于role和text查找元素
 */
function findByRoleText(role, text) {
    if (!role && !text) return null;

    // 构建role选择器
    const roleSelector = role ? `[role="${role}"], ${role}` : '*';
    const candidates = Array.from(document.querySelectorAll(roleSelector));

    if (!text) return candidates[0] || null;

    // 文本匹配
    const normalizeText = (str) => str.replace(/\s+/g, ' ').trim().toLowerCase();
    const targetText = normalizeText(text);

    for (const el of candidates) {
        const elementText = normalizeText(
            el.innerText || el.getAttribute('aria-label') || el.textContent || ''
        );
        if (elementText.includes(targetText)) {
            return el;
        }
    }

    // 回退：全局文本搜索
    const allElements = document.querySelectorAll('button,a,[role],div,span,input,textarea');
    for (const el of allElements) {
        const elementText = normalizeText(el.innerText || el.textContent || '');
        if (elementText.includes(targetText)) {
            return el;
        }
    }

    return null;
}

/**
 * 转换为屏幕坐标
 */
function toScreenRect(rect) {
    return {
        x: rect.left + window.scrollX,
        y: rect.top + window.scrollY,
        w: rect.width,
        h: rect.height
    };
}

/**
 * 获取页面缩放
 */
function getZoom() {
    return window.devicePixelRatio || 1;
}

/**
 * 生成CSS选择器
 */
function generateSelector(element) {
    if (element.id) return `#${element.id}`;

    const path = [];
    let current = element;

    while (current && current.nodeType === Node.ELEMENT_NODE) {
        let selector = current.nodeName.toLowerCase();

        if (current.className) {
            const classes = current.className.split(/\s+/).filter(c => c && /^[a-zA-Z]/.test(c));
            if (classes.length > 0) {
                selector += '.' + classes.slice(0, 2).join('.');
            }
        }

        path.unshift(selector);
        current = current.parentElement;

        if (path.length > 4) break; // 限制深度
    }

    return path.join(' > ');
}

/**
 * 增强的点击功能
 */
async function extClickEnhanced(selectorOrElement) {
    let element;

    if (typeof selectorOrElement === 'string') {
        element = document.querySelector(selectorOrElement);
    } else if (selectorOrElement && selectorOrElement.element) {
        element = selectorOrElement.element;
    } else {
        element = selectorOrElement;
    }

    if (!element) {
        throw new Error('Element not found for clicking');
    }

    // 确保元素可见
    element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    await new Promise(resolve => setTimeout(resolve, 100));

    // 触发完整的点击事件序列
    const rect = element.getBoundingClientRect();
    const clientX = rect.left + rect.width / 2;
    const clientY = rect.top + rect.height / 2;

    const events = [
        new MouseEvent('mousedown', { bubbles: true, clientX, clientY }),
        new MouseEvent('mouseup', { bubbles: true, clientX, clientY }),
        new MouseEvent('click', { bubbles: true, clientX, clientY })
    ];

    for (const event of events) {
        element.dispatchEvent(event);
        await new Promise(resolve => setTimeout(resolve, 10));
    }

    return { ok: true, element: element.tagName, clicked_at: { x: clientX, y: clientY } };
}

/**
 * 增强的文本输入功能
 */
async function extTypeTextEnhanced(selector, text, options = {}) {
    const element = typeof selector === 'string'
        ? document.querySelector(selector)
        : (selector.element || selector);

    if (!element) {
        throw new Error('Element not found for typing');
    }

    const { replace = false, mode = 'type' } = options;

    // 聚焦元素
    element.focus();
    await new Promise(resolve => setTimeout(resolve, 50));

    // 清空（如果需要）
    if (replace) {
        element.value = '';
        element.dispatchEvent(new Event('input', { bubbles: true }));
    }

    if (mode === 'paste') {
        // 粘贴模式
        element.value = (element.value || '') + text;
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
        // 逐字符输入模式
        for (const char of text) {
            element.value = (element.value || '') + char;

            // 触发输入事件
            element.dispatchEvent(new KeyboardEvent('keydown', {
                key: char, bubbles: true
            }));
            element.dispatchEvent(new Event('input', { bubbles: true }));
            element.dispatchEvent(new KeyboardEvent('keyup', {
                key: char, bubbles: true
            }));

            await new Promise(resolve => setTimeout(resolve, 20)); // 模拟打字速度
        }

        element.dispatchEvent(new Event('change', { bubbles: true }));
    }

    return { ok: true, text_length: text.length, element: element.tagName };
}

/**
 * 选择选项功能
 */
async function extSelectOption(selector, valueOrText) {
    const element = typeof selector === 'string'
        ? document.querySelector(selector)
        : (selector.element || selector);

    if (!element || element.tagName.toLowerCase() !== 'select') {
        throw new Error('Element is not a select element');
    }

    const options = Array.from(element.options);
    let matched = false;

    if (typeof valueOrText === 'number') {
        // 按索引选择
        const index = Math.max(0, Math.min(options.length - 1, valueOrText));
        element.selectedIndex = index;
        matched = true;
    } else {
        const value = String(valueOrText);

        // 先按value匹配
        const byValue = options.findIndex(option => option.value === value);
        if (byValue >= 0) {
            element.selectedIndex = byValue;
            matched = true;
        } else {
            // 再按文本匹配
            const byText = options.findIndex(option => option.text.trim() === value);
            if (byText >= 0) {
                element.selectedIndex = byText;
                matched = true;
            }
        }
    }

    if (matched) {
        // 触发变化事件
        element.dispatchEvent(new Event('change', { bubbles: true }));
        element.dispatchEvent(new Event('input', { bubbles: true }));

        return {
            ok: true,
            selected_index: element.selectedIndex,
            selected_value: element.value,
            selected_text: element.options[element.selectedIndex]?.text
        };
    }

    throw new Error(`Option not found: ${valueOrText}`);
}

/**
 * 悬停功能
 */
async function extHover(selector) {
    const element = typeof selector === 'string'
        ? document.querySelector(selector)
        : (selector.element || selector);

    if (!element) {
        throw new Error('Element not found for hovering');
    }

    const rect = element.getBoundingClientRect();
    const clientX = rect.left + rect.width / 2;
    const clientY = rect.top + rect.height / 2;

    // 触发悬停事件序列
    const events = [
        new MouseEvent('mouseover', { bubbles: true, clientX, clientY }),
        new MouseEvent('mouseenter', { bubbles: true, clientX, clientY }),
        new MouseEvent('mousemove', { bubbles: true, clientX, clientY })
    ];

    for (const event of events) {
        element.dispatchEvent(event);
        await new Promise(resolve => setTimeout(resolve, 50));
    }

    return { ok: true, element: element.tagName, hovered_at: { x: clientX, y: clientY } };
}

/**
 * 文件上传功能（需要CDP支持）
 */
async function extUploadFile(selector, filePath) {
    const element = typeof selector === 'string'
        ? document.querySelector(selector)
        : (selector.element || selector);

    if (!element || element.type !== 'file') {
        throw new Error('Element is not a file input');
    }

    // 这里需要通过CDP的DOM.setFileInputFiles来实现
    // 由于安全限制，JavaScript无法直接设置文件路径
    throw new Error('File upload requires CDP backend support');
}

/**
 * 等待页面安静增强版
 */
async function extWaitQuietEnhanced(options = {}) {
    const {
        timeout_ms = 10000,
        network_idle_ms = 2000,
        no_mutations_ms = 1000,
        ignore_images = true
    } = options;

    const startTime = Date.now();
    let lastActivity = Date.now();

    // 监控网络活动
    let activeRequests = 0;
    const originalFetch = window.fetch;
    const originalXHROpen = XMLHttpRequest.prototype.open;

    // 拦截fetch
    window.fetch = async (...args) => {
        activeRequests++;
        try {
            const response = await originalFetch(...args);
            return response;
        } finally {
            activeRequests--;
            lastActivity = Date.now();
        }
    };

    // 拦截XHR
    XMLHttpRequest.prototype.open = function(...args) {
        activeRequests++;
        this.addEventListener('loadend', () => {
            activeRequests--;
            lastActivity = Date.now();
        });
        return originalXHROpen.apply(this, args);
    };

    // 监控DOM变化
    let lastMutation = Date.now();
    const observer = new MutationObserver(() => {
        lastMutation = Date.now();
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true
    });

    try {
        while (Date.now() - startTime < timeout_ms) {
            const now = Date.now();

            // 检查网络是否安静
            const networkQuiet = activeRequests === 0 && (now - lastActivity) >= network_idle_ms;

            // 检查DOM是否安静
            const domQuiet = (now - lastMutation) >= no_mutations_ms;

            if (networkQuiet && domQuiet) {
                break;
            }

            await new Promise(resolve => setTimeout(resolve, 100));
        }

        return { ok: true, waited_ms: Date.now() - startTime };

    } finally {
        // 恢复原始函数
        window.fetch = originalFetch;
        XMLHttpRequest.prototype.open = originalXHROpen;
        observer.disconnect();
    }
}

/**
 * 导出所有增强功能
 */
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        resolveTarget,
        extClickEnhanced,
        extTypeTextEnhanced,
        extSelectOption,
        extHover,
        extUploadFile,
        extWaitQuietEnhanced
    };
} else {
    // 浏览器环境，添加到全局对象
    window.enhancedActions = {
        resolveTarget,
        extClickEnhanced,
        extTypeTextEnhanced,
        extSelectOption,
        extHover,
        extUploadFile,
        extWaitQuietEnhanced
    };
}