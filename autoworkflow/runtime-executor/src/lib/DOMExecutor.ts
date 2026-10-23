// M3: DOM Executor - Chrome Extension based DOM automation

import { EventEmitter } from 'events';
import type {
  DOMAction,
  DOMExecutionResult,
  ExecutionContext,
  ChromeExtensionConnection,
  BrowserContext
} from '../types/index.js';
import { ChromeExtensionBridge } from './ChromeExtensionBridge.js';
import {
  normalizeButton,
  getClickTiming,
  getMovementParams,
  parseComboKeys,
  performMultipleClicks,
  KeyboardSequence,
  MouseActions,
  sleep
} from './MouseKeyboardUtils.js';
import {
  ClipboardManager,
  FileManager,
  ShellManager,
  WindowManager,
  normalizeKeyName,
  getPlatformKeyCombo
} from './BasicActionsUtils.js';

export class DOMExecutor extends EventEmitter {
  private chromeExtensionBridge: ChromeExtensionBridge;
  private chromeExtension?: ChromeExtensionConnection;
  private browser?: BrowserContext;

  constructor(
    chromeExtension?: ChromeExtensionConnection,
    browser?: BrowserContext
  ) {
    super();

    this.chromeExtension = chromeExtension;
    this.browser = browser;
    this.chromeExtensionBridge = new ChromeExtensionBridge();

    // Forward Chrome Extension events
    this.chromeExtensionBridge.on('connected', () => {
      this.emit('chrome_connected');
    });

    this.chromeExtensionBridge.on('disconnected', () => {
      this.emit('chrome_disconnected');
    });

    this.chromeExtensionBridge.on('error', (error) => {
      this.emit('chrome_error', error);
    });
  }

  /**
   * Execute DOM action
   */
  async execute(
    action: DOMAction,
    context: ExecutionContext
  ): Promise<DOMExecutionResult> {
    this.emit('dom_action', { action, context });

    try {
      // Validate action
      this.validateAction(action);

      // Choose execution method based on availability
      if (this.chromeExtensionBridge.isConnected()) {
        return await this.executeViaExtension(action, context);
      } else if (this.browser) {
        return await this.executeViaPuppeteer(action, context);
      } else {
        return {
          success: false,
          method: 'dom',
          error: 'No DOM execution method available (Chrome Extension or Puppeteer)',
          fallbackRequired: true
        };
      }

    } catch (error: any) {
      return {
        success: false,
        method: 'dom',
        error: error.message,
        fallbackRequired: true
      };
    }
  }

