#!/usr/bin/env node
// Manual test script - step by step verification

import readline from 'readline';

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

function ask(question) {
  return new Promise(resolve => rl.question(question, resolve));
}

const API_BASE = 'http://localhost:8787';

async function checkBackend() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    const data = await res.json();
    console.log('✅ Backend health:', data);
    return true;
  } catch (error) {
    console.log('❌ Backend not running:', error.message);
    console.log('📝 Start backend with: npm run dev');
    return false;
  }
}

async function manualTest() {
  console.log('🧪 Manual Test Guide - Hands-Free Automation System\n');
  
  // Step 1: Check backend
  console.log('1️⃣  BACKEND VERIFICATION');
  console.log('═══════════════════════');
  const backendOk = await checkBackend();
  if (!backendOk) return;
  
  await ask('✓ Backend is running. Press Enter to continue...');
  
  // Step 2: Extension setup
  console.log('\n2️⃣  EXTENSION SETUP');
  console.log('═══════════════════════');
  console.log('📋 Follow these steps:');
  console.log('   1. Open Chrome and go to chrome://extensions/');
  console.log('   2. Enable "Developer mode" (top right toggle)');
  console.log('   3. Click "Load unpacked"');
  console.log('   4. Select the /extension folder');
  console.log('   5. Extension should appear as "YOLO+LLM Automation"');
  
  await ask('✓ Extension loaded? Press Enter to continue...');
  
  // Step 3: Test login
  console.log('\n3️⃣  EXTENSION LOGIN TEST');
  console.log('═══════════════════════');
  console.log('📋 Follow these steps:');
  console.log('   1. Click the extension icon in Chrome toolbar');
  console.log('   2. Popup should open showing "Not authenticated"');
  console.log('   3. Click "Login" button (dev mode - no credentials needed)');
  console.log('   4. Status should change to "Hello testuser" in green');
  
  await ask('✓ Login successful? Press Enter to continue...');
  
  // Step 4: Auto-runner test
  console.log('\n4️⃣  AUTO-RUNNER DAEMON TEST');
  console.log('═══════════════════════');
  console.log('📋 In the extension popup:');
  console.log('   1. You should see "Auto-Runner Daemon" section');
  console.log('   2. Status shows "Auto-runner: Stopped" (orange)');
  console.log('   3. Click "Start Auto-Runner" button');
  console.log('   4. Status changes to "Auto-runner: ACTIVE" (green)');
  console.log('   5. Start button becomes disabled, Stop enabled');
  
  await ask('✓ Auto-runner started? Press Enter to continue...');
  
  // Step 5: Command test
  console.log('\n5️⃣  COMMAND QUEUE TEST');
  console.log('═══════════════════════');
  console.log('Now I\'ll enqueue a test command and your extension should pick it up automatically...\n');
  
  try {
    // Create device and enqueue command
    const device_id = 'manual_test_' + Date.now();
    
    console.log('📤 Enqueueing page collection command...');
    const command = {
      device_id,
      type: 'page_collect',
      url: 'https://xiaohongshu.com',
      vars: {
        action: 'collect_page_info',
        include_analysis: true
      }
    };
    
    const res = await fetch(`${API_BASE}/commands/enqueue`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(command)
    });
    
    const result = await res.json();
    console.log('✅ Command enqueued:', result);
    
    console.log('\n📱 Watch your extension:');
    console.log('   - Extension should automatically open xiaohongshu.com');
    console.log('   - It will collect page information');
    console.log('   - Results will be sent back to backend');
    console.log('   - Check browser console for daemon activity logs');
    
  } catch (error) {
    console.log('❌ Command test failed:', error.message);
  }
  
  await ask('✓ Did the extension automatically navigate and collect data? Press Enter to continue...');
  
  // Step 6: Monitoring
  console.log('\n6️⃣  MONITORING & DEBUGGING');
  console.log('═══════════════════════');
  console.log('🔍 To monitor the system:');
  console.log('');
  console.log('Extension Console:');
  console.log('   1. Go to chrome://extensions/');
  console.log('   2. Find your extension');
  console.log('   3. Click "service worker" link');
  console.log('   4. Watch for daemon logs:');
  console.log('      [DAEMON] poll loop starting');
  console.log('      [DAEMON] claimed command: {id: 1}');
  console.log('      [DAEMON] command completed');
  console.log('');
  console.log('Backend Logs:');
  console.log('   - Check your terminal running npm run dev');
  console.log('   - Should show API requests and database activity');
  console.log('');
  console.log('Database Status:');
  console.log('   - Commands are stored in PostgreSQL');
  console.log('   - Device heartbeats tracked automatically');
  
  await ask('✓ System monitoring understood? Press Enter to continue...');
  
  // Step 7: Advanced usage
  console.log('\n7️⃣  ADVANCED USAGE');
  console.log('═══════════════════════');
  console.log('🚀 Now that the system is running, you can:');
  console.log('');
  console.log('Manual Command Creation:');
  console.log('```bash');
  console.log('curl -X POST http://localhost:8787/commands/enqueue \\');
  console.log('  -H "Content-Type: application/json" \\');
  console.log('  -d \'{"device_id":"test","type":"page_collect","url":"https://example.com"}\'');
  console.log('```');
  console.log('');
  console.log('Available Command Types:');
  console.log('   • page_collect - Extract full page information');
  console.log('   • xhs_feed_analysis - Xiaohongshu-specific analysis');
  console.log('   • xhs_reply - Automated social media replies');
  console.log('   • Custom task plans via TQP system');
  console.log('');
  console.log('Multiple Devices:');
  console.log('   - Each browser/device gets unique device_id');
  console.log('   - Commands can target specific devices');
  console.log('   - Load balancing across multiple browsers');
  
  console.log('\n🎉 SETUP COMPLETE!');
  console.log('═════════════════');
  console.log('Your hands-free automation system is now running!');
  console.log('');
  console.log('✅ Backend: http://localhost:8787');
  console.log('✅ Extension: Daemon polling every 5 seconds');
  console.log('✅ Database: Command queue and device tracking');
  console.log('✅ Page Collection: Ready for any website');
  console.log('');
  console.log('💡 Next Steps:');
  console.log('   - Enqueue more commands via API');
  console.log('   - Monitor extension console for activity');
  console.log('   - Customize page scrapers for specific sites');
  console.log('   - Scale to multiple browser instances');
  
  rl.close();
}

manualTest().catch(console.error);