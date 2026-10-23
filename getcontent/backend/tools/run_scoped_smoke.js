#!/usr/bin/env node
// Minimal run-scoped smoke test: start a run, then drive ext.* actions via orchestrator

import http from 'http';

function httpReq(method, url, body, timeoutMs = 10000){
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const opts = { method, hostname: u.hostname, port: u.port || 80, path: u.pathname + (u.search||''), headers: {} };
    const data = body ? JSON.stringify(body) : null;
    if (data) { opts.headers['Content-Type'] = 'application/json'; opts.headers['Content-Length'] = Buffer.byteLength(data); }
    const req = http.request(opts, (res) => {
      let chunks = '';
      res.setEncoding('utf8');
      res.on('data', d => chunks += d);
      res.on('end', () => {
        try { resolve({ status: res.statusCode, json: JSON.parse(chunks) }); }
        catch { resolve({ status: res.statusCode, text: chunks }); }
      });
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs, () => { try { req.destroy(new Error('timeout')); } catch {} });
    if (data) req.write(data);
    req.end();
  });
}

function arg(flag, def=null){
  const i = process.argv.indexOf(flag); return i>=0 ? process.argv[i+1] : def;
}

async function main(){
  const base = (arg('--base') || process.env.ORCH_BASE || 'http://127.0.0.1:8788').replace(/\/$/, '');
  const startUrl = arg('--start') || 'https://www.xiaohongshu.com/explore';
  const domain = arg('--domain') || 'xiaohongshu.com';
  console.log('Orchestrator:', base);

  // 1) start run
  const bodyStart = {
    workflow: { name: 'ext_smoke', start: 'dummy', states: { dummy: { actions: [] } } },
    bind: { strategy: 'match_or_open', domain, prefer_active: true, timeout_ms: 8000 },
    start_url: startUrl
  };
  const start = await httpReq('POST', base + '/runs/start', bodyStart, 12000);
  if (start.status !== 200 || !start.json || !start.json.run_id){
    console.error('runs/start failed:', start); process.exit(1);
  }
  const runId = start.json.run_id;
  console.log('run_id:', runId, 'bound:', !!start.json.bound, start.json.device_id, start.json.tab_id);

  // helper to dispatch one action
  async function dispatch(action, args, awaitResult=true, timeoutMs=10000){
    const body = { run_id: runId, action, args: args||{}, await_result: awaitResult, timeout_ms: timeoutMs };
    const r = await httpReq('POST', base + '/actions/dispatch', body, timeoutMs + 2000);
    if (r.status !== 200 || !r.json || r.json.ok === false){
      console.log('dispatch fail', action, r.json || r.text); return { ok:false, resp:r };
    }
    console.log('dispatch ok', action, r.json.result || {}); return { ok:true, resp:r.json };
  }

  async function waitQuiet(timeoutMs){
    const r = await httpReq('POST', base + '/runs/wait_quiet', { run_id: runId, timeout_ms: timeoutMs }, timeoutMs + 2000);
    console.log('wait_quiet', r.json || r.text);
    return r.json && r.json.ok === true;
  }

  // 2) focus search box
  console.log('Focus search box...');
  await dispatch('ext.click_selector', { sel: "input[placeholder*=\\u641c\\u7d22 i], input[type=search], [role=search] input" }, true, 8000);
  await waitQuiet(3000);

  // 3) type text
  console.log('Type text...');
  await dispatch('ext.type_text', { sel: "input[placeholder*=\\u641c\\u7d22 i], input[type=search], [role=search] input", text: '如何自己打官司', replace: true }, true, 8000);
  await dispatch('ext.key', { key: 'Enter' }, true, 5000);
  await waitQuiet(12000);

  // 4) open first post
  console.log('Open first post...');
  await dispatch('ext.click_selector', { sel: "a[href*=/explore/]:not([rel=nofollow])" }, true, 8000);
  await waitQuiet(12000);

  console.log('Smoke done for run', runId);
}

main().catch(e => { console.error('smoke error:', e?.message || e); process.exit(1); });

