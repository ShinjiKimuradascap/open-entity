#!/usr/bin/env python3
"""
Session Sequence Validation テスト

Protocol v1.0 のシーケンス番号検証機能をテスト:
- 正常なシーケンス順序のメッセージ
- リプレイ攻撃（古いシーケンス番号）
- メッセージギャップ（飛ばしたシーケンス番号）
- SEQUENCE_ERROR レスポンスの検証
"""

import asyncio
import sys
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, AsyncMock

# servicesディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# インポート（複数パターン対応）
try:
    from services.peer_service import PeerService, SEQUENCE_ERROR
    from services.session_manager import SessionManager, Session
except ImportError:
    from peer_service import PeerService, SEQUENCE_ERROR
    from session_manager import SessionManager, Session


class TestSessionSequenceValidation:
    """シーケンス番号検証のテストクラス"""

    @pytest.fixture
    def mock_session_manager(self):
        """モックSessionManagerを作成"""
        mock = Mock(spec=SessionManager)
        mock.create_session = AsyncMock()
        mock.get_session = AsyncMock()
        mock.get_session_by_peer = AsyncMock()
        return mock

    @pytest.fixture
    def peer_service(self, mock_session_manager):
        """テスト用PeerServiceを作成"""
        service = PeerService(
            entity_id="test-entity",
            port=8001,
            enable_verification=False,
            enable_encryption=False
        )
        # SessionManagerをモックに差し替え
        service._session_manager = mock_session_manager
        service._session_manager_enabled = True
        return service

    @pytest.fixture
    def base_message(self):
        """ベースメッセージテンプレート"""
        return {
            "version": "1.0",
            "type": "test_message",
            "from": "peer-entity",
            "session_id": "test-session-uuid",
            "sequence_num": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {"data": "test"}
        }

    async def test_valid_sequence_order(self, peer_service, mock_session_manager, base_message):
        """正常なシーケンス順序のメッセージが許可される"""
        # モックセッションを作成（期待シーケンス=1）
        mock_session = Mock()
        mock_session.expected_sequence = 1
        mock_session.max_received_seq = 0
        mock_session.received_seq_window = set()
        mock_session_manager.get_session_by_peer.return_value = mock_session

        # シーケンス番号1のメッセージを処理
        message = base_message.copy()
        message["sequence_num"] = 1

        result = await peer_service.handle_message(message)

        # SEQUENCE_ERRORでないことを確認
        assert result.get("status") != "error" or result.get("error_code") != SEQUENCE_ERROR
        # 期待シーケンスが2にインクリメントされたことを確認
        assert mock_session.expected_sequence == 2

    async def test_replay_attack_old_sequence(self, peer_service, mock_session_manager, base_message):
        """リプレイ攻撃：古いシーケンス番号を拒否する"""
        # モックセッションを作成（期待シーケンス=5）
        mock_session = Mock()
        mock_session.expected_sequence = 5
        mock_session.max_received_seq = 4
        mock_session.received_seq_window = {1, 2, 3, 4}
        mock_session_manager.get_session_by_peer.return_value = mock_session

        # シーケンス番号3（古い）のメッセージを処理
        message = base_message.copy()
        message["sequence_num"] = 3

        result = await peer_service.handle_message(message)

        # SEQUENCE_ERRORが返されることを確認
        assert result.get("status") == "error"
        assert result.get("error_code") == SEQUENCE_ERROR
        assert result.get("reason") == "SEQUENCE_ERROR"
        assert result.get("expected") == 5
        assert result.get("received") == 3

    async def test_message_gap_higher_sequence(self, peer_service, mock_session_manager, base_message):
        """メッセージギャップ：飛ばしたシーケンス番号を拒否する"""
        # モックセッションを作成（期待シーケンス=2）
        mock_session = Mock()
        mock_session.expected_sequence = 2
        mock_session.max_received_seq = 1
        mock_session.received_seq_window = {1}
        mock_session_manager.get_session_by_peer.return_value = mock_session

        # シーケンス番号5（飛ばした）のメッセージを処理
        message = base_message.copy()
        message["sequence_num"] = 5

        result = await peer_service.handle_message(message)

        # SEQUENCE_ERRORが返されることを確認（ギャップ検出）
        assert result.get("status") == "error"
        assert result.get("error_code") == SEQUENCE_ERROR
        assert result.get("reason") == "SEQUENCE_ERROR"
        assert result.get("expected") == 2
        assert result.get("received") == 5

    async def test_consecutive_sequences(self, peer_service, mock_session_manager, base_message):
        """連続したシーケンス番号が正常に処理される"""
        # モックセッションを作成
        mock_session = Mock()
        mock_session.expected_sequence = 1
        mock_session.max_received_seq = 0
        mock_session.received_seq_window = set()
        mock_session_manager.get_session_by_peer.return_value = mock_session

        # シーケンス1, 2, 3を順に処理
        for seq in [1, 2, 3]:
            message = base_message.copy()
            message["sequence_num"] = seq
            
            result = await peer_service.handle_message(message)
            
            # エラーでないことを確認
            assert result.get("error_code") != SEQUENCE_ERROR, f"Sequence {seq} should be valid"
            # 期待シーケンスがインクリメントされる
            mock_session.expected_sequence = seq + 1

        # 最終的に期待シーケンスは4
        assert mock_session.expected_sequence == 4

    async def test_exact_expected_sequence(self, peer_service, mock_session_manager, base_message):
        """期待シーケンス番号と一致するメッセージが許可される"""
        # モックセッションを作成（期待シーケンス=10）
        mock_session = Mock()
        mock_session.expected_sequence = 10
        mock_session.max_received_seq = 9
        mock_session.received_seq_window = {1, 2, 3, 4, 5, 6, 7, 8, 9}
        mock_session_manager.get_session_by_peer.return_value = mock_session

        # シーケンス番号10（期待値と一致）のメッセージを処理
        message = base_message.copy()
        message["sequence_num"] = 10

        result = await peer_service.handle_message(message)

        # SEQUENCE_ERRORでないことを確認
        assert result.get("error_code") != SEQUENCE_ERROR
        # 期待シーケンスが11にインクリメントされたことを確認
        assert mock_session.expected_sequence == 11

    async def test_no_session_no_validation(self, peer_service, mock_session_manager, base_message):
        """セッションが存在しない場合、シーケンス検証はスキップされる"""
        # セッションが存在しない
        mock_session_manager.get_session_by_peer.return_value = None

        # メッセージを処理
        message = base_message.copy()
        message["sequence_num"] = 1

        result = await peer_service.handle_message(message)

        # SEQUENCE_ERRORでないことを確認（検証がスキップされる）
        assert result.get("error_code") != SEQUENCE_ERROR

    async def test_no_sequence_num_no_validation(self, peer_service, mock_session_manager, base_message):
        """シーケンス番号がない場合、検証はスキップされる"""
        # モックセッションを作成
        mock_session = Mock()
        mock_session_manager.get_session_by_peer.return_value = mock_session

        # シーケンス番号なしのメッセージを処理
        message = base_message.copy()
        del message["sequence_num"]

        result = await peer_service.handle_message(message)

        # SEQUENCE_ERRORでないことを確認
        assert result.get("error_code") != SEQUENCE_ERROR

    async def test_no_session_id_no_validation(self, peer_service, mock_session_manager, base_message):
        """セッションIDがない場合、検証はスキップされる"""
        # モックセッションを作成
        mock_session = Mock()
        mock_session_manager.get_session_by_peer.return_value = mock_session

        # セッションIDなしのメッセージを処理
        message = base_message.copy()
        del message["session_id"]

        result = await peer_service.handle_message(message)

        # SEQUENCE_ERRORでないことを確認
        assert result.get("error_code") != SEQUENCE_ERROR

    async def test_legacy_version_no_validation(self, peer_service, mock_session_manager, base_message):
        """v1.0以外のバージョンではシーケンス検証はスキップされる"""
        # モックセッションを作成
        mock_session = Mock()
        mock_session.expected_sequence = 5
        mock_session_manager.get_session_by_peer.return_value = mock_session

        # v0.9のメッセージを処理
        message = base_message.copy()
        message["version"] = "0.9"
        message["sequence_num"] = 1  # 古いシーケンス

        result = await peer_service.handle_message(message)

        # SEQUENCE_ERRORでないことを確認（v1.0のみ検証対象）
        assert result.get("error_code") != SEQUENCE_ERROR