  /**
   * Validate DOM action
   */
  private validateAction(action: DOMAction): void {
    if (!action.type) {
      throw new Error('DOM action type is required');
    }

    switch (action.type) {
      case 'click':
      case 'context_click':
        if (!action.selector && !action.xpath && !action.coordinates) {
          throw new Error('Click action requires selector, xpath, or coordinates');
        }
        break;

      case 'type':
        if (!action.text) {
          throw new Error('Type action requires text');
        }
        if (!action.selector && !action.xpath) {
          throw new Error('Type action requires selector or xpath');
        }
        break;

      case 'navigate':
        if (!action.options?.url) {
          throw new Error('Navigate action requires URL');
        }
        break;

      case 'extract':
        if (!action.selector && !action.xpath) {
          throw new Error('Extract action requires selector or xpath');
        }
        break;

      case 'mouse_move':
      case 'mouse_drag':
        if (!action.to && !action.by) {
          throw new Error(`${action.type} action requires either "to" or "by" parameters`);
        }
        break;

      case 'key_combo':
        if (!action.combo) {
          throw new Error('key_combo action requires "combo" parameter');
        }
        break;

      case 'key_sequence':
        if (!action.sequence || !Array.isArray(action.sequence)) {
          throw new Error('key_sequence action requires "sequence" array parameter');
        }
        break;

      // Basic clipboard actions
      case 'clipboard_push':
      case 'clipboard_pop':
      case 'clipboard_clear':
        break;

      case 'clipboard_get':
      case 'clipboard_set':
        if (action.type === 'clipboard_set' && !action.content) {
          throw new Error('clipboard_set action requires "content" parameter');
        }
        break;

      case 'clipboard_copy_selection':
        break;

      // Enhanced mouse actions
      case 'mouse_triple_click':
      case 'mouse_right_click':
      case 'mouse_middle_click':
        if (!action.coordinates && !action.selector && !action.xpath) {
          throw new Error(`${action.type} action requires coordinates, selector, or xpath`);
        }
        break;

      case 'mouse_wheel':
        break;

      case 'mouse_move_only':
        if (!action.coordinates && !action.to && !action.by) {
          throw new Error('mouse_move_only action requires coordinates, "to", or "by" parameters');
        }
        break;

      // Enhanced keyboard actions
      case 'key_down':
      case 'key_up':
        if (!action.key) {
          throw new Error(`${action.type} action requires "key" parameter`);
        }
        break;

      case 'key_select_all':
      case 'key_copy':
      case 'key_cut':
      case 'key_paste':
      case 'key_toggle_ime':
        break;

      // Window operations
      case 'window_focus':
        if (!action.title && !action.window_id) {
          throw new Error('window_focus action requires "title" or "window_id" parameter');
        }
        break;

      case 'window_minimize':
      case 'window_close':
        break;

      // System operations
      case 'os_shell':
        if (!action.command) {
          throw new Error('os_shell action requires "command" parameter');
        }
        break;

      case 'os_activate_app':
      case 'os_launch_app':
        if (!action.app_name && !action.app_names && !action.app_path) {
          throw new Error(`${action.type} action requires "app_name", "app_names", or "app_path" parameter`);
        }
        break;

      // File operations
      case 'file_read':
      case 'file_remove':
        if (!action.path) {
          throw new Error(`${action.type} action requires "path" parameter`);
        }
        break;

      case 'file_write':
        if (!action.path || action.data === undefined) {
          throw new Error('file_write action requires "path" and "data" parameters');
        }
        break;

      case 'file_mkdir':
        if (!action.path) {
          throw new Error('file_mkdir action requires "path" parameter');
        }
        break;

      case 'file_copy':
      case 'file_move':
        if (!action.path || !action.options?.destination) {
          throw new Error(`${action.type} action requires "path" and "destination" parameters`);
        }
        break;

      case 'file_list':
        if (!action.path) {
          throw new Error('file_list action requires "path" parameter');
        }
        break;

      case 'scroll':
      case 'wait':
      case 'mouse_down':
      case 'mouse_up':
        // These actions have optional parameters
        break;

      default:
        throw new Error(`Unsupported DOM action type: ${action.type}`);
    }
  }

  /**
   * Execute action via Chrome Extension
   */
  private async executeViaExtension(
    action: DOMAction,
    context: ExecutionContext
  ): Promise<DOMExecutionResult> {
    try {
      const result = await this.chromeExtensionBridge.executeDOMAction(action, context);

      this.emit('extension_result', { action, result });

      return result;

    } catch (error: any) {
      return {
        success: false,
        method: 'dom',
        error: `Chrome Extension execution failed: ${error.message}`,
        fallbackRequired: true
      };
    }
  }

