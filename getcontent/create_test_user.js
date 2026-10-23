// Create test user for login testing
import { createUser } from './backend/src/lib/users.js';

async function createTestUser() {
  try {
    console.log('🔐 Creating test user...');
    
    const user = await createUser({
      account_id: 'test_account_001',
      username: 'testuser',
      password: '123456'
    });
    
    console.log('✅ Test user created:', user);
    console.log('📝 Login credentials:');
    console.log('   Username: testuser');
    console.log('   Password: 123456');
    
    // Also create an admin user for the extension test
    const admin = await createUser({
      account_id: 'admin_account',
      username: 'admin',
      password: 'admin123'
    });
    
    console.log('✅ Admin user created:', admin);
    console.log('📝 Admin credentials:');
    console.log('   Username: admin');
    console.log('   Password: admin123');
    
  } catch (error) {
    console.error('❌ Failed to create test user:', error.message);
    if (error.message.includes('does not exist')) {
      console.log('💡 Run the migrations first: node backend/migrate.js');
    }
  }
}

createTestUser();