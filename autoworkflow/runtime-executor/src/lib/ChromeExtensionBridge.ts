// M3: Chrome Extension Bridge - Interface with GetContent Chrome Extension

import { EventEmitter } from 'events';
import axios from 'axios';
import WebSocket from 'ws';
import type {
  ChromeExtensionConnection,
  ChromeExtensionCommand,
  ChromeExtensionResponse,
  DOMAction,
  DOMExecutionResult,
  ExecutionContext
} from '../types/index.js';

export class ChromeExtensionBridge extends EventEmitter {
  private connection?: ChromeExtensionConnection;
  private ws?: WebSocket;
  private pendingCommands = new Map<string, {
    resolve: (result: ChromeExtensionResponse) => void;
    reject: (error: Error) => void;
    timeout: NodeJS.Timeout;
  }>();

  // GetContent backend URL (from CLAUDE.md)
  private readonly backendUrl: string;

  constructor(backendUrl = 'http://localhost:8787') {
    super();
    this.backendUrl = backendUrl;
    this.setupWebSocketConnection();
  }

  /**
   * Initialize connection to Chrome Extension via GetContent backend
   */
  private async setupWebSocketConnection(): Promise<void> {
    try {
      // Connect to GetContent backend WebSocket
      this.ws = new WebSocket(`${this.backendUrl.replace('http', 'ws')}/ws`);

      this.ws.on('open', () => {
        this.emit('connected');
        console.log('Connected to GetContent Chrome Extension backend');
      });

      this.ws.on('message', (data) => {
        try {
          const message = JSON.parse(data.toString());
          this.handleWebSocketMessage(message);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      });

      this.ws.on('close', () => {
        this.emit('disconnected');
        console.log('Disconnected from GetContent backend');

        // Attempt reconnection after 5 seconds
        setTimeout(() => this.setupWebSocketConnection(), 5000);
      });

      this.ws.on('error', (error) => {
        this.emit('error', error);
        console.error('WebSocket error:', error);
      });

    } catch (error) {
      console.error('Failed to setup WebSocket connection:', error);
      setTimeout(() => this.setupWebSocketConnection(), 5000);
    }
  }

  /**
   * Handle incoming WebSocket messages from GetContent backend
   */
  private handleWebSocketMessage(message: any): void {
    const { type, commandId, data } = message;

    switch (type) {
      case 'command_response':
        this.handleCommandResponse(commandId, data);
        break;

      case 'extension_status':
        this.updateExtensionStatus(data);
        break;

      case 'heartbeat':
        this.handleHeartbeat(data);
        break;

      default:
        console.log('Unknown WebSocket message type:', type);
    }
  }

  /**
   * Handle command response from Chrome Extension
   */
  private handleCommandResponse(commandId: string, data: any): void {
    const pending = this.pendingCommands.get(commandId);

    if (pending) {
      clearTimeout(pending.timeout);
      this.pendingCommands.delete(commandId);

      const response: ChromeExtensionResponse = {
        commandId,
        success: data.success,
        result: data.result,
        error: data.error,
        screenshot: data.screenshot,
        timestamp: new Date()
      };

      pending.resolve(response);
    }
  }

  /**
   * Update extension connection status
   */
  private updateExtensionStatus(status: any): void {
    this.connection = {
      tabId: status.tabId,
      url: status.url,
      isConnected: status.isConnected,
      lastHeartbeat: new Date(),
      capabilities: status.capabilities || ['click', 'type', 'scroll', 'wait', 'extract']
    };

    this.emit('status_update', this.connection);
  }

  /**
   * Handle heartbeat from extension
   */
  private handleHeartbeat(data: any): void {
    if (this.connection) {
      this.connection.lastHeartbeat = new Date();
      this.emit('heartbeat', data);
    }
  }

  /**
   * Execute DOM action via Chrome Extension
   */
  async executeDOMAction(
    action: DOMAction,
    context: ExecutionContext
  ): Promise<DOMExecutionResult> {
    if (!this.isConnected()) {
      return {
        success: false,
        method: 'dom',
        error: 'Chrome Extension not connected',
        fallbackRequired: true
      };
    }

    try {
      // Convert DOMAction to Chrome Extension command
      const command = this.createExtensionCommand(action);

      // Send command and wait for response
      const response = await this.sendCommand(command);

      if (response.success) {
        return {
          success: true,
          method: 'dom',
          output: response.result,
          screenshot: response.screenshot
        };
      } else {
        return {
          success: false,
          method: 'dom',
          error: response.error || 'Unknown extension error',
          fallbackRequired: this.shouldFallbackToVision(response.error)
        };
      }

    } catch (error) {
      return {
        success: false,
        method: 'dom',
        error: error.message,
        fallbackRequired: true
      };
    }
  }

  /**
   * Create Chrome Extension command from DOM action
   */
  private createExtensionCommand(action: DOMAction): ChromeExtensionCommand {
    const commandId = `cmd_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    let payload: any;

    switch (action.type) {
      case 'click':
        payload = {
          action: 'click',
          selector: action.selector,
          xpath: action.xpath,
          coordinates: action.coordinates
        };
        break;

      case 'type':
        payload = {
          action: 'type',
          selector: action.selector,
          xpath: action.xpath,
          text: action.text
        };
        break;

      case 'scroll':
        payload = {
          action: 'scroll',
          selector: action.selector,
          direction: action.options?.direction || 'down',
          amount: action.options?.amount || 3
        };
        break;

      case 'wait':
        payload = {
          action: 'wait',
          selector: action.selector,
          timeout: action.options?.timeout || 5000,
          visible: action.options?.visible !== false
        };
        break;

      case 'navigate':
        payload = {
          action: 'navigate',
          url: action.options?.url
        };
        break;

      case 'extract':
        payload = {
          action: 'extract',
          selector: action.selector,
          attribute: action.options?.attribute,
          multiple: action.options?.multiple
        };
        break;

      default:
        throw new Error(`Unsupported DOM action type: ${action.type}`);
    }

    return {
      id: commandId,
      type: 'execute_action',
      payload,
      timestamp: new Date(),
      timeout_ms: 30000
    };
  }

  /**
   * Send command to Chrome Extension via GetContent backend
   */
  private async sendCommand(command: ChromeExtensionCommand): Promise<ChromeExtensionResponse> {
    return new Promise((resolve, reject) => {
      // Set up timeout
      const timeout = setTimeout(() => {
        this.pendingCommands.delete(command.id);
        reject(new Error(`Command timeout: ${command.id}`));
      }, command.timeout_ms || 30000);

      // Store pending command
      this.pendingCommands.set(command.id, { resolve, reject, timeout });

      // Send command via WebSocket
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({
          type: 'execute_command',
          command
        }));
      } else {
        clearTimeout(timeout);
        this.pendingCommands.delete(command.id);
        reject(new Error('WebSocket connection not available'));
      }
    });
  }

  /**
   * Check if Chrome Extension is connected
   */
  isConnected(): boolean {
    return this.connection?.isConnected === true &&
           this.ws?.readyState === WebSocket.OPEN;
  }

  /**
   * Get current extension status
   */
  getConnection(): ChromeExtensionConnection | undefined {
    return this.connection;
  }

  /**
   * Determine if we should fallback to vision based on error
   */
  private shouldFallbackToVision(error?: string): boolean {
    if (!error) return false;

    const visionFallbackErrors = [
      'element not found',
      'selector failed',
      'timeout waiting for element',
      'element not visible',
      'element not interactable',
      'dynamic content',
      'no matching element'
    ];

    return visionFallbackErrors.some(fallbackError =>
      error.toLowerCase().includes(fallbackError)
    );
  }

  /**
   * Take screenshot via Chrome Extension
   */
  async takeScreenshot(): Promise<string | null> {
    if (!this.isConnected()) {
      return null;
    }

    try {
      const command: ChromeExtensionCommand = {
        id: `screenshot_${Date.now()}`,
        type: 'screenshot',
        payload: {},
        timestamp: new Date(),
        timeout_ms: 10000
      };

      const response = await this.sendCommand(command);
      return response.screenshot || null;

    } catch (error) {
      console.error('Failed to take screenshot:', error);
      return null;
    }
  }

  /**
   * Get current page DOM via Chrome Extension
   */
  async getPageDOM(): Promise<any> {
    if (!this.isConnected()) {
      throw new Error('Chrome Extension not connected');
    }

    try {
      const command: ChromeExtensionCommand = {
        id: `get_dom_${Date.now()}`,
        type: 'get_dom',
        payload: {},
        timestamp: new Date(),
        timeout_ms: 15000
      };

      const response = await this.sendCommand(command);

      if (response.success) {
        return response.result;
      } else {
        throw new Error(response.error || 'Failed to get DOM');
      }

    } catch (error) {
      throw new Error(`Failed to get page DOM: ${error.message}`);
    }
  }

  /**
   * Health check for Chrome Extension connection
   */
  async healthCheck(): Promise<boolean> {
    try {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        return false;
      }

      const command: ChromeExtensionCommand = {
        id: `ping_${Date.now()}`,
        type: 'ping',
        payload: {},
        timestamp: new Date(),
        timeout_ms: 5000
      };

      const response = await this.sendCommand(command);
      return response.success;

    } catch (error) {
      return false;
    }
  }

  /**
   * Close connection
   */
  close(): void {
    if (this.ws) {
      this.ws.close();
    }

    // Clear all pending commands
    for (const [id, pending] of this.pendingCommands) {
      clearTimeout(pending.timeout);
      pending.reject(new Error('Connection closed'));
    }
    this.pendingCommands.clear();
  }
}