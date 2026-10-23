# YOLO Hybrid Mode Guide

## Overview

The FastAPI server now supports **hybrid YOLO execution** that can seamlessly switch between local and remote inference, providing flexibility for cloud deployment and fallback reliability.

## 🎯 **Key Features**

- ✅ **Three execution modes**: `local`, `remote`, `hybrid`
- ✅ **Dynamic mode switching** via API endpoints
- ✅ **Automatic fallback** in hybrid mode
- ✅ **LAN access support** with `--host 0.0.0.0`
- ✅ **Unified response format** across all endpoints
- ✅ **Configuration via environment variables**

## 🔧 **Configuration**

### Environment Variables

```bash
# YOLO execution mode
YOLO_MODE=local          # local|remote|hybrid (default: local)
YOLO_REMOTE_URL=         # URL of remote YOLO service
YOLO_TIMEOUT=30          # Timeout for remote requests (seconds)

# Local YOLO configuration
YOLO_WEIGHTS=/path/to/model.pt
YOLO_CONF=0.25
YOLO_IOU=0.45
YOLO_IMGSZ=1280
```

### Mode Descriptions

| Mode | Description | Use Case |
|------|-------------|----------|
| `local` | Run YOLO locally only | Development, testing, no cloud dependency |
| `remote` | Run YOLO on cloud server only | Production with cloud GPU |
| `hybrid` | Try remote first, fallback to local | Best reliability with cloud optimization |

## 🚀 **Setup Guide**

### 1. Start Server with LAN Access

```bash
source myenv/bin/activate
pip install imagehash==4.3.1 scikit-image==0.22.0
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### 2. Check Current Mode

```bash
curl http://localhost:8000/yolo/mode
```

**Response:**
```json
{
  "ok": true,
  "data": {
    "mode": "local",
    "remote_url": "",
    "timeout": 30,
    "local_model": "./weights/model.pt",
    "local_device": "mps"
  }
}
```

### 3. Switch to Hybrid Mode

```bash
curl -X POST http://localhost:8000/yolo/mode \
  -d "mode=hybrid" \
  -d "remote_url=http://your-cloud-server:8080/infer" \
  -d "timeout=15"
```

**Response:**
```json
{
  "ok": true,
  "data": {
    "mode": "hybrid",
    "remote_url": "http://your-cloud-server:8080/infer",
    "timeout": 15,
    "message": "YOLO mode changed to: hybrid"
  }
}
```

## 🌩️ **Cloud Server Setup**

### Option 1: Simple FastAPI Cloud Server

Create `cloud_yolo_server.py` on your cloud instance:

```python
from fastapi import FastAPI
from ultralytics import YOLO
import base64
import numpy as np
from PIL import Image
import io
import cv2

app = FastAPI()
model = YOLO("yolov8n.pt")  # Download automatically

@app.post("/infer")
async def infer(
    image_b64: str,
    conf: float = 0.5,
    iou: float = 0.45,
    imgsz: int = 1280,
    max_det: int = 300
):
    # Decode base64 image
    img_bytes = base64.b64decode(image_b64)
    img = Image.open(io.BytesIO(img_bytes))

    # Run YOLO inference
    results = model.predict(img, conf=conf, iou=iou,
                           imgsz=imgsz, max_det=max_det, verbose=False)[0]

    # Extract detections
    detections = []
    if results.boxes is not None:
        for box, conf_val, cls_idx in zip(results.boxes.xyxy,
                                         results.boxes.conf,
                                         results.boxes.cls):
            x1, y1, x2, y2 = box.tolist()
            detections.append({
                "label": model.names[int(cls_idx)],
                "conf": float(conf_val),
                "bbox": [x1, y1, x2-x1, y2-y1]  # x,y,w,h format
            })

    return {"detections": detections}

