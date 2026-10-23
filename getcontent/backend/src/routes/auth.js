import express from 'express';
import { findUserByUsername, verifyPassword } from '../lib/users.js';
import { createSession, destroySession } from '../lib/sessions.js';
import { isLocked, recordFail, recordSuccess } from '../lib/bruteforce.js';

const router = express.Router();

router.post('/auth/login', async (req, res) => {
  const { username, password } = req.body || {};
  if (!username || !password) return res.status(400).json({ error: 'username/password required' });
  if (await isLocked(username)) return res.status(429).json({ error: 'locked', message: 'Too many attempts. Try later.' });

  const user = await findUserByUsername(username);
  const ok = await verifyPassword(user, password);
  if (!ok || !user?.is_active) {
    const { locked, lockUntil } = await recordFail(username);
    return res.status(401).json({ error: 'invalid_credentials', locked, lockUntil });
  }

  await recordSuccess(username);
  const ip = req.headers['x-forwarded-for']?.split(',')[0]?.trim() || req.socket.remoteAddress || null;
  const ua = req.headers['user-agent'] || null;
  const { sid, exp } = await createSession({ account_id: user.account_id, username: user.username, ip, ua });

  // keep cookie for web UIs (optional)
  const cookieOpts = { httpOnly: true, sameSite: 'lax' };
  if (process.env.NODE_ENV === 'production') cookieOpts.secure = true;
  res.cookie('sid', sid, cookieOpts);

  // IMPORTANT: also return the sid so the extension can use Authorization header
  res.json({ account_id: user.account_id, username: user.username, exp: Math.floor(exp.getTime()/1000), sid });
});

router.post('/auth/logout', async (req, res) => {
  const sid = req.cookies?.sid;
  if (sid) await destroySession(sid);
  res.clearCookie('sid');
  res.json({ ok: true });
});

router.get('/auth/me', (req, res) => {
  if (!req.session) return res.status(401).json({ error: 'unauthorized' });
  res.json({ account_id: req.session.account_id, username: req.session.username });
});

export default router;
