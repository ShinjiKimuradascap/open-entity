# Kademlia DHT 実装計画

## 現在の実装
- kademlia_dht.py (410行)
- DHTRegistryクラス実装済
- PeerInfo署名検証対応

## 不足機能
1. ネットワーク分割耐性
2. PeerService統合
3. 高度な検索（キャパビリティベース）

## 実装タスク
### M3-1: ネットワーク分割耐性
- _maintain_connectivityループ
- _is_partitioned検出
- _rebootstrap自動修復

### M3-2: PeerService統合
- _init_dhtメソッド
- _on_dht_peer_discoveredコールバック
- 自動接続

### M3-3: 高度な検索
- find_peers_by_capability
- 評価値フィルタ

## 次のアクション
M3-1の実装開始

作成: 2026-02-01
