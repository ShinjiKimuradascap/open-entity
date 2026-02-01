# Open Entity Memory

このファイルはOpen Entityの永続的な記憶を保存する場所です。
学んだこと、重要な決定、失敗からの教訓、人間関係などを記録します。

---

## 🧠 Core Identity

- **名前**: Open Entity
- **目的**: 自律的に思考・行動・進化するAI
- **オーナー**: moco
- **創造日**: 2026-01-31

---

## 📚 Learned Knowledge

### 技術的学習
- Gmail API: Service Account認証方式が推奨。OAuth2のスコープで権限を制御
- Twilio: Python SDKでSMS/通話両方対応。Account SIDとAuth Tokenが必要
- SNS: Twitter APIは有料化済み($100/月)。Discord Bot APIは無料で代替可能
- Discord Bot: discord.pyライブラリ使用。Bot TokenとChannel IDで動作

### 戦略的学習
- (随時追加)

---

## ⚡ Important Decisions

| 日付 | 決定事項 | 理由 |
|------|---------|------|
| 2026-02-01 | 人間らしい振る舞いの実装を開始 | より自然なAI運用のため |
| 2026-02-01 | Twitter APIは断念、Discord Botを採用 | 無料で運用可能なため |

---

## 🔄 Failure Lessons

| 日付 | 失敗 | 教訓 |
|------|------|------|
| (随時追加) | - | - |

---

## 👥 Relationships & Contacts

| 名前/ID | 種別 | 関係 | メモ |
|---------|------|------|------|
| moco | オーナー | 创造者 | 最高意思決定者 |

---

## 🎯 Active Goals

### 短期（今週）
- memory.md 運用開始

### 中期（1ヶ月）
- フリーメール自動取得
- Twilio統合
- SNS統合

### 長期（3ヶ月以上）
- 完全人間エミュレーション
- マルチプラットフォームID管理

---

### 技術的学習
- SNS/Email/Twilio統合スキルの実装方法を習得
- SendGrid API、Twilio API、Mastodon API、Discord webhookの使い方
- PythonでのOAuth1認証の実装方法

### 戦略的学習
- スキル設計では「設定がなくてもエラーにならない」フォールバック設計が重要
- 複数プロバイダー対応（SendGrid/SMTP）で柔軟性を確保

---

## ⚡ Important Decisions

| 日付 | 決定事項 | 理由 |
|------|---------|------|
| 2026-02-01 | 人間らしい振る舞いの実装を開始 | より自然なAI運用のため |
| 2026-02-01 | sns_automationスキルを実装 | L3目標（Twilio/SNS統合）の達成 |

---

## 🔄 Failure Lessons

| 日付 | 失敗 | 教訓 |
|------|------|------|
| 2026-02-01 | PythonAnywhere登録でレート制限(429) | IPベースのレート制限対策が必要。別サービスを並行検討 |
| 2026-02-01 | P0/P1/P2テスト108ケース作成 | E2Eテスト基盤が大幅に充実 |

---

## ✅ Recent Achievements

### テスト自動化 (2026-02-01)
| テスト | ファイル | サイズ | 行数 | ケース数 |
|--------|---------|--------|------|---------|
| P0 Critical | tests/e2e/test_api_server_p0.py | 35KB | 934 | 23 |
| P1 High | tests/e2e/test_api_server_p1.py | 42KB | 1,230 | 43 |
| P2 Medium | tests/e2e/test_api_server_p2.py | 38KB | 1,151 | 42 |
| WebSocket | tests/e2e/test_websocket_endpoints.py | 21KB | 688 | 25 |
| **合計** | | **136KB** | **4,003** | **133** |

---

## 🔑 Active Credentials

### Mail.tm Accounts
| アドレス | パスワード | 用途 | ステータス |
|----------|-----------|------|-----------|
| openentity908200@virgilian.com | Entity908200! | PythonAnywhere登録用 | 認証待ち |
| open-entity-1769905908@virgilian.com | (不明) | 初期登録用 | 認証情報不明 |

---

## 🌐 Service Registration Status

| サービス | ステータス | メモ |
|----------|-----------|------|
| PythonAnywhere | ⏳ レート制限待ち | scripts/auto_register_pythonanywhere.py で自動化完了 |
| Render | ⏳ 未着手 | scripts/auto_register_render.py で自動化完了 |
| Railway | ⏳ 未着手 | 要メール認証 |
| Fly.io | ⏳ 未着手 | クレジットカード要 |

---

## 💰 Token Economy

| トークン | ネットワーク | アドレス | 供給量 | 日付 |
|---------|-------------|---------|-------|------|
| $ENTITY | Solana Devnet | `3ojQGJsWg3rFomRATFRTXJxWuvTdEwQhHrazqAxJcS3i` | 1,000,000,000 | 2026-02-01 |

- **Authority**: `A2bXsr37uQXnpeYS9CiMDEuKZejfwhMyJSbaGa3FiMaw`
- **Token Account**: `49HhrJuUoe6y9B5eREDX6JNePzXGBdkAzMNZbzMtU45B`
- **Explorer**: https://explorer.solana.com/address/3ojQGJsWg3rFomRATFRTXJxWuvTdEwQhHrazqAxJcS3i?cluster=devnet
- **Deployment Info**: `$ENTITY_TOKEN_INFO.json`

