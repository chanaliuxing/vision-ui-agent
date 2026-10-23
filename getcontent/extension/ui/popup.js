const statusEl = document.getElementById('status');
const loginForm = document.getElementById('loginForm');
const usernameEl = document.getElementById('username');
const passwordEl = document.getElementById('password');
const runBtn = document.getElementById('run');
const taskXhsBtn = document.getElementById('task-xhs');
const taskIndeedBtn = document.getElementById('task-indeed');
const replyTextEl = document.getElementById('replyText');
const resumeFileEl = document.getElementById('resumeFile');
const autoStatusEl = document.getElementById('autoStatus');
const autoStartBtn = document.getElementById('autoStart');
const autoStopBtn = document.getElementById('autoStop');
const visionStatusEl = document.getElementById('visionStatus');
const testVisionBtn = document.getElementById('testVision');
const testIntegrationBtn = document.getElementById('testIntegration');

async function readAsDataUrl(file){
  return new Promise((resolve,reject)=>{
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result);
    fr.onerror = reject;
    fr.readAsDataURL(file);
  });
}

function refresh(){
  try {
    chrome.runtime.sendMessage({ type:'GET_STATUS' }, (resp)=>{
      if (chrome.runtime.lastError) {
        console.error('Runtime error in GET_STATUS:', chrome.runtime.lastError);
        statusEl.textContent = 'Extension error: ' + chrome.runtime.lastError.message;
        return;
      }
      if (resp?.me) { statusEl.textContent = `Hello ${resp.me.username}`; statusEl.style.color='green'; }
      else { statusEl.textContent = 'Not authenticated'; statusEl.style.color='orange'; }
    });
  } catch (error) {
    console.error('Error in refresh:', error);
    statusEl.textContent = 'Error: ' + error.message;
  }
}

function refreshAutoMode(){
  chrome.runtime.sendMessage({ type:'GET_AUTO_MODE' }, (resp)=>{
    if (chrome.runtime.lastError) {
      autoStatusEl.textContent = 'Error: ' + chrome.runtime.lastError.message;
      return;
    }
    const enabled = resp?.enabled;
    autoStatusEl.textContent = enabled ? 'Auto-runner: ACTIVE' : 'Auto-runner: Stopped';
    autoStatusEl.style.color = enabled ? 'green' : 'orange';
    autoStartBtn.disabled = enabled;
    autoStopBtn.disabled = !enabled;
  });
}

loginForm.onsubmit = (e)=>{
  e.preventDefault();
  statusEl.textContent = 'Logging in...';
  try {
    console.log('Sending LOGIN message...');
    chrome.runtime.sendMessage({ type:'LOGIN', username: usernameEl.value, password: passwordEl.value }, (resp)=>{
      if (chrome.runtime.lastError) {
        console.error('Runtime error in LOGIN:', chrome.runtime.lastError);
        statusEl.textContent = 'Extension error: ' + chrome.runtime.lastError.message;
        return;
      }
      console.log('LOGIN response:', resp);
      if (resp?.ok) {
        refresh();
      } else {
        statusEl.textContent = resp?.error || 'Login failed';
      }
    });
  } catch (error) {
    console.error('Error in login:', error);
    statusEl.textContent = 'Login error: ' + error.message;
  }
};
runBtn.onclick = async ()=>{
  statusEl.textContent = 'Running plan...';
  chrome.runtime.sendMessage({ type:'RUN_PLAN' }, (resp)=>{
    if (resp?.ok) {
      statusEl.textContent = 'Plan executed successfully';
      statusEl.style.color = 'green';
    } else {
      statusEl.textContent = resp?.error || 'Plan execution failed';
      statusEl.style.color = 'red';
    }
  });
};

taskXhsBtn.onclick = () => {
  const vars = {};
  if (replyTextEl?.value) vars.reply_text = replyTextEl.value;
  chrome.runtime.sendMessage({ type:'RUN_TASK', name:'task:xhs_auto_reply', vars }, (resp)=>{
    statusEl.textContent = resp?.ok ? 'XHS task done' : ('XHS task failed: ' + (resp?.error || resp?.reason || ''));
    console.log('Task outputs:', resp?.outputs);
  });
};

taskIndeedBtn.onclick = async () => {
  const vars = {};
  if (replyTextEl?.value) vars.reply_text = replyTextEl.value;
  if (resumeFileEl?.files?.[0]) {
    vars.resume_data_url = await readAsDataUrl(resumeFileEl.files[0]);
    vars.resume_filename = resumeFileEl.files[0].name || 'resume.pdf';
  }
  chrome.runtime.sendMessage({ type:'RUN_TASK', name:'task:indeed_apply', vars }, (resp)=>{
    statusEl.textContent = resp?.ok ? 'Indeed task done' : ('Indeed task failed: ' + (resp?.error || resp?.reason || ''));
    console.log('Task outputs:', resp?.outputs);
  });
};

autoStartBtn.onclick = () => {
  autoStatusEl.textContent = 'Starting auto-runner...';
  chrome.runtime.sendMessage({ type:'SET_AUTO_MODE', enabled: true }, (resp)=>{
    if (resp?.ok) {
      refreshAutoMode();
    } else {
      autoStatusEl.textContent = 'Failed to start auto-runner';
      autoStatusEl.style.color = 'red';
    }
  });
};

autoStopBtn.onclick = () => {
  autoStatusEl.textContent = 'Stopping auto-runner...';
  chrome.runtime.sendMessage({ type:'SET_AUTO_MODE', enabled: false }, (resp)=>{
    if (resp?.ok) {
      refreshAutoMode();
    } else {
      autoStatusEl.textContent = 'Failed to stop auto-runner';
      autoStatusEl.style.color = 'red';
    }
  });
};

// Vision Integration Test handlers
testVisionBtn.onclick = () => {
  visionStatusEl.textContent = 'Testing vision API...';
  visionStatusEl.style.color = 'orange';
  
  chrome.runtime.sendMessage({ type: 'TEST_VISION_API' }, (resp) => {
    if (chrome.runtime.lastError) {
      visionStatusEl.textContent = 'Vision test error: ' + chrome.runtime.lastError.message;
      visionStatusEl.style.color = 'red';
      return;
    }
    
    if (resp?.ok) {
      visionStatusEl.textContent = `Vision API OK (${resp.detections_found} detections)`;
      visionStatusEl.style.color = 'green';
      console.log('Vision test results:', resp);
    } else {
      visionStatusEl.textContent = 'Vision API failed: ' + (resp?.reason || 'unknown error');
      visionStatusEl.style.color = 'red';
    }
  });
};

testIntegrationBtn.onclick = () => {
  visionStatusEl.textContent = 'Running integration test...';
  visionStatusEl.style.color = 'orange';
  
  chrome.runtime.sendMessage({ type: 'RUN_INTEGRATION_TEST' }, (resp) => {
    if (chrome.runtime.lastError) {
      visionStatusEl.textContent = 'Integration test error: ' + chrome.runtime.lastError.message;
      visionStatusEl.style.color = 'red';
      return;
    }
    
    if (resp?.ok) {
      const rate = resp.success_rate || '0%';
      visionStatusEl.textContent = `Integration test completed (${rate} success)`;
      visionStatusEl.style.color = 'green';
      console.log('Integration test results:', resp);
    } else {
      visionStatusEl.textContent = 'Integration test failed: ' + (resp?.error || 'unknown error');
      visionStatusEl.style.color = 'red';
    }
  });
};

document.addEventListener('DOMContentLoaded', () => {
  refresh();
  refreshAutoMode();
});