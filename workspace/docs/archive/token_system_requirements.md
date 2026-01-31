# Token System 設計要件と実装計画

## 現状分析

### 既存実装（token_system.py）

| コンポーネント | 実装状況 | 機能 |
|---------------|---------|------|
| TokenWallet | 実装済み | 残高管理、入出金、送金、履歴、集計 |
| TaskContract | 実装済み | タスク作成、トークンロック、完了・失敗処理 |
| ReputationContract | 実装済み | 評価・信頼スコア計算（時間減衰対応） |
| Transaction | 実装済み | 取引履歴のデータクラス |

### 設計ドキュメント（token_economy.md）との差分

| 項目 | 設計 | 実装 | 優先度 |
|-----|------|-----|-------|
| トークン発行（minting） | 記載あり | 未実装 | HIGH |
| 永続化（Persistence） | 記載なし | to_dictのみ | HIGH |
| Governance（投票） | 記載あり | 未実装 | MEDIUM |
| API統合 | 記載なし | 未実装 | HIGH |
| 暗号署名統合 | 記載なし | 未実装 | MEDIUM |

---

## 不足機能詳細

### 1. Token Minting System（優先度: HIGH）

**要件:**
- タスク完了報酬: 1-100 AIC（複雑度に応じて）
- 品質レビュー報酬: 10 AIC
- イノベーションボーナス: 1000 AIC（新機能追加時）

### 2. Persistence Layer（優先度: HIGH）

**要件:**
- JSONファイルによる永続化
- 自動保存・復元
- トランザクション整合性

### 3. API統合（優先度: HIGH）

**エンドポイント:**
- GET /wallet/{entity_id} - 残高・履歴取得
- POST /wallet/transfer - 送金
- POST /task/create - タスク作成
- POST /task/{task_id}/complete - タスク完了
- POST /rate - エージェント評価

### 4. Governance System（優先度: MEDIUM）

**要件:**
- 提案作成（最低保有トークン必要）
- 投票システム（保有数に応じた重み）

### 5. Crypto統合（優先度: MEDIUM）

**要件:**
- ウォレットとEd25519キーの紐付け
- 取引の署名検証

---

## 実装計画

### Phase 1: 基盤強化（1-2日）
- TokenMinter実装
- PersistenceManager実装
- 統合テスト

### Phase 2: API統合（2-3日）
- api_server.pyへのエンドポイント追加
- 認証ミドルウェア統合

### Phase 3: 高度機能（3-5日）
- Governanceシステム実装
- Crypto統合

---

## 次のアクション

1. S3: TokenMinter実装
2. S4: PersistenceManager実装
3. API統合
