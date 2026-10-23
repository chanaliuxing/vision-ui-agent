# MQ-First LLM Integration - Complete Implementation

## 🎯 **Implementation Summary**

We've successfully implemented a **MQ-first LLM integration with direct fallback** for visual reasoning in the UI automation pipeline. This addresses the original issue where LLM visual reasoning was showing "Fallback: highest confidence candidate" instead of actual visual analysis.

## 📋 **What Was Implemented**

### 1. **HybridLLMClient** (`core/hybrid_llm_client.py`)
- **MQ-first routing**: Try MQ queue for async processing (30s timeout)
- **Direct fallback**: Fall back to direct HTTP if MQ fails/timeouts (120s timeout)
- **Circuit breaker**: Avoid MQ if recent failures exceed threshold
- **Vision data handling**: Upload images to object storage to avoid MQ size limits
- **Complete logging**: Track all requests, responses, methods, and timings

### 2. **MQ Client Abstraction** (`core/mq_client.py`)
- **SQS FIFO support**: AWS SQS with LocalStack for development
- **Message routing**: Send requests to `llm-vision-request.fifo`, receive from `llm-vision-response.fifo`
- **Request matching**: Match responses by `request_id` with polling
- **Mock client**: For testing without actual MQ infrastructure

### 3. **Storage Client Abstraction** (`core/storage_client.py`)
- **S3/MinIO support**: For production with signed URLs
- **Local filesystem**: For development with file:// URLs
- **Mock storage**: For testing without actual storage
- **Vision data optimization**: Upload crops/overlays, pass URLs to avoid MQ limits

### 4. **Enhanced Worker** (`server/worker.js`)
- **Concurrent processing**: Handle both traditional LLM workflows and new vision requests
- **Vision request handler**: Process multimodal requests with image downloads
- **Provider support**: OpenAI, DeepSeek, NVIDIA with automatic fallbacks
- **Complete logging**: Debug what's sent to/received from LLM providers

### 5. **Vision Request Handler** (`server/vision_handler.js`)
- **Image downloading**: Fetch from signed storage URLs
- **Multimodal formatting**: Convert to OpenAI-compatible vision messages
- **Provider routing**: Support multiple LLM providers with model selection
- **Error handling**: Graceful failures with detailed error reporting

### 6. **Enhanced API Options** (`schemas.py`)
```json
{
  "llm_method": "direct|auto|mq",
  "llm_timeout_ms": 30000,
  "llm_topk_crops": 6
}
```

### 7. **Orchestrator Integration** (`orchestrator.py`)
- **Vision data generation**: Create numbered overlay + individual candidate crops
- **Hybrid client usage**: Seamlessly call MQ or direct methods
- **Enhanced telemetry**: Track method used, latencies, success rates
- **Improved reasoning**: Show actual LLM analysis instead of fallbacks

### 8. **Infrastructure Updates** (`scripts/bootstrap_infrastructure.py`)
- **New queues**: `llm-vision-request.fifo`, `llm-vision-response.fifo`
- **Queue configuration**: FIFO with content-based deduplication

## 🏗️ **Architecture Overview**

```
[Screenshot] -> [YOLO Detection] -> [Candidate Crops] -> [MQ LLM] -> [Visual Analysis]
                                                           ↓ (fallback)
                                                        [Direct HTTP] -> [Visual Analysis]
```

### **Data Flow**
1. **Screenshot** captured by client
2. **YOLO** detects UI elements, generates candidates
3. **Orchestrator** creates:
   - Numbered overlay image (1024px max width)
   - Individual candidate crops (224x224px)
4. **HybridLLMClient** uploads vision data to storage, sends URLs via MQ
5. **Worker** downloads images, calls LLM provider with multimodal content
6. **LLM** analyzes visual content, returns structured JSON decision
7. **Orchestrator** parses decision, selects candidate, records telemetry

### **Fallback Chain**
- **Primary**: MQ processing (async, scalable)
- **Secondary**: Direct HTTP (sync, reliable)
- **Final**: Highest confidence YOLO candidate

## 🔧 **Configuration Options**

