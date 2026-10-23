import express from 'express';
import { DOMAIN_WHITELIST, PRODUCT_ID } from '../config.js';
import { envelope } from '../lib/envelope.js';
import { requireAuth } from '../lib/sessions.js';
const router = express.Router();

router.post('/entitlement/issue', (req,res)=>{
  const { account_id, device_id, product_id, domain } = req.body || {};
  // DEV MODE: bypass auth, use fallback values
  const acc_id = account_id || 'acct_dev';
  const dev_id = device_id || 'dev_device_001';
  if (product_id && product_id !== PRODUCT_ID) return res.status(400).json({ error:'wrong product' });
  const allow = domain ? DOMAIN_WHITELIST.some(d => domain.includes(d)) : true;
  const payload = {
    account_id: acc_id, device_id: dev_id, product_id: PRODUCT_ID,
    exp: Math.floor(Date.now()/1000) + 24*3600,
    scopes: ['plans:read','events:write'],
    domain_whitelist: allow ? DOMAIN_WHITELIST : [],
    features: { network_sniff: true, vision_roi: true }
  };
  res.json(envelope(payload, 24*3600));
});

export default router;