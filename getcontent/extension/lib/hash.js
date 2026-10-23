// Browser-side SHA-256 hash utility for logging
// ESM compatible for MV3 Service Workers

/**
 * Generate SHA-256 hex hash of a string using WebCrypto API
 * @param {string} str - Input string to hash
 * @returns {Promise<string>} - Hex encoded SHA-256 hash
 */
export async function sha256Hex(str) {
  const enc = new TextEncoder();
  const buf = enc.encode(str);
  const digest = await crypto.subtle.digest("SHA-256", buf);
  const arr = Array.from(new Uint8Array(digest));
  return arr.map(b => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Generate compact object signature for logging
 * @param {object} obj - Object to hash
 * @returns {Promise<{hash: string, size: number}>}
 */
export async function objectSignature(obj) {
  const str = JSON.stringify(obj);
  return {
    hash: await sha256Hex(str),
    size: new Blob([str]).size
  };
}