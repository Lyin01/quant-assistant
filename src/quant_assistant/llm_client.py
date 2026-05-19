from __future__ import annotations

import json
import os
import urllib.request
from typing import Any


def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass


def _get_config():
    _load_env()
    return {
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    }


def is_configured() -> bool:
    cfg = _get_config()
    return bool(cfg["api_key"])


def call_llm(prompt: str, temperature: float = 0.3, max_tokens: int = 1500) -> dict[str, Any]:
    """Call DeepSeek API with the given prompt.

    Returns {"ok": True, "text": "..."} or {"ok": False, "error": "..."}
    """
    cfg = _get_config()
    if not cfg["api_key"]:
        return {"ok": False, "error": "DEEPSEEK_API_KEY not configured. Add it to .env file."}

    url = f"{cfg['base_url']}/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": "你是一位理性的量化投资助手。给出直接、具体、可操作的建议。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            text = result["choices"][0]["message"]["content"]
            return {"ok": True, "text": text, "usage": result.get("usage", {})}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return {"ok": False, "error": f"HTTP {exc.code}: {body}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
