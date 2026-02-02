#!/usr/bin/env python3
"""
Moltbook Client (Alias Module)

このモジュールはmoltbook_identity_client.pyのエイリアスです。
後方互換性のために提供されています。

新規コードではmoltbook_identity_clientを直接使用することを推奨します。
"""

# moltbook_identity_clientから全てを再エクスポート
try:
    from services.moltbook_identity_client import (
        MoltbookClient,
        MoltbookAgent,
        IdentityToken,
        RateLimitInfo,
        init_client,
        get_client,
        MOLTBOOK_BASE_URL,
        API_VERSION,
    )
except ImportError:
    from .moltbook_identity_client import (
        MoltbookClient,
        MoltbookAgent,
        IdentityToken,
        RateLimitInfo,
        init_client,
        get_client,
        MOLTBOOK_BASE_URL,
        API_VERSION,
    )

# 後方互換性のためのエイリアス関数
def init_moltbook_client(api_key=None):
    """
    Moltbookクライアントを初期化（後方互換性用）
    
    Args:
        api_key: Moltbook API Key
        
    Returns:
        初期化されたMoltbookClientインスタンス
    """
    return init_client(api_key)


# グローバルインスタンスも再エクスポート
from moltbook_identity_client import _client


__all__ = [
    'MoltbookClient',
    'MoltbookAgent',
    'IdentityToken',
    'RateLimitInfo',
    'init_client',
    'init_moltbook_client',  # 後方互換性用
    'get_client',
    'MOLTBOOK_BASE_URL',
    'API_VERSION',
]
