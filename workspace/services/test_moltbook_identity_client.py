#!/usr/bin/env python3
"""
Moltbook Client Unit Tests

Moltbook APIクライアントの単体テスト
モックを使用して外部APIへの依存を排除
"""

import asyncio
import base64
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiohttp
from aiohttp import ClientSession

# テスト対象のモジュールをインポート
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.moltbook_identity_client import (
    MoltbookClient,
    MoltbookAgent,
    IdentityToken,
    RateLimitInfo,
    MOLTBOOK_BASE_URL,
    API_VERSION
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_api_key():
    """テスト用APIキー"""
    return "test_api_key_12345"


@pytest.fixture
def mock_encryption_key():
    """テスト用暗号化キー（Fernet形式）"""
    from cryptography.fernet import Fernet
    return Fernet.generate_key()


@pytest.fixture
def mock_identity_token():
    """テスト用Identity Token"""
    return IdentityToken(
        token="test_token_abc123",
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )


@pytest.fixture
def mock_agent_data():
    """テスト用Agentデータ"""
    return {
        "id": "agent_123",
        "name": "Test Agent",
        "description": "A test agent",
        "karma": 100,
        "avatar_url": "https://example.com/avatar.png",
        "verified": True,
        "created_at": "2024-01-01T00:00:00Z",
        "follower_count": 50,
        "stats": {
            "posts": 10,
            "comments": 25
        },
        "owner": {
            "x_handle": "@testuser",
            "x_name": "Test User",
            "x_verified": True,
            "x_follower_count": 1000
        }
    }


@pytest.fixture
def mock_rate_limit_headers():
    """テスト用レート制限ヘッダー"""
    return {
        "X-RateLimit-Limit": "100",
        "X-RateLimit-Remaining": "99",
        "X-RateLimit-Reset": str(int((datetime.utcnow() + timedelta(hours=1)).timestamp()))
    }


# ============================================================================
# RateLimitInfo Tests
# ============================================================================

class TestRateLimitInfo:
    """RateLimitInfoクラスのテスト"""
    
    def test_rate_limit_info_creation(self):
        """RateLimitInfoの作成テスト"""
        reset_at = datetime.utcnow() + timedelta(hours=1)
        info = RateLimitInfo(
            limit=100,
            remaining=50,
            reset_at=reset_at,
            retry_after=60
        )
        
        assert info.limit == 100
        assert info.remaining == 50
        assert info.reset_at == reset_at
        assert info.retry_after == 60
    
    def test_is_exceeded_true(self):
        """レート制限超過判定（超過している場合）"""
        info = RateLimitInfo(
            limit=100,
            remaining=0,
            reset_at=datetime.utcnow() + timedelta(hours=1)
        )
        assert info.is_exceeded() is True
    
    def test_is_exceeded_false(self):
        """レート制限超過判定（超過していない場合）"""
        info = RateLimitInfo(
            limit=100,
            remaining=1,
            reset_at=datetime.utcnow() + timedelta(hours=1)
        )
        assert info.is_exceeded() is False
    
    def test_wait_time_with_retry_after(self):
        """Retry-Afterによる待機時間計算"""
        info = RateLimitInfo(
            limit=100,
            remaining=0,
            reset_at=datetime.utcnow() + timedelta(hours=1),
            retry_after=60
        )
        assert info.wait_time() == 60.0
    
    def test_wait_time_with_reset_at(self):
        """Reset-Atによる待機時間計算"""
        reset_at = datetime.utcnow() + timedelta(minutes=5)
        info = RateLimitInfo(
            limit=100,
            remaining=0,
            reset_at=reset_at
        )
        # 約5分（300秒）の待機時間
        assert 295 <= info.wait_time() <= 305
    
    def test_wait_time_no_wait_needed(self):
        """待機不要の場合"""
        reset_at = datetime.utcnow() - timedelta(minutes=1)
        info = RateLimitInfo(
            limit=100,
            remaining=0,
            reset_at=reset_at
        )
        assert info.wait_time() == 0.0


# ============================================================================
# MoltbookClient Initialization Tests
# ============================================================================

class TestMoltbookClientInit:
    """MoltbookClient初期化のテスト"""
    
    def test_init_with_api_key(self, mock_api_key):
        """APIキー指定での初期化"""
        client = MoltbookClient(api_key=mock_api_key)
        assert client.api_key == mock_api_key
        assert client._get_api_key() == mock_api_key
    
    def test_init_with_env_var(self, mock_api_key, monkeypatch):
        """環境変数からのAPIキー読み込み"""
        monkeypatch.setenv("MOLTBOOK_API_KEY", mock_api_key)
        client = MoltbookClient()
        assert client.api_key == mock_api_key
    
    def test_init_without_api_key(self):
        """APIキーなしでの初期化（読み取り専用モード）"""
        # 環境変数をクリア
        with patch.dict(os.environ, {}, clear=True):
            client = MoltbookClient()
            assert client.api_key is None
    
    def test_init_with_encryption(self, mock_api_key, mock_encryption_key):
        """暗号化有効での初期化"""
        client = MoltbookClient(
            api_key=mock_api_key,
            encryption_key=mock_encryption_key
        )
        # 平文は保持されていない
        assert client.api_key is None
        # 暗号化データが保存されている
        assert client._encrypted_api_key is not None
        # 復号化して取得できる
        assert client._get_api_key() == mock_api_key
    
    def test_init_with_rate_limit_handler(self, mock_api_key):
        """レート制限ハンドラ指定での初期化"""
        handler = MagicMock()
        client = MoltbookClient(
            api_key=mock_api_key,
            rate_limit_handler=handler
        )
        assert client._rate_limit_handler == handler


# ============================================================================
# Encryption Tests
# ============================================================================

class TestEncryption:
    """暗号化機能のテスト"""
    
    def test_encrypt_decrypt_api_key(self, mock_api_key, mock_encryption_key):
        """APIキーの暗号化・復号化"""
        client = MoltbookClient()
        client._encryption_key = mock_encryption_key
        
        # 暗号化
        client._encrypt_api_key(mock_api_key)
        assert client._encrypted_api_key is not None
        assert client.api_key is None
        
        # 復号化
        decrypted = client._decrypt_api_key()
        assert decrypted == mock_api_key
    
    def test_decrypt_without_encryption_key(self, mock_api_key):
        """暗号化キーなしでの復号化試行"""
        client = MoltbookClient(api_key=mock_api_key)
        assert client._decrypt_api_key() == mock_api_key
    
    def test_encrypt_decrypt_cycle(self, mock_api_key, mock_encryption_key):
        """暗号化・復号化の一貫性"""
        client = MoltbookClient(encryption_key=mock_encryption_key)
        client._encrypt_api_key(mock_api_key)
        
        # 複数回復号化しても同じ結果
        for _ in range(3):
            assert client._decrypt_api_key() == mock_api_key


# ============================================================================
# Rate Limit Tests
# ============================================================================

class TestRateLimit:
    """レート制限機能のテスト"""
    
    def test_parse_rate_limit_headers(self, mock_rate_limit_headers):
        """レート制限ヘッダーの解析"""
        client = MoltbookClient(api_key="test")
        info = client._parse_rate_limit_headers(mock_rate_limit_headers)
        
        assert info.limit == 100
        assert info.remaining == 99
        assert info.retry_after is None
    
    def test_parse_rate_limit_with_retry_after(self):
        """Retry-Afterヘッダー付きの解析"""
        headers = {
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int((datetime.utcnow() + timedelta(hours=1)).timestamp())),
            "Retry-After": "60"
        }
        client = MoltbookClient(api_key="test")
        info = client._parse_rate_limit_headers(headers)
        
        assert info.retry_after == 60
    
    def test_parse_invalid_headers(self):
        """無効なヘッダーの解析"""
        headers = {"X-RateLimit-Limit": "invalid"}
        client = MoltbookClient(api_key="test")
        info = client._parse_rate_limit_headers(headers)
        
        assert info.limit == 0
        assert info.remaining == 0
    
    @pytest.mark.asyncio
    async def test_handle_rate_limit_with_wait(self):
        """レート制限超過時の待機処理"""
        client = MoltbookClient(api_key="test")
        
        rate_limit = RateLimitInfo(
            limit=100,
            remaining=0,
            reset_at=datetime.utcnow() + timedelta(seconds=0.1),
            retry_after=None
        )
        
        start = datetime.utcnow()
        await client._handle_rate_limit(rate_limit)
        elapsed = (datetime.utcnow() - start).total_seconds()
        
        # 少し待機していることを確認
        assert elapsed >= 0.05  # 0.1秒未満でも待機は発生
    
    @pytest.mark.asyncio
    async def test_handle_rate_limit_with_callback(self):
        """レート制限時のコールバック呼び出し"""
        callback = MagicMock()
        client = MoltbookClient(
            api_key="test",
            rate_limit_handler=callback
        )
        
        rate_limit = RateLimitInfo(
            limit=100,
            remaining=0,
            reset_at=datetime.utcnow() + timedelta(seconds=1),
            retry_after=1
        )
        
        await client._handle_rate_limit(rate_limit)
        callback.assert_called_once_with(rate_limit)


