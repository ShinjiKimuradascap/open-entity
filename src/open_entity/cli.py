#!/usr/bin/env python3
"""Moco CLI - Thin wrapper for cli_main"""

# ruff: noqa: E402
import warnings
# ========================================
# 警告の抑制 (インポート前に設定)
# ========================================
# Python 3.9 EOL や SSL 関連の不要な警告を非表示にする
warnings.filterwarnings("ignore", category=FutureWarning)
try:
    # urllib3 の NotOpenSSLWarning はインポート時に発生するため、
    # 警告フィルターを先に設定しておく必要がある
    warnings.filterwarnings("ignore", message=".*urllib3 v2 only supports OpenSSL 1.1.1+.*")
    # Google GenAI の thought_signature 警告を抑制
    warnings.filterwarnings("ignore", message=".*non-text parts in the response.*")
    warnings.filterwarnings("ignore", message=".*thought_signature.*")
except Exception:
    pass

# ========================================
# 重要: .env の読み込みは最初に行う必要がある
# 他のモジュールがインポート時に環境変数を参照するため
# ========================================
import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

def _early_load_dotenv():
    """モジュールインポート前に .env を読み込む"""
    env_path = find_dotenv(usecwd=True) or (Path(__file__).parent.parent.parent / ".env")
    if env_path:
        load_dotenv(env_path)

# 他のモジュールをインポートする前に環境変数を読み込む
_early_load_dotenv()

# ========================================
# メインロジックは cli_main からインポート
# ========================================
from .cli_main import (
    app,
    main,
    sessions_app,
    skills_app,
    tasks_app,
    init_environment,
    resolve_provider,
)

__all__ = [
    "app",
    "main",
    "sessions_app",
    "skills_app",
    "tasks_app",
    "init_environment",
    "resolve_provider",
]
