// Vision ROI bridge — optional. Posts cropped ROI PNG to a local/remote OCR/OmniParser service.
// Configure endpoint via storage key 'vision_api_base'. If missing, returns [].
import { kvGet } from './db.js';

async function cropDataURL(dataURL, roi){
  // roi = {x,y,w,h} in CSS pixels. Draw into OffscreenCanvas and export PNG Blob.
  const img = await createImageBitmap(await (await fetch(dataURL)).blob());
  const sx = Math.max(0, Math.floor(roi?.x||0));
  const sy = Math.max(0, Math.floor(roi?.y||0));
  const sw = Math.max(1, Math.floor(roi?.w||img.width));
  const sh = Math.max(1, Math.floor(roi?.h||img.height));
  const canvas = new OffscreenCanvas(sw, sh);
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);
  const blob = await canvas.convertToBlob({ type:'image/png' });
  return blob;
}

export async function ocrROI(tabPngDataURL, roi){
  const base = await kvGet('vision_api_base');
  if (!base) return [];
  try{
    const blob = await cropDataURL(tabPngDataURL, roi);
    const fd = new FormData();
    fd.append('image', new File([blob], 'roi.png', { type:'image/png' }));
    const res = await fetch(base + '/ocr', { method:'POST', body: fd });
    if (!res.ok) return [];
    const data = await res.json();
    // expect [{text, bbox:{x,y,w,h}}]
    return Array.isArray(data) ? data : [];
  }catch(e){
    console.warn('ocrROI failed', e);
    return [];
  }
}