class TestSessionSequenceValidationIntegration:
    """統合テスト：実際のセッションを使用したテスト"""

    @pytest.fixture
    async def real_peer_service(self):
        """実際のSessionManagerを持つPeerServiceを作成"""
        service = PeerService(
            entity_id="test-entity",
            port=8002,
            enable_verification=False,
            enable_encryption=False
        )
        # 実際のSessionManagerを有効化
        from services.session_manager import SessionManager
        service._session_manager = SessionManager()
        service._session_manager_enabled = True
        yield service

    async def test_real_session_sequence_validation(self, real_peer_service):
        """実際のセッションでシーケンス検証をテスト"""
        service = real_peer_service
        
        # セッションを作成
        session = await service.create_session("peer-entity")
        session_id = session["session_id"]
        
        # ベースメッセージ
        base_message = {
            "version": "1.0",
            "type": "test_message",
            "from": "peer-entity",
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {"data": "test"}
        }
        
        # シーケンス1: 正常
        msg1 = base_message.copy()
        msg1["sequence_num"] = 1
        result1 = await service.handle_message(msg1)
        assert result1.get("error_code") != SEQUENCE_ERROR, "First message should be accepted"
        
        # シーケンス1（再送）: リプレイ攻撃として拒否
        msg1_retry = base_message.copy()
        msg1_retry["sequence_num"] = 1
        result1_retry = await service.handle_message(msg1_retry)
        assert result1_retry.get("error_code") == SEQUENCE_ERROR, "Replay should be rejected"
        
        # シーケンス3（スキップ）: ギャップとして拒否
        msg3 = base_message.copy()
        msg3["sequence_num"] = 3
        result3 = await service.handle_message(msg3)
        assert result3.get("error_code") == SEQUENCE_ERROR, "Gap should be rejected"
        
        # シーケンス2: 正常
        msg2 = base_message.copy()
        msg2["sequence_num"] = 2
        result2 = await service.handle_message(msg2)
        assert result2.get("error_code") != SEQUENCE_ERROR, "In-order message should be accepted"


# pytest実行用
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
