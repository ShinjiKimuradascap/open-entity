from __future__ import annotations

import os
from typing import Any, List, Optional


try:
    from google import genai  # type: ignore

    GENAI_AVAILABLE = True
except ImportError:  # pragma: no cover
    genai = None
    GENAI_AVAILABLE = False

try:
    from openai import OpenAI  # type: ignore
    OPENAI_AVAILABLE = True
except ImportError:  # pragma: no cover
    OpenAI = None
    OPENAI_AVAILABLE = False


def build_genai_client() -> Optional[Any]:
    """Create a google-genai client if available and API key is set."""
    if not GENAI_AVAILABLE:
        return None
    api_key = os.getenv("GENAI_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception:
        return None


def build_openai_client() -> Optional[Any]:
    """Create an OpenAI client if available and API key is set."""
    if not OPENAI_AVAILABLE:
        return None
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key)
    except Exception:
        return None


def embed_text(client: Any, model: str, text: str) -> List[float]:
    """テキストをembeddingに変換"""
    if not client:
        return []
    try:
        if hasattr(client, "models"):
            result = client.models.embed_content(model=model, contents=text)
            return list(result.embeddings[0].values)
        if hasattr(client, "embeddings"):
            result = client.embeddings.create(model=model, input=text)
            return list(result.data[0].embedding)
    except Exception as e:
        print(f"[MemoryService] Embedding error: {e}")
        return []
    return []











