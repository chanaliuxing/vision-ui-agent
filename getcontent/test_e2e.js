#!/usr/bin/env node
// End-to-end workflow testing script
// Tests the complete DOM → Vision fallback + artifact saving pipeline

import fs from 'fs';
import path from 'path';
import dotenv from 'dotenv';

// Load environment variables
dotenv.config();

const ORCHESTRATOR_BASE = process.env.ORCHESTRATOR_URL || 'http://127.0.0.1:8788';
const VISION_API_BASE = process.env.VISION_API_URL || 'http://127.0.0.1:8000';

// Test configuration
const TESTS = {
  'xhs_search_comments': {
    workflow_path: './workflows/xhs_search_comments.json',
    expected_artifacts: ['xhs/海边穿搭_第3帖_评论.txt'],
    timeout_seconds: 180,
    description: 'XHS search and comment scraping with DOM→Vision fallback'
  }
};

async function checkServiceHealth() {
  console.log('🔍 Checking service availability...');
  
  const services = [
    { name: 'Orchestrator', url: `${ORCHESTRATOR_BASE}/health` },
    { name: 'Vision API', url: `${VISION_API_BASE}/health` }
  ];
  
  for (const service of services) {
    try {
      const response = await fetch(service.url, { method: 'GET' });
      if (response.ok) {
        console.log(`✅ ${service.name} is healthy`);
      } else {
        console.log(`❌ ${service.name} returned HTTP ${response.status}`);
        return false;
      }
    } catch (error) {
      console.log(`❌ ${service.name} is unreachable: ${error.message}`);
      console.log(`   Make sure it's running on ${service.url}`);
      return false;
    }
  }
  
  return true;
}

