// content/extract-bridge.js
// ⚠️ 这里假设你已有 ext.extract 的调用；只需要在拿到"原始 payload"时调用 sendRaw() 即可。

async function sendRaw(payload) {
  try {
    const reduced = await chrome.runtime.sendMessage({ type: "EXT_EXTRACT_RAW", payload });
    // 之后的流程请改用 reduced（而不是原始 payload）
    // 比如：window.postMessage({ type:"DOM_REDUCED", data: reduced }, "*");
    console.debug("[content] reduced:", reduced);
  } catch (e) {
    console.error("[content] send raw failed", e);
  }
}

// ✅ 给你一个全局桥，方便在现有代码里直接调用：
window.__ext_extract_onDone__ = (payload) => {
  // payload 就是你现在打印的那个原始大 JSON
  sendRaw(payload);
};

// 也可以直接在你 ext.extract 的回调里调：
// onExtractDone(payload) { sendRaw(payload) }