"""
OmniParser v2 风格（细字体版、免参数）
- 默认用 Supervision 的默认调色板取色（与 OmniParser v2 一致）
- 字体粗细 TEXT_THICKNESS=1（很细）
- 字号 desktop 档更小（TEXT_SCALE≈0.26），可在 CONFIG 调
- 标签底色半透明，不遮字

运行：
  source ~/yolovenv/bin/activate
  python yolo_omni_style.py

依赖（已装可跳过）：
  pip install ultralytics opencv-python supervision
"""

from ultralytics import YOLO
import cv2
import os

# ------------------ 只改这里 ------------------
class CONFIG:
    MODEL_PATH = "./weights/model.pt"
    SOURCE_PATH = "./s1.png"
    OUT_PATH = None  # None -> 自动在 SOURCE 同目录生成 *_omni.png

    MODE = "desktop"        # "desktop"（小字）或 "mobile"（大一点）
    LINE_THICKNESS = 3      # 框线粗细
    TEXT_THICKNESS = 1      # ✅ 字体粗细（越小越细）
    TEXT_PADDING = 8        # 标签内边距（像素）
    TEXT_SCALE = None       # None 用模式默认；或自己写 0.20/0.26/0.5 等
    LABEL_BG_ALPHA = 0.55   # 标签底色透明度（0~1，越小越透明）
# ------------------------------------------------

# 可选：Supervision 调色板（与 OmniParser v2 一致）
try:
    import supervision as sv
    _USE_SV = True
except Exception:
    _USE_SV = False

def _default_out_path(src_path: str) -> str:
    root, ext = os.path.splitext(src_path)
    return f"{root}_omni{ext}"

def get_palette_color_bgr(index: int):
    """按类别取色（BGR）。优先用 Supervision 默认调色板。"""
    if _USE_SV:
        color = sv.ColorPalette.DEFAULT.by_idx(index)  # RGB
        r, g, b = color.as_rgb()
        return (b, g, r)
    # 没装 supervision 的兜底配色（BGR）
    fallback = [
        (40, 170, 255), (80, 200, 120), (240, 180, 70), (230, 110, 90),
        (200, 80, 200), (90, 220, 240), (90, 90, 240), (180, 180, 60)
    ]
    return fallback[index % len(fallback)]

def luminance_rgb(r, g, b):
    return 0.299 * r + 0.587 * g + 0.114 * b  # 0~255

def draw_rect_alpha(img, p1, p2, color_bgr, alpha):
    """画半透明矩形（作为标签底色）。"""
    overlay = img.copy()
    cv2.rectangle(overlay, p1, p2, color_bgr, thickness=cv2.FILLED)
    return cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)

def draw_omni_style(
    img,
    boxes_xyxy, classes, confs, class_names,
    thickness=3, text_scale=0.26, text_thickness=1, text_padding=8, label_bg_alpha=0.55
):
    font = cv2.FONT_HERSHEY_SIMPLEX

    for i, box in enumerate(boxes_xyxy):
        x1, y1, x2, y2 = map(int, box)
        cls_id = int(classes[i]) if classes is not None else i
        conf = float(confs[i]) if confs is not None else 1.0

        color_bgr = get_palette_color_bgr(cls_id)
        color_rgb = (color_bgr[2], color_bgr[1], color_bgr[0])

        # 框
        cv2.rectangle(img, (x1, y1), (x2, y2), color_bgr, thickness)

        # 文本
        cls_name = class_names.get(cls_id, str(cls_id))
        label = f"{cls_name} {conf:.2f}"

        (tw, th), _ = cv2.getTextSize(label, font, fontScale=text_scale, thickness=text_thickness)

        # 标签放框外左上，溢出就放框内顶部
        tx = x1 + text_padding
        ty = y1 - text_padding
        bg_x1 = x1
        bg_y1 = y1 - (2 * text_padding + th)
        bg_x2 = x1 + (2 * text_padding + tw)
        bg_y2 = y1
        if bg_y1 < 0:
            ty = y1 + text_padding + th
            bg_y1 = y1
            bg_y2 = y1 + (2 * text_padding + th)

        # 半透明底色（同框色），不会糊字
        img = draw_rect_alpha(img, (bg_x1, bg_y1), (bg_x2, bg_y2), color_bgr, label_bg_alpha)

        # 亮度自适应：底色亮 -> 黑字；底色暗 -> 白字
        L = luminance_rgb(*color_rgb)
        text_color = (0, 0, 0) if L > 160 else (255, 255, 255)

        # 细字体 + 抗锯齿
        cv2.putText(img, label, (tx, ty), font, text_scale, text_color, text_thickness, cv2.LINE_AA)

    return img

def main():
    cfg = CONFIG
    # 桌面/移动档的默认字号（更细更小）
    if cfg.TEXT_SCALE is None:
        text_scale = 0.26 if cfg.MODE.lower() == "desktop" else 0.48
    else:
        text_scale = float(cfg.TEXT_SCALE)

    img = cv2.imread(cfg.SOURCE_PATH)
    if img is None:
        raise FileNotFoundError(f"找不到图片：{cfg.SOURCE_PATH}")

    model = YOLO(cfg.MODEL_PATH)
    results = model.predict(source=cfg.SOURCE_PATH, verbose=False)
    r = results[0]
    boxes = r.boxes

    out_path = cfg.OUT_PATH or _default_out_path(cfg.SOURCE_PATH)
    if boxes is None or len(boxes) == 0:
        cv2.imwrite(out_path, img)
        print(f"无检测结果，已保存：{out_path}")
        return

    boxes_xyxy = boxes.xyxy.cpu().numpy()
    classes = boxes.cls.cpu().numpy() if boxes.cls is not None else None
    confs = boxes.conf.cpu().numpy() if boxes.conf is not None else None
    class_names = r.names

    vis = draw_omni_style(
        img.copy(),
        boxes_xyxy, classes, confs, class_names,
        thickness=cfg.LINE_THICKNESS,
        text_scale=text_scale,
        text_thickness=cfg.TEXT_THICKNESS,   # ✅ 这里设为 1，字会非常细
        text_padding=cfg.TEXT_PADDING,
        label_bg_alpha=cfg.LABEL_BG_ALPHA
    )

    cv2.imwrite(out_path, vis)
    print(f"✅ 已保存：{out_path}")

if __name__ == "__main__":
    main()
