# client/adapters/slack.py
import json
from pathlib import Path
from .base import ChatAppAdapter
import numpy as np, cv2, mss, pyautogui

class SlackAdapter(ChatAppAdapter):
    name = "slack"
    def __init__(self):
        config_path = Path("config/profiles/slack.json")
        if config_path.exists():
            self.profile = json.loads(config_path.read_text(encoding="utf-8"))
        else:
            # 默认配置（示例）
            self.profile = {
                "window": {"x":0,"y":0,"w":1400,"h":900,"scale":1.0},
                "left_list": {"x":80,"y":120,"w":280,"h":700},
                "chat_area": {"x":380,"y":100,"w":900,"h":700},
                "input_box": {"x":400,"y":820},
                "anchors": {"notification_dot": "config/anchors/slack/notification_dot.png"},
                "thresholds": {"notification_dot": 0.8}
            }

    def detect(self) -> bool:
        # MVP：简单返回True
        return True

    def locate_window(self):
        return self.profile["window"]

    def get_rois(self):
        return {
            "left_list": self.profile["left_list"],
            "chat_area": self.profile["chat_area"],
            "input_box": self.profile["input_box"]
        }

    def _grab(self, roi):
        with mss.mss() as sct:
            img = np.array(sct.grab({"top":roi["y"],"left":roi["x"],"width":roi["w"],"height":roi["h"]}))
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def find_unread_badges(self):
        left = self.get_rois()["left_list"]
        img = self._grab(left)

        anchor_path = Path(self.profile["anchors"]["notification_dot"])
        if not anchor_path.exists():
            return []

        tpl = cv2.imread(str(anchor_path))
        if tpl is None:
            return []

        res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, maxloc = cv2.minMaxLoc(res)
        if maxv >= self.profile["thresholds"]["notification_dot"]:
            x = left["x"] + maxloc[0] + tpl.shape[1]//2
            y = left["y"] + maxloc[1] + tpl.shape[0]//2
            return [{"x":x,"y":y,"w":tpl.shape[1],"h":tpl.shape[0],"score":float(maxv)}]
        return []

    def open_conversation(self, target=None) -> bool:
        badges = self.find_unread_badges()
        if badges:
            b = badges[0]
            pyautogui.moveTo(b["x"]-50, b["y"], duration=0.12)
            pyautogui.click()
            return True
        return False

    def capture_visible_messages(self):
        chat = self.get_rois()["chat_area"]
        return self._grab(chat)

    def send_text(self, text: str) -> bool:
        ib = self.get_rois()["input_box"]
        pyautogui.click(ib["x"], ib["y"])
        pyautogui.typewrite(text, interval=0.03)
        pyautogui.press("enter")
        return True

    def focus_contact_by_name(self, name: str) -> bool:
        return False