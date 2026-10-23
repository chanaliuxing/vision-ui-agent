// Vision Fallback Module: DOM → Vision API integration for TQP execution
// Calls M3 Vision API when DOM-based automation fails

import { kvGet, kvSet } from './db.js';

let VISION_API_BASE = null;

async function ensureVisionAPI() {
  if (!VISION_API_BASE) {
    VISION_API_BASE = (await kvGet('vision_api_base')) || 'http://localhost:8000';
  }
  return VISION_API_BASE;
}

/**
 * Capture screenshot via chrome.tabs.captureVisibleTab
 * Returns base64 data URL for vision API
 */
async function captureScreenshot(tabId) {
  try {
    const dataUrl = await chrome.tabs.captureVisibleTab(null, {
      format: 'png',
      quality: 95
    });
    return dataUrl;
  } catch (error) {
    console.error('[VISION] Screenshot capture failed:', error);
    return null;
  }
}

/**
 * Convert base64 data URL to blob for API upload
 */
function dataUrlToBlob(dataUrl) {
  const [header, data] = dataUrl.split(',');
  const binary = atob(data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Blob([bytes], { type: 'image/png' });
}

/**
 * Call M3 Vision API /detect endpoint with label filtering
 * @param {string} screenshot - base64 data URL
 * @param {string[]} labels - UI element labels to filter for
 * @param {number} confidence - minimum detection confidence (default 0.5)
 * @returns {Promise<Object>} Vision API response with filtered detections
 */
async function callVisionAPI(screenshot, labels = [], confidence = 0.5) {
  await ensureVisionAPI();
  
  const formData = new FormData();
  formData.append('image', dataUrlToBlob(screenshot));
  
  // Build query params for label filtering
  const params = new URLSearchParams();
  if (labels.length > 0) {
    params.append('labels', labels.join(','));
  }
  params.append('confidence', confidence.toString());
  params.append('return_coords', 'true'); // Request center coordinates
  
  const url = `${VISION_API_BASE}/detect?${params.toString()}`;
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      body: formData
    });
    
    if (!response.ok) {
      throw new Error(`Vision API HTTP ${response.status}`);
    }
    
    const result = await response.json();
    console.log('[VISION] API response:', result);
    return result;
    
  } catch (error) {
    console.error('[VISION] API call failed:', error);
    throw error;
  }
}

/**
 * Convert vision detection to TQP-compatible selector
 * Returns CSS selector or coordinate-based identifier
 */
function visionToSelector(detection) {
  const { label, center, confidence, bbox } = detection;
  
  // For high-confidence detections, use coordinate-based selector
  if (confidence > 0.8 && center) {
    return {
      type: 'coordinate',
      selector: `vision:${center.x},${center.y}`,
      confidence,
      label,
      bbox
    };
  }
  
  // For lower confidence, use label-based hint
  return {
    type: 'label',
    selector: `[data-vision-label="${label}"]`,
    confidence,
    label,
    center,
    bbox
  };
}

/**
 * Click at vision-detected coordinates with proper DPR/zoom/scroll compensation
 * @param {number} tabId - Chrome tab ID
 * @param {Object} center - {x, y} coordinates from vision API (screenshot pixels)
 */
