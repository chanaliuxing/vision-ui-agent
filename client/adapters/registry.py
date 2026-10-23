# client/adapters/registry.py
from typing import Dict, Optional
from .base import ChatAppAdapter
from .wechat import WeChatAdapter
from .slack import SlackAdapter

_REGISTRY: Dict[str, ChatAppAdapter] = {
    "wechat": WeChatAdapter(),
    "slack": SlackAdapter()
}

def get_adapter(app: str) -> Optional[ChatAppAdapter]:
    return _REGISTRY.get(app)

def list_available_apps():
    """返回可用的聊天应用列表"""
    return list(_REGISTRY.keys())