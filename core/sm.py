import time
from typing import Iterable, List

from PIL import Image

from .capture import ScreenCapture
from .yolo_client import YoloClient


class StateMachine:
    """Tiny helper for polling until any of target classes appears."""

    def __init__(self, capturer: ScreenCapture, yolo: YoloClient):
        self.cap = capturer
        self.yolo = yolo

    def wait_for_any(
        self,
        classes: Iterable[str],
        timeout_s: float = 8.0,
        poll_s: float = 0.6,
        conf_min: float = 0.5,
    ) -> List[dict]:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            grab = self.cap.screenshot()
            resp = self.yolo.infer(grab.image, return_image=False)
            dets = self.yolo.to_detections(resp)
            found = [d for d in dets if d.class_name in set(classes) and d.conf >= conf_min]
            if found:
                return [d.__dict__ for d in found]
            time.sleep(poll_s)
        return []

