// src/plans.js
import { pool } from "./db.js";

export async function ensureDeviceAllowance(user_id) {
  const { rows: subs } = await pool.query(
    "select device_limit from subscriptions where user_id=$1 and status='active' order by started_at desc limit 1",
    [user_id]
  );
  const limit = subs[0]?.device_limit ?? 1;

  const { rows: cnt } = await pool.query(
    "select count(*)::int as n from devices where user_id=$1 and status=1",
    [user_id]
  );

  if ((cnt[0]?.n ?? 0) >= limit) {
    const err = new Error("device limit reached");
    err.code = "DEVICE_LIMIT";
    throw err;
  }
}