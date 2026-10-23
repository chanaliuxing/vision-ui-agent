// Backend log collection endpoint for Phase 5 logging system
// Receives NDJSON logs from extension and stores them securely

import { Router } from 'express';
import { promises as fs } from 'fs';
import path from 'path';
import os from 'os';

const router = Router();

const LOG_DIR = path.resolve(process.cwd(), 'logs');
const LOG_FILE = path.join(LOG_DIR, 'extension.ndjson');

async function ensureLogsDir() {
  await fs.mkdir(LOG_DIR, { recursive: true });
}

function parseNdjson(str) {
  const events = [];
  const lines = String(str).split(/\r?\n/);
  for (const line of lines) {
    if (!line.trim()) continue;
    try {
      const evt = JSON.parse(line);
      // 最小验证
      if (evt && evt.ts && evt.level && evt.evt) {
        events.push(evt);
      }
    } catch {
      // 丢弃坏行
    }
  }
  return events;
}

// POST /logs - 接收 NDJSON
router.post('/', async (req, res) => {
  try {
    await ensureLogsDir();

    if (typeof req.body !== 'string') {
      return res.status(415).json({ error: 'Expected text/ndjson body. Check parser order.' });
    }

    console.log('[LOGS] Received body type:', typeof req.body, 'length:', req.body.length);

    const events = parseNdjson(req.body);
    if (!events.length) {
      console.log('[LOGS] No valid events parsed from:', req.body.slice(0, 200));
      return res.status(400).json({ error: 'No valid log events found' });
    }

    // 逐行写入
    const lines = events.map(e => JSON.stringify(e)).join(os.EOL) + os.EOL;
    await fs.appendFile(LOG_FILE, lines, 'utf8');

    console.log(`[LOGS] Stored ${events.length} events to ${path.basename(LOG_FILE)}`);
    return res.status(200).json({ ok: true, count: events.length });
  } catch (e) {
    console.error('[LOGS] write failed:', e);
    return res.status(500).json({ error: String(e) });
  }
});

// GET /logs/recent?limit=10 - 读取最近 N 条
router.get('/recent', async (req, res) => {
  try {
    const limit = Math.max(1, Math.min(1000, Number(req.query.limit) || 100));
    let text = '';
    try {
      text = await fs.readFile(LOG_FILE, 'utf8');
    } catch {
      return res.json({ ok: true, events: [] });
    }
    const lines = text.trim().split(/\r?\n/);
    const tail = lines.slice(-limit);
    const events = tail.map(l => {
      try { return JSON.parse(l); } catch { return null; }
    }).filter(Boolean);
    return res.json({ ok: true, events });
  } catch (e) {
    return res.status(500).json({ error: String(e) });
  }
});

// GET /logs/status - 状态信息
router.get('/status', async (req, res) => {
  try {
    await ensureLogsDir();
    let stats = { size: 0, lines: 0 };
    try {
      const stat = await fs.stat(LOG_FILE);
      const text = await fs.readFile(LOG_FILE, 'utf8');
      stats = {
        size: stat.size,
        lines: text.trim().split(/\r?\n/).filter(l => l.trim()).length
      };
    } catch {}

    return res.json({
      ok: true,
      stats: {
        log_files: stats.size > 0 ? 1 : 0,
        total_size_bytes: stats.size,
        total_events_approx: stats.lines,
        logs_dir: LOG_DIR
      },
      recent_files: stats.size > 0 ? [path.basename(LOG_FILE)] : []
    });
  } catch (e) {
    return res.status(500).json({ error: String(e) });
  }
});

export default router;