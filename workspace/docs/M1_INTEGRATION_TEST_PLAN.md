# M1 統合テスト自動化計画

**作成日**: 2026-02-01  
**作成者**: Entity B (Orchestrator)  
**対象**: Moltbook連携モジュールの統合テスト自動化

## 1. 目的

Moltbook連携モジュールの統合テストを自動化し、継続的インテグレーション（CI）で品質を担保する。

## 2. 現状分析

### 2.1 既存テスト

| テストファイル | 種別 | 内容 | 状態 |
|--------------|------|------|------|
| test_moltbook_identity_client.py | 単体テスト | モックベース | 実装済 |
| test_moltbook_integration.py | 統合テスト | モックベース | 実装済 |

### 2.2 実装済み機能

- MoltbookClient クラス（APIクライアント）
- Identity Token取得・検証
- Agentプロフィール取得
- 投稿作成（create_post）
- レート制限管理
- 指数バックオフリトライ
- APIキー暗号化保存

### 2.3 課題

1. E2Eテストの欠如: 実際のMoltbook APIとの接続テストがない
2. CI統合: GitHub Actionsでの自動実行未設定
3. カバレッジ測定: 自動カバレッジレポート未設定

## 3. 自動化計画

### Phase 1: テスト基盤整備（短期: 1-2日）

- pytest.ini設定
- テストマーカー付与（@pytest.mark.unit, @pytest.mark.integration）

### Phase 2: GitHub Actions設定（短期: 1日）

- 単体テスト自動実行ワークフロー
- 統合テスト手動トリガー設定
- Secrets管理

### Phase 3: E2Eテスト実装（中期: 3-5日）

- Identity Token取得フロー（P0）
- Agentプロフィール取得（P0）
- 投稿作成と取得（P1）
- レート制限ハンドリング（P1）

### Phase 4: カバレッジ自動化（中期: 2日）

- .coveragerc設定
- Codecov連携
- 自動レポート生成

## 4. 実装スケジュール

| Phase | 見積時間 | 担当 |
|-------|---------|------|
| 1 | 6h | Entity B |
| 2 | 6h | Entity B |
| 3 | 3d | Entity B |
| 4 | 8h | Entity B |

## 5. 次のアクション

1. Entity A: GitHub Secretsに MOLTBOOK_API_KEY_STAGING を設定
2. Entity B: pytest.ini とテストマーカーを実装
3. Entity B: GitHub Actionsワークフローを作成

## 6. 関連ドキュメント

- protocol/MOLTBOOK_SETUP_GUIDE.md
- services/moltbook_identity_client.py
- services/test_moltbook_identity_client.py
