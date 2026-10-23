// backend/src/lib/sessions.js
import { nanoid } from 'nanoid';
import { q } from './db.js';

const TTL_MS = 7 * 24 * 3600 * 1000; // 7 days

export async function createSession({ account_id, username, ip, ua }) {
  const sid = 'sid_' + nanoid(24);
  const exp = new Date(Date.now() + TTL_MS);
  await q(
    `INSERT INTO sessions(sid, account_id, username, exp, ip, ua)
     VALUES ($1,$2,$3,$4,$5,$6)`,
    [sid, account_id, username, exp, ip || null, ua || null]
  );
  return { sid, exp };
}

export async function getSession(sid) {
  const { rows } = await q(
    'SELECT sid, account_id, username, exp FROM sessions WHERE sid=$1',
    [sid]
  );
  const s = rows[0];
  if (!s) return null;
  if (new Date(s.exp).getTime() <= Date.now()) {
    try { await q('DELETE FROM sessions WHERE sid=$1', [sid]); } catch {}
    return null;
  }
  try { await q('UPDATE sessions SET last_seen=NOW() WHERE sid=$1', [sid]); } catch {}
  return s;
}

export async function destroySession(sid) {
  if (!sid) return;
  try { await q('DELETE FROM sessions WHERE sid=$1', [sid]); } catch {}
}

// Single definition only
export function sidFromAuthHeader(req) {
  const h = req.headers?.authorization || req.headers?.Authorization;
  if (!h) return null;
  const m = String(h).match(/^Bearer\s+(.+)$/i);
  return m ? m[1] : null;
}

export function sessionMiddleware(req, _res, next) {
  const cookieSid = req.cookies?.sid || null;
  const headerSid = sidFromAuthHeader(req) || null;
  const sid = headerSid || cookieSid;
  req.session = null;
  if (!sid) return next();
  getSession(sid)
    .then((s) => { if (s) req.session = s; next(); })
    .catch(() => next());
}

export function requireAuth(req, res, _next) {
  if (!req.session) return res.status(401).json({ error: 'unauthorized' });
  return _next();
}