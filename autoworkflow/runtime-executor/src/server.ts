// M3: Runtime Executor Server - Main Express application

import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import morgan from 'morgan';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import puppeteer from 'puppeteer';
import type { BrowserContext } from './types/index.js';
import { executionRouter, executionManager } from './routes/execution.js';
import { WebSocketService } from './services/WebSocketService.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

class RuntimeExecutorServer {
  private app: express.Application;
  private webSocketService: WebSocketService;
  private browser?: any; // Puppeteer Browser
  private browserContext?: BrowserContext;

  constructor() {
    this.app = express();
    this.webSocketService = new WebSocketService(executionManager);
    this.setupMiddleware();
    this.setupRoutes();
    this.setupErrorHandling();
  }

  /**
   * Setup Express middleware
   */
  private setupMiddleware(): void {
    // Security
    this.app.use(helmet({
      crossOriginEmbedderPolicy: false,
      contentSecurityPolicy: {
        directives: {
          defaultSrc: ["'self'"],
          styleSrc: ["'self'", "'unsafe-inline'"],
          scriptSrc: ["'self'"],
          imgSrc: ["'self'", "data:", "blob:"],
          connectSrc: ["'self'", "ws:", "wss:"]
        }
      }
    }));

    // CORS
    this.app.use(cors({
      origin: [
        'http://localhost:3000',   // M2 Frontend Studio
        'http://localhost:3001',   // Alternative frontend port
        'http://localhost:8080',   // Development
        'http://localhost:8787'    // GetContent backend
      ],
      credentials: true,
      methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
      allowedHeaders: ['Content-Type', 'Authorization', 'x-execution-id']
    }));

    // Logging
    this.app.use(morgan('combined'));

    // Body parsing
    this.app.use(express.json({ limit: '50mb' }));
    this.app.use(express.urlencoded({ extended: true, limit: '50mb' }));

    // Request ID middleware
    this.app.use((req: any, res, next) => {
      req.id = `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      res.setHeader('x-request-id', req.id);
      next();
    });
  }

  /**
   * Setup API routes
   */
  private setupRoutes(): void {
    // Health check
    this.app.get('/health', async (req, res) => {
      try {
        const health = await executionManager.healthCheck();
        const wsStats = {
          clients: this.webSocketService.getClientsCount(),
          subscriptions: this.webSocketService.getSubscriptionsCount()
        };

        res.json({
          status: 'ok',
          timestamp: new Date(),
          services: {
            executionManager: health,
            webSocket: wsStats,
            browser: !!this.browserContext
          },
          uptime: process.uptime(),
          memory: process.memoryUsage(),
          version: process.env.npm_package_version || '1.0.0'
        });
      } catch (error) {
        res.status(500).json({
          status: 'error',
          error: error.message,
          timestamp: new Date()
        });
      }
    });

    // API routes
    this.app.use('/api/executions', executionRouter);

    // Browser management routes
    this.app.post('/api/browser/start', async (req, res) => {
      try {
        await this.startBrowser(req.body);
        res.json({
          message: 'Browser started successfully',
          headless: this.browserContext?.isHeadless
        });
      } catch (error) {
        res.status(500).json({
          error: 'Failed to start browser',
          details: error.message
        });
      }
    });

    this.app.post('/api/browser/stop', async (req, res) => {
      try {
        await this.stopBrowser();
        res.json({
          message: 'Browser stopped successfully'
        });
      } catch (error) {
        res.status(500).json({
          error: 'Failed to stop browser',
          details: error.message
        });
      }
    });

    this.app.get('/api/browser/status', (req, res) => {
      res.json({
        running: !!this.browser,
        context: this.browserContext ? {
          viewport: this.browserContext.viewport,
          userAgent: this.browserContext.userAgent,
          headless: this.browserContext.isHeadless
        } : null
      });
    });

    // Chrome Extension integration status
    this.app.get('/api/chrome-extension/status', (req, res) => {
      // This would typically check the GetContent backend connection
      res.json({
        connected: false, // Placeholder - actual implementation would check connection
        backendUrl: 'http://localhost:8787',
        capabilities: ['click', 'type', 'scroll', 'wait', 'extract']
      });
    });

    // Vision Engine status
    this.app.get('/api/vision-engine/status', (req, res) => {
      res.json({
        yolo: {
          url: 'http://localhost:8000',
          available: false // Placeholder - actual implementation would check
        },
        ocr: {
          url: 'http://localhost:8001',
          available: false // Placeholder
        },
        workflow: {
          url: 'http://localhost:8002',
          available: false // Placeholder
        }
      });
    });

    // Static files (if any)
    this.app.use('/static', express.static(join(__dirname, '../static')));

    // 404 handler
    this.app.use('*', (req, res) => {
      res.status(404).json({
        error: 'Not Found',
        path: req.originalUrl,
        timestamp: new Date()
      });
    });
  }

  /**
   * Setup error handling
   */
  private setupErrorHandling(): void {
    // Global error handler
    this.app.use((error: any, req: express.Request, res: express.Response, next: express.NextFunction) => {
      console.error('Unhandled error:', error);

      res.status(error.status || 500).json({
        error: 'Internal Server Error',
        message: error.message,
        requestId: req.id,
        timestamp: new Date()
      });
    });

    // Process error handlers
    process.on('uncaughtException', (error) => {
      console.error('Uncaught Exception:', error);
      // Graceful shutdown would go here
    });

    process.on('unhandledRejection', (reason, promise) => {
      console.error('Unhandled Rejection at:', promise, 'reason:', reason);
    });
  }

  /**
   * Start Puppeteer browser
   */
  private async startBrowser(options: any = {}): Promise<void> {
    if (this.browser) {
      await this.stopBrowser();
    }

    const browserOptions = {
      headless: options.headless !== false,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-web-security',
        '--disable-features=VizDisplayCompositor',
        ...(options.args || [])
      ],
      defaultViewport: {
        width: options.width || 1920,
        height: options.height || 1080
      }
    };

    this.browser = await puppeteer.launch(browserOptions);
    const page = await this.browser.newPage();

    // Set user agent
    const userAgent = options.userAgent ||
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';
    await page.setUserAgent(userAgent);

    // Create browser context
    this.browserContext = {
      browser: this.browser,
      page,
      viewport: browserOptions.defaultViewport,
      userAgent,
      isHeadless: browserOptions.headless
    };

    // Set browser context in execution manager
    executionManager.setBrowserContext(this.browserContext);

    console.log('Puppeteer browser started successfully');
  }

  /**
   * Stop Puppeteer browser
   */
  private async stopBrowser(): Promise<void> {
    if (this.browser) {
      await this.browser.close();
      this.browser = undefined;
      this.browserContext = undefined;
      console.log('Puppeteer browser stopped');
    }
  }

  /**
   * Start the server
   */
  async start(port: number = 8003): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.app.listen(port, () => {
          console.log(`🚀 M3 Runtime Executor Server running on port ${port}`);
          console.log(`📊 Health check: http://localhost:${port}/health`);
          console.log(`🔌 WebSocket server: ws://localhost:${port}/ws`);
          console.log(`📚 API docs: http://localhost:${port}/api/executions`);
          resolve();
        });
      } catch (error) {
        reject(error);
      }
    });
  }

  /**
   * Stop the server
   */
  async stop(): Promise<void> {
    await this.stopBrowser();
    await this.webSocketService.close();
    console.log('M3 Runtime Executor Server stopped');
  }

  /**
   * Get Express application
   */
  getApp(): express.Application {
    return this.app;
  }
}

// Start server if this file is run directly
if (import.meta.url === `file://${process.argv[1]}`) {
  const server = new RuntimeExecutorServer();

  const port = parseInt(process.env.PORT || '8003');

  server.start(port).catch(error => {
    console.error('Failed to start server:', error);
    process.exit(1);
  });

  // Graceful shutdown
  process.on('SIGINT', async () => {
    console.log('\nShutting down gracefully...');
    await server.stop();
    process.exit(0);
  });

  process.on('SIGTERM', async () => {
    console.log('\nShutting down gracefully...');
    await server.stop();
    process.exit(0);
  });
}

export { RuntimeExecutorServer };