#!/usr/bin/env node
// Database migration runner for workflow tables

import fs from 'fs';
import path from 'path';
import pkg from 'pg';
const { Pool } = pkg;

async function runMigration() {
  const dbUrl = process.env.DATABASE_URL || process.env.DATABASE;
  
  if (!dbUrl) {
    console.error('❌ DATABASE_URL or DATABASE environment variable required');
    console.log('Example: DATABASE=postgresql://user:pass@localhost:5432/dbname');
    process.exit(1);
  }
  
  console.log('🔄 Connecting to database...');
  const pool = new Pool({ connectionString: dbUrl });
  
  try {
    // Test connection
    const client = await pool.connect();
    console.log('✅ Database connection successful');
    client.release();
    
    // Read migration file
    const migrationPath = path.join(process.cwd(), 'migrations', '001_workflow_tables.sql');
    
    if (!fs.existsSync(migrationPath)) {
      console.error(`❌ Migration file not found: ${migrationPath}`);
      process.exit(1);
    }
    
    const migrationSQL = fs.readFileSync(migrationPath, 'utf8');
    console.log('📄 Loaded migration: 001_workflow_tables.sql');
    
    // Execute migration
    console.log('🚀 Executing migration...');
    await pool.query(migrationSQL);
    console.log('✅ Migration completed successfully!');
    
    // Verify tables were created
    const tables = await pool.query(`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public' 
      AND table_name IN ('workflow_runs', 'run_steps', 'artifacts')
      ORDER BY table_name
    `);
    
    console.log('\n📋 Created tables:');
    for (const row of tables.rows) {
      console.log(`  ✓ ${row.table_name}`);
    }
    
    // Get table counts
    try {
      const counts = await Promise.all([
        pool.query('SELECT COUNT(*) FROM workflow_runs'),
        pool.query('SELECT COUNT(*) FROM run_steps'),
        pool.query('SELECT COUNT(*) FROM artifacts')
      ]);
      
      console.log('\n📊 Table status:');
      console.log(`  workflow_runs: ${counts[0].rows[0].count} rows`);
      console.log(`  run_steps: ${counts[1].rows[0].count} rows`);
      console.log(`  artifacts: ${counts[2].rows[0].count} rows`);
    } catch (e) {
      console.log('📊 Tables created (initial counts not available)');
    }
    
  } catch (error) {
    console.error('❌ Migration failed:', error.message);
    
    if (error.code === 'ECONNREFUSED') {
      console.error('💡 Make sure PostgreSQL is running and connection details are correct');
    } else if (error.code === '3D000') {
      console.error('💡 Database does not exist, please create it first');
    }
    
    process.exit(1);
    
  } finally {
    await pool.end();
  }
}

// Run if called directly
if (import.meta.url === `file://${process.argv[1]}`) {
  runMigration();
}

export { runMigration };