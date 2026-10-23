from typing import List, Dict, Any

_OCR_BACKEND = None
_PADDLE = None
_TESSERACT = None


def _init_backend():
    global _OCR_BACKEND, _PADDLE, _TESSERACT
    if _OCR_BACKEND is not None:
        return
    try:
        from paddleocr import PaddleOCR  # type: ignore
        _PADDLE = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        _OCR_BACKEND = "paddle"
        return
    except Exception:
        pass
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # noqa: F401
        _TESSERACT = pytesseract
        _OCR_BACKEND = "tesseract"
        return
    except Exception:
        pass
    _OCR_BACKEND = "none"


def run_ocr(image_path: str) -> List[Dict[str, Any]]:
    """
    Return OCR lines with positions: [{"text": str, "bbox": [x1,y1,x2,y2], "conf": float}]
    """
    _init_backend()
    if _OCR_BACKEND == "paddle":
        try:
            res = _PADDLE.ocr(image_path, cls=True)
            out: List[Dict[str, Any]] = []
            for line in res[0]:
                ((x1, y1), (x2, y2), (x3, y3), (x4, y4)), (txt, conf) = line
                x_min = int(min(x1, x2, x3, x4)); y_min = int(min(y1, y2, y3, y4))
                x_max = int(max(x1, x2, x3, x4)); y_max = int(max(y1, y2, y3, y4))
                out.append({"text": txt, "bbox": [x_min, y_min, x_max, y_max], "conf": float(conf)})
            return out
        except Exception:
            return []
    if _OCR_BACKEND == "tesseract":
        try:
            from PIL import Image  # type: ignore
            import pytesseract  # type: ignore
            data = pytesseract.image_to_data(Image.open(image_path), output_type=pytesseract.Output.DICT, lang="chi_sim+eng")
            out: List[Dict[str, Any]] = []
            n = len(data.get("text", []))
            for i in range(n):
                txt = (data["text"][i] or "").strip()
                if not txt:
                    continue
                x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                try:
                    conf = float(data.get("conf", [0] * n)[i] or 0)
                except Exception:
                    conf = 0.0
                out.append({"text": txt, "bbox": [int(x), int(y), int(x + w), int(y + h)], "conf": conf})
            return out
        except Exception:
            return []
    return []

