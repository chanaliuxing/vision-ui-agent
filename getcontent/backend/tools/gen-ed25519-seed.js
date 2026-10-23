import { randomBytes } from 'crypto';
console.log(Buffer.from(randomBytes(32)).toString('base64'));