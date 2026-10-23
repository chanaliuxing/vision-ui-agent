export type DeviceProfile = {
  width: number;
  height: number;
  scale?: number;
  name?: string
};

export interface SimEvidenceProvider {
  name: string;
  // 将 CSS selector（或 XPath）解析为近似坐标（页面坐标）
  selectorToPoint(selector: string, dev: DeviceProfile): { x: number; y: number } | null;
  // 根据 fingerprint/anchor id 返回 bbox+center
  fingerprintToBox(anchorId: string, dev: DeviceProfile): { x: number; y: number; w: number; h: number } | null;
  // OCR 预期文本（若可）
  ocrForRegion(region: {x:number;y:number;w:number;h:number}, lang?: string): string | null;
}

// 1) 默认合成 Provider：稳定哈希 → 伪随机但可复现的坐标
export function createDefaultProvider(seed = 1): SimEvidenceProvider {
  const rng = mulberry32(seed);
  return {
    name: "default",
    selectorToPoint(selector, dev) {
      const h = hash(selector);
      const margin = 40;
      const x = margin + (h % (dev.width - margin*2));
      const y = margin + ((h >>> 8) % (dev.height - margin*2));
      return { x, y };
    },
    fingerprintToBox(anchorId, dev) {
      const h = hash(anchorId);
      const w = 120 + (h % 160);
      const hgt = 36 + ((h >>> 8) % 64);
      const x = (h % (dev.width - w));
      const y = ((h >>> 8) % (dev.height - hgt));
      return { x, y, w, h: hgt };
    },
    ocrForRegion(_r, _lang) { return null; }
  };
}

// 2) 回放 Provider：从"上一轮真实执行轨迹/日志"读取
export function createReplayProvider(trace: Array<any>): SimEvidenceProvider {
  // 允许把 vision/ocr 的 outputs 找回
  const byAnchor = new Map<string, any>();
  for (const t of trace || []) {
    const fp = t?.outputs?.fingerprint_id;
    if (fp) byAnchor.set(fp, t.outputs);
  }
  return {
    name: "replay",
    selectorToPoint(selector, _dev) {
      // 回放里若包含 selector 坐标则返回；没有就放弃
      // 这里留空位（根据你日志字段可扩展）
      return null;
    },
    fingerprintToBox(anchorId, _dev) {
      const o = byAnchor.get(anchorId);
      if (!o) return null;
      const b = o.bbox || {};
      return ("x" in b && "y" in b && "w" in b && "h" in b) ? b : null;
    },
    ocrForRegion(_r, _lang) { return null; }
  };
}

// 3) 指纹库 Provider：对接你未来的云端"元素指纹库"
export function createFingerprintProvider(index: Record<string, any>): SimEvidenceProvider {
  return {
    name: "fingerprint-db",
    selectorToPoint(_sel, _dev) { return null; },
    fingerprintToBox(anchorId, _dev) {
      const item = index[anchorId];
      return item?.bbox || null;
    },
    ocrForRegion(_r, _lang) { return null; }
  };
}

// utils
function hash(s: string) {
  let h = 2166136261 >>> 0;
  for (let i=0;i<s.length;i++){ h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

function mulberry32(a: number){
  return function(){
    let t=(a+=0x6D2B79F5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}