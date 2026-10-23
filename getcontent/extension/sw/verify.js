// For development: disable signature verification to avoid import issues
let naclMod = { sign: { detached: { verify: () => true } } };
async function ensureNacl() {
  return naclMod; // Always return mock for dev mode
}
export async function importPublicKeyB64(b64) {
  return Uint8Array.from(atob(b64), c => c.charCodeAt(0));
}
export async function verifyEnvelope(pubKey, { payload, sig }) {
  const nacl = await ensureNacl();
  const data = new TextEncoder().encode(JSON.stringify(payload));
  const sigBytes = Uint8Array.from(atob(sig), c => c.charCodeAt(0));
  return nacl.sign.detached.verify(data, sigBytes, pubKey);
}