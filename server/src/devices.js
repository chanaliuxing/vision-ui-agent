// src/devices.js
import express from "express";
import { authRequired } from "./middleware.js";
import { pool } from "./db.js";
import { ensureDeviceAllowance } from "./plans.js";

export const devices = express.Router();

devices.post("/register", authRequired, async (req, res) => {
  try {
    const user_id = req.user.user_id;
    const { machine_code, name, capabilities } = req.body || {};
    if (!machine_code) return res.status(400).json({ error: "no machine_code" });

    // 检查是否已存在
    const { rows: existing } = await pool.query("select * from devices where machine_code=$1", [machine_code]);
    if (existing.length) {
      // 若已属于其他用户，可以拒绝或转移；这里假设重绑给同一用户
      if (existing[0].user_id !== user_id) {
        return res.status(409).json({ error: "device already registered to another user" });
      }
      const { rows } = await pool.query(
        "update devices set user_id=$1, name=$2, capabilities=$3, status=1, last_seen=now() where machine_code=$4 returning id",
        [user_id, name || existing[0].name, capabilities || existing[0].capabilities, machine_code]
      );
      return res.json({ device_id: rows[0].id, reused: true });
    }

    await ensureDeviceAllowance(user_id);
    const { rows } = await pool.query(
      "insert into devices(user_id,machine_code,name,capabilities,last_seen) values($1,$2,$3,$4,now()) returning id",
      [user_id, machine_code, name || null, capabilities || {}]
    );

    return res.json({ device_id: rows[0].id, reused: false });
  } catch (error) {
    if (error.code === "DEVICE_LIMIT") {
      return res.status(409).json({ error: "device limit reached" });
    }
    console.error("Device register error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

devices.post("/heartbeat", authRequired, async (req, res) => {
  try {
    const user_id = req.user.user_id;
    const { device_id } = req.body || {};
    if (!device_id) return res.status(400).json({ error: "no device_id" });

    await pool.query("update devices set last_seen=now() where id=$1 and user_id=$2", [device_id, user_id]);
    return res.json({ ok: true });
  } catch (error) {
    console.error("Heartbeat error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

devices.get("/list", authRequired, async (req, res) => {
  try {
    const user_id = req.user.user_id;
    const { rows } = await pool.query(
      "select id, name, capabilities, last_seen, created_at from devices where user_id=$1 and status=1",
      [user_id]
    );
    return res.json({ devices: rows });
  } catch (error) {
    console.error("Device list error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});