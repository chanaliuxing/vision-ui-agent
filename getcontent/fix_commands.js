// Fix commands table
import pkg from 'pg';
const { Pool } = pkg;

const pool = new Pool({
  connectionString: 'postgresql://postgres:postgres@localhost:5432/postgres'
});

async function fixCommandsTable() {
  try {
    console.log('🔧 Fixing commands table...');
    
    // Drop existing commands table if it exists
    await pool.query('DROP TABLE IF EXISTS commands CASCADE');
    console.log('🗑️ Dropped existing commands table');
    
    // Create with correct structure
    await pool.query(`
      CREATE TABLE commands (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        queue TEXT NOT NULL DEFAULT 'agent',
        payload JSONB NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        processed_at TIMESTAMPTZ
      )
    `);
    
    await pool.query('CREATE INDEX idx_commands_queue ON commands(queue)');
    await pool.query('CREATE INDEX idx_commands_status ON commands(status)');
    
    console.log('✅ Commands table created with correct structure');
    
    // Test insert
    await pool.query(`
      INSERT INTO commands (queue, payload) 
      VALUES ('test', '{"test": true}')
    `);
    
    // Clean up
    await pool.query('DELETE FROM commands WHERE queue = $1', ['test']);
    
    console.log('✅ Commands table test passed');
    await pool.end();
    
  } catch (error) {
    console.error('❌ Failed to fix commands table:', error.message);
    process.exit(1);
  }
}

fixCommandsTable();