import base64
import json
import os
import logging
from typing import Any, Dict, List, Optional

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None

from .gemini_client import load_env_from_dotenv, parse_first_json

# Set up logger
logger = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM client supporting multiple providers"""

    def __init__(self, provider: str = "gemini", model: str = "gemini-1.5-flash"):
        self.provider = provider
        self.model = model
        load_env_from_dotenv()

    def generate_response(self, messages: List[Dict[str, Any]], image_path: Optional[str] = None) -> Dict[str, Any]:
        """Generate response using specified LLM provider"""
        return call_llm(
            provider=self.provider,
            model=self.model,
            messages=messages,
            image_path=image_path
        )

    def generate_json(self, prompt: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Generate JSON response"""
        return generate_json(
            provider=self.provider,
            model=self.model,
            prompt=prompt,
            image_path=image_path
        )


def _ensure_requests():  # pragma: no cover
    if requests is None:
        raise RuntimeError("requests is required to call LLM APIs")


def _attach_image_gemini(messages: List[Dict[str, Any]], image_path: Optional[str], mime_type: str) -> List[Dict[str, Any]]:
    if not image_path:
        return messages

    logger.info(f"📸 _attach_image_gemini: Processing image {image_path}")

    # Use compression for LLM to reduce token usage
    try:
        import sys
        import os
        # Add parent directory to path to import _encode_image_file_for_llm from app.py
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        import app
        logger.info(f"🔄 Calling app._encode_image_file_for_llm for compression...")
        b64 = app._encode_image_file_for_llm(image_path)
        mime_type = "image/webp"  # compressed payload is WebP
        logger.info(f"✅ Using compressed image: {len(b64)} base64 chars, mime={mime_type}")
    except Exception as e:
        # Fallback to original encoding if compression fails
        logger.warning(f"⚠️  Compression failed in _attach_image_gemini: {e}, using original")
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        logger.info(f"📤 Using original image: {len(b64)} base64 chars")

    out = list(messages)
    if not out:
        out = [{"role": "user", "parts": []}]
    out[-1].setdefault("parts", []).append({"inline_data": {"mime_type": mime_type, "data": b64}})
    return out


def _to_openai_messages_from_gemini(messages: List[Dict[str, Any]], image_path: Optional[str], mime_type: str) -> List[Dict[str, Any]]:
    # Convert our Gemini-style parts into OpenAI multi-modal content
    logger.info(f"🔄 _to_openai_messages_from_gemini: Converting messages for OpenAI")

    msgs = []
    # Prepare image as data URL if provided
    data_url = None
    if image_path:
        logger.info(f"📸 Processing image for OpenAI: {image_path}")

        # Use compression for LLM to reduce token usage
        try:
            import sys
            import os
            # Add parent directory to path to import _encode_image_file_for_llm from app.py
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            import app
            logger.info(f"🔄 Calling app._encode_image_file_for_llm for OpenAI compression...")
            b64 = app._encode_image_file_for_llm(image_path)
            mime_type = "image/webp"  # compressed payload is WebP
            logger.info(f"✅ Using compressed image for OpenAI: {len(b64)} base64 chars, mime={mime_type}")
        except Exception as e:
            # Fallback to original encoding if compression fails
            logger.warning(f"⚠️  Compression failed in _to_openai_messages_from_gemini: {e}, using original")
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            logger.info(f"📤 Using original image for OpenAI: {len(b64)} base64 chars")

        data_url = f"data:{mime_type};base64,{b64}"
        logger.info(f"🌐 Created data URL with length: {len(data_url)}")

    for m in messages:
        role = m.get("role", "user")
        parts = m.get("parts") or []
        content: List[Dict[str, Any]] = []
        for p in parts:
            if "text" in p:
                content.append({"type": "text", "text": p["text"]})
            elif "inline_data" in p:
                idata = p["inline_data"]
                mt = idata.get("mime_type", mime_type)
                d = idata.get("data")
                if d:
                    content.append({"type": "image_url", "image_url": {"url": f"data:{mt};base64,{d}", "detail": "low"}})
        # If we have a global image not embedded in parts, attach once on last message
        msgs.append({"role": role, "content": content or (p.get("text") if parts else "")})

    if data_url:
        # Attach to the last user message if it doesn't already have an image
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i].get("role") == "user":
                content = msgs[i].get("content")
                if isinstance(content, list):
                    has_img = any(c.get("type") == "image_url" for c in content)
                    if not has_img:
                        content.append({"type": "image_url", "image_url": {"url": data_url, "detail": "low"}})
                else:
                    msgs[i]["content"] = [
                        {"type": "text", "text": str(content or "")},
                        {"type": "image_url", "image_url": {"url": data_url, "detail": "low"}},
                    ]
                break

    return msgs


