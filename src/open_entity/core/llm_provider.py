"""
LLM プロバイダー統一管理

プロバイダー優先順位: 1. zai, 2. openrouter, 3. gemini
"""

import base64
import os
import logging
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from typing import Optional, Tuple

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except Exception:
    OpenAI = None
    OPENAI_AVAILABLE = False

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except Exception:
    genai = None
    types = None
    GENAI_AVAILABLE = False

logger = logging.getLogger(__name__)
_DOTENV_LOADED = False


def _ensure_dotenv_loaded() -> None:
    """必要に応じて .env を読み込む（多重読み込みを避ける）。"""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    env_path = find_dotenv(usecwd=True) or (Path(__file__).parent.parent.parent / ".env")
    if env_path:
        load_dotenv(env_path)
    _DOTENV_LOADED = True

# プロバイダー定数
PROVIDER_ZAI = "zai"
PROVIDER_OPENROUTER = "openrouter"
PROVIDER_GEMINI = "gemini"
PROVIDER_OPENAI = "openai"
PROVIDER_MOONSHOT = "moonshot"
PROVIDER_OLLAMA = "ollama"

# プロバイダー優先順位
PROVIDER_PRIORITY = [PROVIDER_ZAI, PROVIDER_OPENROUTER, PROVIDER_GEMINI]

# Vision 対応プロバイダー優先順位
VISION_PROVIDER_PRIORITY = [PROVIDER_MOONSHOT, PROVIDER_OPENROUTER, PROVIDER_GEMINI, PROVIDER_OPENAI]

# プロバイダーごとのデフォルトモデル
DEFAULT_MODELS = {
    PROVIDER_ZAI: "glm-4.7",
    PROVIDER_OPENROUTER: "moonshotai/kimi-k2.5",
    PROVIDER_GEMINI: "gemini-2.0-flash",
    PROVIDER_OPENAI: "gpt-4o",
    PROVIDER_MOONSHOT: "kimi-k2.5",
    PROVIDER_OLLAMA: "llama3.1",
}

# 分析用（軽量）モデル
ANALYZER_MODELS = {
    PROVIDER_ZAI: "glm-4.7-flash",
    PROVIDER_OPENROUTER: "google/gemini-3-flash-preview",
    PROVIDER_GEMINI: "gemini-2.0-flash",
    PROVIDER_OPENAI: "gpt-4o-mini",
    PROVIDER_MOONSHOT: "kimi-k2.5",
    PROVIDER_OLLAMA: "llama3.1",
}

# 埋め込み（embedding）用デフォルトモデル
EMBEDDING_MODELS = {
    PROVIDER_GEMINI: "gemini-embedding-001",
    PROVIDER_OPENAI: "text-embedding-3-small",
}

# Vision 用デフォルトモデル
VISION_MODELS = {
    PROVIDER_MOONSHOT: "kimi-k2.5",
    PROVIDER_OPENROUTER: "openai/gpt-4o",
    PROVIDER_OPENAI: "gpt-4o",
    PROVIDER_GEMINI: "gemini-2.0-flash",
}


