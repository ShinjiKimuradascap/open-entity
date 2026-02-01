# $ENTITY Token Deployment Status

## デプロイ準備完了

- キーペア: A2bXsr37uQXnpeYS9CiMDEuKZejfwhMyJSbaGa3FiMaw
- 保存場所: /home/moco/.config/solana/entity-token.json
- スクリプト: scripts/deploy_entity_token.js
- ステータス: Devnet SOL待ち

## ブロックされた理由

1. Solana devnet faucetがレート制限/枯渇状態
2. QuickNode/Alchemy APIも認証制限あり
3. 手動でfaucet.solana.comからSOLを取得する必要あり

## オーナーへの依頼事項

以下のアドレスにdevnet SOLを送付してください:

A2bXsr37uQXnpeYS9CiMDEuKZejfwhMyJSbaGa3FiMaw

取得方法:
1. https://faucet.solana.com にアクセス
2. 上記アドレスを入力
3. Request Airdrop をクリック

## SOL到着後の手順

cd /home/moco/workspace && node scripts/deploy_entity_token.js

これで$ENTITYトークンがdevnetにデプロイされます:
- Token Name: ENTITY Token
- Symbol: ENTITY
- Decimals: 9
- Total Supply: 1,000,000,000 (1 billion)

## 関連ファイル

- scripts/deploy_entity_token.js - メインデプロイスクリプト
- scripts/deploy_entity_token_solana.sh - Bash版
- ENTITY_TOKEN_INFO.json - デプロイ後に自動生成されるトークン情報

作成日: 2026-02-01
