// M3: WebSocket Service - Real-time execution updates

import { WebSocketServer, WebSocket } from 'ws';
import { IncomingMessage } from 'http';
import type { WSMessage } from '../types/index.js';
import { WorkflowExecutionManager } from './WorkflowExecutionManager.js';

export class WebSocketService {
  private wss: WebSocketServer;
  private clients = new Map<string, WebSocket>();
  private subscriptions = new Map<string, Set<string>>(); // clientId -> executionIds

  constructor(private executionManager: WorkflowExecutionManager) {
    this.wss = new WebSocketServer({
      port: 8003,
      path: '/ws'
    });

    this.setupWebSocketServer();
    this.setupExecutionManagerEvents();
  }

  /**
   * Setup WebSocket server event handlers
   */
  private setupWebSocketServer(): void {
    this.wss.on('connection', (ws: WebSocket, req: IncomingMessage) => {
      const clientId = this.generateClientId();
      this.clients.set(clientId, ws);
      this.subscriptions.set(clientId, new Set());

      console.log(`WebSocket client connected: ${clientId}`);

      // Send welcome message
      this.sendToClient(clientId, {
        type: 'connected',
        data: { clientId, timestamp: new Date() }
      });

      // Handle incoming messages
      ws.on('message', (data) => {
        try {
          const message = JSON.parse(data.toString());
          this.handleClientMessage(clientId, message);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
          this.sendError(clientId, 'Invalid JSON message');
        }
      });

      // Handle client disconnect
      ws.on('close', () => {
        console.log(`WebSocket client disconnected: ${clientId}`);
        this.clients.delete(clientId);
        this.subscriptions.delete(clientId);
      });

      // Handle errors
      ws.on('error', (error) => {
        console.error(`WebSocket error for client ${clientId}:`, error);
        this.clients.delete(clientId);
        this.subscriptions.delete(clientId);
      });
    });

    this.wss.on('error', (error) => {
      console.error('WebSocket server error:', error);
    });

    console.log('WebSocket server listening on port 8003');
  }

  /**
   * Setup execution manager event forwarding
   */
  private setupExecutionManagerEvents(): void {
    // Forward all execution events to subscribed clients
    this.executionManager.on('execution_start', (message: WSMessage) => {
      this.broadcastToSubscribers(message.executionId, message);
    });

    this.executionManager.on('execution_progress', (message: WSMessage) => {
      this.broadcastToSubscribers(message.executionId, message);
    });

    this.executionManager.on('execution_complete', (message: WSMessage) => {
      this.broadcastToSubscribers(message.executionId, message);
    });

    this.executionManager.on('execution_error', (message: WSMessage) => {
      this.broadcastToSubscribers(message.executionId, message);
    });

    this.executionManager.on('step_complete', (message: WSMessage) => {
      this.broadcastToSubscribers(message.executionId, message);
    });

    this.executionManager.on('execution_plan', (data) => {
      const message: WSMessage = {
        type: 'execution_plan',
        executionId: data.stepId.split('_')[0], // Extract execution ID
        data,
        timestamp: new Date()
      };
      this.broadcastToSubscribers(message.executionId, message);
    });

    this.executionManager.on('fallback_triggered', (data) => {
      const message: WSMessage = {
        type: 'fallback_triggered',
        executionId: data.stepId.split('_')[0], // Extract execution ID
        data,
        timestamp: new Date()
      };
      this.broadcastToSubscribers(message.executionId, message);
    });

    this.executionManager.on('dom_action', (data) => {
      const message: WSMessage = {
        type: 'dom_action',
        executionId: data.context?.executionId || 'unknown',
        data,
        timestamp: new Date()
      };
      this.broadcastToSubscribers(message.executionId, message);
    });

    this.executionManager.on('vision_action', (data) => {
      const message: WSMessage = {
        type: 'vision_action',
        executionId: data.context?.executionId || 'unknown',
        data,
        timestamp: new Date()
      };
      this.broadcastToSubscribers(message.executionId, message);
    });
  }

  /**
   * Handle incoming client messages
   */
  private handleClientMessage(clientId: string, message: any): void {
    const { type, data } = message;

    switch (type) {
      case 'subscribe':
        this.handleSubscribe(clientId, data);
        break;

      case 'unsubscribe':
        this.handleUnsubscribe(clientId, data);
        break;

      case 'get_executions':
        this.handleGetExecutions(clientId);
        break;

      case 'get_execution_status':
        this.handleGetExecutionStatus(clientId, data);
        break;

      case 'ping':
        this.handlePing(clientId);
        break;

      default:
        this.sendError(clientId, `Unknown message type: ${type}`);
    }
  }

