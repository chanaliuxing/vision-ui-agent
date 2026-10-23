# AutoStep Engine Migration & Integration Guide

This document provides a comprehensive technical guide for migrating the **AutoStep Engine** (a dynamic Perceive-Decide-Act loop) to other Python-based automation projects. It includes architecture details, core logic extraction, and specific code snippets for implementing the memory and state management systems.

---

## 1. Core Architecture: The PDA Loop

The `AutoStep` engine differs from traditional linear scripts by using a **dynamic graph** driven by real-time perception. It does not rely on hardcoded selectors (XPath/CSS) but instead "sees" the screen, "decides" on actions using LLMs or cached memories, and "acts" accordingly.

### The Dynamic Loop (AutoNext)
The engine operates on a continuous cycle:
1.  **Perceive**: Capture screenshot & detect UI elements (YOLO).
2.  **Graph**: Calculate a **Visual Signature** to uniquely identify the current page state.
    *   *New State?* Create a new node ID (e.g., `pg_001`).
    *   *Known State?* Resolve to an existing ID.
3.  **Decide**:
    *   **Fast Path (Memory)**: Check `RoutesStore` (Anchors) or `StrategyStore`. If a solution exists, execute immediately (0 token cost).
    *   **Slow Path (Intelligence)**: If new, ask **LLM** (Vision-Language Model) what to do based on the User Goal.
4.  **Act**: Execute the action (Click/Type).
5.  **Verify & Learn**: Did the page change?
    *   *Yes*: Save the successful action as a new **Anchor** (Rule) for future "Fast Path" execution.
    *   *No*: Retry, fallback, or mark as failure.
6.  **Transition**: Automatically jump to the next state ID detected in step 2.

---

## 2. Core Modules Implementation Guide

To migrate the engine, you need to implement or adapt the following components. The code snippets provided are extracted from the reference implementation and simplified for clarity.

### 2.1 Visual Signature (`_signature`)
**Source**: `core/workflow.py`

The signature is the "hash" of a page state. It combines visual appearance (`pHash`), semantic structure (`YOLO Hist`), and layout grid.

**Code Snippet:**
```python
import cv2
import math
import hashlib
import numpy as np

def calculate_signature(bgr_image, detections):
    """
    Computes a robust signature for the current page state.
    detections: List of objects with 'class_name' and 'bbox'.
    """
    sig = {}
    
    # 1. Visual Hash (pHash) - Overall appearance
    try:
        gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (16, 16), interpolation=cv2.INTER_AREA)
        avg = small.mean()
        # Create a 256-bit binary string based on pixel > average
        bits = (small > avg).astype(np.uint8).flatten()
        # Convert bits to hex string
        sig["phash"] = "".join('1' if b else '0' for b in bits)
    except Exception:
        sig["phash"] = ""

    # 2. Structural Hash (YOLO Hist) - Semantic content
    # e.g., {"button": 3, "input": 1, "icon": 5}
    hist = {}
    for d in detections:
        cls = d.get("class_name")
        hist[cls] = hist.get(cls, 0) + 1
    sig["yolo_hist"] = hist

    # 3. Layout Grid Hash - Coarse spatial layout
    try:
        small_grid = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
        grid_bits = (small_grid > small_grid.mean()).astype(np.uint8).flatten()
        sig["layout"] = "".join('1' if b else '0' for b in grid_bits)
    except Exception:
        sig["layout"] = ""

    return sig

def signature_similarity(sig_a, sig_b):
    """
    Calculates similarity between two signatures (0.0 to 1.0).
    Weighted combination of pHash equality, Histogram cosine similarity, and Layout hamming.
    """
    # ... (Implementation details: dot product of histograms, hamming distance of phash)
    # Return a score. If > 0.78, consider it the same page.
    pass
```

### 2.2 Visual Anchors (`core/anchors.py`)
**Purpose**: The "Visual GPS". Replaces LLM with Computer Vision for known tasks.

*   **`anchors_from`**: Crops the successful click area.
*   **`locate_instance`**: Finds that template on the current screen.

**Code Snippet:**
```python
def anchors_from(bgr_image, bbox, pad_ratio=0.1):
    """
    Crops a template image from the successful click region.
    """
    x1, y1, x2, y2 = map(int, bbox)
    H, W = bgr_image.shape[:2]
    
    # Add padding context
    w, h = x2 - x1, y2 - y1
    px, py = int(pad_ratio * w), int(pad_ratio * h)
    
    # Clip to image bounds
    rx1, ry1 = max(0, x1 - px), max(0, y1 - py)
    rx2, ry2 = min(W, x2 + px), min(H, y2 + py)
    
    roi = bgr_image[ry1:ry2, rx1:rx2].copy()
    
    # Encode as PNG bytes for storage
    _, buf = cv2.imencode('.png', roi)
    
    return {
        "type": "template",
        "template_png": buf.tobytes().hex(),
        "method": "TM_CCOEFF_NORMED",
        "th": 0.82  # Threshold
    }

def locate_instance(screen_bgr, anchor_data):
    """
    Locates the anchor template on the current screen.
    """
    if anchor_data["type"] != "template": return None
    
    # Decode template
    template_bytes = bytes.fromhex(anchor_data["template_png"])
    template = cv2.imdecode(np.frombuffer(template_bytes, np.uint8), cv2.IMREAD_COLOR)
    
    # Match
    res = cv2.matchTemplate(screen_bgr, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    
    if max_val >= anchor_data["th"]:
        h, w = template.shape[:2]
        x, y = max_loc
        return [x, y, x + w, y + h]  # New bbox
    return None
```

