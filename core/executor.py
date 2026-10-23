import random
import time
import os
import platform
import ctypes
import math
from typing import Tuple


try:
    import pyautogui  # type: ignore
    pyautogui.FAILSAFE = False   # Avoid corner trigger safety exit
    pyautogui.PAUSE = 0          # No extra delays
except Exception as e:  # pragma: no cover
    pyautogui = None


def _need_pag():
    if pyautogui is None:
        raise RuntimeError("pyautogui not installed. Please install: pip install pyautogui")


def _norm_button(btn: str) -> str:
    btn = (btn or "left").lower()
    return btn if btn in ("left", "right", "middle") else "left"


def _norm_key(k: str) -> str:
    """Normalize key names for pyautogui compatibility"""
    if not isinstance(k, str):
        return k
    s = k.strip()
    if not s:
        return s

    mapping_common = {
        "ctrl": "ctrl", "control": "ctrl",
        "shift": "shift",
        "alt": "alt", "option": "alt",
        "enter": "enter", "return": "enter",
        "esc": "esc", "escape": "esc",
        "space": "space",
        "backspace": "backspace", "delete": "delete", "del": "delete",
        "tab": "tab",
        "home": "home", "end": "end",
        "pageup": "pageup", "pagedown": "pagedown",
        "left": "left", "right": "right", "up": "up", "down": "down",
        # Function keys
        "f1":"f1","f2":"f2","f3":"f3","f4":"f4","f5":"f5","f6":"f6",
        "f7":"f7","f8":"f8","f9":"f9","f10":"f10","f11":"f11","f12":"f12",
    }
    sys = platform.system()
    if sys == "Darwin":
        mapping_common.update({
            "meta": "command", "cmd": "command", "command": "command",
            "win": "command",
        })
    else:
        mapping_common.update({
            "meta": "win", "cmd": "win", "command": "win",
            "win": "win",
        })

    low = s.lower()
    return mapping_common.get(low, low)  # Other chars return lowercase


