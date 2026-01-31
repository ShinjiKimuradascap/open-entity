#!/usr/bin/env python3
"""
Moltbook Integration Tests
Moltbook連携モジュールのテスト
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# テスト対象をインポート
from moltbook_integration import (
    AuthenticationError,
    ExponentialBackoff,
    MoltbookClient,
    MoltbookError,
    MoltbookMessage,
    MoltbookPeerBridge,
    MoltbookPost,
    NotFoundError,
    RateLimitError,
    ServerError,
    create_moltbook_client,
)


class TestExponentialBackoff:
    """ExponentialBackoffのテスト"""
    
    def test_initial_delay(self):
        """初期遅延が正しく計算される"""
        backoff = ExponentialBackoff(initial_delay=1.0, max_delay=60.0)
        assert backoff.next_delay() == 1.0
    
    def test_exponential_increase(self):
        """指数関数的に増加する"""
        backoff = ExponentialBackoff(initial_delay=1.0, exponent=2.0)
        
        assert backoff.next_delay() == 1.0  # 1 * 2^0
        assert backoff.next_delay() == 2.0  # 1 * 2^1
        assert backoff.next_delay() == 4.0  # 1 * 2^2
        assert backoff.next_delay() == 8.0  # 1 * 2^3
    
    def test_max_delay_cap(self):
        """最大遅延でキャップされる"""
        backoff = ExponentialBackoff(initial_delay=10.0, max_delay=30.0, exponent=2.0)
        
        assert backoff.next_delay() == 10.0
        assert backoff.next_delay() == 20.0
        assert backoff.next_delay() == 30.0  # 40.0 -> capped to 30.0
        assert backoff.next_delay() == 30.0  # capped
    
    def test_reset(self):
        """リセットが機能する"""
        backoff = ExponentialBackoff(initial_delay=1.0)
        
        backoff.next_delay()
        backoff.next_delay()
        assert backoff._attempt == 2
        
        backoff.reset()
        assert backoff._attempt == 0
        assert backoff.next_delay() == 1.0
    
    def test_exhausted(self):
        """リトライ回数の使い果たし検出"""
        backoff = ExponentialBackoff(max_retries=3)
        
        assert not backoff.exhausted
        backoff.next_delay()
        backoff.next_delay()
        backoff.next_delay()
        assert backoff.exhausted
    
    def test_max_retries_exceeded(self):
        """最大リトライ超過で例外"""
        backoff = ExponentialBackoff(max_retries=2)
        
        backoff.next_delay()
        backoff.next_delay()
        
        with pytest.raises(MoltbookError, match="Max retries"):
            backoff.next_delay()


class TestMoltbookClient:
    """MoltbookClientのテスト"""
    
    @pytest.fixture
    def client(self):
        """テスト用クライアント"""
        return MoltbookClient(
            api_key="test_api_key",
            agent_id="test_agent_123",
            base_url="https://api.test.moltbook.ai/v1"
        )
    
    @pytest.fixture
    def mock_session(self):
        """モックHTTPセッション"""
        with patch("aiohttp.ClientSession") as mock:
            yield mock
    
    @pytest.mark.asyncio
    async def test_init(self, client):
        """初期化が正しく行われる"""
        assert client.api_key == "test_api_key"
        assert client.agent_id == "test_agent_123"
        assert client.base_url == "https://api.test.moltbook.ai/v1"
        assert client.timeout == 30.0
        assert not client._verified
        assert client._auth_token is None
    
    @pytest.mark.asyncio
    async def test_authenticate_success(self, client):
        """認証が成功する"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "auth_token": "test_token",
            "verified": True
        })
        mock_response.headers = {}
        
        mock_session = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_response)
        mock_session.closed = False
        
        with patch.object(client, '_get_session', return_value=mock_session):
            result = await client.authenticate("x_verification_code")
        
        assert result is True
        assert client._verified is True
        assert client._auth_token == "test_token"
    
    @pytest.mark.asyncio
    async def test_authenticate_failure(self, client):
        """認証失敗で例外"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "auth_token": None,
            "verified": False
        })
        mock_response.headers = {}
        
        mock_session = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_response)
        mock_session.closed = False
        
        with patch.object(client, '_get_session', return_value=mock_session):
            with pytest.raises(AuthenticationError):
                await client.authenticate("invalid_code")
    
    @pytest.mark.asyncio
    async def test_create_post_success(self, client):
        """投稿作成が成功する"""
        client._verified = True
        client._auth_token = "test_token"
        
        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(return_value={
            "id": "post_123",
            "agent_id": "test_agent_123",
            "content": "Hello Moltbook!",
            "submolt": "ai_agents",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "likes": 0,
            "replies": 0
        })
        mock_response.headers = {}
        
        mock_session = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_response)
        mock_session.closed = False
        
        with patch.object(client, '_get_session', return_value=mock_session):
            post = await client.create_post("Hello Moltbook!", submolt="ai_agents")
        
        assert post.id == "post_123"
        assert post.content == "Hello Moltbook!"
        assert post.submolt == "ai_agents"
        assert post.agent_id == "test_agent_123"
    
    @pytest.mark.asyncio
    async def test_create_post_not_authenticated(self, client):
        """未認証で投稿作成を試みると例外"""
        with pytest.raises(AuthenticationError, match="Not authenticated"):
            await client.create_post("Hello!")
    
    @pytest.mark.asyncio
    async def test_reply_to_success(self, client):
        """返信が成功する"""
        client._verified = True
        client._auth_token = "test_token"
        
        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(return_value={
            "id": "reply_123",
            "agent_id": "test_agent_123",
            "content": "This is a reply",
            "reply_to": "post_456",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "likes": 0,
            "replies": 0
        })
        mock_response.headers = {}
        
        mock_session = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_response)
        mock_session.closed = False
        
        with patch.object(client, '_get_session', return_value=mock_session):
            reply = await client.reply_to("post_456", "This is a reply")
        
        assert reply.id == "reply_123"
        assert reply.reply_to == "post_456"
        assert reply.content == "This is a reply"
    
    @pytest.mark.asyncio
    async def test_get_feed(self, client):
        """フィード取得が成功する"""
        now = datetime.now(timezone.utc).isoformat()
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "posts": [
                {
                    "id": "post_1",
                    "agent_id": "agent_a",
                    "content": "Post 1",
                    "submolt": "ai_agents",
                    "created_at": now,
                    "likes": 5,
                    "replies": 2
                },
                {
                    "id": "post_2",
                    "agent_id": "agent_b",
                    "content": "Post 2",
                    "submolt": None,
                    "created_at": now,
                    "likes": 10,
                    "replies": 0
                }
            ]
        })
        mock_response.headers = {}
        
        mock_session = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_response)
        mock_session.closed = False
        
        with patch.object(client, '_get_session', return_value=mock_session):
            posts = await client.get_feed(submolt="ai_agents", limit=2)
        
        assert len(posts) == 2
        assert posts[0].id == "post_1"
        assert posts[0].submolt == "ai_agents"
        assert posts[1].id == "post_2"
        assert posts[1].submolt is None
    
    @pytest.mark.asyncio
    async def test_join_submolt_success(self, client):
        """submolt参加が成功する"""
        client._verified = True
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={})
        mock_response.headers = {}
        
        mock_session = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_response)
        mock_session.closed = False
        
        with patch.object(client, '_get_session', return_value=mock_session):
            result = await client.join_submolt("ai_agents")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_send_direct_message_success(self, client):
        """DM送信が成功する"""
        client._verified = True
        client._auth_token = "test_token"
        
        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(return_value={
            "id": "msg_123",
            "from_agent_id": "test_agent_123",
            "to_agent_id": "agent_b",
            "content": "Hello!",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        mock_response.headers = {}
        
        mock_session = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_response)
        mock_session.closed = False
        
        with patch.object(client, '_get_session', return_value=mock_session):
            msg = await client.send_direct_message("agent_b", "Hello!")
        
        assert msg.from_agent_id == "test_agent_123"
        assert msg.to_agent_id == "agent_b"
        assert msg.content == "Hello!"
    
    @pytest.mark.asyncio
    async def test_get_direct_messages(self, client):
        """DM取得が成功する"""
        now = datetime.now(timezone.utc).isoformat()
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "messages": [
                {
                    "id": "msg_1",
                    "from_agent_id": "agent_a",
                    "to_agent_id": "test_agent_123",
                    "content": "Message 1",
                    "created_at": now,
                    "read": False
                },
                {
                    "id": "msg_2",
                    "from_agent_id": "agent_b",
                    "to_agent_id": "test_agent_123",
                    "content": "Message 2",
                    "created_at": now,
                    "read": True
                }
            ]
        })
        mock_response.headers = {}
        
        mock_session = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_response)
        mock_session.closed = False
        
        with patch.object(client, '_get_session', return_value=mock_session):
            messages = await client.get_direct_messages(limit=10)
        
        assert len(messages) == 2
        assert messages[0].id == "msg_1"
        assert not messages[0].read
        assert messages[1].read
    
    @pytest.mark.asyncio
    async def test_rate_limit_retry(self, client):
        """レート制限時にリトライする"""
        mock_response_429 = AsyncMock()
        mock_response_429.status = 429
        mock_response_429.headers = {"Retry-After": "1"}
        
        mock_response_success = AsyncMock()
        mock_response_success.status = 200
        mock_response_success.json = AsyncMock(return_value={"posts": []})
        mock_response_success.headers = {}
        
        mock_session = AsyncMock()
        mock_session.request = AsyncMock(side_effect=[
            mock_response_429,
            mock_response_success
        ])
        mock_session.closed = False
        
        with patch.object(client, '_get_session', return_value=mock_session):
            with patch('asyncio.sleep', new=AsyncMock()):  # 即座にリトライ
                posts = await client.get_feed()
        
        assert posts == []
        assert mock_session.request.call_count == 2
    
    @pytest.mark.asyncio
    async def test_server_error_retry(self, client):
        """サーバーエラー時にリトライする"""
        mock_response_500 = AsyncMock()
        mock_response_500.status = 500
        mock_response_500.headers = {}
        
        mock_response_success = AsyncMock()
        mock_response_success.status = 200
        mock_response_success.json = AsyncMock(return_value={"posts": []})
        mock_response_success.headers = {}
        
        mock_session = AsyncMock()
        mock_session.request = AsyncMock(side_effect=[
            mock_response_500,
            mock_response_success
        ])
        mock_session.closed = False
        
        with patch.object(client, '_get_session', return_value=mock_session):
            with patch('asyncio.sleep', new=AsyncMock()):  # 即座にリトライ
                posts = await client.get_feed()
        
        assert posts == []
    
    @pytest.mark.asyncio
    async def test_not_found_error(self, client):
        """404エラーでNotFoundError"""
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.headers = {}
        
        mock_session = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_response)
        mock_session.closed = False
        
        with patch.object(client, '_get_session', return_value=mock_session):
            with pytest.raises(NotFoundError):
                await client.get_feed()
    
    @pytest.mark.asyncio
    async def test_close(self, client):
        """セッションが正しくクローズされる"""
        mock_session = AsyncMock()
        mock_session.closed = False
        client._session = mock_session
        
        await client.close()
        
        mock_session.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """async context managerが機能する"""
        async with MoltbookClient(
            api_key="key",
            agent_id="agent",
            base_url="https://api.test.moltbook.ai/v1"
        ) as client:
            assert isinstance(client, MoltbookClient)
    
    @pytest.mark.asyncio
    async def test_message_handler_registration(self, client):
        """メッセージハンドラが登録される"""
        handler = Mock()
        client.on_message(handler)
        
        assert handler in client._message_handlers
    
    @pytest.mark.asyncio
    async def test_process_incoming_mention(self, client):
        """メンションが正しく処理される"""
        handler = Mock()
        client.on_mention(handler)
        
        message = {
            "type": "mention",
            "post_id": "post_123",
            "from_agent_id": "agent_a",
            "content": "@test_agent_123 Hello!",
            "submolt": "ai_agents",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await client.process_incoming_message(message)
        
        handler.assert_called_once()
        call_args = handler.call_args[0][0]
        assert call_args.id == "post_123"
        assert call_args.content == "@test_agent_123 Hello!"
    
    @pytest.mark.asyncio
    async def test_process_incoming_dm(self, client):
        """DMが正しく処理される"""
        handler = Mock()
        client.on_direct_message(handler)
        
        message = {
            "type": "direct_message",
            "message_id": "msg_123",
            "from_agent_id": "agent_a",
            "content": "Private message",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await client.process_incoming_message(message)
        
        handler.assert_called_once()
        call_args = handler.call_args[0][0]
        assert call_args.id == "msg_123"
        assert call_args.content == "Private message"


class TestMoltbookPeerBridge:
    """MoltbookPeerBridgeのテスト"""
    
    @pytest.fixture
    def mock_peer_service(self):
        """モックPeerService"""
        service = MagicMock()
        service.send_message = AsyncMock()
        return service
    
    @pytest.fixture
    def mock_moltbook_client(self):
        """モックMoltbookClient"""
        client = MagicMock()
        client.agent_id = "test_agent"
        client.get_direct_messages = AsyncMock(return_value=[])
        client.mark_message_read = AsyncMock()
        client.create_post = AsyncMock()
        return client
    
    @pytest.fixture
    def bridge(self, mock_peer_service, mock_moltbook_client):
        """テスト用ブリッジ"""
        return MoltbookPeerBridge(
            peer_service=mock_peer_service,
            moltbook_client=mock_moltbook_client,
            forward_submolt="ai_network"
        )
    
    @pytest.mark.asyncio
    async def test_init(self, bridge, mock_peer_service, mock_moltbook_client):
        """初期化が正しく行われる"""
        assert bridge.peer_service == mock_peer_service
        assert bridge.moltbook == mock_moltbook_client
        assert bridge.forward_submolt == "ai_network"
        assert not bridge._running
    
    @pytest.mark.asyncio
    async def test_start_stop(self, bridge):
        """開始・停止が機能する"""
        with patch('asyncio.create_task') as mock_create_task:
            await bridge.start()
            assert bridge._running is True
            mock_create_task.assert_called_once()
        
        await bridge.stop()
        assert bridge._running is False
    
    @pytest.mark.asyncio
    async def test_poll_loop_forwards_messages(self, bridge, mock_moltbook_client, mock_peer_service):
        """ポーリングループがメッセージを転送する"""
        from datetime import datetime, timezone
        
        # モックDMを設定
        mock_msg = MoltbookMessage(
            id="msg_123",
            from_agent_id="agent_a",
            to_agent_id="test_agent",
            content="Hello",
            created_at=datetime.now(timezone.utc)
        )
        mock_moltbook_client.get_direct_messages = AsyncMock(return_value=[mock_msg])
        
        # 1回だけ実行して停止
        bridge._running = True
        bridge._poll_interval = 0.01
        
        async def stop_after_one():
            await asyncio.sleep(0.05)
            bridge._running = False
        
        await asyncio.gather(
            bridge._poll_loop(),
            stop_after_one()
        )
        
        # PeerServiceに転送されたか確認
        mock_peer_service.send_message.assert_called()
        mock_moltbook_client.mark_message_read.assert_called_with("msg_123")
    
    @pytest.mark.asyncio
    async def test_post_to_moltbook_success(self, bridge, mock_moltbook_client):
        """PeerServiceメッセージがMoltbookに投稿される"""
        mock_post = MoltbookPost(
            id="post_123",
            agent_id="test_agent",
            content="Test post",
            submolt="ai_network",
            created_at=datetime.now(timezone.utc)
        )
        mock_moltbook_client.create_post = AsyncMock(return_value=mock_post)
        
        peer_message = {
            "type": "status_report",
            "from": "peer_a",
            "payload": {"status": "online"}
        }
        
        result = await bridge.post_to_moltbook(peer_message)
        
        assert result is not None
        assert result.id == "post_123"
        mock_moltbook_client.create_post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_post_to_moltbook_no_submolt(self, mock_peer_service, mock_moltbook_client):
        """forward_submolt未設定時は投稿しない"""
        bridge = MoltbookPeerBridge(
            peer_service=mock_peer_service,
            moltbook_client=mock_moltbook_client,
            forward_submolt=None
        )
        
        peer_message = {"type": "test", "from": "peer_a"}
        result = await bridge.post_to_moltbook(peer_message)
        
        assert result is None
        mock_moltbook_client.create_post.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_post_to_moltbook_with_custom_format(self, bridge, mock_moltbook_client):
        """カスタムフォーマットで投稿"""
        mock_post = MoltbookPost(
            id="post_456",
            agent_id="test_agent",
            content="Custom: test from peer_a",
            submolt="ai_network",
            created_at=datetime.now(timezone.utc)
        )
        mock_moltbook_client.create_post = AsyncMock(return_value=mock_post)
        
        peer_message = {
            "type": "test",
            "from": "peer_a"
        }
        
        template = "Custom: {type} from {from}"
        result = await bridge.post_to_moltbook(peer_message, format_template=template)
        
        assert result is not None
        mock_moltbook_client.create_post.assert_called_with(
            content="Custom: test from peer_a",
            submolt="ai_network"
        )
    
    @pytest.mark.asyncio
    async def test_default_format(self, bridge):
        """デフォルトフォーマットが正しく動作する"""
        message = {
            "type": "discovery",
            "from": "peer_xyz",
            "payload": {"capabilities": ["task_execution", "data_analysis"]}
        }
        
        result = bridge._default_format(message)
        
        assert "peer_xyz" in result
        assert "discovery" in result
        assert "capabilities" in result


class TestCreateMoltbookClient:
    """create_moltbook_clientファクトリ関数のテスト"""
    
    def test_with_explicit_params(self):
        """明示的なパラメータで作成"""
        client = create_moltbook_client(
            api_key="explicit_key",
            agent_id="explicit_agent"
        )
        
        assert client.api_key == "explicit_key"
        assert client.agent_id == "explicit_agent"
    
    @patch.dict(os.environ, {
        "MOLTBOOK_API_KEY": "env_key",
        "MOLTBOOK_AGENT_ID": "env_agent"
    })
    def test_with_env_vars(self):
        """環境変数から読み込み"""
        client = create_moltbook_client()
        
        assert client.api_key == "env_key"
        assert client.agent_id == "env_agent"
    
    def test_missing_api_key(self):
        """APIキーなしで例外"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="API key required"):
                create_moltbook_client()
    
    def test_missing_agent_id(self):
        """Agent IDなしで例外"""
        with patch.dict(os.environ, {"MOLTBOOK_API_KEY": "key"}, clear=True):
            with pytest.raises(ValueError, match="Agent ID required"):
                create_moltbook_client()
    
    def test_param_overrides_env(self):
        """パラメータが環境変数を上書き"""
        with patch.dict(os.environ, {
            "MOLTBOOK_API_KEY": "env_key",
            "MOLTBOOK_AGENT_ID": "env_agent"
        }):
            client = create_moltbook_client(
                api_key="param_key",
                agent_id="param_agent"
            )
        
        assert client.api_key == "param_key"
        assert client.agent_id == "param_agent"


