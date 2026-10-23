// Fix demo user password hash
const bcrypt = require('./server/node_modules/bcrypt');

// Generate correct hash for 'demo123'
const hash = bcrypt.hashSync('demo123', 10);
console.log(`Update SQL:`);
console.log(`UPDATE users SET password_hash = '${hash}' WHERE email = 'demo@acme.com';`);