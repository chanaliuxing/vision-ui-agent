# Model Weights Directory / 模型权重目录

This directory stores the YOLO UI element detection weights.

## Obtaining Weights / 获取权重

By default, the server looks for `weights/model.pt` (configurable via `YOLO_WEIGHTS` in `.env`).

You can use the OmniParser v2 icon detection model or fine-tuned YOLOv8/v11 UI element detector:

```bash
# Automatically download weights using the provided script:
bash scripts/download_weights.sh
```

Or manually download from Hugging Face:
- Repository: [microsoft/OmniParser-v2.0](https://huggingface.co/microsoft/OmniParser-v2.0)
- Target file: `icon_detect/model.pt` -> place as `weights/model.pt`
