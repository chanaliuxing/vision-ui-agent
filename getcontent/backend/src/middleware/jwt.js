import jwt from 'jsonwebtoken';
import { JWT_SECRET, JWT_ISSUER } from '../util/env.js';

export function requireAuth(req, res, next){
  const h = req.headers['authorization']||'';
  const m = /^Bearer\s+(.+)$/i.exec(h);
  if (!m) return res.status(401).json({ error:'missing bearer token' });
  try{
    req.user = jwt.verify(m[1], JWT_SECRET, { issuer: JWT_ISSUER });
    next();
  }catch(e){
    return res.status(401).json({ error:'invalid token' });
  }
}