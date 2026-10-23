# YOLO FastAPI Server — API Documentation (v2.2)

A lightweight HTTP service that runs **Ultralytics YOLO** detection and returns compact JSON (optionally with an annotated image as a Base64 data URL). Label rendering is **inside the box** with adaptive font sizing; IDs are **stable** (by default: top→bottom, then left→right).

* **Base URL:** (your host) e.g., `http://localhost:8000`
* **CORS:** `*` (all origins allowed)
* **Model Weights:** loaded once at startup from `YOLO_WEIGHTS`
* **Device preference:** Apple **MPS** on Apple Silicon if available, else CPU

---

## Quickstart

```bash
# Detect with defaults; JSON response
curl -X POST "http://localhost:8000/predict" \
  -F "image=@/path/to/image.jpg"

# Include annotated image as Base64 data URL in JSON
curl -X POST "http://localhost:8000/predict?return_image=true" \
  -F "image=@/path/to/image.jpg"

# Provide an image via URL (server will fetch it)
curl -X POST "http://localhost:8000/predict" \
  -F "image_url=https://example.com/sample.jpg"
```

Minimal Python client:

```python
import requests
r = requests.post(
    "http://localhost:8000/predict",
    files={"image": open("img.jpg", "rb")},
    params={"return_image": True},
    timeout=60
)
print(r.json())
```

---

## Environment Variables

| Var            | Type  | Default                                    | Notes                        |
| -------------- | ----- | ------------------------------------------ | ---------------------------- |
| `YOLO_WEIGHTS` | str   | `./weights/model.pt` | Path to `.pt` weights        |
| `YOLO_CONF`    | float | `0.25`                                     | Default detection confidence |
| `YOLO_IOU`     | float | `0.45`                                     | NMS IoU                      |
| `YOLO_IMGSZ`   | int   | `1280`                                     | Inference image size         |

---

## Endpoints

### `GET /health`

Check service readiness and runtime settings.

**Response 200**

```json
{
  "status": "ok",
  "model": "/abs/path/to/model.pt",
  "device": "mps"  // or "cpu"
}
```

---

### `POST /predict`

Run YOLO detection and return structured results. Optionally include an annotated PNG as a Base64 data URL.

#### Request

**Image input** *(exactly one must be provided)*

* `image` — multipart file (`-F "image=@file.jpg"`)
* `image_base64` — form field string (raw base64 **bytes**, not a `data:` URL)
* `image_url` — form field; server fetches the image (requires `requests` installed)

**Query parameters** *(all optional; defaults shown)*

**Detection**

* `conf` (float, default = `YOLO_CONF` or `0.25`, range `[0,1]`)
* `iou`  (float, default = `YOLO_IOU`  or `0.45`, range `[0,1]`)
* `imgsz` (int, default = `YOLO_IMGSZ` or `1280`)
* `max_det` (int, default = `300`)

**Output & labeling**

* `return_image` (bool, default `false`) — include annotated image as `image_base64`
* `label_prefix` (str, default `"icon"`) — used when `text_mode="full"`
* `id_order` (str, default `"tl"`) — stable ID assignment: `"tl"` = top→bottom, then left→right; any other value keeps model order
* `show_conf` (bool, default `true`) — include confidence when `text_mode="full"`
* `line_width` (int, default `2`) — box outline thickness

**Font sizing & layout**

* `font_mode` (str, default `"auto"`) — `"auto"` (adaptive per-box) or `"fixed"`
* `font_px` (int, default `12`) — used **only** when `font_mode="fixed"`
* `font_scale_global` (float, default `1.0`) — multiplies computed font px (easy global up/down scale)
* `min_band_px` (int, default `14`) — minimum pixels for top-band label fallback
* `min_band_px_ratio` (float, default `0.012`) — min top-band height as a fraction of image height
* `text_mode` (str, default `"short"`) — `"short"` → just the ID; `"full"` → `"<label_prefix> <id> <conf>"`
* `draw_center` (bool, default `true`) — draw a small center dot (useful for clicking)

#### Response

**200 OK (application/json)**

