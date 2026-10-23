# client/adapters/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple

class ChatAppAdapter(ABC):
    name: str

    @abstractmethod
    def detect(self) -> bool:
        """检查应用是否运行/可用"""
        pass

    @abstractmethod
    def locate_window(self) -> Dict[str, int]:
        """返回 {"x":int,"y":int,"w":int,"h":int,"scale":float}"""
        pass

    @abstractmethod
    def get_rois(self) -> Dict[str, Dict[str,int]]:
        """返回 {"left_list": {...}, "chat_area": {...}, "input_box": {...}}"""
        pass

    @abstractmethod
    def find_unread_badges(self) -> List[Dict[str, Any]]:
        """返回未读标记列表：[{ "x":int,"y":int,"w":int,"h":int,"score":float }]"""
        pass

    @abstractmethod
    def open_conversation(self, target: Optional[str] = None) -> bool:
        """打开会话（未读最新或指定联系人）"""
        pass

    @abstractmethod
    def capture_visible_messages(self) -> Any:
        """返回截图图像（numpy array）或可访问性文本"""
        pass

    @abstractmethod
    def send_text(self, text: str) -> bool:
        """发送文本到当前会话"""
        pass

    def focus_contact_by_name(self, name: str) -> bool:
        """非必需；没有实现可直接返回 False"""
        return False