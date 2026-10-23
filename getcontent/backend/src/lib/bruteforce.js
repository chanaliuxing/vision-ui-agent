// backend/src/lib/bruteforce.js
import { q } from './db.js';

// Config: tweak as needed
const THRESHOLD = 3;          // lock after 3 consecutive failures
const BASE_LOCK_MIN = 5;      // first lock duration = 5 minutes
const MAX_LOCK_MIN = 60;      // cap lock to 60 minutes

async function ensureTable() {
  // Create if missing
  await q(`
    CREATE TABLE IF NOT EXISTS brute_force (
      username_lower TEXT PRIMARY KEY
    )
  `);

  // Make sure all columns exist (idempotent)
  await q(`
    ALTER TABLE brute_force
      ADD COLUMN IF NOT EXISTS streak     INTEGER      NOT NULL DEFAULT 0,
      ADD COLUMN IF NOT EXISTS exponent   INTEGER      NOT NULL DEFAULT 0,
      ADD COLUMN IF NOT EXISTS lock_until TIMESTAMPTZ  NULL,
      ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
  `);
}

function nowUtc() {
  return new Date();
}

function minutesFromNow(min) {
  return new Date(Date.now() + min * 60 * 1000);
}

async function getRow(usernameLower) {
  const { rows } = await q(
    `SELECT username_lower, streak, exponent, lock_until
       FROM brute_force
      WHERE username_lower = $1`,
    [usernameLower]
  );
  return rows[0] || null;
}

async function upsertRow(usernameLower, fields) {
  const cols = Object.keys(fields);
  const values = Object.values(fields);
  const sets = cols.map(
    (c, i) => `${c} = $${i + 2}`
  ).join(', ');

  await q(
    `
    INSERT INTO brute_force (username_lower, ${cols.join(', ')})
    VALUES ($1, ${cols.map((_, i) => `$${i + 2}`).join(', ')})
    ON CONFLICT (username_lower)
    DO UPDATE SET ${sets}, updated_at = NOW()
    `,
    [usernameLower, ...values]
  );
}

/**
 * Check if user is currently locked out.
 * @param {string} username
 * @returns {Promise<boolean>}
 */
export async function isLocked(username) {
  await ensureTable();
  const usernameLower = String(username || '').toLowerCase().trim();
  if (!usernameLower) return false;

  const row = await getRow(usernameLower);
  if (!row || !row.lock_until) return false;

  const locked = new Date(row.lock_until).getTime() > Date.now();
  return locked;
}

/**
 * Record a failed login attempt. Returns lock status and when lock ends (if locked).
 * - After THRESHOLD failures: lock for BASE_LOCK_MIN * 2^exponent minutes (capped).
 * - exponent increases each time a lock is applied.
 */
export async function recordFail(username) {
  await ensureTable();
  const usernameLower = String(username || '').toLowerCase().trim();
  if (!usernameLower) return { locked: false };

  const row = await getRow(usernameLower);
  const now = nowUtc();

  // If already locked, keep it
  if (row?.lock_until && new Date(row.lock_until).getTime() > now.getTime()) {
    return { locked: true, lockUntil: row.lock_until };
  }

  const currentStreak = row?.streak ?? 0;
  const currentExponent = row?.exponent ?? 0;
  const nextStreak = currentStreak + 1;

  if (nextStreak >= THRESHOLD) {
    // Apply (or extend) lock
    const lockMinutes = Math.min(
      BASE_LOCK_MIN * Math.pow(2, currentExponent),
      MAX_LOCK_MIN
    );
    const lockUntil = minutesFromNow(lockMinutes);

    await upsertRow(usernameLower, {
      streak: 0,                       // reset streak on lock
      exponent: currentExponent + 1,   // exponential backoff
      lock_until: lockUntil
    });

    return { locked: true, lockUntil };
  } else {
    // Not locked yet, just increase streak
    await upsertRow(usernameLower, {
      streak: nextStreak,
      exponent: currentExponent,
      lock_until: null
    });
    return { locked: false };
  }
}

/**
 * Record a successful login: clears streak/exponent/lock.
 */
export async function recordSuccess(username) {
  await ensureTable();
  const usernameLower = String(username || '').toLowerCase().trim();
  if (!usernameLower) return;

  await upsertRow(usernameLower, {
    streak: 0,
    exponent: 0,
    lock_until: null
  });
}
