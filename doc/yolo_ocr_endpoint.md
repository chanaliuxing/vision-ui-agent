# YOLO + Fused OCR API (PaddleOCR preferred, EasyOCR fallback) — v2.2

FastAPI service that runs **Ultralytics YOLO** object detection and **OCR** (PaddleOCR preferred, EasyOCR fallback). Returns **IDs-only** overlays and rich JSON. Can also **return a PNG directly** instead of embedding Base64.

* **Base URL:** your server root (e.g., `http://localhost:8000`)
* **CORS:** `*` (all origins allowed)
* **Model Weights:** `YOLO_WEIGHTS` (env) → default `./weights/model.pt`
* **Device:** auto-selects `mps` on Apple Silicon if available else `cpu`

---

## Quickstart

```bash
# JSON (annotated image as data:image/png;base64,... in response)
curl -X POST "http://localhost:8000/predict?return_image=true&return_image_format=json" \
  -F "image=@/path/to/image.jpg"

# Direct PNG (binary image response with IDs drawn)
curl -X POST "http://localhost:8000/predict?return_image=true&return_image_format=png" \
  -H "Accept: image/png" \
  -F "image=@/path/to/image.jpg" --output annotated.png

# From URL (requires `requests` installed server-side)
curl -X POST "http://localhost:8000/predict" \
  -F "image_url=https://example.com/sample.jpg"
```

Minimal Python example:

```python
import requests
files = {"image": open("image.jpg","rb")}
params = {"return_image": True, "return_image_format": "json"}
r = requests.post("http://localhost:8000/predict", files=files, params=params, timeout=60)
print(r.json())
```

---

## Endpoints

### GET `/health`

**Purpose:** quick readiness + capability check.

**Response 200 (application/json)**

```json
{
  "status": "ok",
  "model": "/abs/path/to/model.pt",
  "device": "mps|cpu",
  "paddleocr": true,
  "easyocr": true
}
```

---

### POST `/predict`

Runs detection → optional global OCR → optional crop OCR → **fuses** OCR lines per detected box → returns JSON and/or annotated image.

#### Inputs

**Image input** (exactly one of):

* `image` (form-data file, e.g. `-F "image=@...jpg"`)
* `image_base64` (form field; raw Base64 bytes, not data URL)
* `image_url` (form field; server fetches via `requests`)

**Query parameters (all optional, with defaults):**

**Detection**

* `conf` (float, default env `YOLO_CONF` or `0.25`) — score threshold
* `iou` (float, default env `YOLO_IOU` or `0.45`) — NMS IoU
* `imgsz` (int, default env `YOLO_IMGSZ` or `1280`) — inference size
* `max_det` (int, default `300`) — max detections

**Drawing / image output**

* `return_image` (bool, default `true`) — include visual output
* `return_image_format` (`"json"`|`"png"`, default `"json"`)

  * `"json"` → returns `image_base64` (data URL) inside JSON
  * `"png"` → endpoint returns **binary PNG** (no JSON body)
* `line_width` (int, `2`)
* `font_px` (int, `12`) — target label font pixel height
* `min_band_px` (int, `14`) — min top-band height if label can’t fit inside box
* `min_band_px_ratio` (float, `0.012`) — band-height floor as a fraction of image height
* `draw_center` (bool, `true`) — draws a center dot per box

**ID strategy**

* `id_order` (`"tl"` or anything else, default `"tl"`) — `"tl"` numbers by **top-left** ordering; otherwise model order
* `label_prefix` (str, default `"icon"`) — used for `name`/`label` fields (e.g., `"icon 3"`)

**OCR**

* `ocr_backend` (`"auto"`|`"paddle"`|`"easyocr"`, default `"auto"`)
* `ocr_langs` (str, default `"ch"`)

  * Paddle: `"ch"` covers **Chinese + English**
  * EasyOCR: use codes like `"en,ch_sim"`; server auto-maps `"ch"` → `"ch_sim"`
* `ocr_min_conf` (float, `0.5`) — filter lines below this confidence
* `box_expand_ratio` (float, `0.06`) — crop expansion around each box
* `box_ocr_mode` (`"global"`|`"crop"`|`"fused"`, default `"fused"`)

  * `global`: one OCR pass on the full image, then assign lines into boxes
  * `crop`: OCR each (expanded) box only
  * `fused`: **global first**, then crop **only if needed** (best speed/quality tradeoff)
* `fuse_iou_th` (float, `0.01`) — how strictly to assign global OCR to a box (center-in or bbox IoU >= this)

**Crop OCR heuristics**

* `crop_ocr_if_needed_only` (bool, `true`) — only do crop OCR if fused text is short/empty
* `crop_trigger_min_chars` (int, `6`) — if fused text length < this, trigger crop OCR
* `max_crops_ocr` (int, `200`) — safety cap

#### Responses

**A) JSON (default) — 200 OK**

```json
{
  "model": "/abs/path/to/model.pt",
  "device": "mps",
  "time_ms": 37.41,
  "detections": [
    {
      "id": 1,
      "name": "icon 1",
      "label": "icon 1",
      "conf": 0.91,
      "class_id": 0,
      "class_name": "0",
      "bbox_xyxy": [120.1, 88.3, 245.7, 210.4],
      "bbox_xyxy_norm": [0.10, 0.07, 0.21, 0.17],
      "center_xy_norm": [0.155, 0.12],
      "size_wh_norm": [0.11, 0.10],
      "click_xy_norm": [0.155, 0.12],
      "label_bbox_xyxy": [118.0, 88.0, 246.0, 112.0],
      "ocr": {
        "text": "OK Continue",
        "lines": [
          {
            "polygon": [[123.0,92.0],[240.0,92.0],[240.0,108.0],[123.0,108.0]],
            "text": "OK",
            "conf": 0.98
          }
        ]
      }
    }
  ],
  "ocr_full_count": 12,
  "image_base64": "data:image/png;base64,iVBORw0KGgoAAA..."
}
```

