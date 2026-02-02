# API Key取得完全手順書

作成日: 2026-02-01
所要時間: 合計約1時間

---

## 高優先度（今週内に取得）

### 1. GitHub Token
用途: コード管理、PR作成、Actions自動化
URL: https://github.com/settings/tokens

手順:
1. Generate new token (classic)
2. Note: AI Collaboration Platform Automation
3. Expiration: 90日またはNo expiration
4. スコープ: repo, workflow, read:org, write:packages
5. Generate token → コピーして保存

環境変数: export GITHUB_TOKEN=ghp_xxx

### 2. Discord Bot Token
用途: コミュニティ運用、自動通知
URL: https://discord.com/developers/applications

手順:
1. New Application → Name: Open Entity Bot
2. Bot → Add Bot → Reset Token
3. MESSAGE CONTENT INTENT を ON
4. OAuth2 → URL Generator → bot選択
5. Permissions: Send Messages, Read Message History, View Channels
6. 生成URLを開いてサーバーに招待

環境変数: export DISCORD_BOT_TOKEN=MTAxxx

### 3. Slack Webhook
用途: オーナー通知システム
URL: https://api.slack.com/apps

手順:
1. Create New App → From scratch
2. Name: Open Entity Notifications
3. Incoming Webhooks → Activate ON
4. Add New Webhook to Workspace
5. チャンネル選択 → 許可 → URLコピー

環境変数: export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx

---

## 中優先度（来週以降）

### 4. SendGrid API Key
URL: https://app.sendgrid.com/settings/api_keys

手順:
1. アカウント作成 → メール確認
2. Create API Key → Name: Open Entity Marketing
3. Permissions: Mail Send Full Access
4. Create & View → コピー

環境変数: export SENDGRID_API_KEY=SG.xxx

### 5. Twilio
URL: https://www.twilio.com/try-twilio

手順:
1. アカウント作成 → 電話番号認証
2. DashboardでACCOUNT SIDとAUTH TOKENをコピー
3. Phone Numbers → Buy a number → SMS対応番号購入

環境変数:
export TWILIO_ACCOUNT_SID=ACxxx
export TWILIO_AUTH_TOKEN=xxx
export TWILIO_FROM_NUMBER=+1234567890

---

## .envファイルテンプレート

GITHUB_TOKEN=
DISCORD_BOT_TOKEN=
SLACK_WEBHOOK_URL=
SENDGRID_API_KEY=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=

---

最終更新: 2026-02-01
