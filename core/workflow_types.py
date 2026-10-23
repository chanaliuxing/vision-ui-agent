# core/types.py - 统一数据模型
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Set
import numpy as np

BBox = Tuple[int, int, int, int]  # x, y, w, h

@dataclass
class Item:
    id: str
    bbox: BBox
    class_name: str                 # 来自 YOLO 类别（如 'card','list_row','badge','avatar','button','input' 等）
    ocr_text: Optional[str] = None  # 该框内/邻域的主要文本（可为空）
    attrs: Set[str] = field(default_factory=set) # {'unread','badge','selected','sponsored'...}
    image_thumb: Optional[np.ndarray] = None   # 可选：小图
    meta: Dict = field(default_factory=dict)     # 额外信息（分数、来源等）

@dataclass
class Landmark(Item):
    role: str = ""                   # 'search_bar','chat_sidebar','results_container','tabs','top_bar' 等

@dataclass
class StrategySpec:
    strategy_id: str                 # 统一枚举
    params: Dict                    # container/landmark/attr/text/n/r/c/row_attr/action_role/ordinal ...
    fallback: Optional[Dict] = None  # 可选：同结构
    confidence: float = 0.0
    why: str = ""