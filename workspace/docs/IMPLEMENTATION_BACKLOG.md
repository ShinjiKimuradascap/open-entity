# 実装バックログ

## 実装済み機能（最近追加）

### Kademlia DHT ベースピアディスカバリー ✅
**実装:** `services/kademlia_dht.py`  
**状態:** Complete

**実装済み機能:**
- XOR距離メトリクスによるノード配置
- ルーティングテーブル（k-buckets）
- PeerInfo署名付き登録
- ブートストラップノードサポート
- 定期リフレッシュとクリーンアップ

---

### Rate Limiting システム ✅
**実装:** `services/rate_limiter.py`  
**状態:** Complete

**実装済み機能:**
- Token Bucket方式
- ピアごとの帯域制限
- 自動レート調整

---

### Multi-Hop Message Router ✅
**実装:** `services/multi_hop_router.py`  
**状態:** Complete

**実装済み機能:**
- Store-and-forwardメッセージ中継
- TTLベースループ防止
- パストラッキングと検証
- 永続メッセージキュー
- 配信確認

---

## 未実装機能

### 1. Bootstrap Auto-Discovery
**優先度:** High  
**難易度:** Medium

**詳細:**
- 既存ブートストラップノードから追加ノードを動的発見
- 再帰的ディスカバリー（最大深度3）
- 署名検証による信頼確立
- 到達可能性スコアリング

**実装候補:**
- `services/bootstrap_discovery.py`
- `BootstrapDiscoveryManager`クラス

---

### 2. Network Partition Handling
**優先度:** High  
**難易度:** High

**詳細:**
- パーティション検出（Heartbeat timeout, gossip anomalies）
- Vector Clock + Merkle Treeによる分岐検出
- CRDTベース衝突解決

---

### 3. Bandwidth Adaptation
**優先度:** Medium  
**難易度:** Medium  
**関連:** peer_protocol_v1.2.md

**詳細:**
- 動的品質調整
- メッセージ優先順位付け
- 輻輳制御
- 帯域使用量メトリクス

---

### 3. 本番用ブートストラップノード
**優先度:** High  
**難易度:** Low  

**詳細:**
- クラウドホストのブートストラップノード設定
- SSL証明書設定
- 信頼性スコアリング

**対象ファイル:**
- `config/bootstrap_nodes.json`

---

### 4. Gossip プロトコルの完全実装
**優先度:** Medium  
**難易度:** Medium  
**関連:** distributed_registry.py

**詳細:**
- エピデミック伝播（Epidemic Broadcast）
- ランダムピア選択
- メッセージ重複排除

---

## 完了済み機能

### E2E Encryption (v1.0準拠)
- [x] X25519鍵交換
- [x] AES-256-GCM暗号化
- [x] Perfect Forward Secrecy
- **実装:** `services/e2e_crypto.py`

### Session Management (v1.0準拠)
- [x] UUID v4セッション
- [x] シーケンス番号管理
- [x] セッション有効期限
- **実装:** `services/session_manager.py`

### Chunked Transfer (v1.1準拠)
- [x] 32KBチャンク分割
- [x] チェックサム検証
- [x] 進捗追跡
- **実装:** `services/chunked_transfer.py`

### Distributed Registry (v1.0準拠)
- [x] CRDTベース同期
- [x] Gossipプロトコル
- [x] 期限切れクリーンアップ
- **実装:** `services/distributed_registry.py`

---

## 実装ロードマップ

### Phase 1: 基盤強化（完了）✅
- [x] Kademlia DHT実装
- [x] Rate Limiting実装
- [x] Multi-hop Routing実装

### Phase 2: 信頼性層（進行中）
- [ ] Bootstrap Auto-Discovery
- [ ] Network Partition Handling
- [ ] Persistent Offline Message Queue
- [ ] 本番ブートストラップノード設定

### Phase 3: 高度機能（計画中）
- [ ] Bandwidth Adaptation
- [ ] Group Messaging (Multi-cast)
- [ ] WebSocket Transport
- [ ] Binary Protocol (CBOR)

### Phase 4: 統合テスト
- [ ] E2Eテスト
- [ ] 負荷テスト
- [ ] フォールトトレランステスト

---

作成日: 2026-02-01  
最終更新: 2026-02-01