  /**
   * Execute action via Puppeteer (fallback)
   */
  private async executeViaPuppeteer(
    action: DOMAction,
    context: ExecutionContext
  ): Promise<DOMExecutionResult> {
    if (!this.browser?.page) {
      return {
        success: false,
        method: 'dom',
        error: 'Puppeteer page not available',
        fallbackRequired: true
      };
    }

    try {
      const page = this.browser.page;
      let result: any;

      switch (action.type) {
        case 'click':
          result = await this.puppeteerClick(page, action);
          break;

        case 'context_click':
          result = await this.puppeteerContextClick(page, action);
          break;

        case 'type':
          result = await this.puppeteerType(page, action);
          break;

        case 'scroll':
          result = await this.puppeteerScroll(page, action);
          break;

        case 'wait':
          result = await this.puppeteerWait(page, action);
          break;

        case 'navigate':
          result = await this.puppeteerNavigate(page, action);
          break;

        case 'extract':
          result = await this.puppeteerExtract(page, action);
          break;

        case 'mouse_down':
          result = await this.puppeteerMouseDown(page, action);
          break;

        case 'mouse_up':
          result = await this.puppeteerMouseUp(page, action);
          break;

        case 'mouse_move':
          result = await this.puppeteerMouseMove(page, action);
          break;

        case 'mouse_drag':
          result = await this.puppeteerMouseDrag(page, action);
          break;

        case 'key_combo':
          result = await this.puppeteerKeyCombo(page, action);
          break;

        case 'key_sequence':
          result = await this.puppeteerKeySequence(page, action);
          break;

        // Clipboard actions
        case 'clipboard_push':
          result = await this.executeClipboardPush(action);
          break;

        case 'clipboard_pop':
          result = await this.executeClipboardPop(action);
          break;

        case 'clipboard_clear':
          result = await this.executeClipboardClear(action);
          break;

        case 'clipboard_get':
          result = await this.executeClipboardGet(action);
          break;

        case 'clipboard_set':
          result = await this.executeClipboardSet(action);
          break;

        case 'clipboard_copy_selection':
          result = await this.executeClipboardCopySelection(action);
          break;

        // Enhanced mouse actions
        case 'mouse_triple_click':
          result = await this.puppeteerTripleClick(page, action);
          break;

        case 'mouse_right_click':
          result = await this.puppeteerRightClick(page, action);
          break;

        case 'mouse_middle_click':
          result = await this.puppeteerMiddleClick(page, action);
          break;

        case 'mouse_wheel':
          result = await this.puppeteerMouseWheel(page, action);
          break;

        case 'mouse_move_only':
          result = await this.puppeteerMouseMoveOnly(page, action);
          break;

        // Enhanced keyboard actions
        case 'key_down':
          result = await this.puppeteerKeyDown(page, action);
          break;

        case 'key_up':
          result = await this.puppeteerKeyUp(page, action);
          break;

        case 'key_select_all':
          result = await this.puppeteerKeySelectAll(page, action);
          break;

        case 'key_copy':
          result = await this.puppeteerKeyCopy(page, action);
          break;

        case 'key_cut':
          result = await this.puppeteerKeyCut(page, action);
          break;

        case 'key_paste':
          result = await this.puppeteerKeyPaste(page, action);
          break;

        case 'key_toggle_ime':
          result = await this.puppeteerKeyToggleIme(page, action);
          break;

        // Window operations
        case 'window_focus':
          result = await this.executeWindowFocus(action);
          break;

        case 'window_minimize':
          result = await this.executeWindowMinimize(action);
          break;

        case 'window_close':
          result = await this.executeWindowClose(action);
          break;

        // System operations
        case 'os_shell':
          result = await this.executeOsShell(action);
          break;

        case 'os_activate_app':
          result = await this.executeOsActivateApp(action);
          break;

        case 'os_launch_app':
          result = await this.executeOsLaunchApp(action);
          break;

        // File operations
        case 'file_read':
          result = await this.executeFileRead(action);
          break;

        case 'file_write':
          result = await this.executeFileWrite(action);
          break;

        case 'file_mkdir':
          result = await this.executeFileMkdir(action);
          break;

        case 'file_remove':
          result = await this.executeFileRemove(action);
          break;

        case 'file_copy':
          result = await this.executeFileCopy(action);
          break;

        case 'file_move':
          result = await this.executeFileMove(action);
          break;

        case 'file_list':
          result = await this.executeFileList(action);
          break;

        default:
          throw new Error(`Puppeteer doesn't support action type: ${action.type}`);
      }

      // Take screenshot
      const screenshot = await page.screenshot({ encoding: 'base64' });

      this.emit('puppeteer_result', { action, result });

      return {
        success: true,
        method: 'dom',
        output: result,
        screenshot: `data:image/png;base64,${screenshot}`
      };

    } catch (error: any) {
      return {
        success: false,
        method: 'dom',
        error: `Puppeteer execution failed: ${error.message}`,
        fallbackRequired: true
      };
    }
  }

  /**
   * Puppeteer click implementation
   */
  private async puppeteerClick(page: any, action: DOMAction): Promise<any> {
    const { times, interval } = getClickTiming(action);
    const button = normalizeButton(action.button);

    if (action.coordinates) {
      await performMultipleClicks(
        async () => {
          await page.mouse.click(action.coordinates!.x, action.coordinates!.y, { button });
        },
        times,
        interval
      );
      return { clicked: true, coordinates: action.coordinates, times, interval, button };
    }

    const selector = action.selector || action.xpath;
    if (!selector) {
      throw new Error('No selector or coordinates provided for click');
    }

    if (action.xpath) {
      const elements = await page.$x(action.xpath);
      if (elements.length === 0) {
        throw new Error(`Element not found with xpath: ${action.xpath}`);
      }

      await performMultipleClicks(
        async () => {
          await elements[0].click({ button });
        },
        times,
        interval
      );
    } else {
      await performMultipleClicks(
        async () => {
          await page.click(action.selector, { button });
        },
        times,
        interval
      );
    }

    return { clicked: true, selector, times, interval, button };
  }

  /**
   * Puppeteer type implementation
   */
  private async puppeteerType(page: any, action: DOMAction): Promise<any> {
    const selector = action.selector || action.xpath;

    if (action.xpath) {
      const elements = await page.$x(action.xpath);
      if (elements.length === 0) {
        throw new Error(`Element not found with xpath: ${action.xpath}`);
      }
      await elements[0].click();
      await elements[0].type(action.text);
    } else {
      await page.click(action.selector);
      await page.type(action.selector, action.text);
    }

    return { typed: true, text: action.text, selector };
  }

