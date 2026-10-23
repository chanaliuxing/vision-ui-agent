import nacl from 'tweetnacl';
import fs from 'fs';

const publicKeyB64 = process.argv[2];
const file = process.argv[3];
const env = JSON.parse(fs.readFileSync(file, 'utf8'));
const pub = Uint8Array.from(Buffer.from(publicKeyB64,'base64'));
const data = new TextEncoder().encode(JSON.stringify(env.payload));
const sig = Uint8Array.from(Buffer.from(env.sig,'base64'));
console.log('verify=', nacl.sign.detached.verify(data, sig, pub));