# LLM Client 集成与开发指南

本文档详细记录了本项目中使用的统一 LLM Client (`core/llm_client.py` 及相关模块) 的使用方法，涵盖本地 (Ollama) 和云端 (Gemini, OpenAI, DeepSeek, NVIDIA) 的配置与差异。旨在帮助开发者在其他项目中快速集成此能力。

## 1. 核心架构概览

本项目采用了一个统一的抽象层 (`core/llm_client.py`) 来屏蔽不同 LLM 提供商的差异。

*   **入口函数**: `call_llm(...)` 和 `generate_json(...)`
*   **统一输入**: 支持 Gemini 风格的 `messages` 结构（包含 text/inline_data parts），内部会自动转换为 OpenAI 格式。
*   **统一视觉**: 支持传入 `image_path`，内部自动处理 Base64 编码和压缩（WebP）。

## 2. 快速开始 (Quick Start)

### 2.1 基础调用代码

```python
from core.llm_client import LLMClient, generate_json

# 方式 1: 使用 LLMClient 类 (推荐)
client = LLMClient(provider="ollama", model="qwen2.5vl:latest")
messages = [{"role": "user", "parts": [{"text": "描述这张图片"}]}]
response = client.generate_response(messages, image_path="s1.png")
print(response)

# 方式 2: 直接调用静态函数 (用于一次性脚本)
# 自动读取 .env 配置中的 LLM_PROVIDER 和 LLM_MODEL
result_json = generate_json(
    messages=[{"role": "user", "parts": [{"text": "返回 JSON 格式的图片分析"}]}],
    image_path="s1.png"
)
print(result_json)
```

### 2.2 统一消息格式 (Gemini Style)

为了最大程度兼容多模态，内部推荐使用如下格式：

```python
messages = [
    {
        "role": "user", 
        "parts": [
            {"text": "文本提示词"},
            # 图片可自动通过 image_path 参数注入，无需手动构造 inline_data
        ]
    }
]
```

---

## 3. 本地 LLM (Ollama)

适用于低延迟、隐私敏感或离线场景。

### 3.1 配置 (.env)

```bash
LLM_PROVIDER=ollama
# 推荐视觉模型
LLM_MODEL=qwen2.5vl:latest 
# 默认地址
OLLAMA_BASE_URL=http://127.0.0.1:11434
# 超时时间 (首次加载模型可能需要较长时间)
OLLAMA_TIMEOUT_S=120
```

### 3.2 调用特征

*   **API 路径**: `/api/chat`
*   **输入转换**: 内部会将 Gemini 格式转换为 Ollama 的 `{"images": ["base64..."]}` 格式。
*   **返回结构**: 经过封装的统一字典。
    ```json
    {
      "ok": true,
      "provider": "ollama",
      "model": "qwen2.5vl:latest",
      "content": "图片描述内容...",
      "parsed": {...}, // 尝试解析的 JSON 对象
      "raw": {...},    // Ollama 原始响应
      "method_used": "direct_ollama"
    }
    ```
*   **注意事项**: 
    *   **冷启动慢**: 首次请求可能超时 (`llm_failed`)，建议将超时设置为 300s 以上。
    *   **并发限制**: 本地 GPU 显存有限，并发请求可能导致排队。

---

## 4. 云端 LLM (Gemini, OpenAI, DeepSeek, NVIDIA)

适用于高智能、复杂推理场景。

### 4.1 Gemini (Google)

*   **配置**:
    ```bash
    LLM_PROVIDER=gemini
    LLM_MODEL=gemini-1.5-flash
    GEMINI_API_KEY=AIzaSy...
    ```
*   **特征**: 
    *   原生支持 `parts` 结构，无需转换。
    *   **返回**: 原始 Google API JSON (`GenerateContentResponse`)。
    *   **提取内容**: 需检查 `candidates[0].content.parts[0].text`。

### 4.2 OpenAI / DeepSeek / NVIDIA

这三者均使用 OpenAI 兼容接口。

