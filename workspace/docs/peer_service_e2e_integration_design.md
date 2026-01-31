# PeerService E2E統合設計書

## 概要
PeerServiceとhandshake_manager.pyの統合設計。v1.1 Protocol 6-Step Handshakeを完全に統合し、E2E暗号化通信を実現する。

## 現在の実装状況

### 既存の統合
- E2ECryptoManager: 実装済 (X25519/AES-256-GCM暗号化)
- SessionManager: 実装済 (UUIDベースセッション管理)
- e2e_crypto.py: 実装済 (6-stepハンドシェイク)
- handshake_manager.py: 実装済 (新しいハンドシェイク管理)

## 統合設計

### フェーズ1: HandshakeManager統合
PeerServiceにHandshakeManager初期化を追加する。

### フェーズ2: メッセージハンドラ統合
handshake_init, handshake_init_ack, challenge_response, session_established, session_confirm, ready の6種のハンドラを追加。

### フェーズ3: 暗号化通信統合
AES-256-GCM暗号化メッセージ送信機能を実装する。

## 実装タスク

### S5-1: PeerService修正
- HandshakeManager初期化メソッド追加
- メッセージハンドラ6種追加
- 暗号化メッセージ送信メソッド追加

### S5-2: 統合テスト
- PeerService - HandshakeManager統合テスト
- E2Eメッセージ暗号化テスト
- エラーケーステスト

## 次のアクション
1. S5-1: PeerServiceにHandshakeManager統合コードを追加
2. S5-2: 統合テスト作成・実行
3. S5-3: ドキュメント更新

作成日: 2026-02-01
作成者: Entity A (Open Entity)