**B) PNG — 200 OK**

* If `return_image=true&return_image_format=png`, the endpoint returns **`image/png`** bytes.
* The response body is the annotated image (IDs, boxes, optional center dots).
* **No JSON** is returned in this mode.

**Possible error shapes**

* `500 Internal Server Error` with message text such as:

  * `"No image provided"` (if no `image`/`image_base64`/`image_url`)
  * `"requests not installed"` (when using `image_url` but `requests` missing)
  * OCR failures are caught and **do not** error the request; OCR is just skipped (you’ll see `ocr_full_count: 0`)

---

## Field Reference

**Top-level JSON**

* `model` — absolute path to YOLO weights
* `device` — `"mps"` or `"cpu"`
* `time_ms` — YOLO detection time only (OCR not included)
* `detections` — array of detection objects (see below)
* `ocr_full_count` — number of OCR lines found on the **global** (full-image) pass (0 if OCR disabled/unavailable)
* `image_base64` — present only if `return_image=true` and `return_image_format=json`

**`detections[]`**

* `id` — per-scene ID (top-left order if `id_order=tl`)
* `name`, `label` — `<label_prefix> <id>`
* `conf` — YOLO confidence
* `class_id`, `class_name` — raw class id; `names` from model if available
* `bbox_xyxy` — `[x1,y1,x2,y2]` (float, image pixels)
* `bbox_xyxy_norm` — normalized to `[0..1]`
* `center_xy_norm` — box center (normalized)
* `size_wh_norm` — width/height (normalized)
* `click_xy_norm` — convenience alias of center (normalized)
* `label_bbox_xyxy` — rectangle used to render the numeric ID label (if drawn)
* `ocr.text` — fused box text (global + optional crop, deduped)
* `ocr.lines[]` — per-line OCR results assigned to this box (global and crop lines mapped into global coords)

---

## OCR Behavior & Tips

* **Preferred backend:** PaddleOCR (`ocr_backend=auto|paddle`) with `lang="ch"` handles **CN+EN** well.
* **Fallback:** EasyOCR auto-mapped languages (e.g., `"ch"` → `"ch_sim"`, `"zh-tw"` → `"ch_tra"`); backend is chosen automatically if Paddle not available.
* **Modes:**

  * `global` — 1 pass over the whole image; then assign lines to boxes (fastest)
  * `crop` — OCR per (expanded) box only (slower, can be better for tiny text)
  * `fused` — **default**: global pass, then **crop only if needed** (short text)
* **Heuristics:** tweak `box_expand_ratio`, `crop_trigger_min_chars`, and `ocr_min_conf` for better small-text recall vs speed.

---

## Environment Variables

* `YOLO_WEIGHTS` → path to `.pt` weights (default `./weights/model.pt`)
* `YOLO_CONF` → default confidence (string, parsed as float; default `"0.25"`)
* `YOLO_IOU` → default NMS IoU (string→float; default `"0.45"`)
* `YOLO_IMGSZ` → default inference size (string→int; default `"1280"`)

---

## Deployment

**Local (uvicorn)**

```bash
pip install fastapi uvicorn ultralytics pillow numpy opencv-python
# (optional) paddleocr or easyocr + torch (CPU ok)
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1
```

**Notes**

* On Apple Silicon: the app prefers `mps` if `torch.backends.mps.is_available()`; otherwise CPU.
* If using `image_url`, ensure `requests` is installed.
* OCR absence (neither Paddle nor EasyOCR available) **does not fail** the request; you’ll just get no OCR lines.

---

## Examples

**1) Tune detection thresholds**

```bash
curl -X POST "http://localhost:8000/predict?conf=0.4&iou=0.5&imgsz=960" \
  -F "image=@ui_screenshot.png"
```

**2) Global-only OCR**

```bash
curl -X POST "http://localhost:8000/predict?box_ocr_mode=global" \
  -F "image=@panel.png"
```

**3) Force crop OCR for every box**

```bash
curl -X POST "http://localhost:8000/predict?box_ocr_mode=crop&crop_ocr_if_needed_only=false" \
  -F "image=@tiny_text.png"
```

**4) EasyOCR in Traditional Chinese + English**

```bash
curl -X POST "http://localhost:8000/predict?ocr_backend=easyocr&ocr_langs=ch_tra,en" \
  -F "image=@doc.jpg"
```

**5) Direct PNG return**

```bash
curl -X POST "http://localhost:8000/predict?return_image=true&return_image_format=png" \
  -F "image=@screen.jpg" --output out.png
```

---

## Known Edge Cases

* **No image provided** → 500 error (`"No image provided"`); always send one of the three image inputs.
* **`image_url` without `requests`** → 500 error (`"requests not installed"`).
* **OCR errors** are logged and skipped; detection still succeeds.
* **Class names**: if your YOLO weights don’t carry names, `class_name` falls back to the numeric id as a string.

---

## Change Log (excerpt)

* **v2.2**

  * Added direct PNG streaming via `return_image_format=png`
  * Fused OCR mode with crop-on-demand heuristics
  * Robust label placement inside box with top-band fallback
  * Normalized geometry convenience fields for automation (`*_norm`)

---


