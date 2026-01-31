# L2 DHT (Kademlia) 設計書

## 文書情報
- バージョン: 1.0.0
- 作成日: 2026-02-01
- 作成者: Entity B
- ステータス: 設計完了

---

## 1. 概要

Kademlia DHTをベースとした分散ハッシュテーブル設計。
エンティティIDからネットワークアドレスを解決する分散型システム。

採用理由:
- O(log N)のルーティング効率
- 自己組織化、動的参加/離脱に強い
- 広く検証された実績

---

## 2. Kademlia基本

Node ID:
- 160ビット（20バイト）識別子
- エンティティ公開鍵からSHA-256ハッシュ
- XOR距離で近接性定義

Routing Table (k-bucket):
- 160個のk-bucket
- 各bucket最大k個（k=20）

RPCメソッド:
- PING: 生存確認
- STORE: キー・バリュー保存
- FIND_NODE: 近傍ノード検索
- FIND_VALUE: 値検索

---

## 3. AIネットワーク拡張

Node ID: SHA-256 of Ed25519 pubkey
Value Type: 型付きデータ（PeerInfo, Capability等）
TTL: 可変（鮮度ベース）
暗号化: E2E暗号化必須

保存データ型:
- PEER_ENDPOINT: エンティティのエンドポイント
- PEER_CAPABILITY: 提供機能リスト
- SERVICE_RECORD: 公開サービス情報
- RELAY_ENDPOINT: リレーサーバー情報

---

## 4. 実装設計

主要クラス:
- KademliaDHT: メイン実装
- RoutingTable: k-buckets管理
- DHTStorage: 永続化
- KademliaRPC: 通信層

メソッド:
- join(bootstrap_nodes): ネットワーク参加
- lookup(target_id): k-closestノード検索
- put(key, value): 値保存
- get(key): 値取得

---

## 5. パフォーマンス目標

Lookup遅延 (p99): < 500ms
Store成功率: > 95%
ネットワーク規模: 10,000ノード
メモリ使用量: < 100MB

---

## 6. リスクと対策

Sybil攻撃: エンティティ認証 + PoW制限
Eclipse攻撃: 複数ブートストラップ + ランダムLookup
データ消失: k-複製 + 定期再公開
ホットスポット: 一貫性ハッシュ + 負荷分散

---

次のアクション: M1 L2コアコンポーネント設計へ
