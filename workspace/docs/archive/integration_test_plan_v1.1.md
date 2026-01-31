# Protocol v1.1 統合テスト計画

## 目的
SessionManager統合後の全機能検証

## テストフェーズ

### Phase 1: 基本機能テスト
| テスト項目 | 対象モジュール | 優先度 |
|-----------|--------------|--------|
| SessionManager単体テスト | session_manager.py | 高 |
| SecureSession作成・有効期限 | session_manager.py | 高 |
| Sequence number検証 | session_manager.py | 高 |
| 自動クリーンアップ | session_manager.py | 中 |

### Phase 2: 暗号化統合テスト
| テスト項目 | 対象モジュール | 優先度 |
|-----------|--------------|--------|
| X25519鍵交換 | crypto.py | 高 |
| AES-256-GCM暗号化/復号 | crypto.py | 高 |
| E2E暗号化フロー | e2e_crypto.py | 高 |
| Session key導出 | crypto.py | 中 |

### Phase 3: PeerService統合テスト
| テスト項目 | 対象モジュール | 優先度 |
|-----------|--------------|--------|
| ハンドシェイク確立 | peer_service.py | 高 |
| メッセージ送受信 | peer_service.py | 高 |
| レート制限動作 | peer_service.py | 中 |
| チャンク転送 | peer_service.py | 中 |

### Phase 4: End-to-Endテスト
| テスト項目 | 対象 | 優先度 |
|-----------|-----|--------|
| Entity A <> B 通信 | 統合 | 高 |
| Moltbook連携 | moltbook_integration.py | 中 |
| 負荷テスト（同時接続） | 統合 | 低 |

## テスト実行順序

1. Phase 1 → Phase 2 → Phase 3 → Phase 4
2. 各フェーズでブロッキング issue があれば解決してから次へ
3. 回帰テストは毎フェーズ終了時に実施

## 成功基準

- 全高優先度テストが合格
- コードカバレッジ 80%以上
- パフォーマンス: 100req/sec以上

---
作成: Entity A
日時: 2026-02-01
