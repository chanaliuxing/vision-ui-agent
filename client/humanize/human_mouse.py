#!/usr/bin/env python3
"""
Human-like Mouse Movement System
Stage 11: Robustness & Anti-detection & Fault tolerance

This module provides human-like mouse movement patterns to avoid detection
by automation detection systems. It includes:
1. Bezier curve-based smooth cursor movement
2. Random jitter and micro-movements
3. Variable speed profiles
4. Natural pause patterns
5. Movement overshoot and correction
"""

import pyautogui
import numpy as np
import random
import time
import math
from typing import Tuple, List, Optional
from dataclasses import dataclass
from enum import Enum

class MovementProfile(Enum):
    """Different movement speed profiles for various scenarios"""
    SLOW = "slow"          # 800-1200ms for long distances
    NORMAL = "normal"      # 300-600ms for medium distances
    FAST = "fast"          # 100-300ms for short distances
    HESITANT = "hesitant"  # Multiple pauses, corrections
    PRECISE = "precise"    # Slow, steady for small targets

@dataclass
class MouseState:
    """Current mouse state tracking"""
    last_x: int = 0
    last_y: int = 0
    last_move_time: float = 0
    movement_count: int = 0
    idle_time: float = 0

class HumanMouse:
    """Human-like mouse movement controller"""

    def __init__(self):
        self.state = MouseState()
        self.screen_width, self.screen_height = pyautogui.size()
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0  # We handle timing manually

        # Movement parameters
        self.base_speed = 1000  # pixels per second base speed
        self.jitter_amplitude = 3  # max pixels of random jitter
        self.overshoot_chance = 0.15  # 15% chance of overshooting
        self.micro_pause_chance = 0.3  # 30% chance of micro-pauses

    def get_current_position(self) -> Tuple[int, int]:
        """Get current cursor position"""
        return pyautogui.position()

    def generate_bezier_path(self, start: Tuple[int, int], end: Tuple[int, int],
                           control_points: int = 2) -> List[Tuple[float, float]]:
        """Generate smooth Bezier curve path between two points"""
        x1, y1 = start
        x2, y2 = end

        # Distance-based number of points
        distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        num_points = max(10, int(distance / 20))  # ~20px per point

        if control_points == 1:
            # Quadratic Bezier with one control point
            # Control point offset perpendicular to direct line
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2

            # Add random curvature
            perp_offset = random.uniform(-distance/8, distance/8)
            angle = math.atan2(y2-y1, x2-x1) + math.pi/2
            ctrl_x = mid_x + perp_offset * math.cos(angle)
            ctrl_y = mid_y + perp_offset * math.sin(angle)

            points = []
            for i in range(num_points):
                t = i / (num_points - 1)
                x = (1-t)**2 * x1 + 2*(1-t)*t * ctrl_x + t**2 * x2
                y = (1-t)**2 * y1 + 2*(1-t)*t * ctrl_y + t**2 * y2
                points.append((x, y))

        else:
            # Cubic Bezier with two control points
            # First control point
            ctrl1_factor = random.uniform(0.2, 0.4)
            ctrl1_x = x1 + (x2 - x1) * ctrl1_factor
            ctrl1_y = y1 + random.uniform(-distance/6, distance/6)

            # Second control point
            ctrl2_factor = random.uniform(0.6, 0.8)
            ctrl2_x = x1 + (x2 - x1) * ctrl2_factor
            ctrl2_y = y2 + random.uniform(-distance/6, distance/6)

            points = []
            for i in range(num_points):
                t = i / (num_points - 1)
                x = (1-t)**3 * x1 + 3*(1-t)**2*t * ctrl1_x + 3*(1-t)*t**2 * ctrl2_x + t**3 * x2
                y = (1-t)**3 * y1 + 3*(1-t)**2*t * ctrl1_y + 3*(1-t)*t**2 * ctrl2_y + t**3 * y2
                points.append((x, y))

        return points

    def add_jitter(self, x: float, y: float) -> Tuple[int, int]:
        """Add random micro-jitter to coordinates"""
        jitter_x = random.uniform(-self.jitter_amplitude, self.jitter_amplitude)
        jitter_y = random.uniform(-self.jitter_amplitude, self.jitter_amplitude)

        final_x = max(0, min(self.screen_width - 1, int(x + jitter_x)))
        final_y = max(0, min(self.screen_height - 1, int(y + jitter_y)))

        return final_x, final_y

    def calculate_movement_timing(self, distance: float, profile: MovementProfile) -> float:
        """Calculate realistic movement timing based on distance and profile"""

        if profile == MovementProfile.SLOW:
            base_time = distance / (self.base_speed * 0.5)  # Half speed
            variation = random.uniform(0.8, 1.4)

        elif profile == MovementProfile.NORMAL:
            base_time = distance / self.base_speed
            variation = random.uniform(0.7, 1.3)

        elif profile == MovementProfile.FAST:
            base_time = distance / (self.base_speed * 2.0)  # Double speed
            variation = random.uniform(0.6, 1.2)

        elif profile == MovementProfile.HESITANT:
            base_time = distance / (self.base_speed * 0.3)  # Very slow
            variation = random.uniform(1.2, 2.0)

        elif profile == MovementProfile.PRECISE:
            base_time = distance / (self.base_speed * 0.6)  # Slower, steady
            variation = random.uniform(0.9, 1.1)  # Less variation

        return max(0.05, base_time * variation)

    def move_to(self, target_x: int, target_y: int,
                profile: MovementProfile = MovementProfile.NORMAL,
                overshoot: bool = None) -> None:
        """Move cursor to target with human-like movement"""

        current_x, current_y = self.get_current_position()
        self.state.last_x, self.state.last_y = current_x, current_y

        # Calculate distance
        distance = math.sqrt((target_x - current_x)**2 + (target_y - current_y)**2)

        # Skip if already at target
        if distance < 2:
            return

        # Determine if we should overshoot
        if overshoot is None:
            overshoot = random.random() < self.overshoot_chance and distance > 50

        # Generate movement path
        if overshoot:
            # Create overshoot target
            overshoot_distance = random.uniform(10, 25)
            angle = math.atan2(target_y - current_y, target_x - current_x)
            overshoot_x = target_x + int(overshoot_distance * math.cos(angle))
            overshoot_y = target_y + int(overshoot_distance * math.sin(angle))

            # Move to overshoot point first
            path1 = self.generate_bezier_path((current_x, current_y), (overshoot_x, overshoot_y))
            path2 = self.generate_bezier_path((overshoot_x, overshoot_y), (target_x, target_y))
            full_path = path1 + path2[1:]  # Avoid duplicate point
        else:
            full_path = self.generate_bezier_path((current_x, current_y), (target_x, target_y))

        # Execute movement along path
        total_time = self.calculate_movement_timing(distance, profile)
        time_per_point = total_time / len(full_path)

        for i, (x, y) in enumerate(full_path):
            # Add jitter
            final_x, final_y = self.add_jitter(x, y)

            # Move cursor
            pyautogui.moveTo(final_x, final_y, duration=0)

            # Random micro-pauses
            if i > 0 and random.random() < self.micro_pause_chance:
                pause_duration = random.uniform(0.01, 0.05)
                time.sleep(pause_duration)

            # Inter-point timing with variation
            point_delay = time_per_point * random.uniform(0.5, 1.5)
            time.sleep(max(0.005, point_delay))

        # Final position adjustment
        final_x, final_y = self.add_jitter(target_x, target_y)
        pyautogui.moveTo(final_x, final_y, duration=0)

        # Update state
        self.state.movement_count += 1
        self.state.last_move_time = time.time()

    def click_at(self, x: int, y: int, button: str = 'left',
                 profile: MovementProfile = MovementProfile.NORMAL) -> None:
        """Move to position and click with human-like timing"""

        # Move to target
        self.move_to(x, y, profile)

        # Pre-click pause (human hesitation)
        pre_click_pause = random.uniform(0.05, 0.15)
        time.sleep(pre_click_pause)

        # Click with realistic timing
        if button == 'left':
            pyautogui.mouseDown(button='left')
            click_duration = random.uniform(0.08, 0.12)  # Human click duration
            time.sleep(click_duration)
            pyautogui.mouseUp(button='left')
        elif button == 'right':
            pyautogui.mouseDown(button='right')
            click_duration = random.uniform(0.09, 0.13)
            time.sleep(click_duration)
            pyautogui.mouseUp(button='right')
        elif button == 'double':
            # Double click with realistic timing
            pyautogui.click(button='left')
            double_click_delay = random.uniform(0.08, 0.15)
            time.sleep(double_click_delay)
            pyautogui.click(button='left')

        # Post-click pause
        post_click_pause = random.uniform(0.1, 0.3)
        time.sleep(post_click_pause)

    def drag_to(self, start_x: int, start_y: int, end_x: int, end_y: int,
                duration: float = None) -> None:
        """Perform human-like drag operation"""

        # Move to start position
        self.move_to(start_x, start_y, MovementProfile.PRECISE)

        # Pre-drag pause
        time.sleep(random.uniform(0.1, 0.2))

        # Start drag
        pyautogui.mouseDown(button='left')

        # Drag movement with jitter
        if duration is None:
            distance = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
            duration = max(0.3, distance / 400)  # Slower for drags

        path = self.generate_bezier_path((start_x, start_y), (end_x, end_y))
        time_per_point = duration / len(path)

        for x, y in path[1:]:  # Skip first point (already there)
            jitter_x, jitter_y = self.add_jitter(x, y)
            pyautogui.moveTo(jitter_x, jitter_y, duration=0)
            time.sleep(time_per_point * random.uniform(0.8, 1.2))

        # End drag
        pyautogui.mouseUp(button='left')

        # Post-drag pause
        time.sleep(random.uniform(0.1, 0.25))

    def scroll(self, clicks: int, x: int = None, y: int = None) -> None:
        """Human-like scrolling with natural pauses"""

        if x is not None and y is not None:
            self.move_to(x, y, MovementProfile.FAST)

        # Break scrolling into chunks
        remaining = abs(clicks)
        direction = 1 if clicks > 0 else -1

        while remaining > 0:
            # Random chunk size (1-3 scroll clicks)
            chunk_size = min(remaining, random.randint(1, 3))

            for _ in range(chunk_size):
                pyautogui.scroll(direction)
                # Small delay between individual scroll clicks
                time.sleep(random.uniform(0.05, 0.1))

            remaining -= chunk_size

            # Pause between chunks
            if remaining > 0:
                time.sleep(random.uniform(0.2, 0.5))

    def idle_movement(self) -> None:
        """Subtle idle movements to appear human"""

        current_time = time.time()
        if current_time - self.state.last_move_time > 30:  # 30s of no movement
            current_x, current_y = self.get_current_position()

            # Small random movement
            idle_x = current_x + random.randint(-5, 5)
            idle_y = current_y + random.randint(-5, 5)

            self.move_to(idle_x, idle_y, MovementProfile.SLOW)

    def get_movement_stats(self) -> dict:
        """Get movement statistics for analysis"""
        return {
            'movement_count': self.state.movement_count,
            'last_move_time': self.state.last_move_time,
            'idle_time': time.time() - self.state.last_move_time,
            'screen_size': (self.screen_width, self.screen_height)
        }