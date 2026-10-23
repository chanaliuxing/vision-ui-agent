import express from 'express';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { envelope } from '../lib/envelope.js';
const router = express.Router();
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const plansDir = path.join(__dirname, '..', '..', 'data', 'plans');

function pickPlan(signature={}, scope=''){
  const host = (signature.host||'').toLowerCase();
  if (scope.startsWith('task:')) {
    if (scope === 'task:xhs_auto_reply') return 'xhs_im.tqp.json';
    if (scope === 'task:indeed_apply') return 'indeed_apply.tqp.json';
  }
  if (host.includes('indeed')) return 'indeed_viewjob.eqp.json';
  return 'xhs_im.eqp.json';
}

router.post('/plans/fetch', (req,res)=>{
  const { page_signature, scope } = req.body || {};
  const file = pickPlan(page_signature, scope||'');
  const raw = fs.readFileSync(path.join(plansDir, file), 'utf8');
  const data = JSON.parse(raw);

  let payload;
  if (file.endsWith('.tqp.json')) {
    payload = { tasks: { tqp: data }, version: 1, scope: scope||'task' };
  } else {
    payload = { eqp: data, version: 1, scope: scope||'default' };
  }
  res.json(envelope(payload, 6*3600));
});

export default router;