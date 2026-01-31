# peer_service.py 改善点リスト

## 分析日: 2026-02-01
## 分析対象: peer_service.py (1,856行)

---

## 高優先度（即座に対応が必要）

### Issue #5: __init__でsession_managerパラメータを受け取っていないのに参照している
**場所:** PeerService.__init__メソッド（行1692）
**問題:**
- __init__の引数に`session_manager`パラメータが存在しない
- しかし行1692で`if session_manager is not None:`と参照している
- これはNameErrorを引き起こす明確なバグ

**修正案:**
1. __init__に`session_manager: Optional[NewSessionManager] = None`パラメータを追加

### Issue #6: self.session_managerとself._session_managerの混在
**場所:** send_messageメソッド（行2749-2755）、_create_message_dictメソッド（行2896-2902）、handle_messageメソッド（行3380、3470）
**問題:**
- `self.session_manager`（プロパティなし）と`self._session_manager`（インスタンス変数）を混在して使用
- send_message: `hasattr(self, 'session_manager')`でチェック後、`asyncio.run(self.session_manager...)`を呼ぶ
- _create_message_dict: `self.session_manager is not None`でチェック
- handle_message: `await self.session_manager.get_session_by_peer(sender)`を呼ぶ
- 実際には`self._session_manager`として保存されている

**修正案:**
1. `session_manager`プロパティを追加して`self._session_manager`を返すようにする
2. または全て`self._session_manager`に統一

### Issue #7: send_messageでasyncio.run()を非同期関数内で呼んでいる
**場所:** send_messageメソッド（行2751、2755）
**問題:**
- `session = asyncio.run(self.session_manager.get_session_by_peer(target_id))`としている
- asyncio.run()は既存のイベントループがある場合はRuntimeErrorを発生させる
- send_messageは既にasync関数なので、awaitを使うべき

**修正案:**
1. `asyncio.run()`を`await`に変更
2. 必要に応じて`self.session_manager.get_session_by_peer()`が非同期か確認

### Issue #1: _send_with_retryメソッドが未定義
**場所:** send_messageメソッド（行663-812）内で呼ばれる
**問題:** 
- send_messageメソッドは独自にリトライロジックを実装（行750-798）
- _send_message_directメソッド（行875-884）は_send_with_retryを呼んでいるが、そのメソッドは存在しない
- これは明確なバグ - キュー経由の再送信が機能しない

**修正案:**
1. _send_with_retryメソッドを実装するか、
2. _send_message_directからsend_messageを直接呼ぶように変更

### Issue #2: send_messageメソッドが大規模すぎる
**場所:** send_messageメソッド（行663-812、約150行）
**問題:**
- 複数の責務を持っている:
  - メッセージ形式の判定と構築（行702-745）
  - 署名処理（行708-743）
  - HTTP通信（行753-758）
  - リトライロジック（行750-798）
  - 統計更新（行691-806）
  - キュー追加（行809-810）

### Issue #4: _send_message_directで存在しないメソッドを呼んでいる
**場所:** _send_message_directメソッド（行875-884）
コード内で_send_with_retryを呼んでいるが、このメソッドは存在しない

---

## 中優先度（リファクタリング対象）

### Issue #3: エラーハンドリングが統一されていない
**場所:** 複数箇所
**問題:**
- send_message内: asyncio.TimeoutError, ClientError, Exceptionを別々にハンドリング
- check_peer_health内: 同様のパターンだが異なるログメッセージ
- handle_message内: 署名検証エラーでValueErrorを特別にハンドリング

---

## 完了済み

- [x] test_peer_service.pyにPeerService機能テストを追加（2026-02-01）
  - PeerService初期化テスト
  - ピア管理テスト
  - メッセージハンドラテスト
  - handle_messageテスト
  - ヘルスチェックテスト
  - MessageQueue・HeartbeatManagerテスト

---

## 次のアクション

1. 即座に: _send_with_retryメソッドを実装または_send_message_directを修正
2. 短期: send_messageメソッドをリファクタリング
3. 中期: エラーハンドリングを統一
4. 長期: パフォーマンス最適化
