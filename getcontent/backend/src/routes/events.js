import express from 'express';
import { q } from '../lib/db.js';

const router = express.Router();

router.post('/events/ingest', async (req, res) => {
  try {
    const { type, host, domain, path, ua, ...rest } = req.body || {};
    const h = host || domain || null;   // Prefer host, fallback to domain
    const p = Object.keys(rest).length ? rest : null;
    const account_id = req.session?.account_id || null;

    await q(
      `INSERT INTO events (account_id, type, host, domain, path, ua, payload)
       VALUES ($1, $2, $3, $4, $5, $6, $7)`,
      [account_id, String(type || 'misc'), h, domain || null, path || null, ua || null, p]
    );

    res.json({ ok: true });
  } catch (e) {
    console.error('[events] Database insert failed:', e);
    res.status(500).json({ ok: false, error: 'db_insert_failed' });
  }
});

export default router;