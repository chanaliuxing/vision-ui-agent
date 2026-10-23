from ultralytics import YOLO
import os

IMG = "./s1.png"
OUT = "./1_out.png"
MODEL = "./weights/model.pt"
MODEL = "./weights/best.pt"

# 选一款系统自带字体（中文环境更稳），可按需调整顺序/路径
FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",        # macOS 中文字体
    "/Library/Fonts/Arial Unicode.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]
FONT = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)

# 推荐的可读字号区间（像素）
MIN_PX, MAX_PX = 18, 24
RATIO = 0.028  # 默认按短边的 2.8%，可调 0.025–0.032

model = YOLO(MODEL)
results = model.predict(source=IMG, line_width=1, verbose=False)

for i, r in enumerate(results):
    h, w = r.orig_img.shape[:2]
    fs = max(MIN_PX, min(MAX_PX, int(min(h, w) * RATIO)))  # 取整，锁区间

    out = OUT if len(results) == 1 else OUT.replace(".png", f"_{i}.png")

    # 只用官方 API：Results.save(...) -> 内部调用 plot(...)
    kwargs = dict(
        line_width=1,
        labels=True,   # 显示类别
        conf=True,     # 显示数字（置信度）
        font_size=fs,  # 关键：整数像素
        pil=True       # 用 PIL 文本渲染，字号/中文更可靠
    )
    if FONT:
        kwargs["font"] = FONT

    r.save(filename=out, **kwargs)

print("Saved:", OUT)
