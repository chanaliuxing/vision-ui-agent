// server/src/crypto.js
// AES-GCM encryption for API keys
import crypto from "crypto";

const MASTER_KEY = process.env.MASTER_KEY_HEX
  ? Buffer.from(process.env.MASTER_KEY_HEX, 'hex')
  : crypto.randomBytes(32); // 开发模式随机密钥

export function encryptKey(plaintext) {
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipher('aes-256-gcm', MASTER_KEY);
  cipher.setAAD(Buffer.from('autoagent-api-key', 'utf8'));

  let encrypted = cipher.update(plaintext, 'utf8');
  encrypted = Buffer.concat([encrypted, cipher.final()]);
  const tag = cipher.getAuthTag();

  return {
    enc: encrypted,
    iv: iv,
    tag: tag
  };
}

export function decryptKey(encrypted, iv, tag) {
  const decipher = crypto.createDecipher('aes-256-gcm', MASTER_KEY);
  decipher.setAAD(Buffer.from('autoagent-api-key', 'utf8'));
  decipher.setAuthTag(tag);

  let decrypted = decipher.update(encrypted);
  decrypted = Buffer.concat([decrypted, decipher.final()]);

  return decrypted.toString('utf8');
}