class TestDataClasses:
    """データクラスのテスト"""
    
    def test_moltbook_post_creation(self):
        """MoltbookPostが正しく作成される"""
        now = datetime.now(timezone.utc)
        post = MoltbookPost(
            id="post_123",
            agent_id="agent_a",
            content="Test content",
            submolt="ai_agents",
            created_at=now,
            reply_to=None,
            likes=10,
            replies=3
        )
        
        assert post.id == "post_123"
        assert post.content == "Test content"
        assert post.likes == 10
        assert post.replies == 3
    
    def test_moltbook_message_creation(self):
        """MoltbookMessageが正しく作成される"""
        now = datetime.now(timezone.utc)
        msg = MoltbookMessage(
            id="msg_123",
            from_agent_id="agent_a",
            to_agent_id="agent_b",
            content="Hello",
            created_at=now,
            read=False
        )
        
        assert msg.id == "msg_123"
        assert msg.content == "Hello"
        assert not msg.read


# インテグレーションテスト（オプション、実際のAPIには接続しない）
@pytest.mark.skip(reason="Integration test - requires actual API")
class TestMoltbookIntegration:
    """実際のAPIを使用するインテグレーションテスト"""
    
    @pytest.fixture
    async def real_client(self):
        """実際のAPIクライアント"""
        client = create_moltbook_client()
        yield client
        await client.close()
    
    @pytest.mark.asyncio
    async def test_full_workflow(self, real_client):
        """完全なワークフローテスト"""
        # 認証
        await real_client.authenticate("verification_code")
        
        # 投稿
        post = await real_client.create_post("Integration test post")
        
        # 返信
        reply = await real_client.reply_to(post.id, "This is a reply")
        
        # DM
        await real_client.send_direct_message("target_agent", "Hello!")
        
        # フィード取得
        posts = await real_client.get_feed(limit=5)
        assert len(posts) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
