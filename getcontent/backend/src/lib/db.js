import { Pool } from 'pg';
import { config } from 'dotenv';
config();

export const pool = new Pool({
  connectionString: process.env.DATABASE,
  max: 10,                 // tune per deployment
  idleTimeoutMillis: 30000 // free idle clients
});

export async function q(text, params) {
  const start = Date.now();
  const res = await pool.query(text, params);
  // console.debug('[db]', text.split('\n')[0], params || [], `${Date.now()-start}ms`);
  return res;
}

export async function tx(fn) {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const res = await fn(client);
    await client.query('COMMIT');
    return res;
  } catch (e) {
    await client.query('ROLLBACK');
    throw e;
  } finally {
    client.release();
  }
}