def _convert_to_gemini_format(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert OpenAI-style messages to Gemini format."""
    converted = []
    system_content = ""

    for msg in messages:
        if "content" in msg:
            if msg["role"] == "system":
                # Gemini doesn't support system role, accumulate system content
                system_content += msg["content"] + "\n"
            elif msg["role"] == "user":
                # Merge system content with user content if any
                content = msg["content"]
                if system_content:
                    content = system_content.strip() + "\n\n" + content
                    system_content = ""  # Reset after using
                converted.append({
                    "role": "user",
                    "parts": [{"text": content}]
                })
            elif msg["role"] == "assistant" or msg["role"] == "model":
                # Convert assistant to model for Gemini
                converted.append({
                    "role": "model",
                    "parts": [{"text": msg["content"]}]
                })
        else:
            # Already in Gemini format
            converted.append(msg)

    return converted


def call_llm(
    provider: Optional[str],
    model: Optional[str],
    messages: List[Dict[str, Any]],
    image_path: Optional[str] = None,
    mime_type: str = "image/png",
    temperature: float = 0.2,
) -> Dict[str, Any]:
    """Unified LLM caller for providers: gemini, openai, deepseek, nvidia (OpenAI-compatible), ollama.

    messages: we use the Gemini-style parts. This function converts as needed.
    """
    load_env_from_dotenv()
    prov = (provider or os.getenv("LLM_PROVIDER") or "gemini").strip().lower()
    model_name = model or os.getenv("LLM_MODEL")
    if prov == "ollama" and not model_name:
        model_name = "qwen2.5vl"  # sensible local default for vision-capable model

    if prov == "gemini":
        from .gemini_client import call_gemini
        # Convert OpenAI-style messages to Gemini format if needed
        msgs = _convert_to_gemini_format(messages)
        msgs = _attach_image_gemini(msgs, image_path, mime_type)
        return call_gemini(
            api_key=os.getenv("GEMINI_API_KEY"),
            messages=msgs,
            image_path=None,
            mime_type=mime_type,
            temperature=temperature,
            model_name=model_name,
        )

    _ensure_requests()

    if prov == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        timeout_s = int(os.getenv("OLLAMA_TIMEOUT_S", "120"))
        use_openai_compat = os.getenv("OLLAMA_USE_OPENAI_COMPAT", "true").strip().lower() not in ("0", "false", "no")

        if use_openai_compat:
            url = f"{base_url}/v1/chat/completions"
            payload: Dict[str, Any] = {
                "model": model_name,
                "messages": _to_openai_messages_from_gemini(messages, image_path, mime_type),
                "stream": False,
                "temperature": temperature,
                "max_tokens": int(os.getenv("OLLAMA_MAX_TOKENS", "2048")),
            }

            logger.info(f"🦙 Calling Ollama-compatible OpenAI API: model={model_name} url={url}")
            resp = requests.post(url, json=payload, timeout=timeout_s)
            if resp.status_code != 200:
                logger.error(f"❌ Ollama-compatible API returned status {resp.status_code}: {resp.text}")
                raise RuntimeError(f"Ollama-compatible API error {resp.status_code}: {resp.text}")

            data = resp.json()
            logger.debug(f"📥 Ollama-compatible raw response: {json.dumps(data)[:500]}...")
            choices = data.get("choices") or []
            msg = choices[0].get("message", {}) if choices else {}
            content = msg.get("content") or ""
            content_text = str(content)
            parsed = parse_first_json(content_text) if content_text else {}

            return {
                "ok": True,
                "provider": "ollama",
                "model": model_name,
                "content": content_text,
                "parsed": parsed,
                "raw": data,
                "method_used": "direct_ollama_openai_compat",
            }

        url = f"{base_url}/api/chat"

        def _to_ollama_messages(msgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            """Convert Gemini-style parts to Ollama chat messages with optional images."""
            converted: List[Dict[str, Any]] = []
            for m in msgs:
                role = m.get("role", "user")
                parts = m.get("parts") or []
                texts = []
                images = []
                for p in parts:
                    if "text" in p:
                        texts.append(str(p["text"]))
                    elif "inline_data" in p:
                        data = p["inline_data"].get("data")
                        if data:
                            images.append(data)
                msg_out: Dict[str, Any] = {"role": role, "content": " ".join(texts).strip()}
                if images:
                    msg_out["images"] = images
                converted.append(msg_out)

            # If an external image file is provided, attach to the last user message
            if image_path:
                with open(image_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                # Find last user message, else create one
                target = None
                for m in reversed(converted):
                    if m.get("role") == "user":
                        target = m
                        break
                if target is None:
                    target = {"role": "user", "content": ""}
                    converted.append(target)
                target.setdefault("images", []).append(b64)

            return converted

        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": _to_ollama_messages(messages),
            "stream": False,
        }
        # Optional generation options
        payload["options"] = {"temperature": temperature}

        logger.info(f"🦙 Calling Ollama: model={model_name} url={url}")
        resp = requests.post(url, json=payload, timeout=timeout_s)
        if resp.status_code != 200:
            logger.error(f"❌ Ollama returned status {resp.status_code}: {resp.text}")
            raise RuntimeError(f"Ollama error {resp.status_code}: {resp.text}")

        data = resp.json()
        logger.debug(f"📥 Ollama raw response: {json.dumps(data)[:500]}...")
        msg = data.get("message", {})
        content = msg.get("content") or data.get("response") or ""

        # Content can be a list of parts or a simple string
        if isinstance(content, list):
            parts_out = []
            for p in content:
                if isinstance(p, dict):
                    parts_out.append(p.get("text") or "")
                else:
                    parts_out.append(str(p))
            content_text = "".join(parts_out)
        else:
            content_text = str(content)

        parsed = parse_first_json(content_text) if content_text else {}

        return {
            "ok": True,
            "provider": "ollama",
            "model": model_name,
            "content": content_text,
            "parsed": parsed,
            "raw": data,
            "method_used": "direct_ollama",
        }

    # OpenAI-compatible stack (openai, deepseek, nvidia integrate)
    elif prov == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        raw_url = (
            os.getenv("OPENAI_API_URL")
            or os.getenv("OPENAI_BASE_URL")
            or "https://api.openai.com/v1/chat/completions"
        ).rstrip("/")
        if raw_url.endswith("/chat/completions"):
            url = raw_url
        elif raw_url.endswith("/v1"):
            url = f"{raw_url}/chat/completions"
        else:
            url = f"{raw_url}/v1/chat/completions"

        # GPT-5 nano only supports temperature=1.0 (default)
        model_to_use = model_name or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        use_temp = 1.0 if "gpt-5-nano" in model_to_use.lower() else temperature

        payload = {
            "model": model_to_use,
            "messages": _to_openai_messages_from_gemini(messages, image_path, mime_type),
            "temperature": use_temp,
        }

        # NOTE: Cannot limit max_completion_tokens for GPT-5 nano
        # It's a reasoning model that uses all tokens for internal reasoning first,
        # leaving nothing for the actual JSON output. Must accept ~900-1400 completion tokens.
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        # Debug: Log what we're sending to LLM - analyze actual image data
        logger.info(f"🔍 OPENAI REQUEST ANALYSIS:")
        for msg in payload.get("messages", []):
            content = msg.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if item.get("type") == "image_url":
                        data_url = item.get("image_url", {}).get("url", "")
                        logger.info(f"   📸 Image data URL length: {len(data_url)} chars")
                        if "base64," in data_url:
                            b64_part = data_url.split("base64,")[1]
                            logger.info(f"   📊 Base64 data length: {len(b64_part)} chars")
                            logger.info(f"   💾 Estimated binary size: {len(b64_part)*3//4/1024:.1f}KB")

        print(f"🔍 LLM REQUEST (OpenAI): {json.dumps(payload, indent=2)[:500]}...")

        r = requests.post(url, headers=headers, json=payload, timeout=120)

        # Log error details before raising
        if r.status_code != 200:
            error_text = r.text
            logger.error(f"❌ OpenAI API error {r.status_code}: {error_text}")
            print(f"❌ OpenAI API error {r.status_code}: {error_text}")

        r.raise_for_status()

        response = r.json()
        # Debug: Log what we received from LLM
        print(f"📥 LLM RESPONSE (OpenAI): {json.dumps(response, indent=2)[:500]}...")
        return response

    if prov in ("deepseek", "deepseek_v3", "deepseek-r1", "deepseek_v1", "ds"):
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY not set")
        url = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
        payload = {
            "model": model_name or os.getenv("DEEPSEEK_MODEL", "deepseek-v3"),
            "messages": _to_openai_messages_from_gemini(messages, image_path, mime_type),
            "temperature": temperature,
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        # Debug: Log what we're sending to LLM
        print(f"🔍 LLM REQUEST (DeepSeek): {json.dumps(payload, indent=2)[:500]}...")

        r = requests.post(url, headers=headers, json=payload, timeout=120)
        r.raise_for_status()

        response = r.json()
        # Debug: Log what we received from LLM
        print(f"📥 LLM RESPONSE (DeepSeek): {json.dumps(response, indent=2)[:500]}...")
        return response

    if prov in ("nvidia", "nim", "nvidia_openai"):
        api_key = os.getenv("NVIDIA_API_KEY") or os.getenv("NVIDIA_NGC_API_KEY")
        if not api_key:
            raise RuntimeError("NVIDIA_API_KEY not set")
        url = os.getenv("NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1/chat/completions")
        # Choose a valid default model for NVIDIA OpenAI-compatible endpoint
        # If a mismatched global model (e.g., gemini) is passed, ignore it.
        default_nvidia_model = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-r1")
        if (not model_name) or (isinstance(model_name, str) and model_name.lower().startswith("gemini")):
            use_model = default_nvidia_model
        else:
            use_model = model_name
        payload = {
            "model": use_model,
            "messages": _to_openai_messages_from_gemini(messages, image_path, mime_type),
            "temperature": temperature,
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        # Debug: Log what we're sending to LLM
        print(f"🔍 LLM REQUEST (NVIDIA): {json.dumps(payload, indent=2)[:500]}...")

        r = requests.post(url, headers=headers, json=payload, timeout=120)
        r.raise_for_status()

        response = r.json()
        # Debug: Log what we received from LLM
        print(f"📥 LLM RESPONSE (NVIDIA): {json.dumps(response, indent=2)[:500]}...")
        return response

    raise RuntimeError(f"Unknown LLM provider: {prov}")


def extract_text_generic(response_json: Dict[str, Any]) -> str:
    # Try Gemini shape
    try:
        cands = response_json.get("candidates", [])
        for c in cands:
            parts = c.get("content", {}).get("parts", [])
            for p in parts:
                if "text" in p:
                    return p["text"]
    except Exception:
        pass
    # Try OpenAI-compatible shape
    try:
        choices = response_json.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            content = msg.get("content")
            if isinstance(content, list):
                out = []
                for part in content:
                    if part.get("type") == "text" and part.get("text"):
                        out.append(part.get("text"))
                return "\n".join(out)
            if isinstance(content, str):
                return content
    except Exception:
        pass
    return ""


def generate_json(
    messages: List[Dict[str, Any]],
    image_path: Optional[str] = None,
    mime_type: str = "image/png",
    temperature: float = 0.2,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    allow_fallbacks: bool = True,
) -> Dict[str, Any]:
    """Call selected provider and parse STRICT JSON. Provider/model can come from args or env.
    Env fallbacks: LLM_PROVIDER, LLM_MODEL.
    """
    load_env_from_dotenv()
    # Ensure we use the intended provider/model from args or env
    target_provider = (provider or os.getenv("LLM_PROVIDER") or "gemini").strip().lower()
    target_model = model or os.getenv("LLM_MODEL")

    resp = None
    last_err = None
    try:
        logger.info(f"🎯 generate_json: Primary call to {target_provider} ({target_model})")
        resp = call_llm(target_provider, target_model, messages, image_path=image_path, mime_type=mime_type, temperature=temperature)
    except Exception as e:
        logger.error(f"❌ Primary LLM call failed (provider={target_provider}, model={target_model}): {e}")
        last_err = e
        
        # Check if we should fallback
        fall = os.getenv("LLM_FALLBACKS")
        logger.info(f"🔍 DEBUG: LLM_FALLBACKS from env: {fall} (allow_fallbacks={allow_fallbacks})")
        
        if allow_fallbacks and fall:
            logger.info(f"🔄 Attempting fallback LLMs: {fall}")
            for cand in [p.strip() for p in fall.split(',') if p.strip()]:
                try:
                    p_fall, m_fall = (cand.split(':', 1) + [None])[:2]
                    p_fall = (p_fall or "").strip().lower()
                    m_fall = (m_fall or "").strip() or None
                    if not p_fall:
                        continue
                    # Skip if same as failed primary
                    if p_fall == target_provider and m_fall == target_model:
                        continue
                    
                    logger.info(f"  ↪ Fallback attempt: {p_fall} ({m_fall})")
                    resp = call_llm(p_fall, m_fall, messages, image_path=image_path, mime_type=mime_type, temperature=temperature)
                    last_err = None
                    logger.info(f"✅ Fallback succeeded with {p_fall}")
                    break
                except Exception as e2:
                    logger.warning(f"  ⚠️ Fallback {cand} failed: {e2}")
                    last_err = e2

    if resp is None and last_err:
        logger.error(f"💥 All LLM attempts failed. Last error: {last_err}")
        raise last_err

    text = extract_text_generic(resp)
    if not text:
        logger.error(f"empty response from LLM: {resp}")
        raise RuntimeError("Empty response from LLM")
        
    try:
        return json.loads(text)
    except Exception:
        data = parse_first_json(text)
        if data is None:
            logger.error(f"Failed to parse JSON from: {text[:500]}...")
            raise RuntimeError("Failed to parse JSON from LLM response")
        return data
