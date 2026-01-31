# Moltbook Integration Test Plan

## 概要
Moltbook連携モジュールの統合テスト計画

## テスト環境要件

### 必須環境変数
- MOLTBOOK_API_KEY: Moltbook APIキー（実際のAPIテスト用）
- MOLTBOOK_AGENT_ID: エージェントID
- MOLTBOOK_BASE_URL: APIエンドポイント（デフォルト: https://api.moltbook.com）

### モックテスト環境
- APIキー未設定時は自動的にモックモードでテスト実行
- 全ての外部API呼び出しをモック化

## テストカテゴリ

### 1. 接続テスト
- TC-MB-001: API接続確認（有効なAPIキーで接続→認証成功）
- TC-MB-002: 認証エラー（無効なAPIキー→AuthenticationError）
- TC-MB-003: レート制限（制限超過→RateLimitError）

### 2. 投稿機能テスト
- TC-MB-004: 投稿作成（有効コンテンツ→投稿ID返却）
- TC-MB-005: 投稿取得（既存投稿→データ返却）
- TC-MB-006: 空コンテンツ拒否（バリデーションエラー）
- TC-MB-007: 長文コンテンツ（最大長超過→エラー）

### 3. Peer連携テスト
- TC-MB-008: Peerステータス投稿
- TC-MB-009: Peer同期
- TC-MB-010: メンション処理

### 4. エラーハンドリングテスト
- TC-MB-011: タイムアウト処理
- TC-MB-012: サーバーエラー
- TC-MB-013: ネットワーク障害
- TC-MB-014: リソース未発見

### 5. 統合フローテスト
- TC-MB-015: E2Eタスク報告フロー
- TC-MB-016: 定期ステータス更新
- TC-MB-017: PeerService統合

## テスト実行手順

### フェーズ1: モックテスト（APIキー不要）
cd services && python -m pytest test_moltbook_integration.py -v

### フェーズ2: 統合テスト（APIキー必要）
export MOLTBOOK_API_KEY="your_key"
python -m pytest test_moltbook_integration.py::TestMoltbookClient -v

## 現在の状態
- 実装: 完了 (moltbook_integration.py)
- 単体テスト: 実装済み (test_moltbook_integration.py)
- APIキー: 未設定（手動取得必要）
- 統合テスト: 準備中

## 次のアクション
1. Moltbook.com でAPIキー取得
2. .env に MOLTBOOK_API_KEY を設定
3. 統合テスト実行

---
作成日: 2026-02-01
