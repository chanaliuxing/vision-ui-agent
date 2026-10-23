// Basic Actions Utilities - Clipboard, File, Shell, Window operations
// Adapted from addbasiActions.md for TypeScript/Node.js

import { promisify } from 'util';
import { exec, spawn } from 'child_process';
import * as fs from 'fs/promises';
import * as path from 'path';
import * as os from 'os';

const execAsync = promisify(exec);

/**
 * Cross-platform clipboard operations
 */
export class ClipboardManager {
  private static clipboardStack: string[] = [];

  /**
   * Push current clipboard content to stack
   */
  static async push(): Promise<void> {
    try {
      const current = await this.get();
      this.clipboardStack.push(current);
    } catch (error) {
      this.clipboardStack.push('');
    }
  }

  /**
   * Pop previous clipboard content from stack
   */
  static async pop(): Promise<void> {
    const previous = this.clipboardStack.pop() || '';
    await this.set(previous);
  }

  /**
   * Clear clipboard
   */
  static async clear(): Promise<void> {
    await this.set('');
  }

  /**
   * Get clipboard content
   */
  static async get(): Promise<string> {
    const platform = os.platform();

    try {
      if (platform === 'darwin') {
        const { stdout } = await execAsync('pbpaste');
        return stdout;
      } else if (platform === 'win32') {
        const { stdout } = await execAsync('powershell -command "Get-Clipboard"');
        return stdout.trim();
      } else {
        // Linux - try xclip first, then xsel
        try {
          const { stdout } = await execAsync('xclip -selection clipboard -o');
          return stdout;
        } catch {
          const { stdout } = await execAsync('xsel --clipboard --output');
          return stdout;
        }
      }
    } catch (error) {
      return '';
    }
  }

  /**
   * Set clipboard content
   */
  static async set(content: string): Promise<void> {
    const platform = os.platform();

    try {
      if (platform === 'darwin') {
        await execAsync(`echo "${content.replace(/"/g, '\\"')}" | pbcopy`);
      } else if (platform === 'win32') {
        await execAsync(`echo "${content.replace(/"/g, '""')}" | clip`);
      } else {
        // Linux - try xclip first, then xsel
        try {
          await execAsync(`echo "${content.replace(/"/g, '\\"')}" | xclip -selection clipboard`);
        } catch {
          await execAsync(`echo "${content.replace(/"/g, '\\"')}" | xsel --clipboard --input`);
        }
      }
    } catch (error: any) {
      throw new Error(`Failed to set clipboard: ${error.message}`);
    }
  }

  /**
   * Copy from selection with enhanced options
   */
  static async copyFromSelection(options: {
    trim?: boolean;
    maxLen?: number;
    regex?: string;
    restoreOnFail?: boolean;
    preClear?: boolean;
    waitMs?: number;
  } = {}): Promise<string> {
    const { trim = true, maxLen = 0, regex, restoreOnFail = true, preClear = true, waitMs = 80 } = options;

    let previous = '';
    if (restoreOnFail) {
      previous = await this.get();
    }

    if (preClear) {
      await this.clear();
    }

    // Send copy command (this would need to be integrated with mouse/keyboard actions)
    const platform = os.platform();
    const copyCommand = platform === 'darwin' ? 'cmd+c' : 'ctrl+c';

    // Wait for copy to complete
    await new Promise(resolve => setTimeout(resolve, waitMs));

    let content = await this.get();

    if (trim) {
      content = content.trim();
    }

    if (regex) {
      const match = content.match(new RegExp(regex));
      content = match ? (match[1] || match[0]) : '';
    }

    if (maxLen && content.length > maxLen) {
      content = content.substring(0, maxLen);
    }

    if (!content && restoreOnFail) {
      await this.set(previous);
    }

    return content;
  }
}

/**
 * File system operations
 */
export class FileManager {

  /**
   * Read text file
   */
  static async readText(filePath: string, encoding: BufferEncoding = 'utf8'): Promise<string> {
    try {
      return await fs.readFile(filePath, encoding);
    } catch (error: any) {
      throw new Error(`Failed to read file ${filePath}: ${error.message}`);
    }
  }

  /**
   * Write text file
   */
  static async writeText(filePath: string, content: string, options: {
    encoding?: BufferEncoding;
    mkdirs?: boolean;
  } = {}): Promise<void> {
    const { encoding = 'utf8', mkdirs = true } = options;

    try {
      if (mkdirs) {
        await fs.mkdir(path.dirname(filePath), { recursive: true });
      }
      await fs.writeFile(filePath, content, encoding);
    } catch (error: any) {
      throw new Error(`Failed to write file ${filePath}: ${error.message}`);
    }
  }

