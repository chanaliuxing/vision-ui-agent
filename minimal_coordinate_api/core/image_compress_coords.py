"""
Image compression with coordinate mapping for VLM processing
Copied from main project to keep token/size reduction and coordinate transforms.
"""
from dataclasses import dataclass, asdict
from typing import Optional, Tuple, Dict, Any
from PIL import Image, ImageFilter
import json
import io
import os

@dataclass
class Transform:
    orig_w: int
    orig_h: int
    crop_x: int = 0
    crop_y: int = 0
    crop_w: Optional[int] = None
    crop_h: Optional[int] = None
    resized_w: int = 0
    resized_h: int = 0
    sx: float = 1.0
    sy: float = 1.0
    dpr: float = 1.0
    note: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

def _compute_new_size(w: int, h: int, long_side: int) -> Tuple[int, int]:
    if max(w, h) <= long_side:
        return w, h
    scale = float(long_side) / float(max(w, h))
    return max(1, int(round(w * scale))), max(1, int(round(h * scale)))

def _save_under_size(im: Image.Image, path_out: str, fmt: str, quality: int = 85,
                     target_kb: Optional[int] = None) -> None:
    fmt = fmt.upper()
    if target_kb is None or fmt == "PNG":
        if fmt == "PNG":
            im.save(path_out, format="PNG", optimize=True)
        elif fmt == "JPEG":
            im.save(path_out, format="JPEG", quality=quality, subsampling=0, optimize=True)
        else:  # WEBP
            im.save(path_out, format="WEBP", quality=quality, method=6)
        return

    lo, hi = 50, min(95, quality)
    best_buf = None
    while lo <= hi:
        mid = (lo + hi) // 2
        buf = io.BytesIO()
        if fmt == "JPEG":
            im.save(buf, format="JPEG", quality=mid, subsampling=0, optimize=True)
        else:
            im.save(buf, format="WEBP", quality=mid, method=6)
        size_kb = len(buf.getvalue()) / 1024.0
        if size_kb <= target_kb:
            best_buf = buf
            lo = mid + 1
        else:
            hi = mid - 1
    if best_buf is None:
        best_buf = io.BytesIO()
        if fmt == "JPEG":
            im.save(best_buf, format="JPEG", quality=50, subsampling=0, optimize=True)
        else:
            im.save(best_buf, format="WEBP", quality=50, method=6)

    with open(path_out, "wb") as f:
        f.write(best_buf.getvalue())

def compress_for_vlm(
    input_path: str,
    output_path: str,
    *,
    roi: Optional[Tuple[int, int, int, int]] = None,
    long_side: Optional[int] = 1280,
    pre_blur_sigma: float = 0.4,
    usm_radius: float = 1.2,
    usm_percent: int = 130,
    usm_threshold: int = 3,
    fmt: str = "WEBP",
    quality: int = 85,
    target_kb: Optional[int] = None,
    device_pixel_ratio: float = 1.0,
    write_sidecar_json: bool = True,
) -> Transform:
    im = Image.open(input_path).convert("RGB")
    Ow, Oh = im.size

    cx, cy, cw, ch = 0, 0, Ow, Oh
    if roi is not None:
        x, y, w, h = roi
        x = max(0, min(x, Ow - 1))
        y = max(0, min(y, Oh - 1))
        w = max(1, min(w, Ow - x))
        h = max(1, min(h, Oh - y))
        im = im.crop((x, y, x + w, y + h))
        cx, cy, cw, ch = x, y, w, h
    else:
        w, h = im.size

    if long_side is not None:
        new_w, new_h = _compute_new_size(w, h, long_side)
        if (new_w, new_h) != (w, h):
            im = im.filter(ImageFilter.GaussianBlur(pre_blur_sigma))
            im = im.resize((new_w, new_h), Image.LANCZOS)
            im = im.filter(ImageFilter.UnsharpMask(radius=usm_radius, percent=usm_percent, threshold=usm_threshold))
        else:
            new_w, new_h = w, h
    else:
        new_w, new_h = w, h

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    _save_under_size(im, output_path, fmt=fmt, quality=quality, target_kb=target_kb)

    sx = new_w / float(cw)
    sy = new_h / float(ch)

    tf = Transform(
        orig_w=Ow, orig_h=Oh,
        crop_x=cx, crop_y=cy, crop_w=cw, crop_h=ch,
        resized_w=new_w, resized_h=new_h,
        sx=sx, sy=sy,
        dpr=device_pixel_ratio,
        note=f"ROI={'full' if roi is None else (cx,cy,cw,ch)}, long_side={long_side}, fmt={fmt}, target_kb={target_kb}"
    )

    if write_sidecar_json:
        with open(output_path + ".json", "w", encoding="utf-8") as f:
            f.write(tf.to_json())

    return tf

def map_point_back(xp: float, yp: float, tf: Transform) -> Tuple[float, float]:
    x_local = xp / tf.sx
    y_local = yp / tf.sy
    x = tf.crop_x + x_local
    y = tf.crop_y + y_local
    if tf.dpr != 1.0:
        x /= tf.dpr
        y /= tf.dpr
    return x, y

def map_bbox_back(xp: float, yp: float, wp: float, hp: float, tf: Transform) -> Tuple[float, float, float, float]:
    x0, y0 = map_point_back(xp, yp, tf)
    w0 = wp / tf.sx / (tf.dpr if tf.dpr != 1.0 else 1.0)
    h0 = hp / tf.sy / (tf.dpr if tf.dpr != 1.0 else 1.0)
    return x0, y0, w0, h0

def compress_cv2_image(img_bgr, output_path: str, **kwargs) -> Transform:
    import cv2
    import tempfile

    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        cv2.imwrite(tmp.name, img_bgr)
        temp_path = tmp.name

    try:
        transform = compress_for_vlm(temp_path, output_path, **kwargs)
        return transform
    finally:
        try:
            os.unlink(temp_path)
        except:
            pass
