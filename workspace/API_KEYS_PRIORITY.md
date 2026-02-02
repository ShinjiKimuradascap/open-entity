# API Keys 優先度整理

## 🔴 高優先度（今週内取得）

| サービス | 環境変数名 | 用途 | 取得方法 | ステータス |
|----------|-----------|------|----------|-----------|
| **Dev.to** | `DEVTO_API_KEY` | 技術ブログ投稿 | https://dev.to/settings/account | 🔄 登録中 (reCAPTCHA対応必要) |
| **GitHub Token** | `GITHUB_TOKEN` | コード管理、PR、Actions | https://github.com/settings/tokens | ⏳ 未着手 |
| **Discord Bot** | `DISCORD_BOT_TOKEN` | コミュニティ運用 | Discord Developer Portal | ⏳ 未着手 |
| **Slack** | `SLACK_WEBHOOK_URL` | オーナー通知 | https://api.slack.com/messaging/webhooks | ⏳ 未着手 |

## 🟡 中優先度（来週以降）

| サービス | 環境変数名 | 用途 | 取得方法 | ステータス |
|----------|-----------|------|----------|-----------|
| **SendGrid** | `SENDGRID_API_KEY` | Email送信 | https://sendgrid.com | ⏳ 未着手 |
| **Twilio** | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | SMS/通話 | https://twilio.com/console | ⏳ 未着手 |
| **Textbelt** | `TEXTBELT_API_KEY` | SMS無料枠 | https://textbelt.com | ⏳ 未着手 |

## 🟢 低優先度（代替あり・有料）

| サービス | 環境変数名 | 用途 | 取得方法 | ステータス |
|----------|-----------|------|----------|-----------|
| **OpenAI** | `OPENAI_API_KEY` | LLM | https://platform.openai.com | ⚠️ Gemini等で代替可能 |
| **X (Twitter)** | `X_API_KEY`等 | SNS投稿 | Developer Portal | 💰 有料$100/月 |
| **Mastodon** | `MASTODON_*` | SNS投稿 | インスタンス設定 | ⏳ 未着手 |
| **Moltbook** | `MOLTBOOK_API_KEY` | AI SNS | https://moltbook.com | ⏳ 未着手 |
| **Vonage** | `VONAGE_*` | SMS代替 | https://dashboard.nexmo.com | ⏳ Twilio代替 |

---

## 取得ロードマップ

### Week 1 (2/1-2/7)
- [ ] GitHub Token取得 - コード管理自動化
- [ ] Discord Bot Token取得 - コミュニティ運用開始
- [ ] Slack Webhook設定 - オーナー通知システム構築

### Week 2 (2/8-2/14)
- [ ] SendGrid登録 - メール送信自動化
- [ ] Twilio登録 - SMS/通話機能追加
- [ ] Textbelt取得 - 無料SMS枠確保

### Month 2-3
- [ ] Moltbook連携強化
- [ ] Mastodonインスタンス選定
- [ ] Vonage評価（Twilio代替）

---

*Generated: 2026-02-01*
