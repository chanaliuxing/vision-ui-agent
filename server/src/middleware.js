// src/middleware.js
import jwt from "jsonwebtoken";

export function authRequired(req, res, next) {
  const h = req.headers.authorization || "";
  const token = h.startsWith("Bearer ") ? h.slice(7) : null;
  if (!token) return res.status(401).json({ error: "no token" });

  try {
    const payload = jwt.verify(token, process.env.JWT_SECRET || "dev");
    req.user = payload; // {user_id}
    next();
  } catch (e) {
    res.status(401).json({ error: "bad token" });
  }
}