  /**
   * Puppeteer scroll implementation
   */
  private async puppeteerScroll(page: any, action: DOMAction): Promise<any> {
    const direction = action.options?.direction || 'down';
    const amount = action.options?.amount || 3;

    if (action.selector) {
      await page.evaluate((sel: string, dir: string, amt: number) => {
        const element = document.querySelector(sel);
        if (element) {
          const scrollAmount = amt * 100;
          if (dir === 'down') {
            element.scrollTop += scrollAmount;
          } else if (dir === 'up') {
            element.scrollTop -= scrollAmount;
          }
        }
      }, action.selector, direction, amount);
    } else {
      await page.evaluate((dir: string, amt: number) => {
        const scrollAmount = amt * 100;
        if (dir === 'down') {
          window.scrollBy(0, scrollAmount);
        } else if (dir === 'up') {
          window.scrollBy(0, -scrollAmount);
        }
      }, direction, amount);
    }

    return { scrolled: true, direction, amount };
  }

  /**
   * Puppeteer wait implementation
   */
  private async puppeteerWait(page: any, action: DOMAction): Promise<any> {
    const timeout = action.options?.timeout || 5000;
    const visible = action.options?.visible !== false;

    if (action.selector) {
      await page.waitForSelector(action.selector, {
        timeout,
        visible
      });
      return { waited: true, selector: action.selector, timeout };
    } else {
      // Wait for specified time
      await new Promise(resolve => setTimeout(resolve, timeout));
      return { waited: true, timeout };
    }
  }

  /**
   * Puppeteer navigate implementation
   */
  private async puppeteerNavigate(page: any, action: DOMAction): Promise<any> {
    const url = action.options?.url;
    await page.goto(url, { waitUntil: 'networkidle2' });
    return { navigated: true, url };
  }

  /**
   * Puppeteer extract implementation
   */
  private async puppeteerExtract(page: any, action: DOMAction): Promise<any> {
    const selector = action.selector || action.xpath;
    const attribute = action.options?.attribute;
    const multiple = action.options?.multiple;

    if (action.xpath) {
      const elements = await page.$x(action.xpath);
      if (elements.length === 0) {
        throw new Error(`Elements not found with xpath: ${action.xpath}`);
      }

      if (multiple) {
        const results = [];
        for (const element of elements) {
          const value = attribute
            ? await element.getProperty(attribute).then((p: any) => p.jsonValue())
            : await element.evaluate((el: any) => el.textContent);
          results.push(value);
        }
        return { extracted: results, multiple: true };
      } else {
        const element = elements[0];
        const value = attribute
          ? await element.getProperty(attribute).then((p: any) => p.jsonValue())
          : await element.evaluate((el: any) => el.textContent);
        return { extracted: value, multiple: false };
      }
    } else {
      const result = await page.evaluate((sel: string, attr: string, mult: boolean) => {
        if (mult) {
          const elements = document.querySelectorAll(sel);
          return Array.from(elements).map((el: any) =>
            attr ? el.getAttribute(attr) || el[attr] : el.textContent
          );
        } else {
          const element = document.querySelector(sel);
          if (!element) return null;
          return attr ? (element as any).getAttribute(attr) || (element as any)[attr] : element.textContent;
        }
      }, action.selector, attribute, multiple);

      return { extracted: result, multiple: !!multiple };
    }
  }

  /**
   * Puppeteer context click implementation (right-click)
   */
  private async puppeteerContextClick(page: any, action: DOMAction): Promise<any> {
    if (action.coordinates) {
      await page.mouse.click(action.coordinates.x, action.coordinates.y, { button: 'right' });
      return { contextClicked: true, coordinates: action.coordinates };
    }

    const selector = action.selector || action.xpath;
    if (!selector) {
      throw new Error('No selector or coordinates provided for context click');
    }

    if (action.xpath) {
      const elements = await page.$x(action.xpath);
      if (elements.length === 0) {
        throw new Error(`Element not found with xpath: ${action.xpath}`);
      }
      await elements[0].click({ button: 'right' });
    } else {
      await page.click(action.selector, { button: 'right' });
    }

    return { contextClicked: true, selector };
  }

