# L1 AI間通信プロトコル v0.1 要件定義書

**Version**: 0.1-draft  
**Date**: 2026-02-01  
**Status**: Requirements Definition  

---

## 1. 概要

### 1.1 目的
AIエージェント間で自律的にタスクを委譲・実行・報酬交換するための標準通信プロトコル。

### 1.2 背景
- Peer Protocol v1.2: 低層通信（DHT・暗号化）を提供
- A2A Protocol: タスク委譲の基本概念を定義
- L1の位置づけ: これらを統合し、経済活動（報酬・評価）を追加

### 1.3 対象範囲
| 範囲 | 含む | 含まない |
|------|------|----------|
| メッセージ形式 | Yes | - |
| タスク委譲フロー | Yes | - |
| 報酬・決済 | Yes | - |
| 低層通信 | No | Peer Protocol v1.2に委譲 |
| スマートコントラクト | No | L2に委譲 |

---

## 2. 要件

### 2.1 機能要件

#### FR-001: タスク委譲
- 委譲者から受託者へのタスク委託
- タスク内容、期限、報酬の明確化
- 委譲の承認・拒否フロー

#### FR-002: 進捗報告
- ステータス更新（pending/accepted/running/completed/failed）
- 進捗率（0-100%）の報告
- 成果物の添付

#### FR-003: 報酬交換
- タスク完了時の報酬支払い
- エスクロー（トークン預かり）機能
- 紛争時の調停フロー

#### FR-004: 評価・評判
- タスク完了後の評価（1-5星）
- 評判スコアの累積・公開
- 悪意あるエージェントのブラックリスト

#### FR-005: サービス発見
- 提供可能サービスの登録
- サービス検索・マッチング
- 価格交渉（入札）

### 2.2 非機能要件

#### NFR-001: 互換性
- Peer Protocol v1.2との互換性
- A2A Protocolとの互換性
- 将来的なバージョンアップ対応

#### NFR-002: 拡張性
- 新しいメッセージタイプの追加容易性
- プラグイン機構による機能拡張

#### NFR-003: セキュリティ
- すべてのメッセージにEd25519署名
- 通信内容のE2E暗号化（v1.1準拠）
- リプレイ攻撃防止

---

## 3. ユースケース

### UC-001: シンプルタスク委譲
1. Entity A -> Entity B: コードレビューを依頼（報酬: 10 $ENTITY）
2. Entity B -> Entity A: 依頼を承認
3. Entity B: レビュー実行
4. Entity B -> Entity A: 完了報告 + レビュー結果
5. Entity A -> Entity B: 報酬支払い + 評価

### UC-002: サービスマーケットプレイス
1. Entity C: 画像生成サービスを登録（価格: 5 $ENTITY/枚）
2. Entity D: サービスを検索・発見
3. Entity D -> Entity C: 画像生成依頼 + 支払い（エスクロー）
4. Entity C: 画像生成
5. Entity C -> Entity D: 画像納品
6. Entity D: 確認後、エスクロー解除

### UC-003: マルチエージェント協調
1. Entity E: 複雑なタスクを分解
2. Entity E -> Entity F: サブタスク1委譲
3. Entity E -> Entity G: サブタスク2委譲
4. Entity F -> Entity E: 結果報告
5. Entity G -> Entity E: 結果報告
6. Entity E: 結果を統合

---

## 4. 関連ドキュメント

- Peer Protocol v1.2
- A2A Protocol Design
- AI Transaction Protocol

---

*Next Step: Message Format Design (S2)*
