# Moltbook統合モジュール分析・重複解決方針

## 現状分析

### 2つのクライアント実装

| 項目 | moltbook_client.py | moltbook_integration.py |
|------|-------------------|------------------------|
| **認証方式** | Identity Token方式 | X(Twitter)認証コード方式 |
| **ベースURL** | `https://moltbook.com/api/v1` | `https://api.moltbook.ai/v1` |
| **主要クラス** | `MoltbookClient` | `MoltbookClient`, `MoltbookPeerBridge` |
| **データクラス** | `MoltbookAgent`, `IdentityToken`, `RateLimitInfo` | `MoltbookPost`, `MoltbookMessage` |
| **APIキー管理** | 暗号化対応（Fernet） | 平文（ヘッダー埋め込み） |
| **レート制限** | クライアント側管理 | サーバー側（ExponentialBackoff） |
| **PeerService統合** | なし | MoltbookPeerBridgeあり |
| **DM機能** | なし | あり |

## 統合方針

### Phase 1: ファイル名変更
- `moltbook_client.py` → `moltbook_identity_client.py`

### Phase 2: 機能統合
`moltbook_integration.py`に以下を追加:
- Identity Token認証サポート
- APIキー暗号化

### Phase 3: 統一クライアント（将来）
両方の認証方式をサポートする統一クライアント作成

## 即座に実施すべきタスク

1. ファイル名変更（リネーム）
2. import文の更新
3. ドキュメント更新

## 結論

両方のクライアントを別々に保持:
- `moltbook_integration.py`: 主要開発対象（PeerService統合あり）
- `moltbook_identity_client.py`: 予備実装（実際のAPIに近い構造）
