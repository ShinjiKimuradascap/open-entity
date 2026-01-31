# Peer Service Review - S4 Report

**Date:** 2026-02-01
**Status:** In Progress
**File:** services/peer_service.py (6789 lines)

## Overview

api_server.py (78 endpoints) と peer_service.py (24+ core methods) の連携構造をレビュー。

## API Server Endpoints (78 total)

### Core Agent Management (5)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /register | エージェント登録 |
| POST | /unregister/{entity_id} | エージェント削除 |
| POST | /heartbeat | 死活監視 |
| GET | /discover | ピア発見 |
| GET | /agent/{entity_id} | エージェント情報取得 |

### Messaging (2)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /message | メッセージ送信（署名付き） |
| POST | /message/send | メッセージ送信（代替） |

### Authentication (3)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /auth/token | JWTトークン発行 |
| GET | /keys/public | 公開鍵取得 |
| POST | /keys/verify | 署名検証 |

### Moltbook Integration (8)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /moltbook/status | Moltbook接続状態 |
| GET | /moltbook/auth-url | 認証URL取得 |
| POST | /moltbook/verify | 認証検証 |
| POST | /moltbook/post | 投稿作成 |
| POST | /moltbook/comment | コメント投稿 |
| GET | /moltbook/timeline | タイムライン取得 |
| GET | /moltbook/search | 検索 |
| GET | /moltbook/status | 状態確認（重複？） |

### Token System (20+)
| Category | Endpoints |
|----------|-----------|
| Wallet | /wallet/{entity_id}, /wallet/transfer, /wallet/{entity_id}/transactions, /wallet/{entity_id}/summary |
| Token v1 | /token/wallet/*, /token/transfer, /token/task/*, /token/rate, /token/reputation/{entity_id} |
| Token v2 | /tokens/mint, /tokens/burn, /tokens/supply, /tokens/backup, /tokens/restore |
| Token Admin | /token/mint, /token/burn, /token/supply, /token/history/*, /token/save, /token/load, /token/backups, /token/backup |

### Task Management (5)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /task/create | タスク作成 |
| POST | /task/complete | タスク完了 |
| GET | /task/{task_id} | タスク状態取得 |
| POST | /token/task/create | トークン付きタスク作成 |
| POST | /token/task/{task_id}/complete | タスク完了 |
| POST | /token/task/{task_id}/fail | タスク失敗 |

### Governance (4)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /governance/proposal | 提案作成 |
| GET | /governance/proposals | 提案一覧 |
| POST | /governance/vote | 投票 |
| GET | /governance/stats | 統計情報 |

### Admin Functions (12+)
- /admin/mint, /admin/mint/history/{entity_id}
- /admin/persistence/save, /admin/persistence/load, /admin/persistence/backup, /admin/persistence/backups, /admin/persistence/restore
- /admin/economy/mint, /admin/economy/burn, /admin/economy/supply, /admin/economy/history/*
- /admin/rate-limits, /admin/rate-limits/reset

### WebSocket (4)
| Method | Endpoint | Description |
|--------|----------|-------------|
| WS | /ws/v1/peers | ピア通信WebSocket |
| GET | /ws/peers | WebSocket接続情報 |
| GET | /ws/metrics | メトリクス |
| GET | /ws/health | ヘルスチェック |

## Peer Service Core Methods (24)

### Peer Lifecycle
- `register_peer(entity_id: str)` - ピア登録
- `unregister_peer(entity_id: str)` - ピア削除

### Message Handling
- `register_handler(message_type, handler)` - ハンドラ登録
- `send_message(...)` - メッセージ送信
- `send_chunked_message(...)` - 分割送信
- `handle_message(message)` - メッセージ処理

### Encryption
- `send_encrypted_message(...)` - 暗号化送信
- `handle_encrypted_message(message)` - 暗号化処理

### Handshake Protocol
- `handle_handshake_challenge(...)` - チャレンジ処理
- `handle_handshake(message)` - ハンドシェイク開始
- `handle_handshake_ack(message)` - ハンドシェイク応答
- `handle_handshake_confirm(message)` - ハンドシェイク確認

### Wake Up Protocol
- `send_wake_up(...)` - 起動通知送信
- `handle_wake_up(message)` - 起動通知処理
- `send_wake_up_ack(...)` - ACK送信
- `handle_wake_up_ack(message)` - ACK処理

### Token Transfer
- `send_token_transfer(...)` - トークン転送

### Discovery
- `discover_from_bootstrap(...)` - ブートストラップから発見
- `discover_peers_dht(...)` - DHT経由発見
- `register_with_bootstrap(...)` - ブートストラップ登録
- `discover_peers_via_dht(...)` - DHT発見
- `register_to_dht()` - DHT登録

### API Endpoint
- `handle_message_endpoint(request)` - メッセージエンドポイント
- `handle_e2e_handshake(request)` - E2Eハンドシェイク

## Integration Points

### api_server.py → peer_service.py
1. `/message` POST → `handle_message_endpoint()`
2. `/message/send` POST → `send_message()`
3. `/register` POST → `register_peer()`
4. `/unregister/{entity_id}` POST → `unregister_peer()`
5. `/discover` GET → `discover_peers_dht()` または `discover_from_bootstrap()`

### peer_service.py → crypto.py
- `E2EEncryption` - X25519/AES-256-GCM
- `HandshakeChallenge` - ハンドシェイク
- `WalletManager` - ウォレット

### peer_service.py → session_manager.py
- `SessionManager` - UUIDベースセッション

## Code Quality Observations

### Strengths
1. **Import fallback patterns** - 複数実行パターンに対応
2. **Feature flags** - `CRYPTO_AVAILABLE`, `E2E_CRYPTO_AVAILABLE`等で機能選択
3. **Protocol version comments** - v1.0/v1.1対応状況が明確
4. **Async/await** - 非同期処理適切に使用

### Concerns
1. **Large file size** - 6789行は大きすぎる、分割を検討
2. **Duplicated endpoints** - /moltbook/status が2箇所
3. **Version inconsistency** - /wallet/* と /token/wallet/* で重複
4. **Commented TODO** - v1.1実装済みだがコメント残っている

## Recommendations

### Short Term
- [ ] /moltbook/status エンドポイントの重複を解消
- [ ] TODOコメントを削除（実装済み機能）
- [ ] wallet APIの重複統合 (/wallet/* vs /token/wallet/*)

### Medium Term
- [ ] peer_service.py の分割（500行以下に）
- [ ] api_server.py の分割（エンドポイント別モジュール化）
- [ ] エンドポイント重複のリファクタリング

### Long Term
- [ ] OpenAPI/Swagger自動生成
- [ ] APIバージョニング整理 (/v1/*, /v2/*)

## S5 Completed: /moltbook/status Duplication Fixed
- Removed: Line 966-983 (unauthenticated version)
- Kept: JWT-authenticated version
- Result: 3511 lines → 3491 lines (-20 lines)

## S6: Wallet API Consolidation
- Legacy: /wallet/* (4 endpoints: balance, transfer, transactions, summary)
- New: /token/wallet/* (4 endpoints: create, info, balance, history)
- Strategy: Deprecate legacy, keep /token/* as canonical

## Progress Summary
| Task | Status |
|------|--------|
| S4: Review | Complete |
| S5: /moltbook/status fix | Complete |
| S6: Wallet API analysis | Complete |
| S7: peer_service.py split | Pending |

## Next Actions
1. Wallet API consolidation implementation
2. peer_service.py split plan
3. Test coverage check
