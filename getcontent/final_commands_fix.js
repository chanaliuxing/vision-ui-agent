// Final fix for commands table - make payload nullable and test
import pkg from 'pg';
const { Pool } = pkg;

const pool = new Pool({
  connectionString: process.env.DATABASE || 'postgresql://postgres:postgres@localhost:5432/postgres'
});

async function finalCommandsFix() {
  try {
    console.log('🔧 Final fix for commands table...');
    
    // Make payload nullable since the backend code doesn't always provide it
    await pool.query(`
      ALTER TABLE commands 
      ALTER COLUMN payload DROP NOT NULL
    `);
    
    console.log('✅ Made payload column nullable');
    
    // Now test with the exact same insert the backend code does
    const testAccountId = 'test_account';
    const testDeviceId = 'test_device';
    
    const { rows } = await pool.query(`
      INSERT INTO commands (account_id, device_id, type, url, scope, vars, run_after)
      VALUES ($1,$2,$3,$4,$5,$6,$7)
      RETURNING id
    `, [testAccountId, testDeviceId, 'test_command', null, null, {}, null]);
    
    console.log('✅ Backend-style insert test passed - ID:', rows[0].id);
    
    // Clean up
    await pool.query('DELETE FROM commands WHERE account_id = $1', [testAccountId]);
    
    // Also test the /commands/next query pattern
    await pool.query(`
      INSERT INTO commands (account_id, device_id, type, status, payload) 
      VALUES ('test2', 'device2', 'test', 'pending', '{"test": true}')
    `);
    
    const { rows: nextRows } = await pool.query(`
      SELECT * FROM commands 
      WHERE status = 'pending' 
      ORDER BY created_at ASC 
      LIMIT 1
    `);
    
    console.log('✅ /commands/next query test passed - found command:', nextRows[0]?.id);
    
    // Clean up
    await pool.query('DELETE FROM commands WHERE account_id = $1', ['test2']);
    
    console.log('✅ All commands table fixes completed successfully!');
    console.log('📊 Backend can now use both old and new command patterns');
    
    await pool.end();
    
  } catch (error) {
    console.error('❌ Final fix failed:', error.message);
    console.error('Full error:', error);
    process.exit(1);
  }
}

finalCommandsFix();