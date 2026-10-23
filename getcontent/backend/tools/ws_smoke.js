#!/usr/bin/env node
import http from 'http';

function httpRequest(method, url, body){
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const opts = { method, hostname: u.hostname, port: u.port, path: u.pathname + (u.search||''), headers: {} };
    let dataStr = null;
    if (body){ dataStr = JSON.stringify(body); opts.headers['Content-Type'] = 'application/json'; opts.headers['Content-Length'] = Buffer.byteLength(dataStr); }
    const req = http.request(opts, (res) => {
      let chunks = '';
      res.setEncoding('utf8');
      res.on('data', d=> chunks+=d);
      res.on('end', ()=>{
        try { resolve({ status: res.statusCode, json: JSON.parse(chunks) }); }
        catch { resolve({ status: res.statusCode, text: chunks }); }
      });
    });
    req.on('error', reject);
    if (dataStr) req.write(dataStr);
    req.end();
  });
}

async function main(){
  const base = process.env.ORCH_BASE || 'http://127.0.0.1:8788';
  console.log('Orchestrator base:', base);
  const health = await httpRequest('GET', base + '/ws/health');
  console.log('WS health:', health);
  const conns = await httpRequest('GET', base + '/ws/connections');
  console.log('Connections:', conns);

  const args = process.argv.slice(2);
  const idxDev = args.indexOf('--device_id');
  const idxTab = args.indexOf('--tab_id');
  const idxAction = args.indexOf('--action');
  if (idxDev >= 0 && idxTab >= 0 && idxAction >= 0){
    const device_id = args[idxDev+1];
    const tab_id = parseInt(args[idxTab+1], 10);
    const action = args[idxAction+1];
    const payloadIdx = args.indexOf('--args');
    let a = {};
    if (payloadIdx >= 0){ try { a = JSON.parse(args[payloadIdx+1]); } catch { console.warn('Bad --args JSON, using {}'); a = {}; } }
    console.log('Dispatching action:', action, 'header', {device_id, tab_id}, 'args', a);
    const out = await httpRequest('POST', base + '/ws/action', { header:{ device_id, tab_id }, action, args:a, await_result:true, timeout_ms: 5000 });
    console.log('Action result:', out);
  }
}

main().catch(e=>{ console.error('smoke failed:', e?.message || e); process.exit(1); });