### 2.3 Routes Store (`core/anchors.py`)
**Purpose**: Persistent storage for "If I see this Page Signature + User Goal, click this Anchor".

**Code Snippet:**
```python
import json
import os

class RoutesStore:
    def __init__(self, path="routes.jsonl"):
        self.path = path
        self.cache = []
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                for line in f:
                    self.cache.append(json.loads(line))

    def lookup(self, sig_key, goal):
        """Find a route that matches the signature and goal."""
        # sig_key is usually json.dumps(signature)
        for rec in reversed(self.cache):
            if rec["sig_key"] == sig_key and rec["goal"] == goal:
                return rec
        return None

    def append(self, record):
        """Save a new successful route."""
        self.cache.append(record)
        with open(self.path, "a") as f:
            f.write(json.dumps(record) + "\n")
```

### 2.4 The Engine Logic (`_autostep`)
**Source**: `core/workflow.py`

This is the orchestration logic connecting Perception, Memory, and Action.

**Pseudocode / Implementation Logic:**

```python
def autostep(ctx, goal):
    # 1. PERCEIVE
    screenshot = capture_screen()
    detections = yolo_client.detect(screenshot)
    
    # Compute Signature
    sig = calculate_signature(screenshot, detections)
    sig_key = json.dumps(sig, sort_keys=True)
    
    # Resolve State ID
    state_id = resolve_state_id(sig) # e.g. "pg_005"
    ctx["next_state_id"] = state_id 

    # 2. FAST PATH (Memory)
    route = routes_store.lookup(sig_key, goal)
    if route:
        # Try to locate the anchor
        target_bbox = locate_instance(screenshot, route["anchor"])
        if target_bbox:
            print("Fast Path: Click via Anchor")
            click(center(target_bbox))
            if verify_page_change():
                return "success"
    
    # 3. SLOW PATH (LLM)
    print("Slow Path: Asking LLM")
    
    # Filter detections using Blacklist (Memory)
    blacklist = memory_store.get_blacklist(sig_key)
    valid_detections = [d for d in detections if d.id not in blacklist]
    
    # Construct Prompt
    prompt = f"""
    Goal: {goal}
    Screen Elements: {json.dumps(valid_detections)}
    Task: Return the ID of the element to click.
    """
    
    # Call LLM
    target_id = llm_client.predict(prompt, image=screenshot)
    target_det = find_detection_by_id(valid_detections, target_id)
    
    if target_det:
        click(center(target_det.bbox))
        
        # 4. VERIFY & LEARN
        if verify_page_change():
            # Create and Save Anchor
            anchor = anchors_from(screenshot, target_det.bbox)
            routes_store.append({
                "sig_key": sig_key,
                "goal": goal,
                "anchor": anchor
            })
            # Record Success
            memory_store.record(sig_key, target_id, "success")
        else:
            # Record Failure
            memory_store.record(sig_key, target_id, "fail")

---

## 3. Migration Checklist

Use this checklist to track your porting progress.

### Phase 1: Foundation
- [ ] **Dependencies**: Install `opencv-python`, `numpy`, `pyautogui`, `requests`.
- [ ] **Utilities**: Implement `calculate_signature` (pHash + Histogram).
- [ ] **YOLO Integration**: Ensure you have a working object detection client (local or API).

### Phase 2: The Stores
- [ ] **`RoutesStore`**: Implement JSONL reader/writer.
- [ ] **`MemoryStore`**: Implement simple success/fail logging per signature.
- [ ] **`Anchors`**: Implement `anchors_from` (crop) and `locate_instance` (matchTemplate).

### Phase 3: The Engine
- [ ] **`autostep` Function**: Implement the Perceive -> Fast Path -> Slow Path -> Verify loop.
- [ ] **State Machine**: Update your main loop to respect `ctx["next_state_id"]` for dynamic transitions (`autonext`).

### Phase 4: Integration
- [ ] **Replace Scripts**: Replace linear scripts with `autostep(goal="Login")`.
- [ ] **Training Run**: Run once to populate `routes.jsonl`.
- [ ] **Fast Run**: Run again to verify it uses the Fast Path (anchors) and skips the LLM.

---

## 4. Key Files to Reference (Source Codebase)

*   `core/workflow.py`: Main engine logic (`_autostep`, `_signature`).
*   `core/anchors.py`: Visual anchoring logic (`anchors_from`, `locate_instance`).
*   `core/memory.py`: Short-term memory (`MemoryStore`).
*   `core/strategy_store.py`: Logic-based memory (`StrategyStore`).