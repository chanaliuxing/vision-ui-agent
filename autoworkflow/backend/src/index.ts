import express from 'express';
import cors from 'cors';
import schemasRouter from './routes/schemas';
import validateRouter from './routes/validate';
import lintRouter from './routes/lint';
import { simulateRouter } from './routes/simulate';
import { generateRouter } from './routes/generate';
import { fixRouter } from './routes/fix';
import { templatesRouter } from './routes/templates';

const app = express();
const PORT = process.env.PORT || 8787;

// Middleware
app.use(cors());
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'workflow-config-service',
    version: '0.1.0',
    timestamp: new Date().toISOString()
  });
});

// API routes
app.use('/', schemasRouter);
app.use('/', validateRouter);
app.use('/', lintRouter);
app.use('/', simulateRouter);
app.use('/', generateRouter);
app.use('/', fixRouter);
app.use('/templates', templatesRouter);

// Root endpoint
app.get('/', (req, res) => {
  res.json({
    name: 'Workflow Configuration Service',
    version: '0.1.0',
    description: 'Schema-first workflow validation and configuration service',
    endpoints: {
      health: 'GET /health',
      schemas: {
        workflow: 'GET /schemas/workflow',
        all: 'GET /schemas'
      },
      registry: {
        actions: 'GET /registry/actions',
        action: 'GET /registry/actions/:actionId'
      },
      validation: {
        validate: 'POST /validate',
        lint: 'POST /lint',
        fix: 'POST /fix'
      },
      simulation: {
        simulate: 'POST /simulate'
      },
      generation: {
        generate: 'POST /generate'
      },
      templates: {
        list: 'GET /templates',
        get: 'GET /templates/:id',
        generate: 'POST /templates/:id/generate',
        preview: 'GET /templates/:id/preview',
        create: 'POST /templates',
        update: 'PUT /templates/:id',
        delete: 'DELETE /templates/:id'
      }
    }
  });
});

// Error handling middleware
app.use((err: any, req: express.Request, res: express.Response, next: express.NextFunction) => {
  console.error('Server error:', err);
  res.status(500).json({
    success: false,
    error: 'Internal server error',
    details: process.env.NODE_ENV === 'development' ? err.message : undefined
  });
});

// 404 handler
app.use((req, res) => {
  res.status(404).json({
    success: false,
    error: 'Endpoint not found',
    path: req.path,
    method: req.method
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`🚀 Workflow Config Service running on port ${PORT}`);
  console.log(`📊 Health check: http://localhost:${PORT}/health`);
  console.log(`📋 API docs: http://localhost:${PORT}/`);
  console.log(`🔍 Validation: POST http://localhost:${PORT}/validate`);
});

export default app;