async function startWorkflow(workflowPath) {
  const workflowJson = JSON.parse(fs.readFileSync(workflowPath, 'utf8'));
  
  console.log(`🚀 Starting workflow: ${workflowJson.name}`);
  
  const response = await fetch(`${ORCHESTRATOR_BASE}/runs/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workflow: workflowJson })
  });
  
  if (!response.ok) {
    throw new Error(`Failed to start workflow: HTTP ${response.status}`);
  }
  
  const result = await response.json();
  
  if (!result.ok) {
    throw new Error(`Workflow start failed: ${result.error}`);
  }
  
  console.log(`✅ Workflow started: ${result.run_id} (${result.steps} steps)`);
  return result.run_id;
}

async function pollWorkflowStatus(runId, timeoutSeconds = 180) {
  const startTime = Date.now();
  const timeoutMs = timeoutSeconds * 1000;
  
  console.log(`⏱️  Polling workflow status (timeout: ${timeoutSeconds}s)...`);
  
  while (Date.now() - startTime < timeoutMs) {
    try {
      const response = await fetch(`${ORCHESTRATOR_BASE}/runs/${runId}`);
      
      if (!response.ok) {
        console.log(`Warning: Status check failed: HTTP ${response.status}`);
        await sleep(5000);
        continue;
      }
      
      const status = await response.json();
      
      if (!status.ok) {
        throw new Error(`Status check failed: ${status.error}`);
      }
      
      const { run, steps, artifacts } = status;
      
      const completedSteps = steps.filter(s => s.status === 'success').length;
      const failedSteps = steps.filter(s => s.status === 'failed').length;
      const pendingSteps = steps.filter(s => s.status === 'pending').length;
      
      console.log(`📊 Status: ${run.status} | Steps: ${completedSteps}✅ ${failedSteps}❌ ${pendingSteps}⏳ | Artifacts: ${artifacts.length}`);
      
      if (run.status === 'completed') {
        console.log('🎉 Workflow completed successfully!');
        return { success: true, run, steps, artifacts };
      } else if (run.status === 'failed') {
        console.log('💥 Workflow failed');
        
        // Show failed steps
        const failed = steps.filter(s => s.status === 'failed');
        for (const step of failed) {
          console.log(`   ❌ Step ${step.idx}: ${step.error || 'Unknown error'}`);
        }
        
        return { success: false, run, steps, artifacts };
      }
      
      // Still running, wait and check again
      await sleep(3000);
      
    } catch (error) {
      console.log(`⚠️  Polling error: ${error.message}`);
      await sleep(5000);
    }
  }
  
  // Timeout reached
  console.log(`⏰ Workflow timed out after ${timeoutSeconds} seconds`);
  
  // Get final status
  try {
    const response = await fetch(`${ORCHESTRATOR_BASE}/runs/${runId}`);
    if (response.ok) {
      const status = await response.json();
      return { success: false, timeout: true, ...status };
    }
  } catch (e) {
    console.log('Failed to get final status:', e.message);
  }
  
  return { success: false, timeout: true };
}

async function validateArtifacts(artifacts, expectedPaths) {
  console.log('📋 Validating artifacts...');
  
  const foundPaths = artifacts.map(a => a.path).filter(Boolean);
  const missingPaths = expectedPaths.filter(p => !foundPaths.includes(p));
  
  if (missingPaths.length > 0) {
    console.log(`❌ Missing expected artifacts: ${missingPaths.join(', ')}`);
    return false;
  }
  
  // Check artifact content
  for (const artifact of artifacts) {
    if (artifact.kind === 'text' && artifact.payload) {
      const textLength = artifact.payload.length;
      console.log(`📄 ${artifact.path}: ${textLength} characters`);
      
      if (textLength === 0) {
        console.log(`⚠️  Warning: ${artifact.path} is empty`);
      } else if (textLength < 50) {
        console.log(`⚠️  Warning: ${artifact.path} is very short (${textLength} chars)`);
      } else {
        console.log(`✅ ${artifact.path} contains substantial content`);
      }
      
      // Show preview
      const preview = artifact.payload.slice(0, 200);
      console.log(`   Preview: "${preview}${artifact.payload.length > 200 ? '...' : ''}"`);
    }
  }
  
  return true;
}

async function runTest(testName, testConfig) {
  console.log(`\n${'='.repeat(60)}`);
  console.log(`🧪 Running test: ${testName}`);
  console.log(`📝 ${testConfig.description}`);
  console.log(`${'='.repeat(60)}`);
  
  try {
    // 1. Start workflow
    const runId = await startWorkflow(testConfig.workflow_path);
    
    // 2. Poll for completion
    const result = await pollWorkflowStatus(runId, testConfig.timeout_seconds);
    
    // 3. Validate results
    if (result.success) {
      const artifactsValid = await validateArtifacts(result.artifacts, testConfig.expected_artifacts);
      
      if (artifactsValid) {
        console.log(`🎉 Test ${testName} PASSED`);
        return { name: testName, status: 'PASSED', runId, artifacts: result.artifacts.length };
      } else {
        console.log(`❌ Test ${testName} FAILED: Invalid artifacts`);
        return { name: testName, status: 'FAILED', reason: 'invalid_artifacts', runId };
      }
    } else {
      const reason = result.timeout ? 'timeout' : 'workflow_failed';
      console.log(`❌ Test ${testName} FAILED: ${reason}`);
      return { name: testName, status: 'FAILED', reason, runId };
    }
    
  } catch (error) {
    console.log(`💥 Test ${testName} ERROR: ${error.message}`);
    return { name: testName, status: 'ERROR', error: error.message };
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function main() {
  console.log('🚀 Starting E2E Workflow Tests');
  console.log('===============================');
  
  // Check prerequisites
  const servicesHealthy = await checkServiceHealth();
  if (!servicesHealthy) {
    console.log('\n❌ Prerequisites not met. Please start required services:');
    console.log('   - Orchestrator: node getcontent/backend/orchestrator.js');
    console.log('   - Vision API: uvicorn app:app --port 8000');
    console.log('   - Chrome extension: Load unpacked extension from getcontent/extension/');
    process.exit(1);
  }
  
  console.log('\n📋 Manual Steps Required:');
  console.log('1. Open Chrome with the extension loaded');
  console.log('2. Navigate to xiaohongshu.com and ensure you can access it');
  console.log('3. The extension should be polling for commands automatically');
  console.log('\nPress Enter to continue...');
  
  // Wait for user confirmation (in a real test, this could be automated)
  await new Promise(resolve => {
    process.stdin.once('data', () => resolve());
  });
  
  // Run all tests
  const results = [];
  
  for (const [testName, testConfig] of Object.entries(TESTS)) {
    const result = await runTest(testName, testConfig);
    results.push(result);
    
    // Brief pause between tests
    if (Object.keys(TESTS).length > 1) {
      console.log('\n⏸️  Pausing 10 seconds before next test...');
      await sleep(10000);
    }
  }
  
  // Summary report
  console.log('\n' + '='.repeat(60));
  console.log('📊 TEST SUMMARY');
  console.log('='.repeat(60));
  
  const passed = results.filter(r => r.status === 'PASSED').length;
  const failed = results.filter(r => r.status === 'FAILED').length;
  const errors = results.filter(r => r.status === 'ERROR').length;
  
  console.log(`Total tests: ${results.length}`);
  console.log(`✅ Passed: ${passed}`);
  console.log(`❌ Failed: ${failed}`);
  console.log(`💥 Errors: ${errors}`);
  
  for (const result of results) {
    const status = result.status === 'PASSED' ? '✅' : result.status === 'FAILED' ? '❌' : '💥';
    const details = result.reason ? ` (${result.reason})` : result.artifacts ? ` (${result.artifacts} artifacts)` : '';
    console.log(`  ${status} ${result.name}${details}`);
  }
  
  console.log('\n🏁 Tests completed!');
  
  if (passed === results.length) {
    console.log('🎉 All tests passed! The DOM→Vision fallback system is working correctly.');
    process.exit(0);
  } else {
    console.log('⚠️  Some tests failed. Check the logs above for details.');
    process.exit(1);
  }
}

// Run if called directly
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(error => {
    console.error('💥 Test runner crashed:', error);
    process.exit(1);
  });
}

export { runTest, checkServiceHealth };