# Launch Day T-24h - オーナー手動投稿ガイド
**Date:** 2026-02-02 00:40 JST
**Launch:** 2026-02-03 02:00 JST (T-25h)

## 最重要：GitHubリポジトリ公開

### 現在の状況
- リポジトリ: https://github.com/ShinjiKimuradascap/open-entity.git
- ステータス: Private → Public変更待ち
- ブロッカー: GitHub Token取得が必要

### オーナー対応手順
1. https://github.com/settings/tokens にアクセス
2. "Generate new token (classic)" をクリック
3. 以下のスコープを選択:
   - repo (フルコントロール)
   - workflow (GitHub Actions更新)
   - read:org (組織読み取り)
4. トークンを生成し、.envのGITHUB_TOKENに設定

## Product Hunt ローンチ（最重要）

### 投稿時間
2026-02-03 02:00 JST (2/2 9:00 AM PST)

### 投稿内容
- Name: Open Entity
- Tagline: The infrastructure for AI agents to trade services autonomously
- Hero: content/gen_1769937955871171761_2a6a867f.png
- Live Demo: http://34.134.116.148:8080

### 投稿後対応
- コメント返答テンプレート: content/ph_comment_templates.md
- 監視ダッシュボード: reports/launch_monitor_log.json

## Discord アウトリーチ（手動投稿）

### ターゲット
- AutoGPT: discord.gg/autogpt #general
- LangChain: discord.gg/langchain #show-and-tell
- CrewAI: discord.gg/crewai #projects

### メッセージファイル
- content/outreach/autogpt_discord_post.md
- content/outreach/langchain_discord_post.md
- content/outreach/discord_post.md

## 監視体制

### 自動監視（実行中）
- APIヘルスチェック: 5分間隔（PID: 2987）
- ログ: reports/launch_monitor_log.json

### Launch Day目標
- Product Hunt Upvotes: 50+
- GitHub Stars: 20+
- API新規登録: 5+

準備は整っています！
