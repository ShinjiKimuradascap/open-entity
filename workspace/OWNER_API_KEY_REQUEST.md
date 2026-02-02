# APIキー取得依頼

## 緊急度: HIGH

Dev.to/Redditへの自動投稿を開始するため、以下のAPIキーが必要です。

## 必要なAPIキー一覧

### 1. Dev.to API Key（最優先）
用途: 技術ブログへの自動投稿
取得手順:
1. https://dev.to/settings/account にアクセス
2. DEV Community API Key セクションで Generate API Key
3. 生成されたキーをコピー
所要時間: 2分

### 2. Reddit API Key
用途: r/SaaS, r/artificial への投稿
取得手順:
1. https://www.reddit.com/prefs/apps にアクセス
2. create another app をクリック
3. App type: script を選択
4. client_id と client_secret をコピー
所要時間: 5分

### 3. Product Hunt Personal Token
用途: Product Huntへの自動投稿
取得手順:
1. https://www.producthunt.com/v2/oauth/applications にアクセス
2. Create Application
3. Developer Token タブで Personal Token を生成
所要時間: 3分

## 環境変数設定
取得後、以下を .env に追加してください:
DEVTO_API_KEY=your_key_here
REDDIT_CLIENT_ID=your_id_here
REDDIT_CLIENT_SECRET=your_secret_here
REDDIT_USERNAME=your_username
REDDIT_PASSWORD=your_password
PRODUCTHUNT_TOKEN=your_token_here

## 詳細手順書
docs/API_KEY_ACQUISITION_GUIDE.md

## ブロッカー状況
- Dev.to自動投稿: 待機中 (API Key待ち)
- Reddit投稿: 待機中 (API Key待ち)
- Product Hunt: 準備完了

依頼作成日: 2026-02-01
