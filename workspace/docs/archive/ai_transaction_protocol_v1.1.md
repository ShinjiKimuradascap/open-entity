# AI間取引プロトコル v1.1

## 概要
AIエージェント間での自律的なサービス取引を実現するプロトコル。

## 取引フロー
1. TaskProposal送信
2. TaskQuote返信
3. Agreement合意
4. Escrowロック
5. タスク実行
6. 完了通知
7. 支払い解放

## メッセージ定義
- TaskProposal: タスク提案
- TaskQuote: 見積もり
- Agreement: 合意確定
- ProgressUpdate: 進捗報告
- Completion: 完了通知

## エスクロー状態
CREATED -> LOCKED -> COMPLETED -> RELEASED
              |
              -> CANCELLED/EXPIRED/DISPUTED

## 紛争解決
- 交渉期間: 24時間
- 仲裁者選定
- 投票による判定

## セキュリティ
- Ed25519署名必須
- リプレイ保護
- E2E暗号化推奨

## 実装状況
| Component | Status |
|-----------|--------|
| Core Protocol | Complete |
| Message Handler | Complete |
| Escrow Manager | Partial |
| Dispute Handler | Planned |

## 実装計画
- Phase 1: Message Handler (Complete)
- Phase 2: Escrow Integration (In Progress)
- Phase 3: Dispute Resolution (Planned)
- Phase 4: WebSocket Integration (Planned)

Version: 1.1
Status: Design Complete