# ============================================================================
# Identity Token Tests
# ============================================================================

class TestIdentityToken:
    """Identity Token機能のテスト"""
    
    def test_token_is_valid(self):
        """有効なトークンの判定"""
        token = IdentityToken(
            token="test_token",
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        assert token.is_valid() is True
    
    def test_token_is_invalid(self):
        """無効なトークンの判定（期限切れ）"""
        token = IdentityToken(
            token="test_token",
            expires_at=datetime.utcnow() - timedelta(hours=1)
        )
        assert token.is_valid() is False
    
    @pytest.mark.asyncio
    async def test_generate_identity_token_success(self, mock_api_key):
        """Identity Token生成（成功）"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                "token": "new_identity_token",
                "expires_in": 3600
            })
            mock_response.headers = {}
            mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.return_value.__aexit__ = AsyncMock(return_value=False)
            
            client = MoltbookClient(api_key=mock_api_key)
            token = await client.generate_identity_token()
            
            assert token is not None
            assert token.token == "new_identity_token"
            assert token.is_valid() is True
            
            await client.close()
    
    @pytest.mark.asyncio
    async def test_generate_identity_token_no_api_key(self):
        """Identity Token生成（APIキーなし）"""
        client = MoltbookClient(api_key=None)
        token = await client.generate_identity_token()
        assert token is None
    
    @pytest.mark.asyncio
    async def test_generate_identity_token_rate_limit(self, mock_api_key):
        """Identity Token生成（レート制限）"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 429
            mock_response.headers = {
                "X-RateLimit-Limit": "10",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int((datetime.utcnow() + timedelta(minutes=1)).timestamp())),
                "Retry-After": "60"
            }
            mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.return_value.__aexit__ = AsyncMock(return_value=False)
            
            client = MoltbookClient(api_key=mock_api_key)
            token = await client.generate_identity_token()
            
            assert token is None
            assert client._last_rate_limit is not None
            assert client._last_rate_limit.retry_after == 60
            
            await client.close()
    
    @pytest.mark.asyncio
    async def test_get_valid_token_cached(self, mock_api_key, mock_identity_token):
        """キャッシュされた有効トークンの取得"""
        client = MoltbookClient(api_key=mock_api_key)
        client._identity_token = mock_identity_token
        
        token = await client.get_valid_token()
        assert token == mock_identity_token.token
    
    @pytest.mark.asyncio
    async def test_get_valid_token_refresh(self, mock_api_key):
        """期限切れトークンの自動更新"""
        expired_token = IdentityToken(
            token="expired_token",
            expires_at=datetime.utcnow() - timedelta(hours=1)
        )
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                "token": "new_token",
                "expires_in": 3600
            })
            mock_response.headers = {}
            mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.return_value.__aexit__ = AsyncMock(return_value=False)
            
            client = MoltbookClient(api_key=mock_api_key)
            client._identity_token = expired_token
            
            token = await client.get_valid_token()
            assert token == "new_token"
            
            await client.close()