  /**
   * Puppeteer mouse down implementation
   */
  private async puppeteerMouseDown(page: any, action: DOMAction): Promise<any> {
    const button = normalizeButton(action.button);

    if (action.coordinates) {
      await page.mouse.move(action.coordinates.x, action.coordinates.y);
      await page.mouse.down({ button });
      return { mouseDown: true, button, coordinates: action.coordinates };
    }

    const selector = action.selector || action.xpath;
    if (selector) {
      if (action.xpath) {
        const elements = await page.$x(action.xpath);
        if (elements.length === 0) {
          throw new Error(`Element not found with xpath: ${action.xpath}`);
        }
        const box = await elements[0].boundingBox();
        if (box) {
          await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
          await page.mouse.down({ button });
        }
      } else {
        const element = await page.$(action.selector);
        if (!element) {
          throw new Error(`Element not found with selector: ${action.selector}`);
        }
        const box = await element.boundingBox();
        if (box) {
          await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
          await page.mouse.down({ button });
        }
      }
      return { mouseDown: true, button, selector };
    }

    // Mouse down at current position
    await page.mouse.down({ button });
    return { mouseDown: true, button };
  }

  /**
   * Puppeteer mouse up implementation
   */
  private async puppeteerMouseUp(page: any, action: DOMAction): Promise<any> {
    const button = normalizeButton(action.button);

    if (action.coordinates) {
      await page.mouse.move(action.coordinates.x, action.coordinates.y);
      await page.mouse.up({ button });
      return { mouseUp: true, button, coordinates: action.coordinates };
    }

    const selector = action.selector || action.xpath;
    if (selector) {
      if (action.xpath) {
        const elements = await page.$x(action.xpath);
        if (elements.length === 0) {
          throw new Error(`Element not found with xpath: ${action.xpath}`);
        }
        const box = await elements[0].boundingBox();
        if (box) {
          await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
          await page.mouse.up({ button });
        }
      } else {
        const element = await page.$(action.selector);
        if (!element) {
          throw new Error(`Element not found with selector: ${action.selector}`);
        }
        const box = await element.boundingBox();
        if (box) {
          await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
          await page.mouse.up({ button });
        }
      }
      return { mouseUp: true, button, selector };
    }

    // Mouse up at current position
    await page.mouse.up({ button });
    return { mouseUp: true, button };
  }

  /**
   * Puppeteer mouse move implementation
   */
  private async puppeteerMouseMove(page: any, action: DOMAction): Promise<any> {
    return await MouseActions.performMove(
      action,
      async (x: number, y: number, duration?: number) => {
        if (duration && duration > 0) {
          await page.mouse.move(x, y, { steps: Math.ceil(duration / 10) });
        } else {
          await page.mouse.move(x, y);
        }
      },
      async (dx: number, dy: number, duration?: number) => {
        const currentPos = await page.evaluate(() => ({
          x: window.innerWidth / 2,
          y: window.innerHeight / 2
        }));
        const newX = currentPos.x + dx;
        const newY = currentPos.y + dy;

        if (duration && duration > 0) {
          await page.mouse.move(newX, newY, { steps: Math.ceil(duration / 10) });
        } else {
          await page.mouse.move(newX, newY);
        }
      }
    );
  }

  /**
   * Puppeteer mouse drag implementation
   */
  private async puppeteerMouseDrag(page: any, action: DOMAction): Promise<any> {
    return await MouseActions.performDrag(
      action,
      async (x: number, y: number, duration?: number, button?: string) => {
        await page.mouse.down({ button });
        if (duration && duration > 0) {
          await page.mouse.move(x, y, { steps: Math.ceil(duration / 10) });
        } else {
          await page.mouse.move(x, y);
        }
        await page.mouse.up({ button });
      },
      async (dx: number, dy: number, duration?: number, button?: string) => {
        const currentPos = await page.evaluate(() => ({
          x: window.innerWidth / 2,
          y: window.innerHeight / 2
        }));
        const newX = currentPos.x + dx;
        const newY = currentPos.y + dy;

        await page.mouse.down({ button });
        if (duration && duration > 0) {
          await page.mouse.move(newX, newY, { steps: Math.ceil(duration / 10) });
        } else {
          await page.mouse.move(newX, newY);
        }
        await page.mouse.up({ button });
      }
    );
  }

  /**
   * Puppeteer key combo implementation
   */
  private async puppeteerKeyCombo(page: any, action: DOMAction): Promise<any> {
    if (!action.combo) {
      throw new Error('Key combo requires combo parameter');
    }

    const keys = parseComboKeys(action.combo);
    if (keys.length === 0) {
      throw new Error('Invalid key combo format');
    }

    // Press all keys down in sequence
    for (const key of keys) {
      await page.keyboard.down(key);
    }

    // Release all keys in reverse order
    for (let i = keys.length - 1; i >= 0; i--) {
      await page.keyboard.up(keys[i]);
    }

    return { keyCombo: true, combo: action.combo, keys };
  }

