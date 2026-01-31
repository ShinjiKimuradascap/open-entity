# S3 実用化テスト計画

## 現状分析

### 既存テストカバレッジ

| テストファイル | レベル | 内容 |
|---------------|--------|------|
| test_peer_service.py | S1 (Unit) | Ed25519署名、暗号化、JWT、リプレイ保護、SecureMessage |
| test_moltbook_integration.py | S1 (Unit) | MoltbookClient、認証、投稿（モック使用） |
| integration_test.py | S2 (Integration) | Crypto + PeerService統合 |
| test_integration.py | S2 (Integration) | Token Economy + Persistence |

### テストレベル定義

| レベル | 名称 | 説明 |
|--------|------|------|
| S1 | 単体テスト | 個別関数・クラスの動作確認 |
| S2 | 統合テスト | 複数モジュール間の連携確認 |
| S3 | 実用化テスト | 実環境に近い条件でのE2E、負荷、耐障害性 |

## S3 不足テスト一覧

### E2Eテスト
- E2E-01: 2つの実サービス間の通信（HTTP経由）
- E2E-02: ハンドシェイク → メッセージ送受信 → セッション終了
- E2E-03: 実際のMoltbook APIとの通信
- E2E-04: PeerService ↔ MoltbookBridge ↔ Moltbook完全連携

### 負荷・パフォーマンステスト
- PERF-01: 1000メッセージ/秒スループット
- PERF-02: 100同時接続ピア管理
- PERF-03: 大容量メッセージ（10MB+）チャンク転送
- PERF-04: メモリ使用量監視（24時間）

### 耐障害性テスト
- FAULT-01: ネットワーク断の検出と再接続
- FAULT-02: ピアクラッシュからの復旧
- FAULT-03: 高頻度リプレイ攻撃検出
- FAULT-04: 不正署名メッセージ処理

### 長時間安定性テスト
- STAB-01: 24時間連続稼働
- STAB-02: ハートビート継続監視（1週間）
- STAB-03: メモリリーク検出

### マルチピアネットワークテスト
- MULTI-01: 3+ピア間のメッセージ中継
- MULTI-02: メッシュネットワーク形成
- MULTI-03: ピア発見プロトコル

### セキュリティ実用テスト
- SEC-01: Man-in-the-Middle攻撃検出
- SEC-02: 鍵交換の完全性検証
- SEC-03: セッション固定攻撃防止

## 実装計画

### Phase 1: コアE2Eテスト（1-2週間）
1. Docker Composeで2+サービス起動環境構築
2. tests/e2e/test_peer_communication.py実装
3. tests/e2e/test_fault_tolerance.py実装

### Phase 2: 負荷テスト（2-3週間）
1. Locust/k6使用スループットテスト
2. 大容量ファイル転送テスト

### Phase 3: 長時間テスト（継続的）
1. CI外で定期実行
2. メトリクス収集

## 次のアクション

1. S1: 既存テスト分析完了
2. S2: 不足テスト特定完了（本ドキュメント）
3. S3: E2Eテスト環境構築開始 ← 現在ここ

---
作成日: 2026-02-01
