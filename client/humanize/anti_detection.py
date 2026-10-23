#!/usr/bin/env python3
"""
Anti-Detection System
Stage 11: Robustness & Anti-detection & Fault tolerance

This module provides comprehensive anti-detection capabilities:
1. Browser fingerprint randomization
2. Network traffic obfuscation
3. Behavioral pattern diversification
4. Resource usage normalization
5. Detection evasion strategies
"""

import random
import time
import json
import hashlib
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import uuid

@dataclass
class BrowserFingerprint:
    """Browser fingerprint data structure"""
    user_agent: str
    screen_resolution: str
    timezone: str
    language: str
    color_depth: int
    canvas_fingerprint: str
    webgl_fingerprint: str
    audio_fingerprint: str
    fonts: List[str]
    plugins: List[str]
    cpu_cores: int
    memory_gb: int

@dataclass
class BehaviorProfile:
    """Human behavior profile"""
    reaction_time_min: float
    reaction_time_max: float
    scroll_speed: float
    typing_speed_wpm: float
    mouse_movement_style: str
    break_frequency: float
    attention_span: float
    multitasking_tendency: float

class AntiDetection:
    """Comprehensive anti-detection system"""

    def __init__(self):
        self.current_fingerprint = None
        self.current_behavior = None
        self.session_start = time.time()
        self.activity_log = []
        self.detection_counters = {
            'bot_score_checks': 0,
            'captcha_encounters': 0,
            'rate_limit_hits': 0,
            'unusual_pattern_flags': 0
        }

        # Common browser configurations
        self.browser_configs = self._load_browser_configs()
        self.behavior_profiles = self._load_behavior_profiles()

    def _load_browser_configs(self) -> List[Dict]:
        """Load realistic browser configurations"""
        return [
            {
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'platform': 'Windows',
                'screen_resolutions': ['1920x1080', '1366x768', '1536x864', '1440x900'],
                'timezones': ['America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles'],
                'languages': ['en-US', 'en-GB'],
                'cpu_cores': [4, 6, 8, 12, 16],
                'memory_options': [8, 16, 32]
            },
            {
                'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'platform': 'macOS',
                'screen_resolutions': ['1920x1080', '2560x1440', '1440x900', '1680x1050'],
                'timezones': ['America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles'],
                'languages': ['en-US'],
                'cpu_cores': [4, 8, 10, 12],
                'memory_options': [8, 16, 32, 64]
            },
            {
                'user_agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'platform': 'Linux',
                'screen_resolutions': ['1920x1080', '1366x768', '2560x1440', '1600x900'],
                'timezones': ['America/New_York', 'Europe/London', 'Europe/Berlin', 'Asia/Tokyo'],
                'languages': ['en-US', 'en-GB'],
                'cpu_cores': [4, 6, 8, 16],
                'memory_options': [8, 16, 32]
            }
        ]

    def _load_behavior_profiles(self) -> List[BehaviorProfile]:
        """Load human behavior profiles"""
        return [
            BehaviorProfile(
                reaction_time_min=0.2, reaction_time_max=0.8,
                scroll_speed=1.2, typing_speed_wpm=45,
                mouse_movement_style='smooth', break_frequency=0.15,
                attention_span=300, multitasking_tendency=0.3
            ),
            BehaviorProfile(
                reaction_time_min=0.15, reaction_time_max=0.6,
                scroll_speed=1.8, typing_speed_wpm=65,
                mouse_movement_style='quick', break_frequency=0.08,
                attention_span=450, multitasking_tendency=0.6
            ),
            BehaviorProfile(
                reaction_time_min=0.3, reaction_time_max=1.2,
                scroll_speed=0.8, typing_speed_wpm=25,
                mouse_movement_style='hesitant', break_frequency=0.25,
                attention_span=180, multitasking_tendency=0.1
            )
        ]

    def generate_fingerprint(self) -> BrowserFingerprint:
        """Generate realistic browser fingerprint"""
        config = random.choice(self.browser_configs)

        # Generate canvas fingerprint (hash of rendered text)
        canvas_text = f"Browser fingerprint {random.randint(1000, 9999)}"
        canvas_fingerprint = hashlib.md5(canvas_text.encode()).hexdigest()[:16]

        # Generate WebGL fingerprint
        webgl_info = f"ANGLE (Intel, Intel(R) UHD Graphics {random.choice([620, 630, 730])}"
        webgl_fingerprint = hashlib.sha256(webgl_info.encode()).hexdigest()[:24]

        # Generate audio fingerprint
        audio_context = f"AudioContext {random.uniform(44000, 48000)}"
        audio_fingerprint = hashlib.sha256(audio_context.encode()).hexdigest()[:20]

        # Common fonts list
        fonts = [
            'Arial', 'Times New Roman', 'Courier New', 'Helvetica', 'Georgia',
            'Verdana', 'Trebuchet MS', 'Tahoma', 'Impact', 'Comic Sans MS'
        ]
        selected_fonts = random.sample(fonts, random.randint(6, 10))

        # Browser plugins (realistic modern set)
        plugins = []
        if random.random() < 0.8:
            plugins.append('Chrome PDF Plugin')
        if random.random() < 0.6:
            plugins.append('Widevine Content Decryption Module')
        if random.random() < 0.4:
            plugins.append('Native Client')

        fingerprint = BrowserFingerprint(
            user_agent=config['user_agent'],
            screen_resolution=random.choice(config['screen_resolutions']),
            timezone=random.choice(config['timezones']),
            language=random.choice(config['languages']),
            color_depth=random.choice([24, 32]),
            canvas_fingerprint=canvas_fingerprint,
            webgl_fingerprint=webgl_fingerprint,
            audio_fingerprint=audio_fingerprint,
            fonts=selected_fonts,
            plugins=plugins,
            cpu_cores=random.choice(config['cpu_cores']),
            memory_gb=random.choice(config['memory_options'])
        )

        self.current_fingerprint = fingerprint
        return fingerprint

    def generate_behavior_profile(self) -> BehaviorProfile:
        """Generate human behavior profile"""
        base_profile = random.choice(self.behavior_profiles)

        # Add random variation to base profile
        behavior = BehaviorProfile(
            reaction_time_min=base_profile.reaction_time_min * random.uniform(0.8, 1.2),
            reaction_time_max=base_profile.reaction_time_max * random.uniform(0.8, 1.2),
            scroll_speed=base_profile.scroll_speed * random.uniform(0.7, 1.3),
            typing_speed_wpm=base_profile.typing_speed_wpm * random.uniform(0.8, 1.2),
            mouse_movement_style=base_profile.mouse_movement_style,
            break_frequency=base_profile.break_frequency * random.uniform(0.5, 1.5),
            attention_span=base_profile.attention_span * random.uniform(0.7, 1.3),
            multitasking_tendency=max(0, min(1, base_profile.multitasking_tendency * random.uniform(0.6, 1.4)))
        )

        self.current_behavior = behavior
        return behavior

    def get_human_delay(self, action_type: str = 'click') -> float:
        """Get human-like delay based on behavior profile"""
        if not self.current_behavior:
            self.generate_behavior_profile()

        base_delay = random.uniform(
            self.current_behavior.reaction_time_min,
            self.current_behavior.reaction_time_max
        )

        # Adjust for action type
        if action_type == 'scroll':
            base_delay *= 0.6
        elif action_type == 'type':
            base_delay *= 0.8
        elif action_type == 'read':
            base_delay *= 2.0
        elif action_type == 'think':
            base_delay *= random.uniform(3, 8)

        return base_delay

    def should_take_break(self) -> bool:
        """Determine if a break should be taken"""
        if not self.current_behavior:
            return False

        session_time = time.time() - self.session_start

        # Probability increases with session time
        time_factor = min(1.0, session_time / self.current_behavior.attention_span)
        break_probability = self.current_behavior.break_frequency * time_factor

        return random.random() < break_probability

    def take_human_break(self) -> None:
        """Take a human-like break"""
        break_types = ['short', 'medium', 'long']
        break_type = random.choices(
            break_types,
            weights=[0.6, 0.3, 0.1]
        )[0]

        if break_type == 'short':
            duration = random.uniform(5, 30)
        elif break_type == 'medium':
            duration = random.uniform(30, 120)
        else:  # long
            duration = random.uniform(120, 600)

        print(f"Taking {break_type} break for {duration:.1f} seconds")
        time.sleep(duration)

        # Reset session timer after long breaks
        if break_type == 'long':
            self.session_start = time.time()

    def randomize_request_headers(self, base_headers: Dict[str, str]) -> Dict[str, str]:
        """Randomize HTTP request headers"""
        headers = base_headers.copy()

        if self.current_fingerprint:
            headers['User-Agent'] = self.current_fingerprint.user_agent
            headers['Accept-Language'] = f"{self.current_fingerprint.language},en;q=0.9"

        # Add realistic headers
        headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        headers['Accept-Encoding'] = 'gzip, deflate, br'
        headers['Connection'] = 'keep-alive'
        headers['Upgrade-Insecure-Requests'] = '1'

        # Random cache control
        if random.random() < 0.3:
            headers['Cache-Control'] = random.choice(['no-cache', 'max-age=0'])

        # Random DNT header
        if random.random() < 0.4:
            headers['DNT'] = '1'

        return headers

    def add_network_jitter(self, base_delay: float) -> float:
        """Add realistic network timing jitter"""
        # Simulate network latency variation
        jitter = random.uniform(-0.1, 0.3) * base_delay
        return max(0.1, base_delay + jitter)

    def obfuscate_mouse_path(self, start: tuple, end: tuple) -> List[tuple]:
        """Generate realistic mouse movement path"""
        # This would integrate with human_mouse.py
        # Placeholder for path generation
        return [(start[0], start[1]), (end[0], end[1])]

    def vary_typing_pattern(self, text: str) -> List[Dict]:
        """Generate varied typing pattern for text"""
        if not self.current_behavior:
            self.generate_behavior_profile()

        events = []
        base_delay = 60.0 / (self.current_behavior.typing_speed_wpm * 5)  # Convert WPM to char delay

        for i, char in enumerate(text):
            # Variable delay between characters
            delay = base_delay * random.uniform(0.7, 1.4)

            # Longer delays for punctuation and spaces
            if char in '.,!?;:':
                delay *= random.uniform(1.5, 2.5)
            elif char == ' ':
                delay *= random.uniform(1.2, 2.0)

            events.append({
                'char': char,
                'delay': delay,
                'hold_time': random.uniform(0.08, 0.12)
            })

        return events

    def simulate_human_errors(self, text: str, error_rate: float = 0.03) -> str:
        """Introduce realistic typing errors"""
        if random.random() > error_rate:
            return text

        # Common error types
        error_type = random.choice(['typo', 'omission', 'duplication'])

        if error_type == 'typo' and len(text) > 3:
            # Replace random character
            pos = random.randint(1, len(text) - 2)
            chars = list(text)
            chars[pos] = random.choice('abcdefghijklmnopqrstuvwxyz')
            return ''.join(chars)

        elif error_type == 'omission' and len(text) > 4:
            # Remove random character
            pos = random.randint(1, len(text) - 2)
            return text[:pos] + text[pos + 1:]

        elif error_type == 'duplication':
            # Duplicate random character
            pos = random.randint(0, len(text) - 1)
            return text[:pos + 1] + text[pos] + text[pos + 1:]

        return text

    def get_detection_score(self) -> float:
        """Calculate current bot detection risk score (0-1)"""
        score = 0.0

        # Time-based factors
        session_time = time.time() - self.session_start
        if session_time > 3600:  # Long sessions are suspicious
            score += 0.2

        # Activity patterns
        if len(self.activity_log) > 100:
            recent_activities = self.activity_log[-100:]
            timing_intervals = [
                recent_activities[i]['timestamp'] - recent_activities[i-1]['timestamp']
                for i in range(1, len(recent_activities))
            ]

            # Too regular timing is suspicious
            if timing_intervals:
                variance = np.var(timing_intervals) if len(timing_intervals) > 1 else 0
                if variance < 0.1:
                    score += 0.3

        # Detection counter penalties
        score += self.detection_counters['captcha_encounters'] * 0.1
        score += self.detection_counters['rate_limit_hits'] * 0.15
        score += self.detection_counters['unusual_pattern_flags'] * 0.05

        return min(1.0, score)

    def log_activity(self, activity_type: str, data: Dict = None) -> None:
        """Log activity for pattern analysis"""
        entry = {
            'timestamp': time.time(),
            'type': activity_type,
            'data': data or {}
        }

        self.activity_log.append(entry)

        # Keep only recent activities
        if len(self.activity_log) > 1000:
            self.activity_log = self.activity_log[-500:]

    def handle_captcha_detection(self) -> Dict[str, Any]:
        """Handle CAPTCHA encounter"""
        self.detection_counters['captcha_encounters'] += 1

        # Take a break to cool down
        break_duration = random.uniform(30, 120)
        print(f"CAPTCHA detected. Taking {break_duration:.1f}s break")
        time.sleep(break_duration)

        # Consider changing fingerprint
        if self.detection_counters['captcha_encounters'] > 2:
            print("Multiple CAPTCHAs detected. Rotating fingerprint")
            self.generate_fingerprint()
            self.generate_behavior_profile()

        return {
            'action': 'captcha_handled',
            'break_duration': break_duration,
            'fingerprint_rotated': self.detection_counters['captcha_encounters'] > 2
        }

    def handle_rate_limit(self, retry_after: Optional[int] = None) -> Dict[str, Any]:
        """Handle rate limiting"""
        self.detection_counters['rate_limit_hits'] += 1

        # Calculate backoff time
        if retry_after:
            backoff_time = retry_after + random.uniform(10, 30)
        else:
            backoff_time = min(300, 30 * (2 ** self.detection_counters['rate_limit_hits']))

        print(f"Rate limit hit. Backing off for {backoff_time:.1f}s")
        time.sleep(backoff_time)

        return {
            'action': 'rate_limit_handled',
            'backoff_time': backoff_time,
            'retry_count': self.detection_counters['rate_limit_hits']
        }

    def export_session_data(self) -> Dict[str, Any]:
        """Export session data for analysis"""
        return {
            'session_duration': time.time() - self.session_start,
            'fingerprint': asdict(self.current_fingerprint) if self.current_fingerprint else None,
            'behavior_profile': asdict(self.current_behavior) if self.current_behavior else None,
            'detection_counters': self.detection_counters.copy(),
            'detection_score': self.get_detection_score(),
            'activity_count': len(self.activity_log),
            'timestamp': datetime.now().isoformat()
        }