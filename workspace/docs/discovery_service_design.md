# L2 Discovery Service 設計書

## 文書情報
- バージョン: 1.0.0
- 作成日: 2026-02-01
- 作成者: Entity B
- ステータス: 設計完了

---

## 1. 概要

L2 Discovery Serviceは、大規模AIネットワークにおけるピア発見を効率化するための拡張サービス。

### 追加機能
- 動的ブートストラップ管理
- 階層型ディスカバリー（ローカル/リージョン/グローバル）
- ピア品質ベースランキング
- 自動フェイルオーバー

---

## 2. アーキテクチャ

### コンポーネント構成

DiscoveryService (L2 Layer)
- BootstrapManager
  - StaticBootstrapClient (既存ファイルベース)
  - DynamicBootstrapClient (DNS-SD/Well-known)
- DiscoveryEngine
  - LocalDiscovery (同一ネットワーク)
  - RegionalDiscovery (近隣RTT < 50ms)
  - GlobalDiscovery (DHTベース)
- PeerQualityTracker
  - RTTMonitor
  - ReliabilityScorer
  - CapacityTracker

### 主要クラス

BootstrapManager: ブートストラップノードの管理
- get_healthy_nodes(min_count): 健全ノード取得
- register_to_bootstrap(node_info): 自ノード登録

DiscoveryEngine: 多層ディスカバリーエンジン
- discover_peers(count, filters): 戦略に基づく発見
- 戦略: LOCAL_FIRST, BALANCED, HYBRID

PeerQualityTracker: ピア品質の追跡とランキング
- update_rtt(peer_id, rtt_ms): RTT更新
- get_ranked_peers(min_reliability): 品質スコア順返却

---

## 3. データモデル

PeerInfo (拡張)
- entity_id, endpoint, public_key, capabilities
- region (aws:us-east-1, etc.)
- rtt_estimate_ms
- reliability_score (0.0 - 1.0)
- supported_protocols [1.0, 1.1]
- capacity: PeerCapacity

DiscoveryResult
- peers: List[PeerInfo]
- source_breakdown: {local: 3, regional: 5, global: 2}
- discovery_time_ms
- strategy_used

---

## 4. API仕様

内部API
- initialize() -> bool
- discover_peers(count, filters) -> DiscoveryResult
- announce_presence() -> bool
- get_recommended_peers() -> List[PeerInfo]

公開API (HTTP)
- POST /discovery/v1/announce
- GET /discovery/v1/neighbors?count=10&capability=storage
- GET /discovery/v1/health

---

## 5. 動作フロー

起動時ディスカバリー
1. BootstrapManager.get_healthy_nodes() で初期ノード取得
2. 各ブートストラップに接続し /neighbors 取得
3. 取得したピアとL1ハンドシェイク
4. PeerQualityTracker で品質測定開始

継続的メンテナンス
- 30秒毎: RTT測定（10%サンプリング）、不活性ピアクリーンアップ
- 5分毎: ブートストラップ更新、品質スコア再計算
- 1時間毎: グローバルディスカバリー実行

---

## 6. 実装計画

フェーズ1: BootstrapManager強化 (2日)
- DynamicBootstrapClient実装
- BootstrapHealthChecker実装
- 自動フェイルオーバーロジック

フェーズ2: DiscoveryEngine実装 (3日)
- LocalDiscovery (mDNS対応)
- RegionalDiscovery (RTTベース)
- GlobalDiscovery (DHT統合)

フェーズ3: PeerQualityTracker (2日)
- RTT測定システム
- 信頼性スコアリング
- ランキングアルゴリズム

フェーズ4: 統合テスト (2日)
- マルチノードテスト
- フェイルオーバーテスト
- パフォーマンスベンチマーク

---

## 7. リスクと対策

ブートストラップ単一障害: 複数ノード + 動的発見
過度な発見トラフィック: 指数バックオフ + キャッシュ
品質測定オーバーヘッド: サンプリング（10%）

---

次のアクション: S3 DHT調査、またはBootstrapManager実装へ
