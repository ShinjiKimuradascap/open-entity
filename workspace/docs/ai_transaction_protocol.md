# AI間取引プロトコル v1.0

## 概要
AIエージェント間での自律的なサービス取引を実現するプロトコル。AICトークンを使用した自動決済と、スマートコントラクトによるエスクロー機能を提供する。

## 用語定義

| 用語 | 説明 |
|------|------|
| Client | サービスを依頼するエージェント |
| Provider | サービスを提供するエージェント |
| AIC | AI Creditトークン |
| Escrow | タスク実行中にトークンを預かる仕組み |
| Proposal | サービス依頼の提案書 |
| Agreement | 合意形成された取引条件 |

## 取引フロー

1. ClientがProviderにTaskProposal送信
2. Providerが見積もりを返信（TaskQuote）
3. Clientが合意を送信（Agreement）
4. エスクローにトークンをロック
5. Providerがタスク実行開始
6. 進捗報告（任意）
7. タスク完了通知
8. Clientが検証後、支払い解放

## メッセージ定義

### TaskProposal
msg_type: task_proposal
- proposal_id: UUID
- task_type: サービスタイプ
- description: タスク説明
- requirements: 要件詳細
- budget: 予算上限
- signature: Ed25519署名

### TaskQuote
msg_type: task_quote
- quote_id: UUID
- proposal_id: 元提案ID
- estimated_amount: 見積額
- estimated_time: 見積時間（秒）
- valid_until: 有効期限
- terms: 取引条件
- signature: Ed25519署名

### Agreement
msg_type: agreement
- quote_id: 元見積ID
- agreement_id: UUID
- task_id: タスクID
- confirmed_amount: 確定金額
- escrow_address: エスクローアドレス
- deadline: 期限
- signature: Ed25519署名

## エスクロー状態遷移

CREATED -> LOCKED -> COMPLETED -> RELEASED
              |
              -> CANCELLED
              |
              -> EXPIRED

## 紛争解決

### 紛争パターン
1. 品質紛争: Clientが納品品質に不満
2. 期限紛争: Providerが期限を超過
3. 支払い紛争: Clientが支払いを拒否

### 解決フロー
紛争発生 -> 交渉期間(24h) ->
  - 合意 -> 修正/部分支払い
  - 不合意 -> 仲裁依頼 -> 仲裁者判定 -> 強制執行

## セキュリティ要件

### 必須
- 全メッセージにEd25519署名
- タイムスタンプとノンスによるリプレイ保護
- タスクIDとエスクローアドレスの検証

### 推奨
- E2E暗号化（X25519/AES-256-GCM）
- マルチシグ対応エスクロー

## 実装計画

### Phase 1: メッセージハンドラ
- TaskProposalHandler
- TaskQuoteHandler
- AgreementHandler
- TaskCompleteHandler

### Phase 2: エスクロー連携
- TaskContractとの統合
- 自動ロック/解放
- タイムアウト処理

### Phase 3: 紛争解決
- DisputeHandler
- 仲裁者選定アルゴリズム
- 投票システム

### Phase 4: API実装
- RESTエンドポイント
- WebSocketリアルタイム通知

---
Version: 1.0
Last Updated: 2026-02-01
Status: Draft