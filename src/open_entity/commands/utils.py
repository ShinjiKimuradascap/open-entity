"""CLI utility functions."""
from pathlib import Path
from typing import Optional


def init_environment():
    """環境変数の初期化（後方互換性のために残す）"""
    # env_loader経由で初期化
    from ..utils.env_loader import init_environment as _init_env
    _init_env(override=True)


def resolve_provider(provider_str: str, model: Optional[str] = None) -> tuple:
    """プロバイダ文字列を解決してLLMProviderとモデル名を返す
    
    Args:
        provider_str: プロバイダ文字列 (例: "gemini", "zai/glm-4.7")
        model: モデル名（既に指定されている場合）
    
    Returns:
        tuple: (LLMProvider, model_name) - 無効なプロバイダの場合は typer.Exit を発生
    """
    import typer
    from ..core.runtime import LLMProvider
    
    # "zai/glm-4.7" のような形式をパース
    provider_name = provider_str
    resolved_model = model
    if "/" in provider_str and model is None:
        parts = provider_str.split("/", 1)
        provider_name = parts[0]
        resolved_model = parts[1]
    
    # プロバイダ名のバリデーションとマッピング
    VALID_PROVIDERS = {
        "openai": LLMProvider.OPENAI,
        "openrouter": LLMProvider.OPENROUTER,
        "zai": LLMProvider.ZAI,
        "gemini": LLMProvider.GEMINI,
        "moonshot": LLMProvider.MOONSHOT,
        "ollama": LLMProvider.OLLAMA,
    }
    
    if provider_name not in VALID_PROVIDERS:
        valid_list = ", ".join(sorted(VALID_PROVIDERS.keys()))
        typer.echo(f"Error: Unknown provider '{provider_name}'. Valid options: {valid_list}", err=True)
        raise typer.Exit(code=1)
    
    return VALID_PROVIDERS[provider_name], resolved_model
