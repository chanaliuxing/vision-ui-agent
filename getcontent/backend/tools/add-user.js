import { createUser } from '../src/lib/users.js';
import 'dotenv/config';

const [,, username, password, accountId] = process.argv;
if (!username || !password) {
  console.error('Usage: node tools/add-user.js <username> <password> [account_id]');
  console.error('Example: node tools/add-user.js alice mypassword123 acct_alice');
  process.exit(1);
}

async function main() {
  try {
    const account_id = accountId || `acct_${username}`;
    const user = await createUser({ account_id, username, password });
    console.log('✅ User created/updated in PostgreSQL:');
    console.log(`   Account ID: ${user.account_id}`);
    console.log(`   Username: ${user.username}`);
  } catch (error) {
    console.error('❌ Failed to create user:', error.message);
    process.exit(1);
  }
  process.exit(0);
}

main();