"""
Image compression with coordinate mapping for VLM processing
压缩图像用于视觉语言模型，支持精确坐标反投影
"""
from dataclasses import dataclass, asdict
from typing import Optional, Tuple, Dict, Any
from PIL import Image, ImageFilter
import json
import io
import os

@dataclass
class Transform:
    # 原图尺寸
    orig_w: int
    orig_h: int
    # 如果有 ROI 裁剪：在原图上的矩形
    crop_x: int = 0
    crop_y: int = 0
    crop_w: Optional[int] = None
    crop_h: Optional[int] = None
    # 实际缩放后尺寸（用于精确 scale 计算，避免四舍五入误差）
    resized_w: int = 0
    resized_h: int = 0
    # 等比缩放系数（记录真实值，x/y 分别算，通常相等）
    sx: float = 1.0
    sy: float = 1.0
    # 设备像素比（Retina/高DPI 可用；若点击用逻辑坐标，需再除以 dpr）
    dpr: float = 1.0
    # 说明
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
    """
    保存为 PNG/JPEG/WebP。
    - 若 target_kb 指定（如 100），对 JPEG/WebP 做质量二分搜索，保证 <= target_kb。
    - PNG 无损但通常更大，不做体积逼近。
    """
    fmt = fmt.upper()
    if target_kb is None or fmt == "PNG":
        if fmt == "PNG":
            im.save(path_out, format="PNG", optimize=True)
        elif fmt == "JPEG":
            im.save(path_out, format="JPEG", quality=quality, subsampling=0, optimize=True)
        else:  # WEBP
            im.save(path_out, format="WEBP", quality=quality, method=6)
        return

    # 仅对 JPEG/WebP 做体积控制
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
            lo = mid + 1  # 试试更高质量
        else:
            hi = mid - 1  # 压得更狠
    if best_buf is None:
        # 退而求其次，用最小质量
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
    # ROI：在原图坐标系下的矩形 (x,y,w,h)。不传则全图。
    roi: Optional[Tuple[int, int, int, int]] = None,
    # 等比缩放的"最长边"阈值；不想缩放可传 None
    long_side: Optional[int] = 1280,
    # 画质/清晰度：先轻微去锯齿再锐化
    pre_blur_sigma: float = 0.4,
    usm_radius: float = 1.2,
    usm_percent: int = 130,
    usm_threshold: int = 3,
    # 输出格式与体积控制
    fmt: str = "WEBP",     # "PNG"/"JPEG"/"WEBP"
    quality: int = 85,
    target_kb: Optional[int] = None,  # 例如 100 -> 压到 ≤100KB
    # 高DPI设备像素比（若你的点击 API 用"逻辑坐标"，需要用它做一次换算）
    device_pixel_ratio: float = 1.0,
    # 是否输出同名 .json 记录变换
    write_sidecar_json: bool = True,
) -> Transform:
    """
    压缩用于 LLM 视觉识别的图片，并返回/记录变换参数（用于坐标映射）。
    - 先按 ROI 裁剪（若提供），再等比缩放（若提供 long_side）。
    - 保存时可选强约束到 target_kb（仅JPEG/WebP），与 token 无关，仅为传输成本。
    """
    im = Image.open(input_path).convert("RGB")
    Ow, Oh = im.size

    # 裁剪阶段（不做 letterbox）
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

    # 轻微预模糊，防止缩小时细字锯齿；再用 Lanczos 下采样
    if long_side is not None:
        new_w, new_h = _compute_new_size(w, h, long_side)
        if (new_w, new_h) != (w, h):
            im = im.filter(ImageFilter.GaussianBlur(pre_blur_sigma))
            im = im.resize((new_w, new_h), Image.LANCZOS)
            # 反锐化，恢复边缘
            im = im.filter(ImageFilter.UnsharpMask(radius=usm_radius, percent=usm_percent, threshold=usm_threshold))
        else:
            new_w, new_h = w, h
    else:
        new_w, new_h = w, h  # 不缩放

    # 保存图片（可选 ≤target_kb）
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    _save_under_size(im, output_path, fmt=fmt, quality=quality, target_kb=target_kb)

    # 精确 scale（基于实际像素）
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

# —— 坐标映射 —— #
def map_point_back(xp: float, yp: float, tf: Transform) -> Tuple[float, float]:
    """
    将 LLM 在"压缩后图像坐标系"返回的点 (xp,yp) 反投影回原图坐标系 (x,y)。
    如果你的点击 API 使用逻辑坐标（高DPI下非像素），再除以 tf.dpr。
    """
    # 压缩图 -> 裁剪前局部原图
    x_local = xp / tf.sx
    y_local = yp / tf.sy
    # 局部原图 -> 全局原图
    x = tf.crop_x + x_local
    y = tf.crop_y + y_local
    # 若需要逻辑坐标（例如 macOS Retina 点击库用点而非像素）
    if tf.dpr != 1.0:
        x /= tf.dpr
        y /= tf.dpr
    return x, y

def map_bbox_back(xp: float, yp: float, wp: float, hp: float, tf: Transform) -> Tuple[float, float, float, float]:
    """
    反投影边框 (xp,yp,wp,hp)，同理。
    """
    x0, y0 = map_point_back(xp, yp, tf)
    w0 = wp / tf.sx / (tf.dpr if tf.dpr != 1.0 else 1.0)
    h0 = hp / tf.sy / (tf.dpr if tf.dpr != 1.0 else 1.0)
    return x0, y0, w0, h0

def compress_cv2_image(img_bgr, output_path: str, **kwargs) -> Transform:
    """
    对OpenCV图像(BGR格式)进行压缩，兼容现有代码
    """
    import cv2
    import tempfile

    # 保存为临时文件
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        cv2.imwrite(tmp.name, img_bgr)
        temp_path = tmp.name

    try:
        # 调用主压缩函数
        transform = compress_for_vlm(temp_path, output_path, **kwargs)
        return transform
    finally:
        # 清理临时文件
        try:
            os.unlink(temp_path)
        except:
            pass