*   **配置**:
    ```bash
    # OpenAI
    LLM_PROVIDER=openai
    LLM_MODEL=gpt-4o-mini
    OPENAI_API_KEY=sk-...

    # DeepSeek
    LLM_PROVIDER=deepseek
    LLM_MODEL=deepseek-chat
    DEEPSEEK_API_KEY=sk-...
    DEEPSEEK_API_URL=https://api.deepseek.com/v1

    # NVIDIA
    LLM_PROVIDER=nvidia
    LLM_MODEL=nvidia/llama-3.1-nemotron-70b-instruct
    NVIDIA_API_KEY=nvapi-...
    NVIDIA_API_URL=https://integrate.api.nvidia.com/v1/chat/completions
    ```
*   **特征**:
    *   **输入转换**: 内部自动将 Gemini 的 `parts` 转换为 OpenAI 的 `content: [{"type": "text"}, {"type": "image_url"}]`。
    *   **图片压缩**: 代码包含 `_encode_image_file_for_llm` 逻辑，会自动将大图转为 WebP 以节省 Token。
    *   **返回**: 标准 OpenAI `chat.completion` 对象。
    *   **提取内容**: 需检查 `choices[0].message.content`。

---

## 5. 推理模型 (Reasoning Models) 特殊处理

**DeepSeek-R1** 及其他推理模型 (Reasoning Models) 的输出格式与其他模型显著不同。

### 5.1 `<think>` 标签

DeepSeek 系列（包括本地 Ollama 运行的 `deepseek-r1` 和云端 API）通常会在返回的 `content` 中包含思维链 (Chain of Thought)：

```text
<think>
Here is my reasoning process:
1. Analyze the user request...
2. Identify the image content...
</think>
Here is the final answer.
```

### 5.2 处理建议

1.  **如果你只需要最终答案**:
    *   需要编写代码移除 `<think>...</think>` 标签及其内容。
    *   本项目的 `parse_first_json` 辅助函数使用正则 `\{[\s\S]*\}` 查找 JSON，通常能自动跳过 `<think>` 部分，**前提是 JSON 在 think 标签之后**。
    
2.  **如果你需要 JSON**:
    *   **不要**直接使用 `json.loads(response.text)`，因为开头可能是 `<think>`。
    *   **推荐**: 使用 regex 提取 JSON 部分。

    ```python
    import re
    import json
    
    content = response["content"] # 包含 <think>...
    
    # 移除 <think> 块 (可选)
    content_clean = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    
    # 提取 JSON
    match = re.search(r'\{[\s\S]*\}', content)
    if match:
        data = json.loads(match.group(0))
    ```

---

## 6. 关键差异与迁移指南

在不同项目中复用此 Client 时，注意以下差异：

| 特性 | 本地 (Ollama) | 云端 (OpenAI/Gemini等) | DeepSeek / Reasoning |
| :--- | :--- | :--- | :--- |
| **视觉能力** | 依赖模型 (qwen2.5vl 可用, llama3 不可用) | Gemini/GPT-4o 极强 | 纯文本模型不可用 (需用 VL 版本) |
| **响应格式** | 封装后的 `{ok: true, content: ...}` | 原始 API JSON (需用 `extract_text_generic` 提取) | 同 OpenAI，但内容含 `<think>` |
| **超时** | 需设置极长 (300s+) 以防冷启动 | 通常 30-60s 足够 | 推理时间较长，建议 120s+ |
| **图片处理** | 原始 Base64 | 自动 WebP 压缩 (节省 Token) | 不适用 (通常不支持视觉) |
| **思维链** | 无 (除非用 R1) | 无 (除非用 o1/o3) | **有 `<think>` 标签** |

### 辅助工具函数

为了处理响应格式的不一致，务必使用 `core.llm_client.extract_text_generic(response)`。

```python
from core.llm_client import extract_text_generic

response = client.generate_response(...)
text = extract_text_generic(response)
# 无论底层是 Ollama 还是 OpenAI，此函数均能正确提取文本
```

## 7. 环境依赖

移植此模块时，需要确保以下文件存在：
1.  `core/llm_client.py`: 主逻辑
2.  `core/gemini_client.py`: Gemini 特定实现
3.  `app.py` (可选): 如果需要图片压缩功能 (`_encode_image_file_for_llm`)
4.  `.env` 文件: 存储 API Key

依赖库:
*   `requests`
*   `python-dotenv` (可选，用于加载 .env)