  /**
   * Read JSON file
   */
  static async readJson(filePath: string): Promise<any> {
    try {
      const content = await this.readText(filePath);
      return JSON.parse(content);
    } catch (error: any) {
      throw new Error(`Failed to read JSON file ${filePath}: ${error.message}`);
    }
  }

  /**
   * Write JSON file
   */
  static async writeJson(filePath: string, data: any, options: {
    indent?: number;
    mkdirs?: boolean;
  } = {}): Promise<void> {
    const { indent = 2, mkdirs = true } = options;

    try {
      const content = JSON.stringify(data, null, indent);
      await this.writeText(filePath, content, { mkdirs });
    } catch (error: any) {
      throw new Error(`Failed to write JSON file ${filePath}: ${error.message}`);
    }
  }

  /**
   * Create directory
   */
  static async mkdir(dirPath: string, recursive: boolean = true): Promise<void> {
    try {
      await fs.mkdir(dirPath, { recursive });
    } catch (error: any) {
      throw new Error(`Failed to create directory ${dirPath}: ${error.message}`);
    }
  }

  /**
   * Remove file or directory
   */
  static async remove(filePath: string): Promise<void> {
    try {
      const stats = await fs.stat(filePath);
      if (stats.isDirectory()) {
        await fs.rmdir(filePath, { recursive: true });
      } else {
        await fs.unlink(filePath);
      }
    } catch (error: any) {
      throw new Error(`Failed to remove ${filePath}: ${error.message}`);
    }
  }

  /**
   * Copy file
   */
  static async copy(src: string, dest: string, options: {
    mkdirs?: boolean;
  } = {}): Promise<void> {
    const { mkdirs = true } = options;

    try {
      if (mkdirs) {
        await fs.mkdir(path.dirname(dest), { recursive: true });
      }
      await fs.copyFile(src, dest);
    } catch (error: any) {
      throw new Error(`Failed to copy ${src} to ${dest}: ${error.message}`);
    }
  }

  /**
   * Move file
   */
  static async move(src: string, dest: string, options: {
    mkdirs?: boolean;
  } = {}): Promise<void> {
    const { mkdirs = true } = options;

    try {
      if (mkdirs) {
        await fs.mkdir(path.dirname(dest), { recursive: true });
      }
      await fs.rename(src, dest);
    } catch (error: any) {
      throw new Error(`Failed to move ${src} to ${dest}: ${error.message}`);
    }
  }

  /**
   * List directory contents
   */
  static async list(dirPath: string, options: {
    extensions?: string[];
    pattern?: string;
  } = {}): Promise<string[]> {
    const { extensions, pattern } = options;

    try {
      let files = await fs.readdir(dirPath);

      if (extensions) {
        files = files.filter(file =>
          extensions.some(ext => file.toLowerCase().endsWith(ext.toLowerCase()))
        );
      }

      if (pattern) {
        const regex = new RegExp(pattern);
        files = files.filter(file => regex.test(file));
      }

      return files;
    } catch (error: any) {
      throw new Error(`Failed to list directory ${dirPath}: ${error.message}`);
    }
  }
}

/**
 * Shell command execution
 */
export class ShellManager {

  /**
   * Execute shell command
   */
  static async execute(command: string, options: {
    shell?: boolean;
    timeout?: number;
    cwd?: string;
  } = {}): Promise<{
    code: number;
    stdout: string;
    stderr: string;
  }> {
    const { shell = true, timeout = 30000, cwd } = options;

    try {
      const { stdout, stderr } = await execAsync(command, {
        timeout,
        cwd
      });

      return {
        code: 0,
        stdout: stdout || '',
        stderr: stderr || ''
      };
    } catch (error: any) {
      return {
        code: error.code || -1,
        stdout: error.stdout || '',
        stderr: error.stderr || error.message
      };
    }
  }
}

/**
 * Window and application management
 */
export class WindowManager {

