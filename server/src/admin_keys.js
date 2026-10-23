// server/src/admin_keys.js
// Admin interface for revealing/managing user API keys
import express from "express";
import { pool } from "./db.js";
import { authRequired } from "./middleware.js";
import { decryptKey } from "./crypto.js";

export const adminKeys = express.Router();

// Simple RBAC: admin role only
function adminOnly(req, res, next) {
  if (req.user?.role !== "admin") {
    return res.status(403).json({ error: "forbidden" });
  }
  next();
}

// List API keys (admin view, no auto-reveal)
adminKeys.get("/keys", authRequired, adminOnly, async (req, res) => {
  try {
    const { user_id } = req.query;
    let query, params;

    if (user_id) {
      query = "select id,user_id,provider,name,mode,last4,created_at from user_api_keys where user_id=$1 order by created_at desc";
      params = [user_id];
    } else {
      query = "select id,user_id,provider,name,mode,last4,created_at from user_api_keys order by created_at desc limit 200";
      params = [];
    }

    const { rows } = await pool.query(query, params);
    res.json({ keys: rows });
  } catch (error) {
    console.error("Admin list keys error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Reveal plaintext key (requires reason and optional OTP)
adminKeys.post("/keys/:id/reveal", authRequired, adminOnly, async (req, res) => {
  try {
    const { reason, otp } = req.body || {};
    if (!reason) return res.status(400).json({ error: "reason_required" });

    // TODO: Verify OTP if enabled
    // if (process.env.REQUIRE_OTP && !verifyOTP(req.user.user_id, otp)) {
    //   return res.status(401).json({ error: "invalid_otp" });
    // }

    const { rows } = await pool.query(
      "select * from user_api_keys where id=$1",
      [req.params.id]
    );
    if (!rows.length) return res.status(404).json({ error: "not_found" });

    const k = rows[0];
    let plain = null;

    if (k.mode === "PLAINTEXT") {
      plain = k.plaintext_key;
    } else if (k.enc_key && k.iv && k.tag) {
      try {
        plain = decryptKey(
          Buffer.from(k.enc_key, "base64"),
          Buffer.from(k.iv, "base64"),
          Buffer.from(k.tag, "base64")
        );
      } catch (decryptError) {
        console.error("Decryption failed:", decryptError);
        return res.status(500).json({ error: "decryption_failed" });
      }
    } else {
      return res.status(400).json({ error: "invalid_key_data" });
    }

    // Audit the reveal action
    await pool.query(
      "insert into admin_secret_audit(admin_user_id,action,target_id,reason,ip,ua) values($1,'REVEAL',$2,$3,$4,$5)",
      [req.user.user_id, k.id, reason, req.ip, req.headers['user-agent'] || ""]
    );

    res.json({
      id: k.id,
      provider: k.provider,
      name: k.name,
      mode: k.mode,
      api_key: plain
    });
  } catch (error) {
    console.error("Reveal key error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// List audit logs
adminKeys.get("/audit", authRequired, adminOnly, async (req, res) => {
  try {
    const { target_id, admin_user_id, limit = 100 } = req.query;
    let query = `
      select a.*, u.email as admin_email
      from admin_secret_audit a
      join users u on a.admin_user_id = u.id
      where 1=1
    `;
    const params = [];

    if (target_id) {
      query += " and a.target_id = $" + (params.length + 1);
      params.push(target_id);
    }

    if (admin_user_id) {
      query += " and a.admin_user_id = $" + (params.length + 1);
      params.push(admin_user_id);
    }

    query += " order by a.created_at desc limit $" + (params.length + 1);
    params.push(Math.min(parseInt(limit), 1000));

    const { rows } = await pool.query(query, params);
    res.json({ audit_logs: rows });
  } catch (error) {
    console.error("Get audit logs error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Get user statistics
adminKeys.get("/stats", authRequired, adminOnly, async (req, res) => {
  try {
    const stats = await Promise.all([
      pool.query("select count(*) as total_keys from user_api_keys"),
      pool.query("select count(*) as plaintext_keys from user_api_keys where mode='PLAINTEXT'"),
      pool.query("select count(*) as encrypted_keys from user_api_keys where mode='ENCRYPTED'"),
      pool.query("select count(*) as total_users from users"),
      pool.query("select count(*) as admin_users from users where role='admin'"),
      pool.query("select count(*) as total_reveals from admin_secret_audit where action='REVEAL'"),
    ]);

    res.json({
      stats: {
        total_keys: parseInt(stats[0].rows[0].total_keys),
        plaintext_keys: parseInt(stats[1].rows[0].plaintext_keys),
        encrypted_keys: parseInt(stats[2].rows[0].encrypted_keys),
        total_users: parseInt(stats[3].rows[0].total_users),
        admin_users: parseInt(stats[4].rows[0].admin_users),
        total_reveals: parseInt(stats[5].rows[0].total_reveals),
      }
    });
  } catch (error) {
    console.error("Get stats error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Emergency: Convert plaintext keys to encrypted for a user
adminKeys.post("/convert/:user_id", authRequired, adminOnly, async (req, res) => {
  try {
    const { reason } = req.body || {};
    if (!reason) return res.status(400).json({ error: "reason_required" });

    const { rows: keys } = await pool.query(
      "select id, plaintext_key from user_api_keys where user_id=$1 and mode='PLAINTEXT' and plaintext_key is not null",
      [req.params.user_id]
    );

    let converted = 0;
    for (const key of keys) {
      try {
        const { enc, iv, tag } = encryptKey(key.plaintext_key);
        await pool.query(
          "update user_api_keys set mode='ENCRYPTED', enc_key=$2, iv=$3, tag=$4, plaintext_key=null where id=$1",
          [key.id, enc.toString("base64"), iv.toString("base64"), tag.toString("base64")]
        );
        converted++;
      } catch (error) {
        console.error(`Failed to convert key ${key.id}:`, error);
      }
    }

    // Audit the conversion
    await pool.query(
      "insert into admin_secret_audit(admin_user_id,action,target_id,reason,ip,ua) values($1,'CONVERT',$2,$3,$4,$5)",
      [req.user.user_id, req.params.user_id, reason, req.ip, req.headers['user-agent'] || ""]
    );

    res.json({
      user_id: req.params.user_id,
      converted_keys: converted,
      total_plaintext: keys.length
    });
  } catch (error) {
    console.error("Convert keys error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});