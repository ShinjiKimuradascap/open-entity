# S3 実用化テスト詳細設計ドキュメント

## 概要

本ドキュメントはS3（実用化テスト）フェーズの詳細設計を定義します。
実環境に近い条件でのE2Eテスト、負荷テスト、耐障害性テストの設計仕様を記載します。

---

## Phase 1: コアE2Eテスト (Week 1-2)

### 1.1 Peer Discovery 実用化テスト

**テストファイル**: `tests/practical/test_practical_discovery.py`

#### 目的
- ブートストラップノードを介したピア発見機能の実用レベル検証
- Gossipプロトコルによるピア情報伝播の確認
- ネットワーク分割からの復旧確認

#### テストケース

**DISC-01**: ブートストラップ接続
- peer1を起動しブートストラップノードに接続
- 初期ピアリストを取得
- 自ピアが登録されることを確認

**DISC-02**: Gossipプロトコル伝播
- peer1, peer2を起動
- peer3を後から起動
- peer3の情報が30秒以内に全ピアに伝播することを確認

**DISC-03**: ネットワーク分割復旧
- 3ピアを起動
- peer1をネットワークから隔離
- 復帰後60秒以内に再同期されることを確認

---

### 1.2 Chunked Transfer 実用化テスト

**テストファイル**: `tests/practical/test_practical_chunked.py`

#### 目的
- 大容量メッセージ（10MB-100MB）の分割転送検証
- チャンク喪失時の再送メカニズム確認
- 並行転送時のパフォーマンス検証

#### テストデータ
- small: 1MB
- medium: 10MB
- large: 50MB
- xlarge: 100MB

#### テストケース

**CHUNK-01**: 基本分割転送
- 10MBデータを分割転送し再構成
- 送信データと受信データが一致することを確認

**CHUNK-02**: ランダム順序受信
- チャンクをランダム順序で送信
- 順不同でも正しく再構成されることを確認

**CHUNK-03**: チャンク再送
- 30%のチャンクを意図的にドロップ
- NACKベースの再送要求と復元を確認

**CHUNK-04**: 並行転送
- 10MBデータを5つ同時転送
- 転送時間が順次転送の1/3以下であることを確認

**CHUNK-05**: 期限切れクリーンアップ
- 期限切れ転送の自動削除を確認
- メモリ解放を確認

---

## Phase 2: 負荷・パフォーマンステスト (Week 3-4)

### 2.1 スループットテスト

**Target**: 1000 messages/sec sustained for 60 seconds
**Metrics**: Messages sent/received, Average latency (p50, p95, p99), Error rate

### 2.2 接続スケーリング

**Target**: 100 concurrent peer connections
**Metrics**: Connection establishment time, Memory per connection

---

## Phase 3: 耐障害性テスト (Week 5-6)

- ネットワーク分割検出と復旧
- ピアクラッシュからの復旧
- リプレイ攻撃検出
- 不正署名メッセージ処理

---

## Phase 4: 長時間安定性テスト (Week 7-8)

### 4.1 24時間連続稼働テスト

**Duration**: 24 hours
**Load**: 10 messages/sec sustained
**Pass Criteria**:
- Message delivery rate > 99.9%
- Memory growth < 10%
- No unhandled exceptions

---

## 次のアクション

1. S3-4: test_practical_chunked.py 実装
2. S3-5: test_practical_discovery.py 実装
3. S3-6: docker-compose.practical.yml 作成

---

作成日: 2026-02-01