  /**
   * Focus window by title
   */
  static async focusByTitle(title: string): Promise<boolean> {
    const platform = os.platform();

    try {
      if (platform === 'darwin') {
        await execAsync(`osascript -e 'tell application "System Events" to set frontmost of first process whose name contains "${title}" to true'`);
        return true;
      } else if (platform === 'win32') {
        const result = await execAsync(`powershell -Command "Get-Process | Where-Object {$_.MainWindowTitle -like '*${title}*'} | ForEach-Object {[Microsoft.VisualBasic.Interaction]::AppActivate($_.Id)}"`);
        return true;
      } else {
        // Linux with wmctrl
        await execAsync(`wmctrl -a "${title}"`);
        return true;
      }
    } catch (error) {
      return false;
    }
  }

  /**
   * Activate application by name
   */
  static async activateApp(names: string[]): Promise<boolean> {
    const platform = os.platform();

    for (const name of names) {
      try {
        if (platform === 'darwin') {
          await execAsync(`osascript -e 'tell application "${name}" to activate'`);
          return true;
        } else if (platform === 'win32') {
          const ps = `
            $ErrorActionPreference = 'SilentlyContinue'
            $p = Get-Process -Name "${name}" | Select-Object -First 1
            if ($p -and $p.MainWindowHandle -ne 0) {
              $sig = '[DllImport("user32.dll")]public static extern bool SetForegroundWindow(IntPtr hWnd);'
              Add-Type -MemberDefinition $sig -Name WinAPI -Namespace Win32 | Out-Null
              [Win32.WinAPI]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
              Write-Output 'OK'
            } else {
              Write-Output 'NOHWND'
            }
          `;
          const { stdout } = await execAsync(`powershell -NoProfile -Command "${ps}"`);
          if (stdout.trim().startsWith('OK')) {
            return true;
          }
        }
      } catch (error) {
        continue;
      }
    }

    return false;
  }

  /**
   * Launch application by name or path
   */
  static async launchApp(names: string[], appPath?: string): Promise<boolean> {
    const platform = os.platform();

    try {
      if (appPath) {
        if (platform === 'darwin') {
          await execAsync(`open "${appPath}"`);
          return true;
        } else if (platform === 'win32') {
          await execAsync(`powershell -NoProfile -Command "Start-Process -FilePath '${appPath}'"`);
          return true;
        } else {
          await execAsync(`"${appPath}"`);
          return true;
        }
      }

      for (const name of names) {
        try {
          if (platform === 'darwin') {
            await execAsync(`open -a "${name}"`);
            return true;
          } else if (platform === 'win32') {
            await execAsync(`powershell -NoProfile -Command "Start-Process '${name}'"`);
            return true;
          } else {
            await execAsync(`${name}`);
            return true;
          }
        } catch (error) {
          continue;
        }
      }
    } catch (error) {
      return false;
    }

    return false;
  }
}

/**
 * Cross-platform key name normalization
 */
export function normalizeKeyName(key: string): string {
  if (!key || typeof key !== 'string') return key;

  const keyMap: Record<string, string> = {
    'ctrl': 'Control',
    'control': 'Control',
    'cmd': os.platform() === 'darwin' ? 'Meta' : 'Control',
    'command': os.platform() === 'darwin' ? 'Meta' : 'Control',
    'shift': 'Shift',
    'alt': 'Alt',
    'option': 'Alt',
    'enter': 'Enter',
    'return': 'Enter',
    'esc': 'Escape',
    'escape': 'Escape',
    'space': ' ',
    'tab': 'Tab',
    'backspace': 'Backspace',
    'delete': 'Delete',
    'home': 'Home',
    'end': 'End',
    'pageup': 'PageUp',
    'pagedown': 'PageDown',
    'left': 'ArrowLeft',
    'right': 'ArrowRight',
    'up': 'ArrowUp',
    'down': 'ArrowDown'
  };

  const normalized = key.toLowerCase().trim();
  return keyMap[normalized] || key;
}

/**
 * Get platform-specific key combinations
 */
export function getPlatformKeyCombo(action: 'copy' | 'cut' | 'paste' | 'selectAll' | 'toggleIme'): string[] {
  const platform = os.platform();
  const isMac = platform === 'darwin';

  switch (action) {
    case 'copy':
      return isMac ? ['cmd', 'c'] : ['ctrl', 'c'];
    case 'cut':
      return isMac ? ['cmd', 'x'] : ['ctrl', 'x'];
    case 'paste':
      return isMac ? ['cmd', 'v'] : ['ctrl', 'v'];
    case 'selectAll':
      return isMac ? ['cmd', 'a'] : ['ctrl', 'a'];
    case 'toggleIme':
      return isMac ? ['ctrl', 'space'] : ['shift', 'alt'];
    default:
      return [];
  }
}