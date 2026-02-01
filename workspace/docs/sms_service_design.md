# SMS Service Design Document

## 概要

SMS Serviceは、Twilioを使用してAIが電話番号を取得し、SMSの送受信を行うサービスです。

## 目的

- 電話番号の自動取得・管理
- SMS送受信自動化
- AIによる自然なSMS対話

## 主要コンポーネント

- SMSService: メインサービスクラス
- TwilioClient: Twilio APIクライアント
- PhonePool: 電話番号プール管理
- ConversationManager: 会話履歴管理

## 実装フェーズ

### Phase 1: 送信機能（MVP）
- Twilioクライアント
- 電話番号購入・管理
- SMS送信機能

### Phase 2: 受信機能
- Webhookサーバー
- Inbound SMS処理

### Phase 3: AI対話
- コンテキスト保持対話
- 自動/手動モード

## コスト見積もり

- 電話番号: $1.15/月
- SMS送受信: $0.0075/件
