import 'dotenv/config';
export const PRODUCT_ID = process.env.PRODUCT_ID;
export const KEY_ID = process.env.KEY_ID || 'K1';
export const ED25519_SEED_B64 = process.env.ED25519_SEED_B64;
export const API_BASE = process.env.API_BASE || process.env.BACKEND_URL || 'http://localhost:8787';
export const DOMAIN_WHITELIST = (process.env.DOMAIN_WHITELIST || '').split(',').map(s=>s.trim()).filter(Boolean);
if (!PRODUCT_ID || !ED25519_SEED_B64) {
  console.error('Missing PRODUCT_ID or ED25519_SEED_B64'); process.exit(1);
}