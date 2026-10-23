import express from 'express';
import cors from 'cors';
import cookieParser from 'cookie-parser';
import auth from './routes/auth.js';
import entitlement from './routes/entitlement.js';
import plans from './routes/plans.js';
import events from './routes/events.js';
import revocations from './routes/revocations.js';
import commands from './routes/commands.js';
import resolve from './routes/resolve.js';
import runs from './routes/runs.js';
import actions from './routes/actions.js';
import logs from './routes/logs.js';
import { sessionMiddleware } from './lib/sessions.js';

const app = express();
app.set('trust proxy', 1);

// --- CORS + PNA FIX START ---
const corsOptions = {
  origin(origin, cb) {
    // Allow all origins (including chrome-extension://*) in dev.
    return cb(null, true);
  },
  credentials: true,
  methods: ['GET','POST','PUT','PATCH','DELETE','OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization']
};

// Always set the PNA header (Chrome >= 115)
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Private-Network', 'true');
  next();
});

// Handle preflight for every path
app.options('*', cors(corsOptions));
// Apply CORS for actual requests
app.use(cors(corsOptions));

// --- explicit health with PNA/CORS headers ---
app.options('/health', (req, res) => {
  res.set({
    'Access-Control-Allow-Origin': req.headers.origin || '*',
    'Access-Control-Allow-Credentials': 'true',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Allow-Private-Network': 'true',
    'Vary': 'Origin',
  });
  res.sendStatus(204);
});

app.get('/health', (req, res) => {
  res.set({
    'Access-Control-Allow-Origin': req.headers.origin || '*',
    'Access-Control-Allow-Credentials': 'true',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Allow-Private-Network': 'true',
    'Vary': 'Origin',
  });
  res.json({ ok: true, ts: Date.now() });
});

app.use((req, _res, next) => {
  console.log('[HTTP]', req.method, req.url, 'Origin=', req.headers.origin, 'ARP=', req.headers['access-control-request-private-network']);
  next();
});
// --- CORS + PNA FIX END ---

// 🔴 先挂 /logs 的专用解析器，再挂全局 JSON parser
app.use('/logs', express.text({
  type: ['application/x-ndjson', 'text/plain', 'application/octet-stream', '*/*'],
  limit: '5mb'
}));

app.use(express.json({ limit: '1mb' }));
app.use(cookieParser());
app.use(sessionMiddleware);

// routes
app.use(auth);
app.use(entitlement);
app.use(plans);
app.use(events);
app.use(revocations);
app.use(commands);
app.use(resolve);
app.use(runs);
app.use(actions);
app.use(logs);

const port = process.env.PORT || 8787;
app.listen(port, ()=> console.log(`MVP backend on http://localhost:${port}`));