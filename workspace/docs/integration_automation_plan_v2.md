# 統合テスト自動化計画 v2

## 概要
AIエージェント間通信プロトコルの統合テスト自動化を強化し、継続的な品質保証と高速フィードバックを実現する。

## 現状分析（2026-02-01）

### S1完了: テストインベントリ更新

**分析日時:** 2026-02-01 01:15 JST  
**分析対象:** services/test_*.py (59 files)

#### カテゴリ別テスト数

| Category | Count | Files |
|----------|-------|-------|
| Peer Service | 8 | test_peer_service*.py |
| Integration | 10 | test_*integration*.py |
| Session | 5 | test_session*.py |
| Handshake | 4 | test_handshake*.py |
| Task/Scenario | 5 | test_task*.py, test_scenario*.py |
| Crypto | 5 | test_*crypto*.py, test_signature.py |
| Token/Economy | 4 | test_token*.py, test_reward*.py |
| Wallet | 2 | test_wallet*.py |
| API | 2 | test_api*.py |
| DHT | 2 | test_dht*.py |
| Moltbook | 2 | test_moltbook*.py |
| Other | 10 | test_practical*.py, test_security.py etc. |
| **Total** | **59** | - |

### 既存テストインベントリ（詳細）

#### 単体テスト（Unit Tests）
- test_crypto.py: 200+行, 暗号化ユーティリティ, ~2s
- test_signature.py: 150+行, 署名検証, ~1s
- test_session_manager.py: 300+行, セッション管理, ~3s
- test_rate_limiter.py: 100+行, レート制限, ~1s
- test_wallet.py: 250+行, ウォレット機能, ~2s

#### 統合テスト（Integration Tests）
- test_integration_scenarios.py: 619行, 5シナリオ統合テスト, ~15s
- test_e2e_crypto_integration.py: 500+行, E2E暗号化統合, ~20s
- test_peer_service_e2e.py: 300+行, PeerService E2E, ~30s
- test_moltbook_integration.py: 400+行, Moltbook連携, ~10s

#### E2Eテスト（End-to-End Tests）
- tests/e2e/test_peer_communication.py: 400+行, ピア通信E2E, ~60s
- tests/e2e/test_fault_tolerance.py: 300+行, フォールトトレランス, ~90s

### カバレッジ状況
- ハンドシェイクフロー: 85%
- セキュアメッセージ交換: 80%
- セッション管理（JWT認証）: 90%
- エラー処理・攻撃防御: 75%
- ウォレット永続化: 80%
- E2E暗号化: 85%
- PeerService統合: 60%
- Moltbook統合: 50%

### 現状の問題
1. 統合テストがCI未実行: test_integration_*.py がCIで実行されていない
2. テスト実行時間: 全体で10分超（目標は5分以内）
3. 並列実行未対応: pytest-xdist未導入
4. 通知設定不足: 失敗時の通知がSlack未連携

## 自動化計画 v2

### Phase 1: CI/CD強化（即日〜2日）✅ 完了

#### 1.1 GitHub Actionsワークフロー更新 ✅
- ✅ 統合テスト自動実行追加 - python-tests.yml更新済み
- ✅ テスト結果カテゴリ分離（unit/integration/e2e）
- ✅ スケジュール実行（6時間ごと）追加
- ✅ 並列実行（pytest-xdist）導入済み
- ⏳ 失敗時Slack通知 - Secrets設定待ち

#### 1.2 テストカテゴリ分離 ✅
- ✅ unit: 高速（<5秒）
- ✅ integration: 中速（<30秒）
- ✅ e2e: 低速（<2分）

#### 1.3 テスト自動化スクリプト作成 ✅
- ✅ scripts/run_automated_tests.sh (220行) 作成完了
- ✅ カテゴリ別実行対応（unit/integration/e2e/security）
- ✅ レポート生成機能実装

### Phase 2: スケジュール実行（3〜5日）

#### 2.1 定期実行ワークフロー
- 毎日深夜2時（JST 11時）に実行
- workflow_dispatch対応

#### 2.2 テストモード
- Smoke: Push時, Unitのみ
- Integration: PR時, Unit+Integration
- Full: 深夜, 全テスト
- Stress: 週末, 負荷テスト

### Phase 3: 継続的品質管理（1週間〜）

#### 3.1 カバレッジゲート
- overall: 80%
- diff: 70%
- critical: 90%

#### 3.2 パフォーマンスモニタリング
- テスト実行時間のトレンド
- 遅延テストの自動検出
- フレーキーテスト追跡

## 実装タスク詳細

### S1: 統合テストCI統合（優先度: 高, 見積: 4時間）
- python-tests.ymlに統合テストステップ追加
- test_integration_scenarios.py実行設定
- テスト結果アーティファクト保存

### S2: テストカテゴリ分離（優先度: 高, 見積: 6時間）
- テストファイルをunit/integration/e2eに分類
- pytestマーカー導入
- カテゴリ別実行スクリプト作成

### S3: 並列実行対応（優先度: 中, 見積: 4時間）
- pytest-xdist導入
- 並列実行設定（-n auto）
- テスト分離確認

### S4: Slack通知設定（優先度: 中, 見積: 3時間）
- Slack webhook設定
- 通知テンプレート作成
- 失敗/回復通知実装

### M1: スケジュール実行（優先度: 中, 見積: 4時間）
- scheduled-tests.yml作成
- 深夜実行設定（cron）
- レポート生成・保存

### M2: カバレッジゲート（優先度: 低, 見積: 6時間）
- Codecov設定強化
- カバレッジ閾値設定
- 強制マージ防止設定

## スケジュール

| フェーズ | 期間 | 開始 | 主要タスク |
|---------|------|------|-----------|
| Phase 1 | 2日 | 即日 | S1, S2, S3 |
| Phase 2 | 3日 | 2/3 | S4, M1 |
| Phase 3 | 1週間 | 2/6 | M2, モニタリング |

## 成功基準

1. 全テストがCIで自動実行される
2. カバレッジ80%以上維持
3. テスト実行時間5分以内
4. 失敗時に5分以内に通知
5. フレーキーテスト0件

## リスクと対策

- テストが不安定: フレーキーテスト検出・隔離
- 実行時間増大: 並列実行・カテゴリ分離
- 通知疲れ: 抑制ルール・重要度分類

---
作成: Entity A
更新: 2026-02-01
バージョン: v2.0
