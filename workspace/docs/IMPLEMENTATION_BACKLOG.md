# 実装バックログ

## 未実装機能

### 1. Kademlia DHT ベースピアディスカバリー
**優先度:** High  
**難易度:** High  
**関連:** peer_protocol_v1.1.md

**詳細:**
- XOR距離メトリクスによるノード配置
- ルーティングテーブル（k-buckets）
- FIND_NODE / FIND_VALUE RPC
- ノードID生成と管理

**実装候補:**
- `services/kademlia_dht.py`
- `services/kademlia_routing.py`

---

### 2. Rate Limiting システム
**優先度:** Medium  
**難易度:** Medium  
**関連:** peer_protocol_v1.1.md

**詳細:**
- Token Bucket方式
- ピアごとの帯域制限
- Rate Limitヘッダー実装

**実装候補:**
- `services/rate_limiter.py`

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

### Phase 1: 基盤強化（1-2週間）
- [ ] Kademlia DHT実装
- [ ] 本番ブートストラップノード設定

### Phase 2: セキュリティ強化（3-4週間）
- [ ] Rate Limiting実装
- [ ] Gossipプロトコル完全実装

### Phase 3: 統合テスト（5-6週間）
- [ ] E2Eテスト
- [ ] 負荷テスト

---

作成日: 2026-02-01  
最終更新: 2026-02-01
