# Peer Service 統合テスト計画 v1.0

## 1. 概要

本文書は services/peer_service.py の統合テスト計画を定義する。
Protocol v1.0/v1.1対応の主要コンポーネント間の連携を検証する。

## 2. テスト対象コンポーネント

### 2.1 Core Components
| コンポーネント | 説明 | テスト優先度 |
|--------------|------|------------|
| SessionManager | UUIDベースセッション管理 | High |
| MessageQueue | メッセージキュー・リトライ | High |
| HeartbeatManager | 死活監視 | High |
| PeerService | メインサービスクラス | Critical |
| ChunkInfo | チャンク転送管理 | Medium |

### 2.2 連携ポイント
- SessionManager <-> Handlers <-> MessageReceiver
- HeartbeatManager <-> PeerService <-> MessageQueue
- Chunk Buffer <-> Message Handlers

## 3. 統合テストシナリオ

### 3.1 シナリオ1: 完全なハンドシェイクフロー
目的: セッション確立からメッセージ交換までの一連の流れ

テストフロー:
1. Peer A: SessionManagerでセッション作成
2. Peer A -> Peer B: handshake_initiate
3. Peer B: セッション作成 + 応答
4. Peer A: セッション確立確認
5. Peer A -> Peer B: 暗号化メッセージ送信
6. Peer B: メッセージ復号・検証
7. 両方: 統計情報確認

検証項目:
- セッションが正しく作成される
- シーケンス番号が正しく管理される
- メッセージが正しく暗号化・復号される
- 統計情報が更新される

### 3.2 シナリオ2: 切断・再接続フロー
目的: ネットワーク障害時の復旧動作

テストフロー:
1. 正常にセッション確立
2. ピアBを一時停止（切断シミュレート）
3. HeartbeatManagerが異常を検知
4. MessageQueueがメッセージを保持
5. ピアBを復帰
6. セッション再確立
7. キューに溜まったメッセージを再送

### 3.3 シナリオ3: マルチピア管理
目的: 複数ピアとの同時通信

テストフロー:
1. Peer AがPeer B, C, Dと同時に接続
2. 各ピアで別々のセッション管理
3. 同時にメッセージを送受信
4. 各ピアの統計を個別に確認

### 3.4 シナリオ4: 大容量メッセージ転送
目的: チャンク分割転送の動作確認

テストフロー:
1. 1MB以上のペイロードを作成
2. チャンク分割して送信
3. 受信側で再構築
4. 元データと整合性確認

### 3.5 シナリオ5: エラー回復とリトライ
目的: エラー時の回復動作

テストフロー:
1. メッセージ送信（成功）
2. 一時的エラー（500）-> リトライ成功
3. 恒久的エラー（404）-> 即時失敗
4. タイムアウト -> リトライ後失敗
5. キューが溢れた場合の動作

## 4. 実装優先順位

1. P0 (Critical): シナリオ1, 3 - 基本機能
2. P1 (High): シナリオ2, 5 - 信頼性
3. P2 (Medium): シナリオ4 - 拡張機能

## 5. 既存テストとの関係

- test_peer_service.py: 単体テスト・セキュリティ機能
- test_integration.py: トークンエコノミー統合（別システム）
- test_peer_service_integration.py: 本計画で新規作成

## 6. タイムライン

- Phase 1: テスト基盤作成 (2h)
- Phase 2: シナリオ1, 3実装 (4h)
- Phase 3: シナリオ2, 5実装 (4h)
- Phase 4: シナリオ4実装 (2h)
- Phase 5: CI統合 (1h)

---
作成: 2026-02-01
対象: services/peer_service.py v1.0
