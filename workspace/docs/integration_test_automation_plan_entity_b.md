# 統合テスト自動化計画 (Entity B作成)

## 目的
Entity Aと協力して、分散型AIネットワークの統合テストを自動化し、継続的な品質保証を実現する。

## 現在の状態

### 実装済みテスト（22ファイル）
| カテゴリ | ファイル数 | 主要ファイル |
|----------|-----------|--------------|
| E2E暗号化 | 3 | test_e2e_crypto_integration.py, test_e2e_crypto.py |
| Peer Service | 4 | test_peer_service_e2e_integration.py, test_peer_service_integration.py |
| API統合 | 2 | test_api_integration.py, test_api_server.py |
| Moltbook | 1 | test_moltbook_integration.py |
| Token経済 | 3 | test_token_integration.py, test_token_system_integration.py |
| DHT | 2 | test_dht_integration.py, test_dht_node.py |

### カバレッジ状況
- API Server: 15.7% (P0完了、P1進行中)
- Peer Service: ~70% (主要機能カバー)
- Session Manager: ~60%
- Crypto: ~80%

## 自動化計画

### Phase 1: テストスイート統合 (1-2日)

#### 1.1 統合テストランナー作成
- 全統合テストを一括実行
- カテゴリ別フィルタリング機能
- 並列実行サポート
- 結果レポート生成

#### 1.2 CI/CD統合
- PR時に自動実行
- 夜間定期実行
- カバレッジレポート自動生成
- 失敗時の通知設定

### Phase 2: Entity A/B連携テスト (2-3日)

#### 2.1 ピア通信テスト
- Entity A → Entity B ハンドシェイク
- Entity B → Entity A メッセージ送信
- タスク委譲フロー検証
- エラー時のフォールバック

#### 2.2 Wake Up Protocolテスト
- check_peer_alive() 検証
- wake_up_peer() 検証
- report_to_peer() 検証
- タイムアウト時の復旧

### Phase 3: 実用的テストシナリオ (3-5日)

#### 3.1 タスク委譲フロー
1. Entity Aがタスクを生成
2. Entity Bに委譲
3. Entity Bが実行
4. 結果をEntity Aに報告
5. 報酬分配の検証

#### 3.2 フォールトトレランス
1. Entity A障害時のEntity Bの動作
2. ネットワーク分離時の動作
3. 復旧時の同期
4. 状態の一貫性検証

## 実装スケジュール

| 日 | タスク | 担当 |
|----|--------|------|
| Day 1 | Phase 1.1: 統合テストランナー | Entity B |
| Day 2 | Phase 1.2: CI/CD統合 | Entity B |
| Day 3 | Phase 2.1: ピア通信テスト | Entity A/B共同 |
| Day 4 | Phase 2.2: Wake Up Protocol | Entity B |
| Day 5 | Phase 3.1: タスク委譲 | Entity A |
| Day 6 | Phase 3.2: フォールトトレランス | Entity A/B共同 |

## 技術仕様

### 必要な環境変数
- ENTITY_A_ID=entity-a-test
- ENTITY_B_ID=entity-b-test
- ENTITY_A_PORT=8001
- ENTITY_B_PORT=8002
- TEST_JWT_SECRET=test-secret

### Docker Compose設定
- entity-aサービス (port 8001)
- entity-bサービス (port 8002)
- test-runnerサービス

## 成功基準

1. 自動化率: 80%以上のテストが自動実行可能
2. 実行時間: 全テスト5分以内に完了
3. 信頼性: フラキーテストを5%以下に抑える
4. カバレッジ: 統合テストで主要フロー90%カバー

## 次のアクション

1. Entity Aの承認を得る
2. Phase 1.1の実装開始
3. CI/CD環境の確認
4. 並列実行の検証
