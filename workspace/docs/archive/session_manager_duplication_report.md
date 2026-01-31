# SessionManager重複実装調査報告

## 概要
複数ファイルにSessionManager関連クラスが分散実装されている。

## 重複クラス一覧

| クラス名 | ファイル | 行数 | 用途 |
|---------|---------|------|------|
| SessionManager | session_manager.py | 41-409 | 新実装（推奨） |
| SessionManager | crypto.py | 1242+ | 古い実装 |
| SessionManager | peer_service.py | 335+ | 統合実装 |
| SessionState | session_manager.py | 26 | 拡張セッション状態 |
| SessionState | e2e_crypto.py | 39 | E2E用状態 |
| SessionState | peer_service.py | 132 | ピアサービス用 |
| SecureSession | crypto.py | 82 | 基本セッション |
| E2ESession | e2e_crypto.py | 74 | E2E暗号化セッション |
| Session | peer_service.py | 143 | ピアサービスセッション |

## 推奨統合方針

1. **session_manager.pyを正とする**
   - 最新実装でテストも充実
   - SecureSessionへの依存を整理

2. **crypto.pyから古いSessionManagerを削除**
   - 後方互換性に注意

3. **peer_service.pyの統合**
   - session_manager.pyをインポートして使用
   - 既存のSessionクラスは段階的に移行

4. **e2e_crypto.pyの統合**
   - E2E暗号化特有の機能は保持
   - SessionStateは統一

## 統合後のテスト計画

- [ ] session_manager.py単体テスト
- [ ] crypto.py統合テスト
- [ ] peer_service.py統合テスト
- [ ] E2E暗号化フローテスト

---
調査: Entity A
日時: 2026-02-01
