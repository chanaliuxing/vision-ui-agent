// Fix commands table to add missing account_id and device_id columns
import pkg from 'pg';
const { Pool } = pkg;

const pool = new Pool({
  connectionString: process.env.DATABASE || 'postgresql://postgres:postgres@localhost:5432/postgres'
});

async function fixCommandsSchema() {
  try {
    console.log('🔧 Adding missing columns to commands table...');
    
    // Add missing columns that the backend expects
    await pool.query(`
      ALTER TABLE commands 
      ADD COLUMN IF NOT EXISTS account_id TEXT,
      ADD COLUMN IF NOT EXISTS device_id TEXT,
      ADD COLUMN IF NOT EXISTS type TEXT,
      ADD COLUMN IF NOT EXISTS url TEXT,
      ADD COLUMN IF NOT EXISTS scope TEXT,
      ADD COLUMN IF NOT EXISTS vars JSONB DEFAULT '{}',
      ADD COLUMN IF NOT EXISTS run_after TIMESTAMPTZ
    `);
    
    console.log('✅ Added missing columns to commands table');
    
    // Add indexes for performance
    await pool.query(`
      CREATE INDEX IF NOT EXISTS idx_commands_account_id ON commands(account_id);
      CREATE INDEX IF NOT EXISTS idx_commands_device_id ON commands(device_id);
      CREATE INDEX IF NOT EXISTS idx_commands_type ON commands(type);
    `);
    
    console.log('✅ Added indexes to commands table');
    
    // Test the new schema with a sample insert (like the backend does)
    const testAccountId = 'test_account';
    const testDeviceId = 'test_device';
    
    const { rows } = await pool.query(`
      INSERT INTO commands (account_id, device_id, type, url, scope, vars, run_after)
      VALUES ($1,$2,$3,$4,$5,$6,$7)
      RETURNING id
    `, [testAccountId, testDeviceId, 'test_command', null, null, {}, null]);
    
    console.log('✅ Schema test passed - inserted command with ID:', rows[0].id);
    
    // Clean up test data
    await pool.query('DELETE FROM commands WHERE account_id = $1', [testAccountId]);
    console.log('✅ Test data cleaned up');
    
    console.log('✅ Commands table schema fixed successfully!');
    await pool.end();
    
  } catch (error) {
    console.error('❌ Failed to fix commands schema:', error.message);
    console.error('Full error:', error);
    process.exit(1);
  }
}

fixCommandsSchema();