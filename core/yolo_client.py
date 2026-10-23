import base64
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from PIL import Image

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None


@dataclass
class Detection:
    id: int
    class_name: str
    conf: float
    bbox_xyxy: List[float]


class YoloClient:
    """Client for the local FastAPI YOLO endpoint in this repo.

    Server route is POST `{root}/predict`.
    Expect JSON with `detections[{class_name, conf, bbox_xyxy}]` and optional `image_base64`.
    """

    def __init__(self, endpoint: str = "http://127.0.0.1:8000") -> None:
        self.endpoint = endpoint.rstrip("/")

    def _img_to_base64(self, image: Image.Image) -> str:
        buf = __import__("io").BytesIO()
        image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def infer(
        self,
        image: Image.Image,
        return_image: bool = False,
        conf: float = 0.25,
        iou: float = 0.45,
        imgsz: int = 1280,
    ) -> Dict[str, Any]:
        if requests is None:
            raise RuntimeError("requests is required to call the YOLO API")

        # FastAPI expects image as form (image or image_base64) and config in query.
        payload = {
            "image_base64": self._img_to_base64(image),
        }
        params = {
            "conf": conf,
            "iou": iou,
            "imgsz": imgsz,
            "return_image": str(bool(return_image)).lower(),
        }
        resp = requests.post(f"{self.endpoint}/predict", params=params, data=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def to_detections(resp: Dict[str, Any]) -> List[Detection]:
        out: List[Detection] = []
        for d in resp.get("detections", []) or []:
            out.append(
                Detection(
                    id=int(d.get("id", 0)),
                    class_name=str(d.get("class_name", "")),
                    conf=float(d.get("conf", 0.0)),
                    bbox_xyxy=[float(x) for x in d.get("bbox_xyxy", [0, 0, 0, 0])],
                )
            )
        return out