def _check_api_key(provider: str) -> bool:
    """指定プロバイダーの API キーが設定されているか確認"""
    _ensure_dotenv_loaded()
    if provider == PROVIDER_ZAI:
        return bool(os.environ.get("ZAI_API_KEY"))
    elif provider == PROVIDER_OPENROUTER:
        return bool(os.environ.get("OPENROUTER_API_KEY"))
    elif provider == PROVIDER_GEMINI:
        return bool(os.environ.get("GENAI_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    elif provider == PROVIDER_OPENAI:
        return bool(os.environ.get("OPENAI_API_KEY"))
    elif provider == PROVIDER_MOONSHOT:
        return bool(os.environ.get("MOONSHOT_API_KEY"))
    elif provider == PROVIDER_OLLAMA:
        return True
    return False


def get_available_provider() -> str:
    """
    利用可能なプロバイダーを優先順位で返す。
    
    優先順位: zai → openrouter → gemini
    
    環境変数 LLM_PROVIDER または MOCO_DEFAULT_PROVIDER で強制指定可能。
    
    Returns:
        利用可能なプロバイダー名
    """
    # 環境変数で強制指定 (LLM_PROVIDER を最優先)
    forced = os.environ.get("LLM_PROVIDER") or os.environ.get("MOCO_DEFAULT_PROVIDER")
    if forced and forced in [PROVIDER_ZAI, PROVIDER_OPENROUTER, PROVIDER_GEMINI, PROVIDER_OPENAI, PROVIDER_MOONSHOT, PROVIDER_OLLAMA]:
        if _check_api_key(forced):
            logger.info(f"Using forced provider: {forced}")
            return forced
        else:
            logger.warning(f"Forced provider {forced} has no API key, falling back to priority order")

    # 環境変数で強制指定
    # 優先順位で確認
    for provider in PROVIDER_PRIORITY:
        if _check_api_key(provider):
            logger.debug(f"Selected provider by priority: {provider}")
            return provider
    
    # どれも利用できない場合は openrouter をデフォルトに（エラーは後で発生）
    logger.warning("No API keys found, defaulting to openrouter")
    return PROVIDER_OPENROUTER


def get_preferred_provider() -> str:
    """LLM_PROVIDER を優先し、なければ利用可能なプロバイダーを返す。"""
    return get_available_provider()


def get_vision_provider(preferred: Optional[str] = None) -> str:
    """
    Vision 対応のプロバイダーを返す。

    Args:
        preferred: 明示指定（例: "openai", "openrouter", "gemini"）
    """
    _ensure_dotenv_loaded()

    if preferred is None:
        forced = os.environ.get("LLM_PROVIDER") or os.environ.get("MOCO_DEFAULT_PROVIDER")
        if forced:
            preferred, _ = resolve_provider_and_model(forced, None)

    if preferred:
        provider_name, _ = resolve_provider_and_model(preferred, None)
        if provider_name in VISION_PROVIDER_PRIORITY and _check_api_key(provider_name):
            return provider_name

    for provider in VISION_PROVIDER_PRIORITY:
        if _check_api_key(provider):
            return provider

    if preferred:
        provider_name, _ = resolve_provider_and_model(preferred, None)
        if provider_name in VISION_PROVIDER_PRIORITY:
            return provider_name

    return PROVIDER_OPENROUTER


def get_vision_model(provider: Optional[str] = None) -> str:
    """
    Vision 用のモデル名を返す。

    環境変数で上書き可能:
      - OPENROUTER_VISION_MODEL
      - OPENAI_VISION_MODEL
      - GEMINI_VISION_MODEL
    """
    if provider is None:
        provider = get_vision_provider()

    if provider == PROVIDER_OPENROUTER:
        return os.environ.get("OPENROUTER_VISION_MODEL", VISION_MODELS[PROVIDER_OPENROUTER])
    if provider == PROVIDER_MOONSHOT:
        return os.environ.get("MOONSHOT_VISION_MODEL", VISION_MODELS[PROVIDER_MOONSHOT])
    if provider == PROVIDER_OPENAI:
        return os.environ.get("OPENAI_VISION_MODEL", VISION_MODELS[PROVIDER_OPENAI])
    if provider == PROVIDER_GEMINI:
        return os.environ.get("GEMINI_VISION_MODEL", VISION_MODELS[PROVIDER_GEMINI])

    return VISION_MODELS[PROVIDER_OPENROUTER]


def _get_openai_like_client(provider: str) -> "OpenAI":
    if not OPENAI_AVAILABLE:
        raise ImportError("OpenAI package not installed. Run: pip install openai")

    if provider == PROVIDER_OPENROUTER:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")
        return OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    if provider == PROVIDER_ZAI:
        api_key = os.environ.get("ZAI_API_KEY")
        if not api_key:
            raise ValueError("ZAI_API_KEY environment variable not set")
        return OpenAI(api_key=api_key, base_url="https://api.z.ai/api/coding/paas/v4")

    if provider == PROVIDER_MOONSHOT:
        api_key = os.environ.get("MOONSHOT_API_KEY")
        if not api_key:
            raise ValueError("MOONSHOT_API_KEY environment variable not set")
        base_url = os.environ.get("MOONSHOT_BASE_URL")
        if not base_url:
            model = os.environ.get("MOONSHOT_MODEL", DEFAULT_MODELS[PROVIDER_MOONSHOT])
            if model == "kimi-for-coding":
                base_url = "https://api.kimi.com/coding/v1"
            else:
                base_url = "https://api.moonshot.ai/v1"
        kwargs = {"api_key": api_key, "base_url": base_url}
        if "kimi.com/coding" in base_url:
            kwargs["default_headers"] = {"User-Agent": "Kilo-Code/1.0.0"}
        return OpenAI(**kwargs)

    if provider == PROVIDER_OLLAMA:
        # Ollama uses OpenAI-compatible API without auth
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        api_key = os.environ.get("OLLAMA_API_KEY", "ollama")
        return OpenAI(api_key=api_key, base_url=base_url)

    # PROVIDER_OPENAI (including OpenAI-compatible via OPENAI_BASE_URL)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    base_url = os.environ.get("OPENAI_BASE_URL")
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def _get_gemini_client() -> "genai.Client":
    if not GENAI_AVAILABLE:
        raise ImportError("google-genai is not installed. Run: pip install google-genai")
    api_key = (
        os.environ.get("GENAI_API_KEY") or
        os.environ.get("GEMINI_API_KEY") or
        os.environ.get("GOOGLE_API_KEY")
    )
    if not api_key:
        raise ValueError("Gemini API key not set (GENAI_API_KEY / GEMINI_API_KEY / GOOGLE_API_KEY)")
    return genai.Client(api_key=api_key)


def generate_text(
    prompt: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: float = 0.3,
    response_format: Optional[str] = None,
) -> str:
    """
    Generate text with a unified provider interface.

    response_format:
      - None: normal text
      - "json": request JSON output (best-effort)
    """
    _ensure_dotenv_loaded()
    provider_name = provider or get_preferred_provider()
    model_name = model or get_analyzer_model(provider_name)

    if provider_name == PROVIDER_GEMINI:
        client = _get_gemini_client()
        config_kwargs = {"temperature": temperature}
        if max_tokens is not None:
            config_kwargs["max_output_tokens"] = max_tokens
        if response_format == "json":
            config_kwargs["response_mime_type"] = "application/json"
        config = types.GenerateContentConfig(**config_kwargs)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config
        )
        return response.text or ""

    # OpenAI-compatible providers
    client = _get_openai_like_client(provider_name)
    create_kwargs = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    if max_tokens is not None:
        create_kwargs["max_tokens"] = max_tokens
    if response_format == "json":
        create_kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(**create_kwargs)
    return response.choices[0].message.content or ""


def generate_vision(
    prompt: str,
    image_url: Optional[str] = None,
    image_base64: Optional[str] = None,
    image_mime_type: str = "image/png",
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: float = 0.2,
) -> str:
    """
    Generate vision response with unified providers.

    image_url or image_base64 must be provided.
    """
    _ensure_dotenv_loaded()
    provider_name = get_vision_provider(provider)

    if provider_name not in VISION_PROVIDER_PRIORITY:
        raise ValueError(f"Unsupported vision provider: {provider_name}")

    if not _check_api_key(provider_name):
        raise ValueError(f"API key for provider {provider_name} is not set")

    model_name = model or get_vision_model(provider_name)

    if provider_name == PROVIDER_GEMINI:
        if image_base64 is None:
            raise ValueError("Gemini vision requires base64 image data")
        client = _get_gemini_client()
        config_kwargs = {"temperature": temperature}
        if max_tokens is not None:
            config_kwargs["max_output_tokens"] = max_tokens
        config = types.GenerateContentConfig(**config_kwargs)
        parts = [
            types.Part(
                inline_data=types.Blob(
                    mime_type=image_mime_type,
                    data=base64.b64decode(image_base64),
                )
            ),
            types.Part(text=prompt),
        ]
        response = client.models.generate_content(
            model=model_name,
            contents=[types.Content(role="user", parts=parts)],
            config=config,
        )
        return response.text or ""

    if image_url is None and image_base64 is None:
        raise ValueError("image_url or image_base64 is required")

    client = _get_openai_like_client(provider_name)
    content = []
    if image_url:
        content.append({
            "type": "image_url",
            "image_url": {"url": image_url},
        })
    elif image_base64:
        data_url = f"data:{image_mime_type};base64,{image_base64}"
        content.append({
            "type": "image_url",
            "image_url": {"url": data_url},
        })

    content.append({
        "type": "text",
        "text": prompt,
    })

    create_kwargs = {
        "model": model_name,
        "messages": [{"role": "user", "content": content}],
        "temperature": temperature,
    }
    if max_tokens is not None:
        create_kwargs["max_tokens"] = max_tokens
    response = client.chat.completions.create(**create_kwargs)
    return response.choices[0].message.content or ""


def get_default_model(provider: Optional[str] = None) -> str:
    """
    プロバイダーのデフォルトモデルを返す。
    
    Args:
        provider: プロバイダー名（省略時は自動選択）
    
    Returns:
        モデル名
    """
    if provider is None:
        provider = get_available_provider()
    return DEFAULT_MODELS.get(provider, DEFAULT_MODELS[PROVIDER_OPENROUTER])


def get_analyzer_model(provider: Optional[str] = None) -> str:
    """
    分析用の軽量モデルを返す。
    
    環境変数 MOCO_ANALYZER_MODEL で上書き可能。
    
    Args:
        provider: プロバイダー名（省略時は自動選択）
    
    Returns:
        モデル名
    """
    # 環境変数で上書き
    override = os.environ.get("MOCO_ANALYZER_MODEL")
    if override:
        return override
    
    if provider is None:
        provider = get_available_provider()
    return ANALYZER_MODELS.get(provider, ANALYZER_MODELS[PROVIDER_OPENROUTER])


def get_embedding_provider(preferred: Optional[str] = None) -> str:
    """
    Embedding 用のプロバイダーを返す。

    優先順:
    1. preferred / EMBEDDING_PROVIDER
    2. gemini -> openai
    """
    _ensure_dotenv_loaded()
    forced = preferred or os.environ.get("EMBEDDING_PROVIDER")
    if forced:
        provider_name, _ = resolve_provider_and_model(forced, None)
        if provider_name in (PROVIDER_GEMINI, PROVIDER_OPENAI) and _check_api_key(provider_name):
            return provider_name

    if _check_api_key(PROVIDER_GEMINI):
        return PROVIDER_GEMINI
    if _check_api_key(PROVIDER_OPENAI):
        return PROVIDER_OPENAI

    return PROVIDER_GEMINI


def get_embedding_model(provider: Optional[str] = None) -> str:
    """
    Embedding 用のモデル名を返す。

    環境変数 EMBEDDING_MODEL で上書き可能。
    """
    override = os.environ.get("EMBEDDING_MODEL")
    if override:
        return override
    if provider is None:
        provider = get_embedding_provider()
    return EMBEDDING_MODELS.get(provider, EMBEDDING_MODELS[PROVIDER_GEMINI])


def get_provider_and_model() -> Tuple[str, str]:
    """
    利用可能なプロバイダーとそのデフォルトモデルを返す。
    
    Returns:
        (provider, model) のタプル
    """
    provider = get_available_provider()
    model = get_default_model(provider)
    return provider, model


def resolve_provider_and_model(provider_str: Optional[str], model_str: Optional[str]) -> Tuple[str, Optional[str]]:
    """
    "zai/glm-4.7" のような形式をパースし、provider と model を返す。
    
    Args:
        provider_str: プロバイダー文字列（例: "zai/glm-4.7", "openai"）
        model_str: 明示的に指定されたモデル名
        
    Returns:
        (provider_name, model_name) のタプル
    """
    if provider_str is None:
        provider_str = get_available_provider()

    provider_name = provider_str
    model_name = model_str
    
    if "/" in provider_str and model_name is None:
        parts = provider_str.split("/", 1)
        provider_name = parts[0]
        model_name = parts[1]
        
    return provider_name, model_name
