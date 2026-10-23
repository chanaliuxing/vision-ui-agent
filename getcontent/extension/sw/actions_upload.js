async function runInPage(tabId, fn, args=[]) {
  const res = await chrome.scripting.executeScript({
    target:{ tabId, allFrames:false }, world:'MAIN', func: fn, args
  });
  return res?.[0]?.result;
}

/**
 * Best-effort: create File from dataURL and dispatch dragenter/dragover/drop on drop zone.
 * @returns {Promise<{ok:boolean, reason?:string}>}
 */
export async function dropFileFromDataUrl(tabId, selector, dataUrl, filename='resume.pdf'){
  return runInPage(tabId, async (sel, dataUrl, filename) => {
    try {
      const target = document.querySelector(sel);
      if (!target) return { ok:false, reason:'drop_zone_not_found' };

      const res = await fetch(dataUrl);
      const buf = await res.arrayBuffer();
      const blob = new Blob([buf], { type: (dataUrl.split(';')[0].split(':')[1] || 'application/octet-stream') });
      const file = new File([blob], filename, { type: blob.type });

      const dt = new DataTransfer();
      dt.items.add(file);

      function fire(type){
        const e = new DragEvent(type, { bubbles:true, cancelable:true, dataTransfer: dt });
        target.dispatchEvent(e);
      }
      fire('dragenter'); fire('dragover'); fire('drop');

      // Some widgets expose hidden input after drop — give a small settle time
      setTimeout(()=>{}, 50);
      return { ok:true };
    } catch(e) {
      return { ok:false, reason:String(e) };
    }
  }, [selector, dataUrl, filename]);
}

/** User-assisted fallback: focus & click file input so user picks manually */
export async function focusFileInput(tabId, selector){
  return runInPage(tabId, sel => {
    const el = document.querySelector(sel);
    if (!el) return { ok:false, reason:'file_input_not_found' };
    el.scrollIntoView({block:'center', inline:'center'});
    el.focus();
    (el instanceof HTMLElement) && el.click();
    return { ok:true };
  }, [selector]);
}