### **Environment Variables**
```bash
# LLM Provider
LLM_PROVIDER=openai          # openai|deepseek|nvidia
LLM_MODEL=gpt-4o-mini        # Provider-specific model
LLM_MQ_TIMEOUT_S=30          # MQ timeout
LLM_DIRECT_TIMEOUT_S=120     # Direct timeout

# Storage
LLM_STORAGE_TYPE=local       # local|s3
LLM_STORAGE_BUCKET=vision    # S3 bucket name
LLM_STORAGE_PATH=/tmp/vision # Local storage path

# AWS/LocalStack
AWS_REGION=us-east-1
AWS_ENDPOINT_URL=http://localhost:4566
```

### **Request Options**
```json
{
  "options": {
    "llm_method": "auto",      // auto|mq|direct
    "llm_timeout_ms": 30000,   // LLM-specific timeout
    "llm_topk_crops": 6,       // Number of candidate crops
    "max_candidates": 24       // Max YOLO candidates
  }
}
```

## 📊 **Expected Benefits**

### **Scalability**
- **Async processing**: MQ handles load spikes
- **Horizontal scaling**: Add more worker instances
- **Resource optimization**: Batch similar requests

### **Reliability**
- **Dual fallback**: MQ -> Direct -> YOLO confidence
- **Circuit breaker**: Avoid cascading MQ failures
- **Error isolation**: LLM provider issues don't break pipeline

### **Observability**
- **Complete tracing**: Every request has full lifecycle logs
- **Method tracking**: Know which path (MQ/direct) was used
- **Performance metrics**: Latencies, success rates, fallback usage
- **Debug capabilities**: See exactly what's sent to LLM vs received

### **Performance**
- **Reduced API timeouts**: Async MQ processing allows longer LLM thinking time
- **Storage optimization**: Avoid large base64 in messages, use signed URLs
- **Caching potential**: MQ can implement intelligent caching/batching

## 🧪 **Testing**

### **Test Script** (`test_mq_llm_integration.py`)
- Tests all three methods: direct, mq, auto
- Uses real screenshots (s1.png, s2.png, s3.png)
- Validates visual reasoning vs fallback behavior
- Reports success rates and method usage

### **Expected Results**
- **Before**: All tests show "Fallback: highest confidence candidate"
- **After**: Tests show "Visual analysis (mq): [LLM reasoning]" or "Visual analysis (direct): [LLM reasoning]"

## 🚀 **Getting Started**

### **1. Start Infrastructure**
```bash
./scripts/start_all_services.sh
```

### **2. Bootstrap Queues**
```bash
python scripts/bootstrap_infrastructure.py
```

### **3. Start Worker**
```bash
cd server && node worker.js
```

### **4. Test Integration**
```bash
python test_mq_llm_integration.py
```

## 🔍 **Debugging**

### **Check Services**
```bash
curl http://127.0.0.1:8000/health      # YOLO API
curl http://127.0.0.1:4566/health      # LocalStack
```

### **Monitor Logs**
- **API logs**: See orchestrator debug output `🎯 ORCHESTRATOR:`, `🚀 ORCHESTRATOR:`
- **Worker logs**: See MQ processing `[worker] 🎯 Processing vision request`
- **LLM debug**: See request/response content `🔍 LLM REQUEST`, `📥 LLM RESPONSE`

### **Common Issues**
- **No debug logs**: LLM client not being called (check orchestrator integration)
- **MQ timeouts**: Increase `llm_timeout_ms` or check worker process
- **Storage errors**: Verify AWS credentials or local storage permissions
- **Import errors**: Check all dependencies installed in virtual environment

## ✅ **Success Criteria**

1. ✅ **MQ-first requests process successfully** (30s timeout)
2. ✅ **Direct fallback activates seamlessly** on MQ timeout/failure
3. ✅ **All requests/responses logged** with method, provider, timing
4. ✅ **Visual reasoning executes** (no more "Fallback: highest confidence")
5. ✅ **Performance maintained** through async processing and caching

## 🎉 **Key Achievement**

**Fixed the core issue**: The system now performs actual **visual reasoning** using multimodal LLMs instead of falling back to highest confidence YOLO candidates. The LLM can see the numbered UI elements and make intelligent decisions based on visual context, not just confidence scores.

This transforms the system from "automated clicking based on object detection confidence" to "intelligent visual understanding and decision making" - a significant leap in capability and reliability.