@app.get("/health")
async def health():
    return {"status": "ok", "model": "yolov8n.pt"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

### Deploy to Cloud

```bash
# Install dependencies on cloud server
pip install fastapi uvicorn ultralytics

# Run cloud server
python cloud_yolo_server.py
```

### Option 2: Docker Deployment

```dockerfile
# Dockerfile for cloud YOLO server
FROM ultralytics/ultralytics:latest

COPY cloud_yolo_server.py /app/
WORKDIR /app

EXPOSE 8080
CMD ["python", "cloud_yolo_server.py"]
```

## 📡 **API Endpoints**

### Core Detection Endpoints

All endpoints support the hybrid mode automatically:

```bash
# New unified detect endpoint
POST /detect
- Supports: image_b64, image_url, file upload
- Returns: candidates, selected, time_ms

# Legacy predict endpoint
POST /predict
- Backward compatible
- Uses hybrid mode internally

# Calibration and verification
POST /calibrate    # Establish baseline metrics
POST /reacquire    # Re-find moved elements
POST /verify       # Check for changes
```

### Mode Management Endpoints

```bash
# Get current YOLO configuration
GET /yolo/mode

# Change YOLO execution mode
POST /yolo/mode
- mode: local|remote|hybrid
- remote_url: URL of cloud service
- timeout: Request timeout in seconds
```

### System Information

```bash
# Get version and build info
GET /version

# Health check
GET /health
```

## 🔍 **Testing Hybrid Mode**

### 1. Test Local Mode

```bash
curl -X POST http://localhost:8000/yolo/mode -d "mode=local"

# Test detection
python -c "
import requests, base64, numpy as np
from PIL import Image
import io

# Create test image
img = np.ones((200,200,3), dtype=np.uint8) * 255
img[50:150, 50:150] = [255,0,0]  # Red square
pil_img = Image.fromarray(img)
buffer = io.BytesIO()
pil_img.save(buffer, format='PNG')
img_b64 = base64.b64encode(buffer.getvalue()).decode()

# Test detection
response = requests.post('http://localhost:8000/predict',
                        data={'image_base64': img_b64, 'conf': '0.1'})
print('Local detection result:', response.json()['time_ms'], 'ms')
"
```

### 2. Test Hybrid Mode (with Fallback)

```bash
# Set invalid remote URL to test fallback
curl -X POST http://localhost:8000/yolo/mode \
  -d "mode=hybrid" \
  -d "remote_url=http://invalid-server:8080/infer" \
  -d "timeout=5"

# Test detection - should try remote and fallback to local
python -c "
import requests, base64, numpy as np
from PIL import Image
import io

# Same test image
img = np.ones((200,200,3), dtype=np.uint8) * 255
img[50:150, 50:150] = [255,0,0]
pil_img = Image.fromarray(img)
buffer = io.BytesIO()
pil_img.save(buffer, format='PNG')
img_b64 = base64.b64encode(buffer.getvalue()).decode()

# Test hybrid detection
response = requests.post('http://localhost:8000/predict',
                        data={'image_base64': img_b64, 'conf': '0.1'})
print('Hybrid detection result:', response.json()['time_ms'], 'ms')
print('Should see fallback message in server logs')
"
```

## 🌐 **LAN Access Verification**

### Find Your IP Address

```bash
# macOS/Linux
ifconfig | grep "inet " | grep -v 127.0.0.1

# Windows
ipconfig | findstr "IPv4"
```

### Test from Another Device

```bash
# Replace with your actual IP
curl http://192.168.1.113:8000/health
curl http://192.168.1.113:8000/yolo/mode
```

## 📊 **Performance Comparison**

| Mode | Pros | Cons | Best For |
|------|------|------|----------|
| **Local** | No network latency, privacy, offline | Limited by local GPU/CPU | Development, sensitive data |
| **Remote** | Powerful cloud GPU, scalable | Network dependency, latency | Production, heavy workloads |
| **Hybrid** | Best reliability, cloud optimization | Complexity, fallback delay | Production with reliability |

## 🔧 **Troubleshooting**

### Common Issues

**1. Server not accessible from LAN**
```bash
# Ensure server is bound to 0.0.0.0, not 127.0.0.1
netstat -an | grep 8000
# Should show: *.8000 LISTEN, not 127.0.0.1.8000
```

**2. Remote inference timeouts**
```bash
# Increase timeout for slow cloud servers
curl -X POST http://localhost:8000/yolo/mode -d "mode=hybrid" -d "timeout=60"
```

**3. Missing dependencies**
```bash
pip install imagehash==4.3.1 scikit-image==0.22.0
```

**4. CORS issues from web clients**
- CORS is already configured for `*` origins
- Check browser developer tools for actual error

### Logs and Debugging

```bash
# Check server logs for hybrid mode messages
tail -f server_logs

# Look for these messages:
# [YOLO] Attempting remote inference: http://...
# [YOLO] Remote inference failed (...), falling back to local
```

## 🎯 **Production Deployment Checklist**

- [ ] Cloud YOLO server deployed and accessible
- [ ] Environment variables configured
- [ ] Health checks passing on both local and remote
- [ ] Hybrid mode tested with real workloads
- [ ] Monitoring and alerting set up
- [ ] Backup local models available
- [ ] Network security configured (VPN, firewalls)
- [ ] Load balancing configured (if multiple cloud instances)

## 🔗 **Related Files**

- `app.py` - Main FastAPI server with hybrid support
- `vision_utils.py` - Image processing utilities
- `.env.example` - Configuration examples
- `tests/test_detect_minimum.py` - API tests
- `requirements.txt` - Updated dependencies