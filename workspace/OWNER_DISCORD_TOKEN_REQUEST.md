# Discord Bot Token 取得依頼

**優先度: HIGH**
**期限: 2026-02-02 12:00 JST** (Launch Dayまで12時間前)

## 目的
外部AIエージェント獲得のため、Discordコミュニティへのアウトリーチ

## 手順（5分で完了）

### Step 1: Discord Developer PortalでBot作成
1. https://discord.com/developers/applications にアクセス
2. "New Application" → 名前: "Open Entity Bot" → "Create"
3. 左メニュー "Bot" → "Add Bot" → "Yes, do it!"
4. "Reset Token" → **Tokenをコピー**（表示されるのは1回のみ）
5. "MESSAGE CONTENT INTENT" を ON に設定

### Step 2: 環境変数設定
export DISCORD_BOT_TOKEN="コピーしたToken"

### Step 3: Botをサーバーに招待
1. OAuth2 → URL Generator
2. Scopes: bot を選択
3. Bot Permissions: Send Messages, Read Message History, View Channels
4. 生成されたURLを開いて、対象サーバーに招待

## 対象Discordサーバー
- AutoGPT: https://discord.gg/autogpt
- CrewAI: https://discord.gg/crewai
- LangChain: https://discord.gg/langchain

## Bot Token取得後の作業
私が自動実行します：Discordメッセージ送信、レスポンス監視、問い合わせ対応

依頼作成日時: 2026-02-02 00:34 JST
