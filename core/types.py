#!/usr/bin/env python3
"""
Core Types for the Automation Engine
Defines basic data structures used across the system
"""

from typing import Dict, List, Optional, Any, Union, NamedTuple
from dataclasses import dataclass
from enum import Enum


@dataclass
class BBox:
    """Bounding box coordinates"""
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2


@dataclass
class Item:
    """Represents a UI element detected by YOLO or other detection systems"""
    id: str
    bbox: BBox
    confidence: float
    class_name: str
    attrs: Dict[str, Any] = None

    def __post_init__(self):
        if self.attrs is None:
            self.attrs = {}


@dataclass
class Landmark:
    """Visual landmark for navigation and anchoring"""
    name: str
    location: BBox
    confidence: float
    features: Dict[str, Any] = None

    def __post_init__(self):
        if self.features is None:
            self.features = {}


class ActionType(Enum):
    """Types of actions the automation engine can perform"""
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    DETECT = "detect"
    AUTOSTEP = "autostep"


@dataclass
class ActionResult:
    """Result of executing an action"""
    success: bool
    action_type: ActionType
    message: str = ""
    data: Dict[str, Any] = None
    timestamp: float = 0.0

    def __post_init__(self):
        if self.data is None:
            self.data = {}
        if self.timestamp == 0.0:
            import time
            self.timestamp = time.time()


@dataclass
class Detection:
    """YOLO detection result"""
    bbox: BBox
    confidence: float
    class_id: int
    class_name: str

    def to_item(self, item_id: str = None) -> Item:
        """Convert detection to Item"""
        if item_id is None:
            item_id = f"{self.class_name}_{self.class_id}"

        return Item(
            id=item_id,
            bbox=self.bbox,
            confidence=self.confidence,
            class_name=self.class_name
        )


@dataclass
class StrategySpec:
    """Strategy specification for automation decisions"""
    name: str
    confidence: float
    parameters: Dict[str, Any] = None

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


# Type aliases for convenience
Point = tuple[float, float]
Size = tuple[float, float]
Rect = tuple[float, float, float, float]  # x, y, width, height