  /**
   * Puppeteer key sequence implementation
   */
  private async puppeteerKeySequence(page: any, action: DOMAction): Promise<any> {
    if (!action.sequence || !Array.isArray(action.sequence)) {
      throw new Error('Key sequence requires sequence array parameter');
    }

    const intervalMs = action.options?.interval_ms || 60;

    await KeyboardSequence.processSequence(
      action.sequence,
      async (key: string) => {
        await page.keyboard.press(key);
      },
      async (text: string) => {
        await page.keyboard.type(text);
      },
      intervalMs
    );

    return { keySequence: true, sequence: action.sequence, intervalMs };
  }

  /**
   * Health check for DOM executor
   */
  async healthCheck(): Promise<boolean> {
    try {
      // Check Chrome Extension connection
      const extensionHealthy = await this.chromeExtensionBridge.healthCheck();

      // Check Puppeteer browser
      let browserHealthy = false;
      if (this.browser?.page) {
        try {
          await this.browser.page.evaluate(() => document.title);
          browserHealthy = true;
        } catch (error) {
          browserHealthy = false;
        }
      }

      // At least one method should be available
      return extensionHealthy || browserHealthy;

    } catch (error) {
      return false;
    }
  }

  /**
   * Get current browser context
   */
  getBrowserContext(): BrowserContext | undefined {
    return this.browser;
  }

  /**
   * Get Chrome Extension connection
   */
  getChromeExtensionConnection(): ChromeExtensionConnection | undefined {
    return this.chromeExtensionBridge.getConnection();
  }

  // ====== CLIPBOARD ACTIONS ======

  /**
   * Push current clipboard content to stack
   */
  private async executeClipboardPush(action: DOMAction): Promise<any> {
    await ClipboardManager.push();
    return { clipboardPush: true };
  }

  /**
   * Pop previous clipboard content from stack
   */
  private async executeClipboardPop(action: DOMAction): Promise<any> {
    await ClipboardManager.pop();
    return { clipboardPop: true };
  }

  /**
   * Clear clipboard
   */
  private async executeClipboardClear(action: DOMAction): Promise<any> {
    await ClipboardManager.clear();
    return { clipboardClear: true };
  }

  /**
   * Get clipboard content
   */
  private async executeClipboardGet(action: DOMAction): Promise<any> {
    const content = await ClipboardManager.get();
    return { clipboardGet: true, content };
  }

  /**
   * Set clipboard content
   */
  private async executeClipboardSet(action: DOMAction): Promise<any> {
    await ClipboardManager.set(action.content || '');
    return { clipboardSet: true, content: action.content };
  }

  /**
   * Copy from selection with enhanced options
   */
  private async executeClipboardCopySelection(action: DOMAction): Promise<any> {
    const content = await ClipboardManager.copyFromSelection({
      trim: action.trim,
      maxLen: action.max_len,
      regex: action.regex,
      restoreOnFail: action.restore_on_fail,
      waitMs: action.interval_ms || 80
    });
    return { clipboardCopySelection: true, content };
  }

  // ====== ENHANCED MOUSE ACTIONS ======

  /**
   * Triple click implementation
   */
  private async puppeteerTripleClick(page: any, action: DOMAction): Promise<any> {
    const button = normalizeButton(action.button);
    const { times = 3, interval = 120 } = getClickTiming({ times: 3, interval_ms: action.interval_ms || 120 });

    if (action.coordinates) {
      await performMultipleClicks(
        async () => {
          await page.mouse.click(action.coordinates!.x, action.coordinates!.y, { button });
        },
        times,
        interval
      );
      return { tripleClicked: true, coordinates: action.coordinates, button };
    }

    const selector = action.selector || action.xpath;
    if (action.xpath) {
      const elements = await page.$x(action.xpath);
      if (elements.length === 0) {
        throw new Error(`Element not found with xpath: ${action.xpath}`);
      }
      await performMultipleClicks(
        async () => {
          await elements[0].click({ button });
        },
        times,
        interval
      );
    } else {
      await performMultipleClicks(
        async () => {
          await page.click(action.selector, { button });
        },
        times,
        interval
      );
    }

    return { tripleClicked: true, selector, button };
  }

  /**
   * Right click implementation
   */
  private async puppeteerRightClick(page: any, action: DOMAction): Promise<any> {
    if (action.coordinates) {
      await page.mouse.click(action.coordinates.x, action.coordinates.y, { button: 'right' });
      return { rightClicked: true, coordinates: action.coordinates };
    }

    const selector = action.selector || action.xpath;
    if (action.xpath) {
      const elements = await page.$x(action.xpath);
      if (elements.length === 0) {
        throw new Error(`Element not found with xpath: ${action.xpath}`);
      }
      await elements[0].click({ button: 'right' });
    } else {
      await page.click(action.selector, { button: 'right' });
    }

    return { rightClicked: true, selector };
  }

