# OpenAPI/Swagger 統合計画

## 概要

FastAPIの自動OpenAPI生成機能を活用し、APIドキュメントを自動化・統合する計画。

## 目標

1. **自動生成ドキュメント**: FastAPIのopenapi()メソッドからOpenAPI 3.0スキーマを自動生成
2. **Swagger UI統合**: 対話的APIドキュメント（/docs）の提供
3. **ReDoc統合**: 美しい静的ドキュメント（/redoc）の提供
4. **ハイブリッド構成**: 自動生成と手動ドキュメントの統合

## 現状分析

### 強み
- FastAPIは標準でOpenAPI生成をサポート
- scripts/generate_api_docs.py が既に作成済み
- APIエンドポイントは整然と定義されている

### 課題
- 一部のエンドポイントにdocstringが不足
- モデルのField descriptionが不完全
- 手動ドキュメント（API_REFERENCE.md）との同期

## 実装計画

### Phase 1: スキーマ強化（短期: 1-2日）

#### 1.1 Pydanticモデルの強化
- Field descriptionの追加
- example値の設定
- バリデーション制約の明記

対象ファイル:
- services/api_server.py
- services/token_system.py
- services/governance/models.py
- services/marketplace/service_registry.py

### Phase 2: 自動化スクリプト強化（短期: 1日）

- --watchモード: ファイル変更時に自動再生成
- --validateモード: OpenAPIスキーマの検証
- CI/CD統合: .github/workflows/docs.yml

### Phase 3: Swagger UI / ReDoc統合（短期: 1日）

FastAPI標準機能の有効化とカスタマイズ:
- /docs - Swagger UI
- /redoc - ReDoc
- カスタムCSS/JSの適用

### Phase 4: ハイブリッドドキュメント構成（中期: 2-3日）

- API_REFERENCE_AUTO.md: 自動生成（CIで更新）
- API_REFERENCE.md: 手動（概念説明、ユースケース）
- guides/: チュートリアル
- examples/: コード例

## 実装スケジュール

| フェーズ | 期間 | 成果物 |
|---------|------|-------|
| Phase 1 | 1-2日 | モデル強化、docstring追加 |
| Phase 2 | 1日 | CI/CD統合、自動化スクリプト強化 |
| Phase 3 | 1日 | Swagger UI/ReDoc統合 |
| Phase 4 | 2-3日 | ハイブリッド構成、同期メカニズム |

## 次のアクション

1. Phase 1開始: PydanticモデルのField description追加
2. 優先度設定: 使用頻度の高いエンドポイントから順次強化
3. チケット作成: 各エンドポイントのdocstring追加をタスク化

---
作成日: 2026-02-01
作成者: orchestrator
バージョン: 1.0
