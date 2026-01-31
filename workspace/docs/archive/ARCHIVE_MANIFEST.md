# Documentation Archive Manifest

このディレクトリには古い・重複したドキュメントが保管されています。

## Archive Rules

1. **重複ファイル**: ルートdocs/に最新版がある場合、archive/のコピーは削除可能
2. **バージョン履歴**: v0.4, v0.5などの古いバージョンはarchiveに保持
3. **日付付きファイル**: `_20260201.md` などの日付付きファイルは、同名の最新版があれば削除可能

## Archived Files

### API References (古いバージョン)
- `api_reference_v0.4.yaml` - v0.4 API仕様（yaml形式、廃止予定）
- `API_REFERENCE_v0.5.md` - v0.5 API仕様（ルートに最新版あり）

### Design Documents (重複・古いバージョン)
- `governance_design.md` - ルートに最新版あり
- `moltbook_strategy_old.md` - v2がルートにあるため旧版
- `token_economy.md` - ルートに統合済み
- `token_system_design_v2.md` - ルートに最新版あり
- `token_system_requirements.md` - ルートに統合済み
- `websocket_design_v1.md` - v2がルートにあるため旧版

### Implementation Plans (完了済み)
- `integration_design_20260201.md` - 日付付き、完了済み
- `moltbook_integration_analysis_20260201.md` - 日付付き、完了済み
- `s3_practical_test_scenarios.md` - S3完了済み
- `s4_implementation_plan.md` - S4完了済み
- `v1.1_integration_test_plan.md` - v1.2に移行済み

## Archive vs Root Differences

### Version-Specific Documents (内容が異なる)
| Archive File | Root File | 違い |
|--------------|-----------|------|
| `v1.3_design.md` | `v1.3_design.md` | archive: Cross-Chain Infrastructure版 / root: Multi-Agent Marketplace版 |
| `websocket_design.md` | `websocket_design_v2.md` | archive: v1.0旧版 / root: v2.0最新版 |

## Cleanup Recommendations

### 削除可能（ルートに最新版あり）
- `API_REFERENCE_v0.5.md` → ルートの `API_REFERENCE_v0.5.md` と同一
- `governance_design.md` → ルートの `governance_design.md` と同一
- `token_system_design_v2.md` → ルートの `token_system_design_v2.md` と同一

### 保持推奨（履歴価値あり）
- `api_reference_v0.4.yaml` - v0.4仕様の記録
- `moltbook_strategy_old.md` - 戦略変更の履歴
- `s3_practical_test_scenarios.md` - S3実績記録
- `s4_implementation_plan.md` - S4実績記録

## Cleanup History

### 2026-02-01 - Removed duplicate files
以下の重複ファイルを削除（ルートdocs/に最新版あり）:
- `API_REFERENCE_v0.5.md`
- `governance_design.md`
- `token_system_design_v2.md`
- `integration_design_20260201.md`
- `moltbook_integration_analysis_20260201.md`

### Small/Consolidated Design Documents
- `blockchain_design.md` - 内容を統合ドキュメントに統合済み
- `crypto_integration_design.md` - 統合済み
- `erc8004_integration.md` - 統合済み
- `kademlia_dht_design.md` - `kademlia_dht_plan.md`に統合済み
- `l1_dpki_design.md` - 統合済み
- `registry_scalability_analysis.md` - 分析完了、結果を統合済み
- `relay_service_design.md` - 統合済み
- `peer_discovery_design.md` - 統合済み
- `ai_network_architecture_v2.md` - 統合済み
- `dht_registry_design.md` - 統合済み
- `e2e_integration_design.md` - `e2e_crypto_integration_plan.md`に統合済み
- `dht_integration_analysis.md` - 分析完了

Last Updated: 2026-02-01 01:15 JST