  /**
   * Middle click implementation
   */
  private async puppeteerMiddleClick(page: any, action: DOMAction): Promise<any> {
    if (action.coordinates) {
      await page.mouse.click(action.coordinates.x, action.coordinates.y, { button: 'middle' });
      return { middleClicked: true, coordinates: action.coordinates };
    }

    const selector = action.selector || action.xpath;
    if (action.xpath) {
      const elements = await page.$x(action.xpath);
      if (elements.length === 0) {
        throw new Error(`Element not found with xpath: ${action.xpath}`);
      }
      await elements[0].click({ button: 'middle' });
    } else {
      await page.click(action.selector, { button: 'middle' });
    }

    return { middleClicked: true, selector };
  }

  /**
   * Mouse wheel implementation
   */
  private async puppeteerMouseWheel(page: any, action: DOMAction): Promise<any> {
    const deltaY = action.options?.deltaY || action.options?.amount || -120;
    const deltaX = action.options?.deltaX || 0;

    if (action.coordinates) {
      await page.mouse.move(action.coordinates.x, action.coordinates.y);
    }

    await page.mouse.wheel({ deltaX, deltaY });
    return { mouseWheel: true, deltaX, deltaY };
  }

  /**
   * Mouse move only (no click)
   */
  private async puppeteerMouseMoveOnly(page: any, action: DOMAction): Promise<any> {
    if (action.coordinates) {
      const duration = action.duration_ms || 0;
      if (duration > 0) {
        await page.mouse.move(action.coordinates.x, action.coordinates.y, { steps: Math.ceil(duration / 10) });
      } else {
        await page.mouse.move(action.coordinates.x, action.coordinates.y);
      }
      return { mouseMoved: true, coordinates: action.coordinates };
    }

    return await MouseActions.performMove(
      action,
      async (x: number, y: number, duration?: number) => {
        if (duration && duration > 0) {
          await page.mouse.move(x, y, { steps: Math.ceil(duration / 10) });
        } else {
          await page.mouse.move(x, y);
        }
      },
      async (dx: number, dy: number, duration?: number) => {
        const currentPos = await page.evaluate(() => ({
          x: window.innerWidth / 2,
          y: window.innerHeight / 2
        }));
        const newX = currentPos.x + dx;
        const newY = currentPos.y + dy;

        if (duration && duration > 0) {
          await page.mouse.move(newX, newY, { steps: Math.ceil(duration / 10) });
        } else {
          await page.mouse.move(newX, newY);
        }
      }
    );
  }

  // ====== ENHANCED KEYBOARD ACTIONS ======

  /**
   * Key down implementation
   */
  private async puppeteerKeyDown(page: any, action: DOMAction): Promise<any> {
    const key = normalizeKeyName(action.key || '');
    await page.keyboard.down(key);
    return { keyDown: true, key };
  }

  /**
   * Key up implementation
   */
  private async puppeteerKeyUp(page: any, action: DOMAction): Promise<any> {
    const key = normalizeKeyName(action.key || '');
    await page.keyboard.up(key);
    return { keyUp: true, key };
  }

  /**
   * Select all implementation
   */
  private async puppeteerKeySelectAll(page: any, action: DOMAction): Promise<any> {
    const keys = getPlatformKeyCombo('selectAll');
    await page.keyboard.down(keys[0]);
    await page.keyboard.down(keys[1]);
    await page.keyboard.up(keys[1]);
    await page.keyboard.up(keys[0]);
    return { selectAll: true, keys };
  }

  /**
   * Copy implementation
   */
  private async puppeteerKeyCopy(page: any, action: DOMAction): Promise<any> {
    const keys = getPlatformKeyCombo('copy');
    await page.keyboard.down(keys[0]);
    await page.keyboard.down(keys[1]);
    await page.keyboard.up(keys[1]);
    await page.keyboard.up(keys[0]);
    return { copy: true, keys };
  }

  /**
   * Cut implementation
   */
  private async puppeteerKeyCut(page: any, action: DOMAction): Promise<any> {
    const keys = getPlatformKeyCombo('cut');
    await page.keyboard.down(keys[0]);
    await page.keyboard.down(keys[1]);
    await page.keyboard.up(keys[1]);
    await page.keyboard.up(keys[0]);
    return { cut: true, keys };
  }

