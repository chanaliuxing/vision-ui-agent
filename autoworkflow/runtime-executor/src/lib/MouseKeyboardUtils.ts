// M3: Enhanced Mouse and Keyboard Utilities
// Implements functionality described in mouseKeyboard.md

/**
 * Normalize button name to standard values
 */
export function normalizeButton(button?: string): 'left' | 'right' | 'middle' {
  const normalized = (button || 'left').toLowerCase();
  return ['left', 'right', 'middle'].includes(normalized)
    ? normalized as 'left' | 'right' | 'middle'
    : 'left';
}

/**
 * Get click timing parameters with safe defaults
 */
export function getClickTiming(action: any): { times: number; interval: number } {
  const times = Math.max(1, parseInt(action.times || action.clicks || 1));
  const interval = Math.max(0, parseInt(action.interval_ms || 120));
  return { times, interval };
}

/**
 * Get movement parameters
 */
export function getMovementParams(action: any): {
  to?: [number, number];
  by?: [number, number];
  duration: number;
} {
  const duration = Math.max(0, parseInt(action.duration_ms || 0));
  const to = action.to ? [parseInt(action.to[0]), parseInt(action.to[1])] as [number, number] : undefined;
  const by = action.by ? [parseInt(action.by[0]), parseInt(action.by[1])] as [number, number] : undefined;

  return { to, by, duration };
}

/**
 * Normalize key names for cross-platform compatibility
 */
export function normalizeKey(key: string): string {
  if (!key || typeof key !== 'string') return key;

  const keyMap: Record<string, string> = {
    // Common keys
    'ctrl': 'Control',
    'control': 'Control',
    'shift': 'Shift',
    'alt': 'Alt',
    'option': 'Alt',
    'enter': 'Enter',
    'return': 'Enter',
    'esc': 'Escape',
    'escape': 'Escape',
    'space': ' ',
    'backspace': 'Backspace',
    'delete': 'Delete',
    'del': 'Delete',
    'tab': 'Tab',
    'home': 'Home',
    'end': 'End',
    'pageup': 'PageUp',
    'pagedown': 'PageDown',
    'left': 'ArrowLeft',
    'right': 'ArrowRight',
    'up': 'ArrowUp',
    'down': 'ArrowDown',
    // Function keys
    'f1': 'F1', 'f2': 'F2', 'f3': 'F3', 'f4': 'F4',
    'f5': 'F5', 'f6': 'F6', 'f7': 'F7', 'f8': 'F8',
    'f9': 'F9', 'f10': 'F10', 'f11': 'F11', 'f12': 'F12'
  };

  // Handle platform-specific meta keys
  const platform = process.platform;
  if (platform === 'darwin') {
    keyMap.meta = 'Meta';
    keyMap.cmd = 'Meta';
    keyMap.command = 'Meta';
    keyMap.win = 'Meta';
  } else {
    keyMap.meta = 'Meta';
    keyMap.cmd = 'Meta';
    keyMap.command = 'Meta';
    keyMap.win = 'Meta';
  }

  const normalized = key.toLowerCase().trim();
  return keyMap[normalized] || key;
}

/**
 * Parse combo key string into individual keys
 */
export function parseComboKeys(combo: string): string[] {
  if (!combo || typeof combo !== 'string') return [];

  return combo.split('+')
    .map(key => key.trim())
    .filter(key => key.length > 0)
    .map(key => normalizeKey(key));
}

/**
 * Validate coordinates
 */
export function validateCoordinates(coords?: { x: number; y: number } | [number, number]): [number, number] | null {
  if (!coords) return null;

  if (Array.isArray(coords)) {
    const [x, y] = coords;
    return [parseInt(String(x)), parseInt(String(y))];
  }

  if (typeof coords === 'object' && 'x' in coords && 'y' in coords) {
    return [parseInt(String(coords.x)), parseInt(String(coords.y))];
  }

  return null;
}

/**
 * Sleep utility for timing
 */
