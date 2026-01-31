# Session Manager 統合計画

## 分析日: 2026-02-01

## 現状の重複実装

| ファイル | クラス名 | 主な機能 | 行数 |
|:---------|:---------|:---------|:-----|
| peer_service.py:637 | SessionManager | ピア通信用セッション管理、シーケンス検証 | ~200行 |
| session_manager.py:56 | SessionManager | 一般的なセッション管理、TTL制御 | ~424行 |
| e2e_session.py:337 | E2ESessionManager | E2E暗号化セッション管理 | ~606行 |
| crypto.py:800 | MessageValidator.validate_sequence | 基本的なシーケンス検証 | 静的メソッド |

## 統合戦略

### Phase 1: 責務の明確化

- SessionManager (統合コア): UUID生成、TTL管理、シーケンス管理、ステート管理
- E2ESession (暗号化レイヤ): X25519鍵交換、AES-GCM暗号化、ペイロード暗号化
- MessageValidator (検証ユーティリティ): シーケンス検証、署名検証、リプレイ保護

### Phase 2: 統合実装計画

1. session_manager.pyをコアとして採用
2. peer_service.pyからSessionManagerクラスを削除
3. e2e_session.pyは独立して維持

## 実装タスク

- [ ] S1: session_manager.pyにシーケンス検証機能を統合
- [ ] S2: peer_service.pyのSessionManagerを削除・移行
- [ ] S3: 統合テスト作成
- [ ] S4: 既存テストの互換性確認

## 期待される効果

- コード重複削減: ~200行削除
- メンテナンス性向上: 単一の信頼性の高い実装
- テスト効率化: 重複テストケースの削減
