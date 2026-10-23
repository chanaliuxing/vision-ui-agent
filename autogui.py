import os
import time
import subprocess
import pyautogui

# --- PyAutoGUI safety and pacing ---
pyautogui.FAILSAFE = True         # Move mouse to top-left corner to abort
pyautogui.PAUSE = 0.05            # Small delay after each action

# --- Config ---
CONFIDENCE = 0.9                  # Lower a bit (e.g., 0.85) if matches fail
CHECK_INTERVAL = 0.5              # Time between checks when nothing found
ACTION_COOLDOWN = 2.0             # Cooldown after an action to avoid spamming
SEARCH_GRAYSCALE = True           # Often improves robustness/speed

# Image filenames (must be in same directory as this script)
BASE_IMAGE = "codex.png"
STOP_IMAGE = "codexstop.png"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_PATH = os.path.join(SCRIPT_DIR, BASE_IMAGE)
STOP_PATH = os.path.join(SCRIPT_DIR, STOP_IMAGE)

def bring_terminal_to_front():
    """
    Bring Apple's Terminal to the foreground.
    Falls back to iTerm if you use that.
    """
    # Try Terminal
    cmd_terminal = ['osascript', '-e', 'tell application "Terminal" to activate']
    # Try iTerm as fallback
    cmd_iterm = ['osascript', '-e', 'tell application "iTerm" to activate']

    try:
        subprocess.run(cmd_terminal, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    except Exception:
        pass

    try:
        subprocess.run(cmd_iterm, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    except Exception:
        pass

def locate(image_path: str):
    """
    Returns the center point (x, y) of the first match of image on screen,
    or None if not found.
    """
    try:
        # Using confidence requires OpenCV to be installed
        box = pyautogui.locateOnScreen(
            image_path,
            confidence=CONFIDENCE,
            grayscale=SEARCH_GRAYSCALE
        )
        if box:
            return pyautogui.center(box)
    except Exception:
        # If something odd happened (e.g., permissions), just treat as not found
        return None
    return None

def press_enter():
    pyautogui.press('enter')

def type_and_enter(text: str):
    pyautogui.typewrite(text, interval=0.02)
    pyautogui.press('enter')

def main():
    # Basic checks
    if not os.path.exists(BASE_PATH):
        print(f"[ERROR] Missing image: {BASE_PATH}")
        return
    if not os.path.exists(STOP_PATH):
        print(f"[WARN] Missing image: {STOP_PATH} (will still run)")

    print("[INFO] Starting watcher. Move mouse to top-left corner to abort.")

    last_action_ts = 0.0

    while True:
        bring_terminal_to_front()

        # Look for the base image first
        p = locate(BASE_PATH)
        if p:
            if time.time() - last_action_ts >= ACTION_COOLDOWN:
                print("[MATCH] Found codex.png → pressing Enter")
                press_enter()
                last_action_ts = time.time()
            time.sleep(CHECK_INTERVAL)
            continue

        # If base not found, look for the stop image
        p2 = locate(STOP_PATH)
        if p2:
            if time.time() - last_action_ts >= ACTION_COOLDOWN:
                print('[MATCH] Found codexstop.png → typing "continue roadmap/to do list with your plan" + Enter')
                type_and_enter("continue with your plan")
                last_action_ts = time.time()
            time.sleep(CHECK_INTERVAL)
            continue

        # Nothing matched; short sleep before next scan
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
