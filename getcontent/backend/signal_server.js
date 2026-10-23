#!/usr/bin/env node
// Minimal local signal server for Python workflow integration
// Exposes:
//  - GET  /health           -> { ok:true }
//  - GET  /page_stable      -> { stable: boolean }
//  - POST /page_stable      -> set stable=true for a short window and return ok
//  - POST /reset            -> set stable=false

import express from 'express';

const app = express();
app.use(express.json());

let stable = false;
let lastAt = 0;
const WINDOW_MS = parseInt(process.env.SIGNAL_WINDOW_MS || '3000', 10);

function isStable() {
  if (!stable) return false;
  if (Date.now() - lastAt > WINDOW_MS) { stable = false; }
  return stable;
}

app.get('/health', (_req, res) => res.json({ ok: true }));

app.get('/page_stable', (_req, res) => {
  res.json({ stable: isStable() });
});

app.post('/page_stable', (req, res) => {
  stable = true; lastAt = Date.now();
  res.status(200).send('ok');
});

app.post('/reset', (_req, res) => { stable = false; res.json({ ok: true }); });

const PORT = parseInt(process.env.EXT_SIGNAL_PORT || '8789', 10);
app.listen(PORT, () => {
  console.log(`[signal] Listening on http://127.0.0.1:${PORT}`);
});

