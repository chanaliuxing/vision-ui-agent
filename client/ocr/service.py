# client/ocr/service.py
import numpy as np, cv2, threading, queue, time
from typing import Dict, Any

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

class OCRService:
    def __init__(self, lang="chi_sim+eng", psm=6):
        self.lang = lang
        self.psm = psm
        self.q = queue.Queue(maxsize=8)
        self.res = {}
        self.t = threading.Thread(target=self._loop, daemon=True)
        self.t.start()

    def _loop(self):
        while True:
            try:
                job_id, img = self.q.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                if TESSERACT_AVAILABLE:
                    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
                    cfg = f"--psm {self.psm}"
                    txt = pytesseract.image_to_string(b, lang=self.lang, config=cfg)
                    self.res[job_id] = txt.strip()
                else:
                    # 模拟OCR结果（开发模式）
                    self.res[job_id] = f"[MOCK OCR] 检测到图像 {img.shape}，模拟识别结果"
            except Exception as e:
                self.res[job_id] = ""
            time.sleep(0.005)

    def submit(self, img: np.ndarray) -> str:
        """提交OCR任务，返回job_id"""
        jid = f"ocr-{time.time_ns()}"
        try:
            self.q.put((jid, img), block=False)
        except queue.Full:
            # 队列满时返回空job_id
            self.res[jid] = ""
        return jid

    def fetch(self, job_id: str) -> str | None:
        """获取OCR结果，如果还没完成返回None"""
        return self.res.pop(job_id, None)