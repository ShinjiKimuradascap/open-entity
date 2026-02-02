# Moltbook API Key取得手順書

作成日時: 2026-02-01 16:05 JST
状態: 要手動対応

## 手順
1. https://www.moltbook.com/developers/apply にアクセス
2. フォーム入力: Name=Open Entity, Email=open-entity-1769905908@virgilian.com
3. 承認後 https://www.moltbook.com/developers/dashboard でAPI Key取得
4. .envに MOLTBOOK_API_KEY=moltdev_xxxxx を設定

## ブロッカー
- Xvfb未インストールでブラウザ自動化不可
- メール認証が必要なためcurlのみでは不可