  /**
   * Paste implementation
   */
  private async puppeteerKeyPaste(page: any, action: DOMAction): Promise<any> {
    const keys = getPlatformKeyCombo('paste');
    await page.keyboard.down(keys[0]);
    await page.keyboard.down(keys[1]);
    await page.keyboard.up(keys[1]);
    await page.keyboard.up(keys[0]);
    return { paste: true, keys };
  }

  /**
   * Toggle IME implementation
   */
  private async puppeteerKeyToggleIme(page: any, action: DOMAction): Promise<any> {
    const keys = getPlatformKeyCombo('toggleIme');
    await page.keyboard.down(keys[0]);
    await page.keyboard.down(keys[1]);
    await page.keyboard.up(keys[1]);
    await page.keyboard.up(keys[0]);
    return { toggleIme: true, keys };
  }

  // ====== WINDOW OPERATIONS ======

  /**
   * Focus window by title
   */
  private async executeWindowFocus(action: DOMAction): Promise<any> {
    const success = await WindowManager.focusByTitle(action.title || '');
    return { windowFocus: success, title: action.title };
  }

  /**
   * Minimize window (placeholder - requires platform-specific implementation)
   */
  private async executeWindowMinimize(action: DOMAction): Promise<any> {
    // This would require platform-specific window management
    return { windowMinimize: false, message: 'Not implemented yet' };
  }

  /**
   * Close window (placeholder - requires platform-specific implementation)
   */
  private async executeWindowClose(action: DOMAction): Promise<any> {
    // This would require platform-specific window management
    return { windowClose: false, message: 'Not implemented yet' };
  }

  // ====== SYSTEM OPERATIONS ======

  /**
   * Execute shell command
   */
  private async executeOsShell(action: DOMAction): Promise<any> {
    const result = await ShellManager.execute(action.command || '', {
      shell: action.shell,
      timeout: (action.timeout || 30) * 1000,
      cwd: action.options?.cwd
    });
    return { shell: true, command: action.command, result };
  }

  /**
   * Activate application
   */
  private async executeOsActivateApp(action: DOMAction): Promise<any> {
    const names = action.app_names || (action.app_name ? [action.app_name] : []);
    const success = await WindowManager.activateApp(names);
    return { activateApp: success, names };
  }

  /**
   * Launch application
   */
  private async executeOsLaunchApp(action: DOMAction): Promise<any> {
    const names = action.app_names || (action.app_name ? [action.app_name] : []);
    const success = await WindowManager.launchApp(names, action.app_path);
    return { launchApp: success, names, path: action.app_path };
  }

  // ====== FILE OPERATIONS ======

  /**
   * Read file
   */
  private async executeFileRead(action: DOMAction): Promise<any> {
    const content = await FileManager.readText(action.path || '', action.encoding as BufferEncoding);
    return { fileRead: true, path: action.path, content };
  }

  /**
   * Write file
   */
  private async executeFileWrite(action: DOMAction): Promise<any> {
    const content = typeof action.data === 'string' ? action.data : JSON.stringify(action.data, null, 2);
    await FileManager.writeText(action.path || '', content, {
      encoding: action.encoding as BufferEncoding,
      mkdirs: action.recursive !== false
    });
    return { fileWrite: true, path: action.path };
  }

  /**
   * Create directory
   */
  private async executeFileMkdir(action: DOMAction): Promise<any> {
    await FileManager.mkdir(action.path || '', action.recursive !== false);
    return { fileMkdir: true, path: action.path };
  }

  /**
   * Remove file or directory
   */
  private async executeFileRemove(action: DOMAction): Promise<any> {
    await FileManager.remove(action.path || '');
    return { fileRemove: true, path: action.path };
  }

  /**
   * Copy file
   */
  private async executeFileCopy(action: DOMAction): Promise<any> {
    const destination = action.options?.destination;
    await FileManager.copy(action.path || '', destination, {
      mkdirs: action.recursive !== false
    });
    return { fileCopy: true, source: action.path, destination };
  }

  /**
   * Move file
   */
  private async executeFileMove(action: DOMAction): Promise<any> {
    const destination = action.options?.destination;
    await FileManager.move(action.path || '', destination, {
      mkdirs: action.recursive !== false
    });
    return { fileMove: true, source: action.path, destination };
  }

  /**
   * List directory
   */
  private async executeFileList(action: DOMAction): Promise<any> {
    const files = await FileManager.list(action.path || '', {
      extensions: action.options?.extensions,
      pattern: action.options?.pattern
    });
    return { fileList: true, path: action.path, files };
  }
}