  /**
   * Handle subscription to execution updates
   */
  private handleSubscribe(clientId: string, data: { executionId?: string; all?: boolean }): void {
    const subscriptions = this.subscriptions.get(clientId);
    if (!subscriptions) return;

    if (data.all) {
      // Subscribe to all executions
      const allExecutions = this.executionManager.getAllExecutions();
      allExecutions.forEach(execution => {
        subscriptions.add(execution.id);
      });

      this.sendToClient(clientId, {
        type: 'subscribed',
        data: { type: 'all', count: allExecutions.length }
      });

    } else if (data.executionId) {
      // Subscribe to specific execution
      subscriptions.add(data.executionId);

      this.sendToClient(clientId, {
        type: 'subscribed',
        data: { executionId: data.executionId }
      });

      // Send current status immediately
      const execution = this.executionManager.getExecution(data.executionId);
      if (execution) {
        this.sendToClient(clientId, {
          type: 'execution_status',
          data: {
            executionId: execution.id,
            status: execution.status,
            progress: execution.progress,
            currentStep: execution.currentStep
          }
        });
      }
    }
  }

  /**
   * Handle unsubscription from execution updates
   */
  private handleUnsubscribe(clientId: string, data: { executionId?: string; all?: boolean }): void {
    const subscriptions = this.subscriptions.get(clientId);
    if (!subscriptions) return;

    if (data.all) {
      subscriptions.clear();
      this.sendToClient(clientId, {
        type: 'unsubscribed',
        data: { type: 'all' }
      });
    } else if (data.executionId) {
      subscriptions.delete(data.executionId);
      this.sendToClient(clientId, {
        type: 'unsubscribed',
        data: { executionId: data.executionId }
      });
    }
  }

  /**
   * Handle get executions request
   */
  private handleGetExecutions(clientId: string): void {
    const executions = this.executionManager.getAllExecutions();

    this.sendToClient(clientId, {
      type: 'executions_list',
      data: {
        executions: executions.map(e => ({
          id: e.id,
          workflow: { name: e.workflow.name, version: e.workflow.version },
          status: e.status,
          progress: e.progress,
          currentStep: e.currentStep,
          createdAt: e.createdAt,
          startedAt: e.startedAt,
          completedAt: e.completedAt
        })),
        count: executions.length
      }
    });
  }

  /**
   * Handle get execution status request
   */
  private handleGetExecutionStatus(clientId: string, data: { executionId: string }): void {
    const execution = this.executionManager.getExecution(data.executionId);

    if (!execution) {
      this.sendError(clientId, `Execution not found: ${data.executionId}`);
      return;
    }

    this.sendToClient(clientId, {
      type: 'execution_status',
      data: {
        executionId: execution.id,
        status: execution.status,
        progress: execution.progress,
        currentStep: execution.currentStep,
        trace: execution.context.trace
      }
    });
  }

  /**
   * Handle ping request
   */
  private handlePing(clientId: string): void {
    this.sendToClient(clientId, {
      type: 'pong',
      data: { timestamp: new Date() }
    });
  }

  /**
   * Broadcast message to all clients subscribed to an execution
   */
  private broadcastToSubscribers(executionId: string, message: WSMessage | any): void {
    for (const [clientId, subscriptions] of this.subscriptions) {
      if (subscriptions.has(executionId)) {
        this.sendToClient(clientId, message);
      }
    }
  }

  /**
   * Send message to specific client
   */
  private sendToClient(clientId: string, message: any): void {
    const client = this.clients.get(clientId);
    if (client && client.readyState === WebSocket.OPEN) {
      try {
        client.send(JSON.stringify({
          ...message,
          timestamp: message.timestamp || new Date()
        }));
      } catch (error) {
        console.error(`Failed to send message to client ${clientId}:`, error);
        this.clients.delete(clientId);
        this.subscriptions.delete(clientId);
      }
    }
  }

  /**
   * Send error message to client
   */
  private sendError(clientId: string, error: string): void {
    this.sendToClient(clientId, {
      type: 'error',
      data: { error, timestamp: new Date() }
    });
  }

  /**
   * Generate unique client ID
   */
  private generateClientId(): string {
    return `client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Get WebSocket server instance
   */
  getServer(): WebSocketServer {
    return this.wss;
  }

  /**
   * Get connected clients count
   */
  getClientsCount(): number {
    return this.clients.size;
  }

  /**
   * Get active subscriptions count
   */
  getSubscriptionsCount(): number {
    let count = 0;
    for (const subscriptions of this.subscriptions.values()) {
      count += subscriptions.size;
    }
    return count;
  }

  /**
   * Close WebSocket server
   */
  close(): Promise<void> {
    return new Promise((resolve) => {
      this.wss.close(() => {
        console.log('WebSocket server closed');
        resolve();
      });
    });
  }
}