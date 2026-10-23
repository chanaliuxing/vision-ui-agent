// src/auth.js
import express from "express";
import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import { pool } from "./db.js";

export const auth = express.Router();

auth.post("/register", async (req, res) => {
  try {
    const { email, password } = req.body || {};
    if (!email || !password) return res.status(400).json({ error: "bad params" });

    const hash = await bcrypt.hash(password, 10);
    const { rows } = await pool.query(
      "insert into users(email,password_hash) values($1,$2) returning id,email",
      [email, hash]
    );

    return res.json({ user: rows[0] });
  } catch (error) {
    if (error.code === '23505') {
      return res.status(409).json({ error: "email already exists" });
    }
    console.error("Register error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

auth.post("/login", async (req, res) => {
  try {
    const { email, password } = req.body || {};
    const { rows } = await pool.query("select id,password_hash from users where email=$1", [email]);
    const u = rows[0];

    if (!u) return res.status(401).json({ error: "bad creds" });

    const ok = await bcrypt.compare(password, u.password_hash);
    if (!ok) return res.status(401).json({ error: "bad creds" });

    const token = jwt.sign({ user_id: u.id }, process.env.JWT_SECRET || "dev", { expiresIn: "8h" });
    return res.json({ access_token: token, user: { id: u.id, email } });
  } catch (error) {
    console.error("Login error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});