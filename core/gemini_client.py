import base64
import json
import os
from typing import Any, Dict, List, Optional

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None


def _gemini_url(model_name: Optional[str] = None) -> str:
    """Resolve Gemini endpoint URL.
    Priority:
      1) GEMINI_API_URL (full URL)
      2) Construct from model name (LLM_MODEL or arg)
    """
    url_env = os.getenv("GEMINI_API_URL")
    if url_env:
        return url_env
    name = (model_name or os.getenv("LLM_MODEL") or "gemini-1.5-flash").strip()
    return f"https://generativelanguage.googleapis.com/v1beta/models/{name}:generateContent"


def load_env_from_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass


def read_image_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_gemini(
    api_key: Optional[str],
    messages: List[Dict[str, Any]],
    image_path: Optional[str] = None,
    mime_type: str = "image/png",
    temperature: float = 0.2,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    if requests is None:
        raise RuntimeError("requests is required to call Gemini API")

    if api_key is None:
        load_env_from_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set (set env var or .env)")

    # Attach image inline if provided
    if image_path:
        b64 = read_image_b64(image_path)
        # Append an inline_data part to the last message
        if not messages:
            messages.append({"role": "user", "parts": []})
        messages[-1].setdefault("parts", []).append(
            {"inline_data": {"mime_type": mime_type, "data": b64}}
        )

    payload = {
        "contents": messages,
        "generationConfig": {"temperature": temperature},
    }
    params = {"key": api_key}
    url = _gemini_url(model_name)
    resp = requests.post(url, params=params, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def extract_text(response_json: Dict[str, Any]) -> str:
    try:
        cands = response_json.get("candidates", [])
        for c in cands:
            parts = c.get("content", {}).get("parts", [])
            for p in parts:
                if "text" in p:
                    return p["text"]
    except Exception:
        pass
    return ""


def parse_first_json(text: str) -> Optional[Dict[str, Any]]:
    import re

    # Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass
    # Fallback: find first JSON object
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    frag = m.group(0)
    try:
        return json.loads(frag)
    except Exception:
        return None


def generate_json(
    messages: List[Dict[str, Any]],
    image_path: Optional[str] = None,
    mime_type: str = "image/png",
    temperature: float = 0.2,
) -> Dict[str, Any]:
    """Call Gemini with messages (and optional image) and parse STRICT JSON from the response.

    Returns a Python dict. Raises RuntimeError if JSON cannot be parsed.
    """
    resp = call_gemini(api_key=os.getenv("GEMINI_API_KEY"), messages=messages, image_path=image_path, mime_type=mime_type, temperature=temperature)
    text = extract_text(resp)
    data = None
    # Try direct JSON parse first
    try:
        data = json.loads(text)
    except Exception:
        data = parse_first_json(text)
    if data is None:
        raise RuntimeError("Failed to parse JSON from LLM response")
    return data
