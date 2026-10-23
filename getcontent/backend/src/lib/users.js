import bcrypt from 'bcryptjs';
import { q } from './db.js';

export async function findUserByUsername(username) {
  const { rows } = await q(
    'SELECT account_id, username, password_hash, is_active FROM users WHERE username = $1',
    [username]
  );
  return rows[0] || null;
}

export async function createUser({ account_id, username, password }) {
  const password_hash = bcrypt.hashSync(password, 10);
  await q(
    `INSERT INTO users(account_id, username, password_hash, is_active)
     VALUES ($1,$2,$3,TRUE)
     ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash`,
    [account_id, username, password_hash]
  );
  return { account_id, username };
}

export async function verifyPassword(user, password) {
  if (!user || !user.password_hash) return false;
  return bcrypt.compare(password, user.password_hash);
}