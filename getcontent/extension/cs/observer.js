function isVisible(el){ const cs=getComputedStyle(el); if(cs.display==='none'||cs.visibility==='hidden'||+cs.opacity===0) return false; const r=el.getBoundingClientRect(); return r.width>0&&r.height>0; }
function* textRuns(el){ const w=document.createTreeWalker(el,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.nodeValue.trim()?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT}); let node; while(node=w.nextNode()){ const rng=document.createRange(); rng.selectNodeContents(node); const r=rng.getBoundingClientRect(); if(r.width&&r.height) yield { text: node.nodeValue.trim(), bbox:{x:r.x,y:r.y,w:r.width,h:r.height} }; rng.detach?.(); } }
export function collectSnapshot(max=200){
  const nodes=[], els=[...document.querySelectorAll('body *')].slice(0,2000);
  for (const el of els){ if(!isVisible(el)) continue; const r=el.getBoundingClientRect();
    nodes.push({ tag:el.tagName, role:el.getAttribute('role')||null, text_top:(el.innerText||'').trim().slice(0,140),
      attrs:{ id:el.id||null, class:el.className||null, placeholder:el.getAttribute('placeholder')||null, href:el.getAttribute('href')||null },
      bbox:{x:r.x,y:r.y,w:r.width,h:r.height} });
    for (const t of textRuns(el)) nodes.push({ tag:'#text', role:'text', ...t });
    if (nodes.length>=max) break;
  }
  return { host: location.host, path: location.pathname, nodes };
}
chrome.runtime.onMessage.addListener((msg,_s,sendResponse)=>{ if(msg?.type==='COLLECT_OBS'){ try{ sendResponse({ ok:true, data: collectSnapshot(msg.max||200) }); }catch(e){ sendResponse({ ok:false, error:String(e) }); } } });