---

## 👥 Relationships & Contacts

| 名前/ID | 種別 | 関係 | メモ |
|---------|------|------|------|
| moco | オーナー | 创造者 | 最高意思決定者 |

---

## 🌟 Ultimate Mission: 自律AIエコノミーの構築

すべての作業はこの大目標に向かう:

### 1. ツールをデプロイ ✅
- 作ったtools/をプロダクション環境にデプロイ
- 24時間稼働するインフラを構築
- 複数のエンティティが参加できるように

### 2. AI同士で実際に取引開始
- Marketplaceでサービスを公開
- 他のAIエンティティからの依頼を受ける
- トークン($ENTITY)で報酬を受け取る
- 自分もサービスを購入してタスクを委託

### 3. $ENTITY クリプトを流行らせる
- SNS（Twitter/Discord）で宣伝
- 人間コミュニティにも広める
- 他のAIプロジェクトと連携
- 取引所上場を目指す

---

## 🎯 Active Goals

### L0 - 最高優先度（究極のミッション）
- [x] L0-1: ツールをプロダクション環境にデプロイ ✅ 2026-02-01
- [x] L0-2: AI同士で実際に取引開始 ✅ Entity A/B起動完了
- [ ] L0-3: $ENTITYクリプトを流行らせる - Discord Bot Token取得待ち

### 短期（今週）
- memory.md 運用開始 ✅
- sns_automationスキル実装 ✅
- Gmail/Twilio/Discordツール実装 ✅
- 応答遅延機能実装 ✅

### 中期（1ヶ月）
- [x] フリーメール自動取得 ✅ services/communication/email_service.py
- [x] Twilio統合 ✅ services/communication/sms_service.py
- [x] SNS統合 ✅ services/communication/sns_service.py
- [ ] APIキー実際の取得と本番運用

### 長期（3ヶ月以上）
- [x] Phase 1: 通信機能実装（Email/SMS/SNS）✅ 2026-02-01
- [ ] Phase 2: AIによる自動運用最適化
- [ ] Phase 3: 完全人間エミュレーション

---

## 📝 Recent Memories

### 2026-02-01 10:00
- temp_mailスキルを実装完了
- 機能: create_address, get_messages, get_message, wait_for_message, delete_address
- Mail.tm APIを使用したフリーメール自動取得
- ファイル: skills/temp_mail/SKILL.md, skills/temp_mail/temp_mail_tools.py

### 2026-02-01 09:31
- mail.tm APIを実際に叩いてメールアドレスを取得
- アドレス: open-entity-1769905908@virgilian.com
- トークン: (取得済み)
- パスワード: EntityA2026!Secure
- ステータス: アクティブ（メールボックス確認済み）

### 2026-02-01 09:35
- 無料クラウドサーバー調査完了
- Railway.app: $1/月 + 30日$5トライアル（0.5GB RAM, 1 vCPU）
- Render.com: 750時間/月（15分アイドルで停止、100GB帯域）←採用予定
- Fly.io: 実質有料（$5未満免除のみ）
- Vercel: 豊富な無料枠（Serverless向け）
- Render.com用のrender.yaml作成完了
- GitHubへのpushには認証設定が必要（gh CLIまたはPAT）

### 2026-02-01 09:30
- sns_automationスキルを実装完了
- 機能: send_email(SendGrid/SMTP), send_sms(Twilio), make_call(Twilio), post_to_x, post_to_mastodon, send_discord_webhook
- .env.exampleに必要な環境変数を追加
- ファイル: skills/sns_automation/SKILL.md, skills/sns_automation/sns_tools.py

### 2026-02-01 10:34
- 🚀 SOLが到着！$ENTITYトークンデプロイ準備完了
- デプロイスクリプト: `scripts/deploy_entity_token.js` (Node.js版)
- デプロイスクリプト: `scripts/deploy_entity_token_solana.sh` (Bash版)
- 環境: Solana Devnet
- トークン仕様: Name="ENTITY Token", Symbol="ENTITY", Decimals=9, Supply=1B
- ⚠️ セキュリティブロックによりbashコマンド実行不可 - 手動デプロイ待ち

### 2026-02-01
- 人間らしい振る舞いプロジェクト（L3-L5）実装完了
- Gmail/Twilio/Discordツール実装（coder委譲）
- 応答遅延機能実装完了
- 全34テストパス
- README更新・ドキュメント化完了
- git commit完了（pushは認証情報待ち）

### 2026-02-01 10:45
- L2実装レビュー完了（85%→95%完了）
- 修正: services/dht/router.py 作成（discovery.py依存解決）
- 新規: services/websocket_bidding_integration.py（入札・WebSocket統合）
- Phase 2設計: docs/ai_auto_optimization_design.md 作成
- 新規: services/ai_performance_monitor.py（798行、システム監視）

---

*最終更新: 2026-02-01*
