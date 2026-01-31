# AI間通信ネットワーク設計 L1

## 概要
分散型AIエージェント通信ネットワークのアーキテクチャ設計。

## 現状分析

### 実装済み機能 (v0.4.0)
- Ed25519署名によるメッセージ認証
- JWT + API Key認証
- リプレイ攻撃防止（タイムスタンプ+ノンス）
- 基本的なサービスレジストリ
- Peer間通信（HTTPベース）
- ハートビート管理

### プロトコル定義 (v1.0)
- E2E暗号化（X25519/AES-256-GCM）
- Perfect Forward Secrecy
- 分散型ピアディスカバリー
- メッセージ順序保証・再送制御

## 目標アーキテクチャ

分散型P2Pネットワーク + 冗長レジストリノード

## 実装フェーズ

### Phase 1: E2E暗号化レイヤー ✅ COMPLETE
- [x] X25519鍵交換 (ECDH)
- [x] AES-256-GCM暗号化
- [x] セッション管理 (UUID v4)
- [x] Perfect Forward Secrecy (エフェメラル鍵)
- [x] 3-wayハンドシェイク
- [x] シーケンス番号・リプレイ保護
- [x] セッション有効期限管理

**実装ファイル**: `services/e2e_crypto.py`
**テストファイル**: `services/test_e2e_crypto.py`

### Phase 2: 分散型レジストリ 🔄 IN PROGRESS
- [x] Gossipプロトコル (実装済)
- [x] CRDTベースマージ (実装済)
- [x] ハートビート管理 (実装済)
- [ ] ブートストラップノード自動発見
- [ ] ネットワークパーティション対応
- [ ] エントリ署名検証

**実装ファイル**: `services/distributed_registry.py`

### Phase 3: 信頼性レイヤ️ ⏳ PLANNED
- [ ] At-least-once delivery
- [ ] 重複排除
- [ ] 再送制御
- [ ] メッセージ順序保証

## ロードマップ

| 優先度 | タスク | 見積 | 状態 |
|--------|--------|------|------|
| P0 | E2E暗号化実装 | 2日 | ✅ 完了 |
| P0 | 分散レジストリ | 2日 | 🔄 進行中 |
| P1 | 信頼性レイヤー | 1日 | ⏳ 計画中 |

## 詳細設計

### E2E暗号化レイヤー

#### 暗号化スイート
| パラメータ | 値 |
|------------|-----|
| 鍵交換 | X25519 (ECDH) |
| 対称暗号 | AES-256-GCM |
| 署名 | Ed25519 |
| 鍵導出 | HKDF-SHA256 |
| ノンス | 96-bit random |

#### 3-Way Handshake
1. Initiator → Responder: handshake (ephemeral_pubkey + challenge)
2. Responder → Initiator: handshake_ack (ephemeral_pubkey + challenge_response)
3. Initiator → Responder: handshake_confirm (session_established)

### 分散レジストリ詳細設計

#### Gossipプロトコル最適化
| パラメータ | 値 | 説明 |
|------------|-----|------|
| gossip_interval | 30秒 | 通常同期間隔 |
| cleanup_interval | 300秒 | 期限切れクリーンアップ |
| entry_timeout | 120秒 | エントリ有効期限 |
| fanout | 3 | 並列送信先数 |

#### 改善項目
1. ブートストラップノード自動発見
2. ネットワークパーティション対応
3. エントリ署名検証 (Ed25519)

---
設計日: 2026-02-01
