import cv2
import supervision as sv
from inference import get_model
from dotenv import load_dotenv
import os

# 加载 .env 文件
load_dotenv()

# 从 .env 获取 key
api_key = os.getenv("ROBOFLOW_API_KEY")

if not api_key:
    raise ValueError("❌ 没有找到 ROBOFLOW_API_KEY，请检查 .env 文件")

# 正确的 model_id
model = get_model(model_id="wechatui02/2", api_key=api_key)

# 输入图片路径
image_path = "./s3.png"
image = cv2.imread(image_path)

# 执行推理
results = model.infer(image)[0]

# 转换为 supervision 的 detections
detections = sv.Detections.from_inference(results)

# 绘制检测结果
box_annotator = sv.BoxAnnotator()
label_annotator = sv.LabelAnnotator()

annotated = box_annotator.annotate(scene=image, detections=detections)
annotated = label_annotator.annotate(scene=annotated, detections=detections)

# 保存到桌面
output_path = "./1_detected.png"
cv2.imwrite(output_path, annotated)

print(f"✅ 检测完成，结果已保存到: {output_path}")
