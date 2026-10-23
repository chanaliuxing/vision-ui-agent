import fs from 'fs';
import path from 'path';
const root = path.join(path.dirname(process.cwd()), 'extension','sw');
const files = fs.readdirSync(root).filter(f=>f.endsWith('.js'));
const bad = [];
for (const f of files){
  const s = fs.readFileSync(path.join(root,f),'utf8');
  if (s.match(/import\s*\(['"]https?:\/\//)) bad.push(f);
  if (s.match(/from\s+['"]https?:\/\//)) bad.push(f);
}
if (bad.length){ console.error('External imports not allowed in SW:', bad); process.exit(1); }
console.log('SW imports check passed');