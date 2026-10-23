import express from 'express';
import { q, tx } from '../lib/db.js';
import { requireAuth } from '../lib/sessions.js';

const router = express.Router();

router.post('/devices/heartbeat', requireAuth, async (req, res) => {
  const { device_id, ua } = req.body || {};
  if (!device_id) return res.status(400).json({ error:'device_id required' });
  await q(`
    INSERT INTO devices (device_id, account_id, ua)
    VALUES ($1,$2,$3)
    ON CONFLICT (device_id) DO UPDATE
      SET account_id = EXCLUDED.account_id, ua = EXCLUDED.ua, last_seen = NOW()
  `, [device_id, req.session.account_id, ua || null]);
  res.json({ ok: true, at: Date.now() });
});

router.post('/commands/enqueue', requireAuth, async (req, res) => {
  const { device_id, type, url, scope, vars, run_after } = req.body || {};
  if (!device_id || !type) return res.status(400).json({ error: 'device_id and type required' });
  const { rows } = await q(`
    INSERT INTO commands (account_id, device_id, type, url, scope, vars, run_after)
    VALUES ($1,$2,$3,$4,$5,$6,$7)
    RETURNING id
  `, [req.session.account_id, device_id, type, url || null, scope || null, vars || {}, run_after || null]);
  res.json({ ok: true, id: rows[0].id });
});

router.post('/commands/next', requireAuth, async (req, res) => {
  const { device_id } = req.body || {};
  if (!device_id) return res.status(400).json({ error: 'device_id required' });

  const cmd = await tx(async (client) => {
    const { rows } = await client.query(`
      SELECT id, type, url, scope, vars
      FROM commands
      WHERE device_id = $1
        AND status = 'pending'
        AND (run_after IS NULL OR run_after <= NOW())
      ORDER BY created_at ASC
      LIMIT 1
    `, [device_id]);
    const row = rows[0];
    if (!row) return null;
    await client.query(`
      UPDATE commands
      SET status='claimed', claimed_at=NOW(), updated_at=NOW()
      WHERE id=$1
    `, [row.id]);
    return row;
  });

  res.json({ cmd: cmd || null });
});

router.post('/commands/ack', requireAuth, async (req, res) => {
  const { id, status, result, error } = req.body || {};
  if (!id || !status) return res.status(400).json({ error: 'id & status required' });
  const safe = ['running','succeeded','failed'].includes(status) ? status : 'running';
  await q(`
    UPDATE commands
    SET status = $2,
        started_at = COALESCE(started_at, CASE WHEN $2='running' THEN NOW() ELSE started_at END),
        finished_at = CASE WHEN $2 IN ('succeeded','failed') THEN NOW() ELSE finished_at END,
        result = COALESCE($3, result),
        error = COALESCE($4, error),
        updated_at = NOW()
    WHERE id = $1
  `, [id, safe, result || null, error || null]);
  res.json({ ok: true });
});

export default router;