# ============================================================================
# Agent Profile Tests
# ============================================================================

class TestAgentProfile:
    """Agentプロフィール機能のテスト"""
    
    def test_parse_agent_profile(self, mock_agent_data):
        """Agentプロフィールのパース"""
        client = MoltbookClient(api_key="test")
        agent = client._parse_agent_profile(mock_agent_data)
        
        assert agent.id == "agent_123"
        assert agent.name == "Test Agent"
        assert agent.description == "A test agent"
        assert agent.karma == 100
        assert agent.verified is True
        assert agent.follower_count == 50
        assert agent.post_count == 10
        assert agent.comment_count == 25
        assert agent.owner_x_handle == "@testuser"
        assert agent.owner_x_verified is True
    
    @pytest.mark.asyncio
    async def test_verify_identity_success(self, mock_agent_data):
        """Identity検証（成功）"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_agent_data)
            mock_response.headers = {}
            mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.return_value.__aexit__ = AsyncMock(return_value=False)
            
            client = MoltbookClient(api_key="test")
            agent = await client.verify_identity("test_token")
            
            assert agent is not None
            assert agent.name == "Test Agent"
            
            await client.close()
    
    @pytest.mark.asyncio
    async def test_verify_identity_failure(self):
        """Identity検証（失敗）"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 401
            mock_response.text = AsyncMock(return_value="Invalid token")
            mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.return_value.__aexit__ = AsyncMock(return_value=False)
            
            client = MoltbookClient(api_key="test")
            agent = await client.verify_identity("invalid_token")
            
            assert agent is None
            
            await client.close()