```json
{
  "model": "/abs/path/to/model.pt",
  "device": "mps",
  "time_ms": 37.42,
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
      "label_bbox_xyxy": [118.0, 88.0, 246.0, 112.0]
    }
  ],
  "image_base64": "data:image/png;base64,iVBORw0KGgoAAA..."  // present only if return_image=true
}
```

> Notes
>
> * `time_ms` measures **detection** latency only.
> * `label_bbox_xyxy` is the actual rectangle used to draw the ID text inside the box (present when an image was rendered).
> * `click_xy_norm` is the normalized box center (handy for UI automation clicks).
> * If there are zero detections, you still get `image_base64` when `return_image=true` (original image with no boxes).

#### Field Reference

**Top level**

* `model` — weights path used
* `device` — `"mps"` or `"cpu"`
* `time_ms` — detection time in milliseconds
* `detections[]` — list of detection objects
* `image_base64` — optional `data:image/png;base64,...` when `return_image=true`

**`detections[]` object**

* `id` — stable per-scene ID (based on `id_order`)
* `name`, `label` — `"${label_prefix} ${id}"`
* `conf` — YOLO confidence score
* `class_id` — numeric class id
* `class_name` — mapped from model names if available, else stringified id
* `bbox_xyxy` — `[x1, y1, x2, y2]` in pixels
* `bbox_xyxy_norm` — normalized `[x1/W, y1/H, x2/W, y2/H]`
* `center_xy_norm` — normalized center of the box
* `size_wh_norm` — normalized width & height
* `click_xy_norm` — normalized click target (center); always filled (even when `return_image=false`)
* `label_bbox_xyxy` — pixel rect where label was rendered (present if `return_image=true`)

---

## Error Handling

* **422 Unprocessable Entity** — FastAPI validation (e.g., bad parameter types or ranges).
* **500 Internal Server Error** — common cases:

  * No image input provided → `"No image provided"`
  * `image_url` used but `requests` not installed → `"requests is not installed; cannot fetch image_url"`
  * Invalid/unsupported image format → PIL load error

> The service does **not** crash on annotation failures; it will still return detections (without `image_base64` if rendering failed).

---

## Label Rendering Behavior (Inside-the-box)

1. Try to place the label in a **corner** inside the box (auto-shrinks font if needed).
2. If still too tight, switch to a **top semi-transparent band** inside the box (height respects `min_band_px` and `min_band_px_ratio`).
3. A small **center dot** is drawn if `draw_center=true` (default) to indicate a click target.

With `font_mode="auto"`, the base font size adapts to **box height**, **image height**, **target density**, and **text length**. You can nudge it globally with `font_scale_global`.

---

## Deployment

```bash
pip install fastapi uvicorn ultralytics pillow numpy opencv-python
# If you’ll use image_url: pip install requests
uvicorn app:app --host 0.0.0.0 --port 8000
```

* The YOLO model is loaded once at startup from `YOLO_WEIGHTS`.
* On Apple Silicon, the server prefers **MPS** (`torch.backends.mps.is_available()`), else CPU.
* Interactive docs are available at:

  * Swagger UI: `/docs`
  * ReDoc: `/redoc`

---

## Examples

**Tune thresholds & fonts**

```bash
curl -X POST "http://localhost:8000/predict?conf=0.4&iou=0.5&font_mode=fixed&font_px=16&text_mode=full&show_conf=true&return_image=true" \
  -F "image=@screen.png"
```

**Use Base64 input**

```bash
PYB64=$(base64 -w0 screen.png)
curl -X POST "http://localhost:8000/predict?return_image=true" \
  -F "image_base64=$PYB64"
```

**Stable IDs in model order**

```bash
curl -X POST "http://localhost:8000/predict?id_order=model" \
  -F "image=@frame.jpg"
```

---

## Version Notes

* **v2.2**

  * Inside-the-box label placement with smart fallback top band
  * Adaptive font sizing (`font_mode=auto`) and global scale knob
  * Stable ID assignment (`id_order`)
  * `click_xy_norm` & `label_bbox_xyxy` for UI automation alignment
