import io
from dataclasses import dataclass
from typing import Tuple
import platform
import subprocess
import ctypes  # type: ignore

import numpy as np
from PIL import Image


try:
    import pyautogui  # type: ignore
except Exception as e:  # pragma: no cover
    pyautogui = None  # noqa: E305


@dataclass
class GrabResult:
    image: Image.Image
    dpr: float
    size_px: Tuple[int, int]


class ScreenCapture:
    """Simple screen capture utility that records device pixel ratio (DPR).

    Coordinates in this project are always in physical screen pixels.
    We infer DPR by comparing logical screen size with screenshot size.
    """

    def __init__(self, force_dpr: float | None = None):
        self._force_dpr = force_dpr

    def _infer_dpr(self, img: Image.Image) -> float:
        if self._force_dpr:
            return float(self._force_dpr)
        if pyautogui is None:
            return 1.0
        try:
            w_pts, h_pts = pyautogui.size()
            dpr = max(1.0, round(img.width / float(w_pts), 2))
            return dpr
        except Exception:
            return 1.0

    def screenshot(self) -> GrabResult:
        if pyautogui is None:
            raise RuntimeError("pyautogui is required for screenshot()")
        img = pyautogui.screenshot()
        dpr = self._infer_dpr(img)
        return GrabResult(image=img, dpr=dpr, size_px=(img.width, img.height))

    # ---- Active window helpers (per-OS) ----
    def _active_window_region(self) -> Tuple[int, int, int, int] | None:
        sysname = platform.system()
        if sysname == "Darwin":
            try:
                # AppleScript to get front window bounds: returns {left, top, right, bottom}
                script = (
                    'tell application "System Events" to set frontApp to name of first application process whose frontmost is true\n'
                    'tell application frontApp\n'
                    'try\n'
                    'set b to bounds of front window\n'
                    'on error\n'
                    'set b to {0, 0, 0, 0}\n'
                    'end try\n'
                    'end tell\n'
                    'return b'
                )
                out = subprocess.check_output(["osascript", "-e", script], timeout=2.0)
                s = out.decode("utf-8", errors="ignore").strip()
                parts = [int(p.strip()) for p in s.replace("{", "").replace("}", "").split(",") if p.strip()]
                if len(parts) == 4:
                    x1, y1, x2, y2 = parts
                    w = max(0, x2 - x1)
                    h = max(0, y2 - y1)
                    if w > 0 and h > 0:
                        return (x1, y1, w, h)
            except Exception:
                return None
        elif sysname == "Windows":
            try:
                user32 = ctypes.windll.user32  # type: ignore[attr-defined]
                rect = ctypes.wintypes.RECT()  # type: ignore[attr-defined]
                hwnd = user32.GetForegroundWindow()
                if hwnd:
                    ok = user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    if ok:
                        x1, y1, x2, y2 = rect.left, rect.top, rect.right, rect.bottom
                        w = max(0, x2 - x1)
                        h = max(0, y2 - y1)
                        if w > 0 and h > 0:
                            return (int(x1), int(y1), int(w), int(h))
            except Exception:
                return None
        return None

    def screenshot_active_window(self) -> Tuple[GrabResult, Tuple[int, int] | None]:
        """Capture the active window region if possible.

        Returns (GrabResult, (offset_x, offset_y) or None if full fallback)
        """
        if pyautogui is None:
            raise RuntimeError("pyautogui is required for screenshot_active_window()")
        region = self._active_window_region()
        if not region:
            # Fallback to full screen
            g = self.screenshot()
            return g, None
        img = pyautogui.screenshot(region=region)
        dpr = self._infer_dpr(img)
        x, y, w, h = region
        return GrabResult(image=img, dpr=dpr, size_px=(img.width, img.height)), (x, y)

    @staticmethod
    def pil_to_bgr(img: Image.Image) -> np.ndarray:
        arr = np.array(img.convert("RGB"))
        # RGB -> BGR for OpenCV drawing
        return arr[:, :, ::-1].copy()

    @staticmethod
    def bgr_to_png_bytes(bgr: np.ndarray) -> bytes:
        rgb = bgr[:, :, ::-1]
        im = Image.fromarray(rgb)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()
