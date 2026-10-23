import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { Pool } from 'pg';
import 'dotenv/config';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MIG_DIR = path.join(__dirname, '..', 'migrations');

const pool = new Pool({ connectionString: process.env.DATABASE });

async function alreadyApplied(client) {
  await client.query(`
    CREATE TABLE IF NOT EXISTS schema_migrations(
      id SERIAL PRIMARY KEY,
      filename TEXT UNIQUE NOT NULL,
      applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `);
  const { rows } = await client.query('SELECT filename FROM schema_migrations');
  return new Set(rows.map(r => r.filename));
}

async function main() {
  const files = fs.readdirSync(MIG_DIR).filter(f => f.endsWith('.sql')).sort();
  const client = await pool.connect();
  try {
    const done = await alreadyApplied(client);
    for (const f of files) {
      if (done.has(f)) { console.log('[migrate] skip', f); continue; }
      const sql = fs.readFileSync(path.join(MIG_DIR, f), 'utf8');
      console.log('[migrate] apply', f);
      await client.query('BEGIN');
      await client.query(sql);
      await client.query('INSERT INTO schema_migrations(filename) VALUES($1)', [f]);
      await client.query('COMMIT');
    }
    console.log('[migrate] all done');
  } catch (e) {
    await client.query('ROLLBACK').catch(()=>{});
    console.error('[migrate] failed:', e);
    process.exit(1);
  } finally {
    client.release();
    await pool.end();
  }
}
main();