export function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, Math.max(0, ms)));
}

/**
 * Simulate multiple clicks with timing
 */
export async function performMultipleClicks(
  clickFn: () => Promise<void> | void,
  times: number,
  intervalMs: number
): Promise<void> {
  for (let i = 0; i < Math.max(1, times); i++) {
    await clickFn();
    if (i < times - 1) {
      await sleep(intervalMs);
    }
  }
}

/**
 * Keyboard sequence utilities
 */
export class KeyboardSequence {
  private static isSpecialKey(key: string): boolean {
    const specialKeys = [
      'enter', 'tab', 'esc', 'escape', 'space', 'backspace',
      'delete', 'home', 'end', 'pageup', 'pagedown',
      'left', 'right', 'up', 'down'
    ];
    return specialKeys.includes(key.toLowerCase());
  }

  /**
   * Process a sequence of keyboard inputs
   */
  static async processSequence(
    sequence: string[],
    keyFn: (key: string) => Promise<void> | void,
    typeFn: (text: string) => Promise<void> | void,
    intervalMs: number = 60
  ): Promise<void> {
    for (let i = 0; i < sequence.length; i++) {
      const item = sequence[i];

      if (typeof item === 'string') {
        if (item.length <= 20 && this.isSpecialKey(item)) {
          // Special key
          await keyFn(normalizeKey(item));
        } else {
          // Text input
          await typeFn(item);
        }
      }

      // Add delay between sequence items
      if (i < sequence.length - 1) {
        await sleep(intervalMs);
      }
    }
  }
}

/**
 * Mouse action utilities
 */
export class MouseActions {
  /**
   * Validate and perform mouse movement
   */
  static async performMove(
    action: any,
    moveToFn: (x: number, y: number, duration?: number) => Promise<void> | void,
    moveByFn: (dx: number, dy: number, duration?: number) => Promise<void> | void
  ): Promise<void> {
    const { to, by, duration } = getMovementParams(action);

    if (to) {
      await moveToFn(to[0], to[1], duration);
    } else if (by) {
      await moveByFn(by[0], by[1], duration);
    } else {
      throw new Error('Mouse move action requires either "to" or "by" parameters');
    }
  }

  /**
   * Validate and perform mouse drag
   */
  static async performDrag(
    action: any,
    dragToFn: (x: number, y: number, duration?: number, button?: string) => Promise<void> | void,
    dragByFn: (dx: number, dy: number, duration?: number, button?: string) => Promise<void> | void
  ): Promise<void> {
    const { to, by, duration } = getMovementParams(action);
    const button = normalizeButton(action.button);

    if (to) {
      await dragToFn(to[0], to[1], duration, button);
    } else if (by) {
      await dragByFn(by[0], by[1], duration, button);
    } else {
      throw new Error('Mouse drag action requires either "to" or "by" parameters');
    }
  }
}

/**
 * Action validation utilities
 */
export class ActionValidator {
  /**
   * Validate mouse action parameters
   */
  static validateMouseAction(action: any): void {
    const requiredParams = ['mouse_move', 'mouse_drag'];

    if (requiredParams.includes(action.type)) {
      if (!action.to && !action.by) {
        throw new Error(`${action.type} action requires either "to" or "by" parameters`);
      }
    }
  }

  /**
   * Validate keyboard action parameters
   */
  static validateKeyboardAction(action: any): void {
    if (action.type === 'key_combo' && !action.combo) {
      throw new Error('key_combo action requires "combo" parameter');
    }

    if (action.type === 'key_sequence' && (!action.sequence || !Array.isArray(action.sequence))) {
      throw new Error('key_sequence action requires "sequence" array parameter');
    }
  }

  /**
   * Validate enhanced click action parameters
   */
  static validateClickAction(action: any): void {
    if (action.times && action.times < 1) {
      throw new Error('Click times must be at least 1');
    }

    if (action.interval_ms && action.interval_ms < 0) {
      throw new Error('Click interval must be non-negative');
    }
  }
}