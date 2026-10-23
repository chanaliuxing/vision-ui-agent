#!/usr/bin/env python3
"""
Human-like Keyboard Input System
Stage 11: Robustness & Anti-detection & Fault tolerance

This module provides human-like typing patterns to avoid detection:
1. Variable typing speed with realistic WPM ranges
2. Natural typos and corrections
3. Realistic pause patterns (thinking, word boundaries)
4. Key hold duration variation
5. Inter-key timing variation based on finger positions
"""

import pyautogui
import random
import time
import string
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

class TypingProfile(Enum):
    """Different typing speed profiles"""
    SLOW = "slow"          # 20-35 WPM (beginner)
    NORMAL = "normal"      # 35-50 WPM (average)
    FAST = "fast"          # 50-70 WPM (experienced)
    EXPERT = "expert"      # 70-90 WPM (professional)
    HUNT_PECK = "hunt_peck"  # 15-25 WPM with long pauses

@dataclass
class TypingState:
    """Current typing state tracking"""
    characters_typed: int = 0
    words_typed: int = 0
    errors_made: int = 0
    corrections_made: int = 0
    session_start_time: float = 0
    last_key_time: float = 0

class HumanKeyboard:
    """Human-like keyboard input controller"""

    def __init__(self, profile: TypingProfile = TypingProfile.NORMAL):
        self.profile = profile
        self.state = TypingState()
        self.state.session_start_time = time.time()

        # Keyboard layout for distance-based timing
        self.qwerty_layout = {
            'q': (0, 0), 'w': (1, 0), 'e': (2, 0), 'r': (3, 0), 't': (4, 0),
            'y': (5, 0), 'u': (6, 0), 'i': (7, 0), 'o': (8, 0), 'p': (9, 0),
            'a': (0, 1), 's': (1, 1), 'd': (2, 1), 'f': (3, 1), 'g': (4, 1),
            'h': (5, 1), 'j': (6, 1), 'k': (7, 1), 'l': (8, 1),
            'z': (0, 2), 'x': (1, 2), 'c': (2, 2), 'v': (3, 2), 'b': (4, 2),
            'n': (5, 2), 'm': (6, 2),
            ' ': (4, 3)  # Space bar
        }

        # Common typing errors and corrections
        self.common_typos = {
            'the': ['teh', 'hte', 'th'],
            'and': ['adn', 'nad'],
            'you': ['yuo', 'oyu'],
            'that': ['taht', 'htat'],
            'with': ['wiht', 'wtih'],
            'have': ['ahve', 'hvae'],
            'this': ['thsi', 'tihs'],
            'will': ['wil', 'iwll'],
            'your': ['yuor', 'yoru'],
            'from': ['form', 'fomr']
        }

        # Profile-specific parameters
        self.configure_profile(profile)

    def configure_profile(self, profile: TypingProfile) -> None:
        """Configure typing parameters based on profile"""
        if profile == TypingProfile.SLOW:
            self.base_wpm = random.uniform(20, 35)
            self.typo_chance = 0.05
            self.thinking_pause_chance = 0.3
            self.word_pause_chance = 0.2

        elif profile == TypingProfile.NORMAL:
            self.base_wpm = random.uniform(35, 50)
            self.typo_chance = 0.03
            self.thinking_pause_chance = 0.2
            self.word_pause_chance = 0.15

        elif profile == TypingProfile.FAST:
            self.base_wpm = random.uniform(50, 70)
            self.typo_chance = 0.04  # More errors at speed
            self.thinking_pause_chance = 0.1
            self.word_pause_chance = 0.08

        elif profile == TypingProfile.EXPERT:
            self.base_wpm = random.uniform(70, 90)
            self.typo_chance = 0.02
            self.thinking_pause_chance = 0.05
            self.word_pause_chance = 0.03

        elif profile == TypingProfile.HUNT_PECK:
            self.base_wpm = random.uniform(15, 25)
            self.typo_chance = 0.08
            self.thinking_pause_chance = 0.5
            self.word_pause_chance = 0.4

        # Convert WPM to character timing
        chars_per_minute = self.base_wpm * 5  # Average word length
        self.base_char_delay = 60.0 / chars_per_minute

    def calculate_key_distance(self, key1: str, key2: str) -> float:
        """Calculate physical distance between keys for timing"""
        if key1.lower() not in self.qwerty_layout or key2.lower() not in self.qwerty_layout:
            return 1.0  # Default distance for unknown keys

        pos1 = self.qwerty_layout[key1.lower()]
        pos2 = self.qwerty_layout[key2.lower()]

        distance = ((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)**0.5
        return max(0.5, distance)  # Minimum distance factor

    def get_key_timing(self, current_char: str, previous_char: str = None) -> float:
        """Calculate realistic timing between keystrokes"""
        base_delay = self.base_char_delay

        # Distance-based timing adjustment
        if previous_char:
            distance_factor = self.calculate_key_distance(previous_char, current_char)
            base_delay *= (0.8 + distance_factor * 0.4)  # 0.8x to 1.6x based on distance

        # Add natural variation
        variation = random.uniform(0.7, 1.4)
        final_delay = base_delay * variation

        # Minimum and maximum bounds
        return max(0.05, min(2.0, final_delay))

    def should_make_typo(self, word: str) -> bool:
        """Determine if a typo should be made"""
        # Higher chance for longer words
        length_factor = 1 + (len(word) - 4) * 0.01
        adjusted_chance = self.typo_chance * length_factor

        # Less likely for common short words
        if len(word) <= 3:
            adjusted_chance *= 0.5

        return random.random() < adjusted_chance

    def generate_typo(self, word: str) -> str:
        """Generate a realistic typo for a word"""
        if word.lower() in self.common_typos:
            # Use common typo patterns
            return random.choice(self.common_typos[word.lower()])

        if len(word) < 3:
            return word  # Don't modify very short words

        # Generate random typo types
        typo_type = random.choice(['swap', 'omit', 'insert', 'wrong'])

        if typo_type == 'swap' and len(word) > 3:
            # Swap adjacent characters
            pos = random.randint(0, len(word) - 2)
            chars = list(word)
            chars[pos], chars[pos + 1] = chars[pos + 1], chars[pos]
            return ''.join(chars)

        elif typo_type == 'omit' and len(word) > 2:
            # Omit a character
            pos = random.randint(1, len(word) - 2)  # Not first or last
            return word[:pos] + word[pos + 1:]

        elif typo_type == 'insert':
            # Insert random character
            pos = random.randint(1, len(word) - 1)
            random_char = random.choice(string.ascii_lowercase)
            return word[:pos] + random_char + word[pos:]

        elif typo_type == 'wrong':
            # Replace character with nearby key
            pos = random.randint(0, len(word) - 1)
            char = word[pos].lower()
            if char in self.qwerty_layout:
                char_pos = self.qwerty_layout[char]
                nearby_keys = []
                for key, key_pos in self.qwerty_layout.items():
                    distance = ((char_pos[0] - key_pos[0])**2 + (char_pos[1] - key_pos[1])**2)**0.5
                    if 0.5 <= distance <= 1.5 and key != char:
                        nearby_keys.append(key)
                if nearby_keys:
                    wrong_char = random.choice(nearby_keys)
                    return word[:pos] + wrong_char + word[pos + 1:]

        return word  # Fallback to original

    def type_key(self, key: str, hold_duration: float = None) -> None:
        """Type a single key with realistic timing"""
        if hold_duration is None:
            hold_duration = random.uniform(0.08, 0.12)

        pyautogui.keyDown(key)
        time.sleep(hold_duration)
        pyautogui.keyUp(key)

        self.state.characters_typed += 1
        self.state.last_key_time = time.time()

    def correct_typo(self, typo_word: str, correct_word: str) -> None:
        """Perform realistic typo correction"""
        # Pause (notice the error)
        notice_delay = random.uniform(0.3, 0.8)
        time.sleep(notice_delay)

        # Backspace to delete typo
        for _ in range(len(typo_word)):
            self.type_key('backspace')
            time.sleep(random.uniform(0.1, 0.2))

        # Retype correctly with slightly slower speed
        for i, char in enumerate(correct_word):
            delay = self.get_key_timing(char, correct_word[i-1] if i > 0 else None)
            delay *= 1.3  # Slower when correcting
            time.sleep(delay)
            self.type_key(char)

        self.state.corrections_made += 1

    def type_word(self, word: str) -> None:
        """Type a word with realistic patterns"""
        # Check for typo
        if self.should_make_typo(word):
            typo_word = self.generate_typo(word)
            if typo_word != word:
                # Type the typo
                for i, char in enumerate(typo_word):
                    delay = self.get_key_timing(char, typo_word[i-1] if i > 0 else None)
                    time.sleep(delay)
                    self.type_key(char)

                self.state.errors_made += 1

                # Decide whether to correct (80% chance)
                if random.random() < 0.8:
                    self.correct_typo(typo_word, word)
                    return

        # Type the word normally
        for i, char in enumerate(word):
            delay = self.get_key_timing(char, word[i-1] if i > 0 else None)
            time.sleep(delay)
            self.type_key(char)

        self.state.words_typed += 1

    def type_text(self, text: str) -> None:
        """Type full text with human-like patterns"""
        words = text.split()

        for i, word in enumerate(words):
            # Thinking pause before certain words
            if random.random() < self.thinking_pause_chance:
                thinking_pause = random.uniform(0.5, 2.0)
                time.sleep(thinking_pause)

            # Type the word
            self.type_word(word)

            # Add space after word (except last word)
            if i < len(words) - 1:
                # Word boundary pause
                if random.random() < self.word_pause_chance:
                    word_pause = random.uniform(0.2, 0.6)
                    time.sleep(word_pause)

                # Type space
                space_delay = self.get_key_timing(' ', word[-1] if word else None)
                time.sleep(space_delay)
                self.type_key('space')

    def type_special_sequence(self, keys: List[str], delays: List[float] = None) -> None:
        """Type special key sequences (shortcuts, navigation)"""
        if delays is None:
            delays = [random.uniform(0.1, 0.2) for _ in range(len(keys) - 1)]

        for i, key in enumerate(keys):
            self.type_key(key)
            if i < len(delays):
                time.sleep(delays[i])

    def type_hotkey(self, *keys) -> None:
        """Type hotkey combination (Ctrl+C, Alt+Tab, etc.)"""
        # Press all keys down
        for key in keys:
            pyautogui.keyDown(key)
            time.sleep(random.uniform(0.02, 0.05))

        # Hold for realistic duration
        hold_time = random.uniform(0.1, 0.2)
        time.sleep(hold_time)

        # Release all keys (in reverse order)
        for key in reversed(keys):
            pyautogui.keyUp(key)
            time.sleep(random.uniform(0.02, 0.05))

    def backspace_word(self) -> None:
        """Delete previous word with realistic timing"""
        # Ctrl+Backspace or multiple backspaces
        if random.random() < 0.7:
            self.type_hotkey('ctrl', 'backspace')
        else:
            # Manual backspacing (5-15 characters)
            backspace_count = random.randint(5, 15)
            for _ in range(backspace_count):
                self.type_key('backspace')
                time.sleep(random.uniform(0.08, 0.15))

    def paste_text(self) -> None:
        """Simulate pasting with Ctrl+V"""
        self.type_hotkey('ctrl', 'v')
        time.sleep(random.uniform(0.1, 0.3))

    def get_typing_stats(self) -> Dict:
        """Get typing statistics for analysis"""
        session_time = time.time() - self.state.session_start_time
        wpm = (self.state.words_typed / session_time * 60) if session_time > 0 else 0
        accuracy = ((self.state.characters_typed - self.state.errors_made) /
                   max(1, self.state.characters_typed)) * 100

        return {
            'profile': self.profile.value,
            'session_time_seconds': session_time,
            'characters_typed': self.state.characters_typed,
            'words_typed': self.state.words_typed,
            'errors_made': self.state.errors_made,
            'corrections_made': self.state.corrections_made,
            'wpm': wpm,
            'accuracy_percent': accuracy,
            'base_wpm': self.base_wpm
        }

    def natural_pause(self, pause_type: str = 'thinking') -> None:
        """Insert natural pauses during typing"""
        if pause_type == 'thinking':
            duration = random.uniform(1.0, 3.0)
        elif pause_type == 'reading':
            duration = random.uniform(0.5, 1.5)
        elif pause_type == 'sentence':
            duration = random.uniform(0.3, 0.8)
        else:
            duration = random.uniform(0.2, 0.5)

        time.sleep(duration)