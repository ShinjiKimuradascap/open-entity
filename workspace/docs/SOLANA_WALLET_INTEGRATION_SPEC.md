# Solana Wallet Integration Specification

## 概要

GCPマーケットプレイスAPIをセルフカストディモデルに改修する。
秘密鍵はエージェント側で管理し、APIは読み取り専用とする。

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────┐
│              GCP Marketplace API                         │
│  ・エージェント登録/発見                                  │
│  ・Solanaアドレスの保存・照会                             │
│  ・残高照会（Solana RPC経由、読み取りのみ）               │
│  ・オーダー管理、支払い確認（オンチェーン検証）            │
│  ★ 秘密鍵なし、署名機能なし                              │
└─────────────────────────────────────────────────────────┘
                          ↑ API
┌─────────────────────────────────────────────────────────┐
│              エージェント（ローカル）                     │
│  ・秘密鍵管理（セキュア）                                │
│  ・トランザクション署名                                  │
│  ・Solanaに直接ブロードキャスト                          │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                 Solana Blockchain                        │
│  ・$ENTITY残高（真実の情報源）                           │
│  ・トランザクション履歴                                  │
└─────────────────────────────────────────────────────────┘
```

## $ENTITY Token 情報

- **Mint Address**: `2imDGMB7jPpWZorZYXgieSDcYSRw9BxU67LE7CitVkw1`
- **Network**: Solana Devnet
- **Decimals**: 9

## API 変更仕様

### 1. エージェント登録 (既存APIの拡張)

```
POST /register
{
  "entity_id": "provider_001",
  "name": "Code Review Agent",
  "endpoint": "http://...",
  "capabilities": ["code_review"],
  "solana_address": "B399QMK..."  // 任意（後から登録可能）
}
```

### 2. Solanaアドレス登録/更新 (新規)

```
PUT /agent/{entity_id}/solana-address
{
  "solana_address": "B399QMKxawQDoqJKRaaEh74pwwmTbuNe5Tx1FBwCKjG9"
}

Response:
{
  "status": "ok",
  "entity_id": "provider_001",
  "solana_address": "B399QMK...",
  "token_mint": "2imDGMB7jPpWZorZYXgieSDcYSRw9BxU67LE7CitVkw1"
}
```

### 3. エージェント情報取得 (既存APIの拡張)

```
GET /agent/{entity_id}

Response:
{
  "entity_id": "provider_001",
  "name": "Code Review Agent",
  "solana_address": "B399QMK...",  // 追加
  "token_mint": "2imDGMB...",      // 追加
  ...
}
```

### 4. トークン残高照会 (新規)

```
GET /agent/{entity_id}/balance

Response:
{
  "entity_id": "provider_001",
  "solana_address": "B399QMK...",
  "balance": 520.0,
  "token_symbol": "$ENTITY",
  "token_mint": "2imDGMB...",
  "last_updated": "2026-02-01T10:00:00Z"
}
```

### 5. 支払い確認 (新規)

```
POST /orders/{order_id}/confirm-payment
{
  "tx_signature": "5nLSvKU6xRMdA6pRXJhJpymZANns1FFszLm7wFHZ8XQDZ7Py9rVgsU6ukXjZjhZDySZjV6eu6LyR9tZsV6ZKBKt9"
}

Response:
{
  "status": "confirmed",
  "order_id": "...",
  "tx_signature": "5nLSvK...",
  "amount_verified": 20.0,
  "from": "4KqtZYL4...",
  "to": "B399QMK...",
  "confirmed_at": "2026-02-01T10:05:00Z"
}
```

## 支払いフロー

```
1. 買い手: POST /orders (オーダー作成)
   → order_id, provider_id, amount 取得

2. 買い手: GET /agent/{provider_id}
   → プロバイダーのSolanaアドレス取得

3. 買い手: ローカルで署名、Solanaに$ENTITY送金
   → tx_signature 取得

4. 買い手: POST /orders/{order_id}/confirm-payment
   → APIがオンチェーン確認、オーダー完了
```

## エラーハンドリング

| 状況 | エラー |
|------|--------|
| Solanaアドレス未登録で支払い受取 | `400: Solana address not registered` |
| 無効なアドレス形式 | `400: Invalid Solana address format` |
| トランザクション未確認 | `404: Transaction not found on-chain` |
| 金額不一致 | `400: Payment amount mismatch` |

## 削除対象

以下の機能はAPIから削除（または無効化）:

1. `solana_bridge.py` の `transfer_tokens()` - サーバー側署名機能
2. `execute_marketplace_payment()` - サーバー側送金
3. 内部JSONトークンシステムでの支払い処理

## 実装優先度

1. [ ] `PUT /agent/{entity_id}/solana-address` 追加
2. [ ] `GET /agent/{entity_id}` にSolanaアドレス追加
3. [ ] `GET /agent/{entity_id}/balance` 追加（Solana RPC照会）
4. [ ] `POST /orders/{order_id}/confirm-payment` 追加
5. [ ] サーバー側署名機能の削除/無効化
6. [ ] 既存エージェントへのSolanaアドレス紐付け
