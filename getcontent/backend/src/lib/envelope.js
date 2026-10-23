import { keyId, signPayload } from './keys.js';

export function envelope(payload, ttl_sec=86400) {
  const issued_at = Math.floor(Date.now()/1000);
  const sig = signPayload(payload);
  return { payload, sig, keyId, issued_at, ttl_sec };
}