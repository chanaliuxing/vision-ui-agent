// Quick database table check
import pkg from 'pg';
const { Pool } = pkg;

const pool = new Pool({
  connectionString: 'postgresql://postgres:postgres@localhost:5432/postgres'
});

async function checkTables() {
  try {
    const tables = await pool.query(`
      SELECT table_name, column_name, data_type 
      FROM information_schema.columns 
      WHERE table_name IN ('workflow_runs', 'run_steps', 'artifacts')
      ORDER BY table_name, ordinal_position
    `);
    
    console.log('📋 Database Tables Structure:');
    let currentTable = '';
    for (const row of tables.rows) {
      if (row.table_name !== currentTable) {
        currentTable = row.table_name;
        console.log(`\n✅ ${currentTable}:`);
      }
      console.log(`  - ${row.column_name}: ${row.data_type}`);
    }
    
    // Get row counts
    const counts = await Promise.all([
      pool.query('SELECT COUNT(*) FROM workflow_runs'),
      pool.query('SELECT COUNT(*) FROM run_steps'),
      pool.query('SELECT COUNT(*) FROM artifacts')
    ]);
    
    console.log('\n📊 Table Counts:');
    console.log(`  workflow_runs: ${counts[0].rows[0].count} rows`);
    console.log(`  run_steps: ${counts[1].rows[0].count} rows`);
    console.log(`  artifacts: ${counts[2].rows[0].count} rows`);
    
    await pool.end();
    console.log('\n✅ Database check completed!');
    
  } catch (error) {
    console.error('❌ Database check failed:', error.message);
    process.exit(1);
  }
}

checkTables();