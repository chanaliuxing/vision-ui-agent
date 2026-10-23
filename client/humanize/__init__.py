#!/usr/bin/env python3
"""
Humanize Package - Human-like Input Simulation
Stage 11: Robustness & Anti-detection & Fault tolerance

This package provides comprehensive human-like behavior simulation:
- HumanMouse: Bezier curve movement, jitter, natural timing
- HumanKeyboard: Variable typing speed, typos, corrections
- AntiDetection: Fingerprint randomization, behavior diversification
"""

from .human_mouse import HumanMouse, MovementProfile
from .human_keyboard import HumanKeyboard, TypingProfile
from .anti_detection import AntiDetection, BrowserFingerprint, BehaviorProfile

__version__ = "1.0.0"
__author__ = "AutoAgent Engine"

__all__ = [
    'HumanMouse',
    'HumanKeyboard',
    'AntiDetection',
    'MovementProfile',
    'TypingProfile',
    'BrowserFingerprint',
    'BehaviorProfile'
]

class HumanizedInput:
    """Unified interface for all humanized input methods"""

    def __init__(self, typing_profile: TypingProfile = TypingProfile.NORMAL):
        self.mouse = HumanMouse()
        self.keyboard = HumanKeyboard(typing_profile)
        self.anti_detection = AntiDetection()

        # Initialize with human-like profiles
        self.anti_detection.generate_fingerprint()
        self.anti_detection.generate_behavior_profile()

    def click(self, x: int, y: int, button: str = 'left',
              profile: MovementProfile = MovementProfile.NORMAL) -> None:
        """Human-like click with movement and timing"""
        # Check if break is needed
        if self.anti_detection.should_take_break():
            self.anti_detection.take_human_break()

        # Log activity
        self.anti_detection.log_activity('click', {'x': x, 'y': y, 'button': button})

        # Add human delay
        delay = self.anti_detection.get_human_delay('click')
        import time
        time.sleep(delay)

        # Perform click
        self.mouse.click_at(x, y, button, profile)

    def type(self, text: str) -> None:
        """Human-like typing with errors and corrections"""
        # Check if break is needed
        if self.anti_detection.should_take_break():
            self.anti_detection.take_human_break()

        # Log activity
        self.anti_detection.log_activity('type', {'text_length': len(text)})

        # Add human delay
        delay = self.anti_detection.get_human_delay('type')
        import time
        time.sleep(delay)

        # Perform typing
        self.keyboard.type_text(text)

    def move_to(self, x: int, y: int,
                profile: MovementProfile = MovementProfile.NORMAL) -> None:
        """Human-like mouse movement"""
        # Log activity
        self.anti_detection.log_activity('move', {'x': x, 'y': y})

        # Perform movement
        self.mouse.move_to(x, y, profile)

    def get_detection_score(self) -> float:
        """Get current bot detection risk score"""
        return self.anti_detection.get_detection_score()

    def rotate_identity(self) -> None:
        """Rotate browser fingerprint and behavior profile"""
        self.anti_detection.generate_fingerprint()
        self.anti_detection.generate_behavior_profile()
        print("Identity rotated for anti-detection")