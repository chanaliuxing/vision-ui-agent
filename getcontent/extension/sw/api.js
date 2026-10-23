// Self-contained API helpers that do NOT import from bootstrap to avoid cycles.
import { kvGet } from './db.js';

async function apiBase(){
  return (await kvGet('api_base')) || 'http://localhost:8787';
}

export async function postJSON(path, body){
  const base = await apiBase();
  const res = await fetch(base + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(body||{})
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function postEvent(eventName, payload){
  try{
    const env = await postJSON('/events/ingest', { event: eventName, ts: Date.now(), payload });
    return env;
  }catch(e){
    // non-fatal
    console.warn('postEvent failed', e);
    return null;
  }
}