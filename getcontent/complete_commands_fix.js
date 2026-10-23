// Complete fix for commands table - add all missing columns
import pkg from 'pg';
const { Pool } = pkg;

const pool = new Pool({
  connectionString: process.env.DATABASE || 'postgresql://postgres:postgres@localhost:5432/postgres'
});

async function completeCommandsFix() {
  try {
    console.log('🔧 Adding all missing columns to commands table...');
    
    // Add all missing columns that the backend routes expect
    await pool.query(`
      ALTER TABLE commands 
      ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ,
      ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW(),
      ADD COLUMN IF NOT EXISTS result JSONB,
      ADD COLUMN IF NOT EXISTS error TEXT
    `);
    
    console.log('✅ Added claimed_at, updated_at, result, error columns');
    
    // Test the /commands/next workflow exactly as the backend does it
    console.log('🧪 Testing /commands/next workflow...');
    
    // Step 1: Insert a test command (like /commands/enqueue does)
    const testAccountId = 'test_next';
    const testDeviceId = 'test_device_next';
    
    const { rows: insertRows } = await pool.query(`
      INSERT INTO commands (account_id, device_id, type, url, scope, vars, run_after)
      VALUES ($1,$2,$3,$4,$5,$6,$7)
      RETURNING id
    `, [testAccountId, testDeviceId, 'test_next_command', null, null, {}, null]);
    
    console.log('✅ Test command inserted:', insertRows[0].id);
    
    // Step 2: Query like /commands/next does (within transaction)
    const client = await pool.connect();
    try {
      await client.query('BEGIN');
      
      const { rows: selectRows } = await client.query(`
        SELECT id, type, url, scope, vars
        FROM commands
        WHERE device_id = $1
          AND status = 'pending'
          AND (run_after IS NULL OR run_after <= NOW())
        ORDER BY created_at ASC
        LIMIT 1
      `, [testDeviceId]);
      
      console.log('✅ Found command:', selectRows[0]?.id);
      
      if (selectRows[0]) {
        // Step 3: Update with claimed status (as /commands/next does)
        await client.query(`
          UPDATE commands
          SET status='claimed', claimed_at=NOW(), updated_at=NOW()
          WHERE id=$1
        `, [selectRows[0].id]);
        
        console.log('✅ Command claimed successfully');
      }
      
      await client.query('COMMIT');
    } catch (error) {
      await client.query('ROLLBACK');
      throw error;
    } finally {
      client.release();
    }
    
    // Test /commands/ack workflow
    console.log('🧪 Testing /commands/ack workflow...');
    
    await pool.query(`
      UPDATE commands
      SET status = $1, result = $2, error = $3, updated_at = NOW()
      WHERE id = $4
    `, ['completed', {success: true}, null, insertRows[0].id]);
    
    console.log('✅ Command acknowledged successfully');
    
    // Clean up test data
    await pool.query('DELETE FROM commands WHERE account_id = $1', [testAccountId]);
    console.log('✅ Test data cleaned up');
    
    console.log('🎉 Commands table is now fully compatible with all backend routes!');
    
    // Show final schema
    const { rows: schemaRows } = await pool.query(`
      SELECT column_name, data_type, is_nullable, column_default
      FROM information_schema.columns 
      WHERE table_name = 'commands'
      ORDER BY ordinal_position
    `);
    
    console.log('📋 Final commands table schema:');
    schemaRows.forEach(row => {
      console.log(`  ${row.column_name}: ${row.data_type} ${row.is_nullable === 'YES' ? '(nullable)' : '(not null)'}`);
    });
    
    await pool.end();
    
  } catch (error) {
    console.error('❌ Complete fix failed:', error.message);
    console.error('Full error:', error);
    process.exit(1);
  }
}

completeCommandsFix();