async function clickAtCoordinates(tabId, center) {
  // 1) Get viewport info and DPR from the page
  const [info] = await chrome.scripting.executeScript({
    target: { tabId, allFrames: false },
    world: 'MAIN',
    func: () => ({
      dpr: window.devicePixelRatio || 1,
      vw: window.innerWidth,
      vh: window.innerHeight,
      sx: window.scrollX,
      sy: window.scrollY,
    }),
  });
  
  if (!info?.result) {
    return { ok: false, reason: 'failed_to_get_viewport_info' };
  }
  
  const { dpr, vw, vh, sx, sy } = info.result;
  
  // 2) Convert screenshot pixels to CSS pixels
  const cssX = center.x / dpr;
  const cssY = center.y / dpr;
  
  // 3) Get chrome tab zoom factor
  let zoomFactor = 1;
  try {
    zoomFactor = await chrome.tabs.getZoom(tabId);
  } catch (e) {
    console.warn('[VISION] Could not get zoom factor, using 1.0');
  }
  
  // 4) Adjust for zoom
  const adjustedX = cssX / zoomFactor;
  const adjustedY = cssY / zoomFactor;
  
  // 5) Execute click with proper coordinate handling
  const result = await chrome.scripting.executeScript({
    target: { tabId, allFrames: false },
    world: 'MAIN',
    func: ({ cssX, cssY, targetInView }) => {
      // Scroll to center the target if it's out of view
      if (!targetInView) {
        const scrollToY = Math.max(cssY - window.innerHeight / 2, 0);
        window.scrollTo({ top: scrollToY, behavior: 'instant' });
      }
      
      // Clamp coordinates to viewport bounds
      const clampedX = Math.max(5, Math.min(cssX, window.innerWidth - 5));
      const clampedY = Math.max(5, Math.min(cssY, window.innerHeight - 5));
      
      const element = document.elementFromPoint(clampedX, clampedY);
      
      if (element) {
        const evtInit = { 
          clientX: clampedX, 
          clientY: clampedY, 
          bubbles: true, 
          cancelable: true 
        };
        
        // Simulate realistic mouse interaction sequence
        element.dispatchEvent(new MouseEvent('mousemove', evtInit));
        element.dispatchEvent(new MouseEvent('mousedown', evtInit));
        element.dispatchEvent(new MouseEvent('mouseup', evtInit));
        element.click();
        
        return { 
          ok: true, 
          tag: element.tagName, 
          text: element.innerText?.slice(0, 50),
          coords: { x: clampedX, y: clampedY },
          scrollAdjusted: !targetInView
        };
      } else {
        return { ok: false, reason: 'no_element_at_coordinates', coords: { x: clampedX, y: clampedY } };
      }
    },
    args: [{ 
      cssX: adjustedX, 
      cssY: adjustedY,
      targetInView: adjustedY >= 0 && adjustedY <= vh
    }]
  });
  
  return result?.[0]?.result || { ok: false, reason: 'script_execution_failed' };
}

/**
 * Vision fallback for TQP step execution
 * Called when DOM-based selector fails
 * @param {number} tabId - Chrome tab ID
 * @param {Object} step - TQP step with action details
 * @param {Object} actionSpec - Action specification from TQP
 * @returns {Promise<Object>} Execution result
 */
export async function visionFallback(tabId, step, actionSpec) {
  console.log('[VISION] Fallback triggered for step:', step.slot, actionSpec.type);
  
  try {
    // 1. Capture screenshot
    const screenshot = await captureScreenshot(tabId);
    if (!screenshot) {
      return { ok: false, reason: 'screenshot_failed' };
    }
    
    // 2. Determine target labels from step context
    const targetLabels = inferLabelsFromStep(step, actionSpec);
    
    // 3. Call vision API with label filtering
    const visionResult = await callVisionAPI(screenshot, targetLabels, 0.6);
    
    if (!visionResult.detections || visionResult.detections.length === 0) {
      return { ok: false, reason: 'no_vision_detections' };
    }
    
    // 4. Select best detection candidate
    const bestDetection = selectBestDetection(visionResult.detections, step, actionSpec);
    if (!bestDetection) {
      return { ok: false, reason: 'no_suitable_detection' };
    }
    
    // 5. Execute action based on detection type
    const selector = visionToSelector(bestDetection);
    let execResult;
    
    if (selector.type === 'coordinate' && actionSpec.type === 'click') {
      execResult = await clickAtCoordinates(tabId, bestDetection.center);
    } else {
      // Fall back to traditional selector-based execution
      const { clickSelector, typeSelector } = await import('./actions.js');
      
      if (actionSpec.type === 'click') {
        execResult = await clickSelector(tabId, selector.selector);
      } else if (actionSpec.type === 'type') {
        execResult = await typeSelector(tabId, selector.selector, actionSpec.text || '', { replace: actionSpec.replace !== false });
      } else {
        return { ok: false, reason: 'unsupported_vision_action' };
      }
    }
    
    console.log('[VISION] Fallback execution result:', execResult);
    
    return {
      ok: execResult.ok,
      reason: execResult.reason || null,
      vision_detection: bestDetection,
      selector_used: selector,
      method: 'vision_fallback'
    };
    
  } catch (error) {
    console.error('[VISION] Fallback execution failed:', error);
    return { ok: false, reason: error.message, method: 'vision_fallback' };
  }
}

