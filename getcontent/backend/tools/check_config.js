#!/usr/bin/env node
// Configuration verification script

import fs from 'fs';
import path from 'path';

console.log('🔧 Configuration Checker\n');

// Check backend configuration
console.log('1️⃣  BACKEND CONFIGURATION');
console.log('═══════════════════════');

// Check .env file
const envPath = '.env';
if (fs.existsSync(envPath)) {
  console.log('✅ .env file exists');
  const envContent = fs.readFileSync(envPath, 'utf8');
  
  const checkEnvVar = (name, required = true) => {
    if (envContent.includes(`${name}=`)) {
      const value = envContent.split('\n').find(line => line.startsWith(`${name}=`))?.split('=')[1];
      if (value && value.trim() !== '') {
        console.log(`✅ ${name} = ${value.substring(0, 20)}...`);
      } else {
        console.log(`⚠️  ${name} is empty`);
      }
    } else {
      console.log(`${required ? '❌' : '⚠️ '} ${name} not found`);
    }
  };
  
  checkEnvVar('DATABASE');
  checkEnvVar('GEMINI_API_KEY');
  checkEnvVar('OPENAI_API_KEY');
  checkEnvVar('ED25519_PRIVATE_KEY_B64');
  checkEnvVar('ED25519_PUBLIC_KEY_B64');
  
} else {
  console.log('❌ .env file missing');
  console.log('📝 Run: cp .env.example .env');
}

// Check package.json
if (fs.existsSync('package.json')) {
  console.log('✅ package.json exists');
} else {
  console.log('❌ package.json missing');
}

// Check node_modules
if (fs.existsSync('node_modules')) {
  console.log('✅ node_modules exists');
} else {
  console.log('❌ node_modules missing');
  console.log('📝 Run: npm install');
}

console.log('\n2️⃣  EXTENSION CONFIGURATION');
console.log('═══════════════════════');

// Check extension files
const extensionPath = '../extension';
const checkFile = (filePath, description) => {
  if (fs.existsSync(filePath)) {
    console.log(`✅ ${description}`);
  } else {
    console.log(`❌ ${description} missing: ${filePath}`);
  }
};

checkFile(`${extensionPath}/manifest.json`, 'Extension manifest');
checkFile(`${extensionPath}/keys.json`, 'Extension keys');
checkFile(`${extensionPath}/sw/bootstrap.js`, 'Service worker');
checkFile(`${extensionPath}/sw/daemon.js`, 'Daemon system');
checkFile(`${extensionPath}/sw/page_info.js`, 'Page scraper');
checkFile(`${extensionPath}/ui/popup.html`, 'Extension popup');

// Check manifest.json content
const manifestPath = `${extensionPath}/manifest.json`;
if (fs.existsSync(manifestPath)) {
  try {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    console.log(`✅ Manifest version: ${manifest.manifest_version}`);
    console.log(`✅ Extension name: ${manifest.name}`);
    
    const requiredPermissions = ['activeTab', 'scripting', 'storage', 'tabs', 'alarms', 'webNavigation'];
    const hasPermissions = requiredPermissions.every(perm => manifest.permissions?.includes(perm));
    console.log(`${hasPermissions ? '✅' : '❌'} Required permissions: ${hasPermissions ? 'OK' : 'MISSING'}`);
    
    const hasLocalhostPermission = manifest.host_permissions?.some(perm => perm.includes('localhost:8787'));
    console.log(`${hasLocalhostPermission ? '✅' : '❌'} Localhost permission: ${hasLocalhostPermission ? 'OK' : 'MISSING'}`);
    
  } catch (error) {
    console.log('❌ Invalid manifest.json:', error.message);
  }
}

// Check keys.json
const keysPath = `${extensionPath}/keys.json`;
if (fs.existsSync(keysPath)) {
  try {
    const keys = JSON.parse(fs.readFileSync(keysPath, 'utf8'));
    console.log(`✅ Extension public key: ${keys.publicKey_b64?.substring(0, 20)}...`);
  } catch (error) {
    console.log('❌ Invalid keys.json:', error.message);
  }
}

console.log('\n3️⃣  DATABASE CONFIGURATION');
console.log('═══════════════════════');

// Check if backend is running
try {
  const res = await fetch('http://localhost:8787/health');
  const data = await res.json();
  console.log('✅ Backend server running');
  console.log(`✅ Database status: ${data.database}`);
} catch (error) {
  console.log('❌ Backend server not running');
  console.log('📝 Start with: npm run dev');
}

console.log('\n4️⃣  QUICK START COMMANDS');
console.log('═══════════════════════');
console.log('Backend setup:');
console.log('  npm install');
console.log('  cp .env.example .env');
console.log('  npm run gen:seed        # Generate keys');
console.log('  npm run dev             # Start server');
console.log('');
console.log('Extension setup:');
console.log('  1. Open chrome://extensions/');
console.log('  2. Enable Developer mode');
console.log('  3. Load unpacked extension from /extension folder');
console.log('');
console.log('Testing:');
console.log('  node tools/manual_test.js     # Interactive guide');
console.log('  node tools/test_daemon_flow.js # Automated test');
console.log('');
console.log('Manual command:');
console.log('  curl -X POST http://localhost:8787/commands/enqueue \\');
console.log('    -H "Content-Type: application/json" \\');
console.log('    -d \'{"device_id":"test","type":"page_collect","url":"https://xiaohongshu.com"}\'');