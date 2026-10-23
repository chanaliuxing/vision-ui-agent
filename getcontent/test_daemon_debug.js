#!/usr/bin/env node
// Debug script to test daemon command polling

// Test 1: Start a simple workflow
console.log('🚀 Testing Daemon Command Polling');

async function testCommandPolling() {
  const ORCHESTRATOR_BASE = 'http://127.0.0.1:8789';
  
  try {
    // 1. Create a simple test workflow
    console.log('1. Creating test workflow...');
    
    const testWorkflow = {
      "name": "daemon_test", 
      "start": "main",
      "states": {
        "main": {
          "actions": [
            {
              "do": "open_url",
              "args": {"url": "https://www.xiaohongshu.com/explore"},
              "description": "Test URL open"
            }
          ]
        }
      }
    };
    
    const startResponse = await fetch(`${ORCHESTRATOR_BASE}/runs/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workflow: testWorkflow })
    });
    
    if (!startResponse.ok) {
      throw new Error(`Start failed: ${startResponse.status}`);
    }
    
    const startResult = await startResponse.json();
    console.log(`✅ Workflow started: ${startResult.run_id}`);
    
    // 2. Test command polling endpoint
    console.log('2. Testing command polling...');
    
    for (let i = 0; i < 5; i++) {
      const pollResponse = await fetch(`${ORCHESTRATOR_BASE}/commands/next`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: 'test_device_123' })
      });
      
      if (!pollResponse.ok) {
        throw new Error(`Poll failed: ${pollResponse.status}`);
      }
      
      const pollResult = await pollResponse.json();
      
      if (pollResult.cmd) {
        console.log(`✅ Command received: ${pollResult.cmd.id}`);
        console.log(`   Action: ${pollResult.cmd.action?.do}`);
        console.log(`   URL: ${pollResult.cmd.action?.args?.url}`);
        
        // 3. Acknowledge command (simulate successful execution)
        const ackResponse = await fetch(`${ORCHESTRATOR_BASE}/commands/ack`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            id: pollResult.cmd.id,
            status: 'succeeded',
            result: { success: true, message: 'Test execution completed' }
          })
        });
        
        if (ackResponse.ok) {
          console.log(`✅ Command acknowledged: ${pollResult.cmd.id}`);
        }
        
        break;
      } else {
        console.log(`⏳ No commands available (attempt ${i + 1}/5)`);
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
    }
    
    // 4. Check workflow status
    console.log('3. Checking workflow status...');
    const statusResponse = await fetch(`${ORCHESTRATOR_BASE}/runs/${startResult.run_id}`);
    
    if (statusResponse.ok) {
      const status = await statusResponse.json();
      console.log(`📊 Workflow status: ${status.run?.status}`);
      
      const completed = status.steps?.filter(s => s.status === 'success').length || 0;
      const failed = status.steps?.filter(s => s.status === 'failed').length || 0;
      const pending = status.steps?.filter(s => s.status === 'pending').length || 0;
      
      console.log(`📊 Steps: ${completed}✅ ${failed}❌ ${pending}⏳`);
    }
    
    console.log('\n🎉 Command polling test completed successfully!');
    console.log('\n📋 Next steps:');
    console.log('1. Ensure Chrome extension daemon is configured to use port 8789');
    console.log('2. Start extension daemon to begin automatic command polling');
    console.log('3. Run full workflow test');
    
  } catch (error) {
    console.error('❌ Command polling test failed:', error.message);
  }
}

testCommandPolling();