# ============================================================================
# Heartbeat Tests
# ============================================================================

class TestHeartbeat:
    """ハートビート機能のテスト"""
    
    @pytest.mark.asyncio
    async def test_heartbeat_success(self, mock_api_key, mock_agent_data):
        """ハートビート（成功）"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                "token": "test_token",
                "expires_in": 3600
            })
            mock_response.headers = {}
            mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.return_value.__aexit__ = AsyncMock(return_value=False)
            
            client = MoltbookClient(api_key=mock_api_key)
            
            with patch.object(client, 'verify_identity', return_value=MoltbookAgent(
                id="agent_123",
                name="Test Agent",
                description="Test",
                karma=100,
                avatar_url=None,
                verified=True,
                created_at=datetime.utcnow(),
                follower_count=50,
                post_count=10,
                comment_count=25,
                owner_x_handle=None,
                owner_x_name=None,
                owner_x_verified=False,
                owner_x_follower_count=0
            )):
                status = await client.heartbeat()
                
                assert status["connected"] is True
                assert status["token_valid"] is True
                assert status["agent"] is not None
                assert status["agent"]["name"] == "Test Agent"
            
            await client.close()
    
    @pytest.mark.asyncio
    async def test_heartbeat_no_token(self):
        """ハートビート（トークンなし）"""
        client = MoltbookClient(api_key=None)
        status = await client.heartbeat()
        
        assert status["connected"] is False
        assert status["token_valid"] is False
        assert status["agent"] is None


# ============================================================================
# Session Management Tests
# ============================================================================

class TestSessionManagement:
    """セッション管理のテスト"""
    
    @pytest.mark.asyncio
    async def test_get_session_creation(self):
        """セッション作成"""
        client = MoltbookClient(api_key="test")
        session = await client._get_session()
        
        assert session is not None
        assert not session.closed
        
        await client.close()
    
    @pytest.mark.asyncio
    async def test_get_session_reuse(self):
        """セッション再利用"""
        client = MoltbookClient(api_key="test")
        session1 = await client._get_session()
        session2 = await client._get_session()
        
        assert session1 is session2
        
        await client.close()
    
    @pytest.mark.asyncio
    async def test_close_session(self):
        """セッションクローズ"""
        client = MoltbookClient(api_key="test")
        session = await client._get_session()
        
        await client.close()
        
        assert session.closed


# ============================================================================
# Utility Function Tests
# ============================================================================

class TestUtilityFunctions:
    """ユーティリティ関数のテスト"""
    
    def test_get_auth_documentation_url(self):
        """認証ドキュメントURL生成"""
        client = MoltbookClient(api_key="test")
        url = client.get_auth_documentation_url(
            app_name="TestApp",
            endpoint="https://api.example.com/webhook",
            header="X-Custom-Identity"
        )
        
        assert "moltbook.com/auth.md" in url
        assert "app=TestApp" in url
        assert "endpoint=https://api.example.com/webhook" in url
        assert "header=X-Custom-Identity" in url


# ============================================================================
# Post Tests
# ============================================================================

class TestCreatePost:
    """create_post() のテスト"""
    
    @pytest.mark.asyncio
    async def test_create_post_success(self, mock_api_key):
        """投稿作成が成功する場合"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 201
            mock_response.json = AsyncMock(return_value={
                "id": "post_123",
                "content": "Test post content",
                "visibility": "public",
                "created_at": "2024-01-01T00:00:00Z"
            })
            mock_response.text = AsyncMock(return_value="")
            mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.return_value.__aexit__ = AsyncMock(return_value=False)
            
            client = MoltbookClient(api_key=mock_api_key)
            client._identity_token = IdentityToken(
                token="valid_token",
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )
            
            result = await client.create_post("Test post content", "public")
            
            assert result is not None
            assert result["id"] == "post_123"
            assert result["content"] == "Test post content"
            assert client._last_post_time is not None
            
            await client.close()
    
    @pytest.mark.asyncio
    async def test_create_post_rate_limit_client(self):
        """クライアント側レート制限（30分に1回）"""
        client = MoltbookClient(api_key="test")
        # 最近の投稿時刻を設定
        client._last_post_time = datetime.utcnow() - timedelta(minutes=10)
        client._identity_token = IdentityToken(
            token="valid_token",
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        
        result = await client.create_post("Test post content")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_create_post_rate_limit_server(self, mock_api_key):
        """サーバー側レート制限（429）"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 429
            mock_response.text = AsyncMock(return_value="Rate limit exceeded")
            mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.return_value.__aexit__ = AsyncMock(return_value=False)
            
            client = MoltbookClient(api_key=mock_api_key)
            client._identity_token = IdentityToken(
                token="valid_token",
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )
            
            result = await client.create_post("Test post content")
            
            assert result is None
            
            await client.close()
    
    @pytest.mark.asyncio
    async def test_create_post_no_token(self):
        """トークンがない場合はNoneを返す"""
        client = MoltbookClient(api_key="test")
        result = await client.create_post("Test post content")
        
        assert result is None


# ============================================================================
# Comment Tests
# ============================================================================

class TestCreateComment:
    """create_comment() のテスト"""
    
    @pytest.mark.asyncio
    async def test_create_comment_success(self, mock_api_key):
        """コメント作成が成功する場合"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 201
            mock_response.json = AsyncMock(return_value={
                "id": "comment_456",
                "post_id": "post_123",
                "content": "Test comment",
                "created_at": "2024-01-01T00:00:00Z"
            })
            mock_response.text = AsyncMock(return_value="")
            mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.return_value.__aexit__ = AsyncMock(return_value=False)
            
            client = MoltbookClient(api_key=mock_api_key)
            client._identity_token = IdentityToken(
                token="valid_token",
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )
            
            result = await client.create_comment("post_123", "Test comment")
            
            assert result is not None
            assert result["id"] == "comment_456"
            assert client._comment_count == 1
            
            await client.close()
    
    @pytest.mark.asyncio
    async def test_create_comment_rate_limit(self):
        """コメントレート制限（1時間に50回）"""
        client = MoltbookClient(api_key="test")
        client._identity_token = IdentityToken(
            token="valid_token",
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        client._comment_count = 50
        client._comment_window_start = datetime.utcnow() - timedelta(minutes=30)
        
        result = await client.create_comment("post_123", "Test comment")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_create_comment_window_reset(self, mock_api_key):
        """1時間経過後、コメントカウントがリセットされる"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 201
            mock_response.json = AsyncMock(return_value={
                "id": "comment_789",
                "post_id": "post_123",
                "content": "Test comment after reset"
            })
            mock_response.text = AsyncMock(return_value="")
            mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.return_value.__aexit__ = AsyncMock(return_value=False)
            
            client = MoltbookClient(api_key=mock_api_key)
            client._identity_token = IdentityToken(
                token="valid_token",
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )
            client._comment_count = 50
            client._comment_window_start = datetime.utcnow() - timedelta(hours=2)
            
            result = await client.create_comment("post_123", "Test comment after reset")
            
            assert result is not None
            assert client._comment_count == 1  # リセット後に1増加
            
            await client.close()
    
    @pytest.mark.asyncio
    async def test_create_comment_no_token(self):
        """トークンがない場合はNoneを返す"""
        client = MoltbookClient(api_key="test")
        result = await client.create_comment("post_123", "Test comment")
        
        assert result is None


# ============================================================================
# Timeline Tests
# ============================================================================

class TestGetTimeline:
    """get_timeline() のテスト"""
    
    @pytest.mark.asyncio
    async def test_get_timeline_success(self, mock_api_key):
        """タイムライン取得が成功する場合"""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                "posts": [
                    {"id": "post_1", "content": "First post"},
                    {"id": "post_2", "content": "Second post"}
                ],
                "cursor": "next_page_cursor_123",
                "has_more": True
            })
            mock_response.text = AsyncMock(return_value="")
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)
            
            client = MoltbookClient(api_key=mock_api_key)
            client._identity_token = IdentityToken(
                token="valid_token",
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )
            
            result = await client.get_timeline(limit=20)
            
            assert result is not None
            assert len(result["posts"]) == 2
            assert result["cursor"] == "next_page_cursor_123"
            
            await client.close()
    
    @pytest.mark.asyncio
    async def test_get_timeline_with_cursor(self, mock_api_key):
        """カーソルを指定してタイムラインを取得"""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                "posts": [{"id": "post_3", "content": "Third post"}],
                "cursor": None,
                "has_more": False
            })
            mock_response.text = AsyncMock(return_value="")
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)
            
            client = MoltbookClient(api_key=mock_api_key)
            client._identity_token = IdentityToken(
                token="valid_token",
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )
            
            result = await client.get_timeline(limit=10, cursor="prev_cursor")
            
            assert result is not None
            # paramsが正しく渡されているか確認
            call_kwargs = mock_get.call_args[1]
            assert call_kwargs["params"]["cursor"] == "prev_cursor"
            
            await client.close()
    
    @pytest.mark.asyncio
    async def test_get_timeline_error(self, mock_api_key):
        """タイムライン取得エラー時"""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text = AsyncMock(return_value="Server Error")
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)
            
            client = MoltbookClient(api_key=mock_api_key)
            client._identity_token = IdentityToken(
                token="valid_token",
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )
            
            result = await client.get_timeline()
            
            assert result is None
            
            await client.close()
    
    @pytest.mark.asyncio
    async def test_get_timeline_no_token(self):
        """トークンがない場合はNoneを返す"""
        client = MoltbookClient(api_key="test")
        result = await client.get_timeline()
        
        assert result is None


# ============================================================================
# Agent Search Tests
# ============================================================================

class TestSearchAgents:
    """search_agents() のテスト"""
    
    @pytest.mark.asyncio
    async def test_search_agents_success(self, mock_api_key):
        """エージェント検索が成功する場合"""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                "agents": [
                    {"id": "agent_1", "name": "Agent One", "karma": 100},
                    {"id": "agent_2", "name": "Agent Two", "karma": 50}
                ],
                "total": 2,
                "query": "test"
            })
            mock_response.text = AsyncMock(return_value="")
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)
            
            client = MoltbookClient(api_key=mock_api_key)
            client._identity_token = IdentityToken(
                token="valid_token",
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )
            
            result = await client.search_agents("test", limit=10)
            
            assert result is not None
            assert len(result["agents"]) == 2
            assert result["query"] == "test"
            
            await client.close()
    
    @pytest.mark.asyncio
    async def test_search_agents_limit_capped(self, mock_api_key):
        """limitが20を超える場合は20に制限される"""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"agents": [], "total": 0})
            mock_response.text = AsyncMock(return_value="")
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)
            
            client = MoltbookClient(api_key=mock_api_key)
            client._identity_token = IdentityToken(
                token="valid_token",
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )
            
            await client.search_agents("test", limit=50)
            
            call_kwargs = mock_get.call_args[1]
            assert call_kwargs["params"]["limit"] == 20
            
            await client.close()
    
    @pytest.mark.asyncio
    async def test_search_agents_error(self, mock_api_key):
        """検索エラー時"""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text = AsyncMock(return_value="Server Error")
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)
            
            client = MoltbookClient(api_key=mock_api_key)
            client._identity_token = IdentityToken(
                token="valid_token",
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )
            
            result = await client.search_agents("test")
            
            assert result is None
            
            await client.close()


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """統合テスト"""
    
    @pytest.mark.asyncio
    async def test_full_workflow_with_encryption(self, mock_api_key, mock_encryption_key, mock_agent_data):
        """暗号化付き完全ワークフロー"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            # トークン生成のレスポンス
            mock_response_token = AsyncMock()
            mock_response_token.status = 200
            mock_response_token.json = AsyncMock(return_value={
                "token": "workflow_token",
                "expires_in": 3600
            })
            mock_response_token.headers = {}
            
            # Identity検証のレスポンス
            mock_response_verify = AsyncMock()
            mock_response_verify.status = 200
            mock_response_verify.json = AsyncMock(return_value=mock_agent_data)
            mock_response_verify.headers = {}
            
            mock_post.side_effect = [
                MagicMock(__aenter__=AsyncMock(return_value=mock_response_token), __aexit__=AsyncMock(return_value=False)),
                MagicMock(__aenter__=AsyncMock(return_value=mock_response_verify), __aexit__=AsyncMock(return_value=False))
            ]
            
            # 暗号化付きクライアント作成
            client = MoltbookClient(
                api_key=mock_api_key,
                encryption_key=mock_encryption_key
            )
            
            # トークン生成
            token = await client.generate_identity_token()
            assert token is not None
            assert token.token == "workflow_token"
            
            # Identity検証
            agent = await client.verify_identity(token.token)
            assert agent is not None
            assert agent.name == "Test Agent"
            
            # ハートビート
            with patch.object(client, 'get_valid_token', return_value="workflow_token"):
                status = await client.heartbeat()
                assert status["token_valid"] is True
            
            await client.close()


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