class Executor:
    def __init__(self, jitter_px: int = 2):
        self.jitter_px = jitter_px

    def _ensure_pg(self):
        if pyautogui is None:
            raise RuntimeError("pyautogui is required for Executor actions")

    def _jitter(self, x: int, y: int) -> Tuple[int, int]:
        jx = random.randint(-self.jitter_px, self.jitter_px)
        jy = random.randint(-self.jitter_px, self.jitter_px)
        return x + jx, y + jy

    def move_to(self, x: int, y: int, duration: float | None = None):
        self._ensure_pg()
        x2, y2 = self._jitter(x, y)
        dur = duration if duration is not None else random.uniform(0.12, 0.25)
        tween = getattr(pyautogui, "easeInOutQuad", None)
        try:
            if tween:
                pyautogui.moveTo(x2, y2, duration=dur, tween=tween)
            else:
                pyautogui.moveTo(x2, y2, duration=dur)
        except Exception:
            pyautogui.moveTo(x2, y2, duration=dur)

    def click(self, x: int, y: int, duration: float = 0.15, post_sleep: Tuple[float, float] = (0.6, 1.0), dpr: float = 1.0, button: str = "left"):
        self._ensure_pg()
        # pyautogui expects OS logical coordinates; on Retina, divide pixels by DPR
        sx = int(round(x / max(1.0, dpr)))
        sy = int(round(y / max(1.0, dpr)))
        # human-like move with easing
        self.move_to(sx, sy, duration)
        pyautogui.click(button=_norm_button(button))
        time.sleep(random.uniform(*post_sleep))
        # park pointer away from edges to avoid hover overlays (avoid failsafe corners)
        try:
            self.move_to(24, 24, duration=None)
        except Exception:
            # Ignore any failsafe exceptions and keep going
            pass

    def type_text(self, text: str, interval: Tuple[float, float] = (0.02, 0.05), mode: str | None = None):
        """Type text into the focused field.

        mode: None|'auto'|'type'|'paste'. In 'auto' (default), if the text contains non-ASCII
        characters, prefer clipboard paste for better IME/unicode compatibility (especially on macOS).
        """
        self._ensure_pg()
        m = (mode or os.getenv("EXEC_TYPE_MODE", "auto")).lower()
        if m not in ("auto", "type", "paste"):
            m = "auto"
        contains_non_ascii = any(ord(c) > 127 for c in (text or ""))
        # macOS: try real Unicode typing via Quartz (counts as keystrokes, not paste)
        if platform.system() == "Darwin" and contains_non_ascii and m in ("auto", "type") and os.getenv("EXEC_TYPE_MACOS_UNICODE", "1") == "1":
            try:
                from Quartz import (
                    CGEventCreateKeyboardEvent, CGEventPost,
                    kCGSessionEventTap, CGEventKeyboardSetUnicodeString
                )
                # Post the whole string as a Unicode key event
                down = CGEventCreateKeyboardEvent(None, 0, True)
                CGEventKeyboardSetUnicodeString(down, len(text), text)
                CGEventPost(kCGSessionEventTap, down)
                up = CGEventCreateKeyboardEvent(None, 0, False)
                CGEventKeyboardSetUnicodeString(up, len(text), text)
                CGEventPost(kCGSessionEventTap, up)
                return
            except Exception:
                # Fall through to paste or typewrite
                pass

        # Windows: try real Unicode typing via SendInput (KEYEVENTF_UNICODE)
        if platform.system() == "Windows" and contains_non_ascii and m in ("auto", "type") and os.getenv("EXEC_TYPE_WINDOWS_UNICODE", "1") == "1":
            try:
                # Structures and constants for SendInput
                user32 = ctypes.windll.user32
                INPUT_KEYBOARD = 1
                KEYEVENTF_UNICODE = 0x0004
                KEYEVENTF_KEYUP = 0x0002

                class KEYBDINPUT(ctypes.Structure):
                    _fields_ = [
                        ("wVk", ctypes.c_ushort),
                        ("wScan", ctypes.c_ushort),
                        ("dwFlags", ctypes.c_ulong),
                        ("time", ctypes.c_ulong),
                        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
                    ]

                class INPUT(ctypes.Structure):
                    _fields_ = [("type", ctypes.c_ulong), ("ki", KEYBDINPUT)]

                def _send_unicode_char(ch: str, up: bool = False):
                    ev = INPUT()
                    ev.type = INPUT_KEYBOARD
                    ev.ki = KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0), 0, None)
                    user32.SendInput(1, ctypes.byref(ev), ctypes.sizeof(ev))

                # Send each char as key down + key up (with small delay to mimic typing)
                delay = max(0.005, random.uniform(*interval))
                for ch in text:
                    _send_unicode_char(ch, up=False)
                    time.sleep(delay)
                    _send_unicode_char(ch, up=True)
                return
            except Exception:
                # Fall through to paste or typewrite
                pass

        use_paste = (m == "paste") or (m == "auto" and contains_non_ascii)
        if use_paste:
            # macOS: use pbcopy to avoid extra deps; others: fallback to pyperclip if available
            try:
                import subprocess, time as _t
                sysname = platform.system()
                if sysname == "Darwin":
                    p = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
                    _ = p.communicate(input=text.encode('utf-8'))
                    _t.sleep(0.05)
                    pyautogui.hotkey('command', 'v')
                    return
                else:
                    try:
                        import pyperclip  # type: ignore
                        pyperclip.copy(text)
                        _t.sleep(0.05)
                        # common paste shortcuts
                        pyautogui.hotkey('ctrl', 'v')
                        return
                    except Exception:
                        pass
            except Exception:
                pass
        # Fallback to regular typing
        iv = random.uniform(*interval)
        pyautogui.typewrite(text, interval=iv)

    def scroll(self, clicks: int = -400):
        self._ensure_pg()
        pyautogui.scroll(clicks)

    def go_back(self):
        """Best-effort back navigation (browser-style)."""
        self._ensure_pg()
        import platform
        sysname = platform.system()
        try:
            if sysname == "Darwin":
                pyautogui.hotkey("command", "[")
            elif sysname == "Windows":
                pyautogui.hotkey("alt", "left")
            else:
                pyautogui.hotkey("alt", "left")
        except Exception:
            pass

    # ========= Enhanced Mouse Operations =========
    def move_by(self, dx: int, dy: int, duration: float = 0.0):
        _need_pag()
        pyautogui.moveRel(int(dx), int(dy), duration=max(0.0, float(duration)))

    def mouse_down(self, button: str = "left"):
        _need_pag()
        pyautogui.mouseDown(button=_norm_button(button))

    def mouse_up(self, button: str = "left"):
        _need_pag()
        pyautogui.mouseUp(button=_norm_button(button))

    def drag_to(self, x: int, y: int, duration: float = 0.2, button: str = "left"):
        _need_pag()
        pyautogui.dragTo(int(x), int(y), duration=max(0.0, float(duration)), button=_norm_button(button))

    def drag_by(self, dx: int, dy: int, duration: float = 0.2, button: str = "left"):
        _need_pag()
        pyautogui.dragRel(int(dx), int(dy), duration=max(0.0, float(duration)), button=_norm_button(button))

    # ========= Enhanced Keyboard Operations =========
    def key(self, key: str):
        """Send single key (e.g., 'enter', 'tab', 'a')."""
        _need_pag()
        pyautogui.press(_norm_key(str(key)))

    def key_down(self, key: str):
        _need_pag()
        pyautogui.keyDown(_norm_key(str(key)))

    def key_up(self, key: str):
        _need_pag()
        pyautogui.keyUp(_norm_key(str(key)))

    def key_combo(self, *keys):
        """
        Combo keys: e.g., key_combo("Ctrl", "Shift", "N") or key_combo("Meta", "K").
        Automatically handles macOS command/win key differences.
        """
        _need_pag()
        if not keys:
            return
        normed = [_norm_key(str(k)) for k in keys]
        # pyautogui.hotkey automatically presses then releases
        pyautogui.hotkey(*normed)

    # ========= Clipboard Operations =========
    def clipboard_get(self) -> str:
        """Get clipboard content as text."""
        try:
            sysname = platform.system()
            if sysname == "Darwin":
                import subprocess
                result = subprocess.run(['pbpaste'], capture_output=True, text=True, timeout=2)
                return result.stdout
            else:
                try:
                    import pyperclip  # type: ignore
                    return pyperclip.paste()
                except Exception:
                    return ""
        except Exception:
            return ""

    def clipboard_set(self, text: str):
        """Set clipboard content."""
        try:
            sysname = platform.system()
            if sysname == "Darwin":
                import subprocess
                subprocess.run(['pbcopy'], input=str(text), text=True, timeout=2)
            else:
                try:
                    import pyperclip  # type: ignore
                    pyperclip.copy(str(text))
                except Exception:
                    pass
        except Exception:
            pass

    def clipboard_clear(self):
        """Clear clipboard content."""
        self.clipboard_set("")
