import io
import os
from typing import List, Optional

from PIL import Image


class OcrClient:
    """Minimal OCR client for app_ocr.py endpoint.

    If `requests` is unavailable or endpoint not set, calls are no-ops returning [].
    """

    def __init__(self, endpoint: Optional[str]) -> None:
        self.endpoint = (endpoint or "").rstrip("/") if endpoint else None
        try:
            import requests  # type: ignore
            self._requests = requests
        except Exception:
            self._requests = None

    def read_texts(self, pil: Image.Image, lang: Optional[str] = None, min_conf: float = 0.5) -> List[str]:
        if not self.endpoint or self._requests is None or pil is None:
            return []
        url = f"{self.endpoint}/predict"
        params = {
            "return_image": "false",
            "box_ocr_mode": "global",
            "ocr_backend": os.getenv("OCR_BACKEND", "auto"),
            "ocr_langs": lang or os.getenv("OCR_LANGS", "ch"),
            "ocr_min_conf": str(min_conf),
            "imgsz": os.getenv("YOLO_IMGSZ", "1280"),
        }
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        buf.seek(0)
        files = {"image": ("screen.png", buf.getvalue(), "image/png")}
        try:
            r = self._requests.post(url, params=params, files=files, timeout=20)
            r.raise_for_status()
            data = r.json() if r.content else {}
            texts: List[str] = []
            for d in (data.get("detections") or []):
                o = d.get("ocr") or {}
                t = o.get("text")
                if isinstance(t, str) and t:
                    texts.append(t)
            return texts
        except Exception:
            return []

    def read_lines(self, pil: Image.Image, lang: Optional[str] = None, min_conf: float = 0.5) -> List[dict]:
        """Return OCR line dicts with polygon/text/conf aggregated from detection crops.
        Requires app_ocr.py endpoint.
        """
        if not self.endpoint or self._requests is None or pil is None:
            return []
        url = f"{self.endpoint}/predict"
        params = {
            "return_image": "false",
            "box_ocr_mode": "fused",
            "ocr_backend": os.getenv("OCR_BACKEND", "auto"),
            "ocr_langs": lang or os.getenv("OCR_LANGS", "ch"),
            "ocr_min_conf": str(min_conf),
            "imgsz": os.getenv("YOLO_IMGSZ", "1280"),
        }
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        buf.seek(0)
        files = {"image": ("screen.png", buf.getvalue(), "image/png")}
        try:
            r = self._requests.post(url, params=params, files=files, timeout=20)
            r.raise_for_status()
            data = r.json() if r.content else {}
            lines: List[dict] = []
            for d in (data.get("detections") or []):
                o = d.get("ocr") or {}
                for ln in (o.get("lines") or []):
                    if isinstance(ln, dict) and ln.get("polygon") and ln.get("text") is not None:
                        lines.append({"polygon": ln.get("polygon"), "text": ln.get("text"), "conf": ln.get("conf", 0.0)})
            return lines
        except Exception:
            return []