/**
 * Infer target labels from TQP step context
 * Maps common UI interactions to vision labels
 */
function inferLabelsFromStep(step, actionSpec) {
  const labels = [];
  
  // Extract hints from step
  const slotLower = (step.slot || '').toLowerCase();
  const actionType = actionSpec.type;
  
  // Common label mappings
  if (slotLower.includes('search') || slotLower.includes('搜索')) {
    labels.push('search_box', 'textbox', 'input');
  }
  
  if (slotLower.includes('button') || slotLower.includes('btn') || actionType === 'click') {
    labels.push('button', 'clickable');
  }
  
  if (slotLower.includes('post') || slotLower.includes('item') || slotLower.includes('card')) {
    labels.push('post_card', 'list_item', 'clickable');
  }
  
  if (actionType === 'type' || slotLower.includes('input') || slotLower.includes('text')) {
    labels.push('textbox', 'input', 'textarea');
  }
  
  if (slotLower.includes('submit') || slotLower.includes('send') || slotLower.includes('确定')) {
    labels.push('submit_button', 'button');
  }
  
  // Default fallback
  if (labels.length === 0) {
    labels.push('clickable', 'button', 'textbox');
  }
  
  return [...new Set(labels)]; // Remove duplicates
}

/**
 * Select best detection candidate based on step context and confidence
 */
function selectBestDetection(detections, step, actionSpec) {
  if (detections.length === 0) return null;
  
  // Sort by confidence descending
  const sorted = detections.sort((a, b) => b.confidence - a.confidence);
  
  // For search actions, prefer high-confidence textbox detections
  if (step.slot?.toLowerCase().includes('search') || actionSpec.type === 'type') {
    const textInputs = sorted.filter(d => 
      ['textbox', 'search_box', 'input', 'textarea'].includes(d.label) && d.confidence > 0.7
    );
    if (textInputs.length > 0) return textInputs[0];
  }
  
  // For click actions, prefer buttons or clickable elements
  if (actionSpec.type === 'click') {
    const clickables = sorted.filter(d => 
      ['button', 'submit_button', 'clickable', 'post_card'].includes(d.label) && d.confidence > 0.6
    );
    if (clickables.length > 0) return clickables[0];
  }
  
  // Default: return highest confidence detection above threshold
  return sorted.find(d => d.confidence > 0.6) || sorted[0];
}

/**
 * Test vision fallback system
 * @param {number} tabId - Chrome tab ID
 * @returns {Promise<Object>} Test results
 */
export async function testVisionFallback(tabId) {
  try {
    const screenshot = await captureScreenshot(tabId);
    if (!screenshot) return { ok: false, reason: 'screenshot_failed' };
    
    const result = await callVisionAPI(screenshot, ['button', 'textbox', 'clickable'], 0.5);
    
    return {
      ok: true,
      detections_count: result.detections?.length || 0,
      detections: result.detections?.map(d => ({
        label: d.label,
        confidence: d.confidence,
        center: d.center
      })) || []
    };
  } catch (error) {
    return { ok: false, reason: error.message };
  }
}

/**
 * Configure vision API endpoint
 * @param {string} apiBase - Vision API base URL (e.g., 'http://localhost:8000')
 */
export async function setVisionAPIBase(apiBase) {
  await kvSet('vision_api_base', apiBase);
  VISION_API_BASE = apiBase;
  console.log('[VISION] API base configured:', apiBase);
}