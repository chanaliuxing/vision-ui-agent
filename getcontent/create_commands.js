// Create commands table
import pkg from 'pg';
const { Pool } = pkg;

const pool = new Pool({
  connectionString: 'postgresql://postgres:postgres@localhost:5432/postgres'
});

async function createCommandsTable() {
  try {
    await pool.query(`
      CREATE TABLE IF NOT EXISTS commands (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        queue TEXT NOT NULL DEFAULT 'agent',
        payload JSONB NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        processed_at TIMESTAMPTZ
      )
    `);
    
    await pool.query('CREATE INDEX IF NOT EXISTS idx_commands_queue ON commands(queue)');
    await pool.query('CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status)');
    
    console.log('✅ Commands table created successfully');
    await pool.end();
    
  } catch (error) {
    console.error('❌ Failed to create commands table:', error.message);
    process.exit(1);
  }
}

createCommandsTable();