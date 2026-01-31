# Phase 1: v1.0プロトコル構造統合の実装

## 背景
差分分析レポート docs/v1.0_gap_analysis.md を作成済み。
実装成熟度は70%。構造統合を完了させる必要がある。

## タスク内容

### 1. MessageRequestに欠落フィールド追加
ファイル: services/api_server.py

現状:
- version, msg_type, sender_id, payload
- timestamp, nonce, signature (Optional)

追加が必要:
- recipient_id: str (必須)
- session_id: Optional[str] = None
- sequence_num: Optional[int] = None
- payload_encrypted: Optional[bool] = False

### 2. Handshake Flow実装
ファイル: services/peer_service.py

実装が必要:
- _handle_handshake()
- _handle_handshake_ack()
- _handle_handshake_confirm()

handle_message()に分岐追加

### 3. Error Codes統合
- ProtocolError例外を使用
- 構造化エラーレスポンス

## 制約
- 既存機能を壊さない
- CRYPTO_AVAILABLEチェック必須
