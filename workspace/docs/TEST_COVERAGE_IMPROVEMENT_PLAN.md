# テストカバレッジ改善計画

## 現状分析

### テストファイル統計
- 総テストファイル数: 67 files
- services/ディレクトリ: 67 test_*.py files
- 重複・類似テスト: 推定 15-20 files

### 主要モジュール別カバレッジ

| モジュール | テストファイル | カバレッジ | 優先度 |
|-----------|--------------|-----------|--------|
| peer_service | 5 files | Medium | High |
| crypto/e2e | 8 files | Medium | High |
| api_server | 4 files | Medium | High |
| session | 6 files | Good | Medium |
| token_system | 5 files | Medium | Medium |
| moltbook | 3 files | Good | Low |
| dht | 4 files | Medium | Medium |

## 改善タスク

### Phase 1: 重複テスト整理（短期）

#### 1.1 Peer Service テスト統合
統合先: test_peer_service.py（メイン）
アーカイブ: test_peer_service_v1.py, test_peer_service_pytest.py

#### 1.2 Crypto テスト統合
統合先: test_crypto_integration.py（メイン）
アーカイブ: test_signature.py（重複）

#### 1.3 API Server テスト統合
統合先: test_api_server.py（メイン）
アーカイブ: test_endpoints_manual.py（手動テスト）

### Phase 2: 不足カバレッジ追加（中期）

- test_concurrent_transfers.py（token_system並行転送）
- test_connection_pool_stress.py（接続プール負荷）
- test_error_recovery.py（エラー回復）
- test_end_to_end_workflow.py（E2Eフロー）

### Phase 3: テストフレームワーク移行（中期）

- pytest移行
- pytest-cov導入
- CI/CD統合

## 実装ロードマップ

### Week 1: 重複整理
- Day 1-2: Peer Serviceテスト統合
- Day 3-4: Cryptoテスト統合
- Day 5: APIテスト統合

### Week 2: カバレッジ追加
- Day 1-2: 並行処理テスト
- Day 3-4: エラーケーステスト

### Week 3: フレームワーク移行
- Day 1-2: pytest移行
- Day 3-4: カバレッジ計測導入

## メトリクス目標

| 指標 | 現在 | 目標 |
|-----|------|------|
| テストファイル数 | 67 | 40 (-40%) |
| コードカバレッジ | ~60% | 80%+ |
| 重複テスト率 | ~30% | <10% |

作成: 2026-02-01
