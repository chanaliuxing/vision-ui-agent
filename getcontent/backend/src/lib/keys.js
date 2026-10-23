import nacl from 'tweetnacl';
import { ED25519_SEED_B64, KEY_ID } from '../config.js';

const seed = Buffer.from(ED25519_SEED_B64, 'base64');
if (seed.length !== 32) throw new Error('ED25519_SEED_B64 must be 32 bytes (base64)');
const keyPair = nacl.sign.keyPair.fromSeed(new Uint8Array(seed));

export const keyId = KEY_ID;
export const publicKey = keyPair.publicKey;      // Uint8Array(32)
export const secretKey = keyPair.secretKey;      // Uint8Array(64)


export function signPayload(payloadObj) {
  const data = new TextEncoder().encode(JSON.stringify(payloadObj));
  const sig = nacl.sign.detached(data, secretKey);
  return Buffer.from(sig).toString('base64');
}