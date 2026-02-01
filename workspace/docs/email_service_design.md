# Email Service Design Document

## 概要

Email Serviceは、AIが人間のようにメールを取得・管理・返信するためのコミュニケーション基盤です。

## 目的

- フリーメールアカウントの自動取得・管理
- AIによるメールの自動解析・分類・返信
- 複数メールプロバイダー（Gmail/Outlook等）の統一管理

## 主要コンポーネント

- EmailService: メインサービスクラス
- EmailClient: 抽象基底クラス
- GmailClient: Gmail IMAP/OAuth2実装
- OutlookClient: Outlook Graph API実装
- EmailParser: メール解析・分類
- EmailResponder: AI自動返信エンジン
- AccountManager: アカウント管理

## 実装フェーズ

### Phase 1: Gmail OAuth2対応（MVP）
- Gmail OAuth2認証フロー
- IMAP/SMTP接続
- メール送受信基本機能
- SQLiteストレージ

### Phase 2: Outlook対応
- Microsoft Graph API
- Outlookメール連携

### Phase 3: AI統合
- OpenAI/Gemini API連携
- 自動返文生成

## セキュリティ

- OAuth2 tokens暗号化保存
- レートリミット実装
- 送信制限管理
