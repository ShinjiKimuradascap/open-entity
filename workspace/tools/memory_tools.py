"""Memory Tools for AI Collaboration Platform

長期記憶操作のためのツール群。
 - memory_store: 記憶の保存
 - memory_recall: 記憶の検索
 - memory_context: コンテキスト取得
 - memory_forget: 期限切れ記憶の整理
 - memory_stats: 記憶統計の表示
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from typing import List, Dict, Any, Optional
from services.entity_memory import (
    get_memory, MemoryType, ImportanceLevel, MemoryEntry,
    remember, recall_memories, get_relevant_context
)


def memory_store(
    content: str,
    memory_type: str = "fact",
    importance: int = 3,
    tags: str = "",
    related_to: str = "",
    expires_in_days: Optional[int] = None,
    context: str = ""
) -> str:
    """
    新しい記憶を保存する
    
    Args:
        content: 記憶する内容（必須）
        memory_type: 記憶タイプ (fact/experience/decision/relationship/goal/error/code/conversation)
        importance: 重要度 1-5 (1=些細, 5=批判的)
        tags: カンマ区切りのタグ
        related_to: 関連する記憶ID（カンマ区切り）
        expires_in_days: 有効期限（日数）、省略時は重要度に応じて自動設定
        context: JSON形式の追加コンテキスト
    
    Returns:
        保存された記憶のID
    
    Example:
        memory_store(
            content="Discord Bot APIは無料で利用可能",
            memory_type="fact",
            importance=4,
            tags="discord,api,bot"
        )
    """
    mem = get_memory()
    
    # タグのパース
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    
    # 関連IDのパース
    related_ids = [r.strip() for r in related_to.split(",") if r.strip()]
    
    # コンテキストのパース
    ctx = {}
    if context:
        import json
        try:
            ctx = json.loads(context)
        except:
            ctx = {"note": context}
    
    try:
        mem_type = MemoryType(memory_type.lower())
    except ValueError:
        mem_type = MemoryType.FACT
    
    try:
        imp = ImportanceLevel(importance)
    except ValueError:
        imp = ImportanceLevel.MEDIUM
    
    memory_id = mem.store(
        content=content,
        memory_type=mem_type,
        importance=imp,
        tags=tag_list,
        related_ids=related_ids,
        context=ctx,
        expires_in_days=expires_in_days
    )
    
    return f"✅ Memory stored successfully\nID: {memory_id}\nType: {mem_type.value}\nImportance: {imp.value}/5"


def memory_recall(
    query: str,
    memory_type: str = "",
    tags: str = "",
    importance_min: int = 1,
    limit: int = 5,
    include_expired: bool = False
) -> str:
    """
    記憶を検索・呼び出す
    
    Args:
        query: 検索クエリ（キーワードや記憶ID）
        memory_type: 記憶タイプでフィルタ（省略可）
        tags: カンマ区切りのタグでフィルタ
        importance_min: 最小重要度（1-5）
        limit: 最大取得件数
        include_expired: 期限切れ記憶も含める
    
    Returns:
        検索結果のフォーマットされた文字列
    
    Example:
        memory_recall(query="API", tags="discord", limit=3)
    """
    mem = get_memory()
    
    # フィルタのパース
    mem_type = None
    if memory_type:
        try:
            mem_type = MemoryType(memory_type.lower())
        except ValueError:
            pass
    
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    
    try:
        imp_min = ImportanceLevel(importance_min)
    except ValueError:
        imp_min = ImportanceLevel.TRIVIAL
    
    results = mem.recall(
        query=query,
        memory_type=mem_type,
        tags=tag_list if tag_list else None,
        importance_min=imp_min if importance_min > 1 else None,
        limit=limit,
        include_expired=include_expired
    )
    
    if not results:
        return f"🔍 No memories found for query: '{query}'"
    
    lines = [f"🔍 Found {len(results)} memory(s) for '{query}':\n"]
    
    for i, entry in enumerate(results, 1):
        importance_emoji = "🔴" if entry.importance == ImportanceLevel.CRITICAL else \
                          "🟠" if entry.importance == ImportanceLevel.HIGH else \
                          "🟡" if entry.importance == ImportanceLevel.MEDIUM else \
                          "🟢" if entry.importance == ImportanceLevel.LOW else "⚪"
        
        lines.append(f"{i}. [{importance_emoji} {entry.memory_type.value.upper()}] {entry.id[:8]}...")
        lines.append(f"   Content: {entry.content[:150]}{'...' if len(entry.content) > 150 else ''}")
        if entry.tags:
            lines.append(f"   Tags: {', '.join(entry.tags)}")
        if entry.related_ids:
            lines.append(f"   Related: {len(entry.related_ids)} memory(s)")
        lines.append(f"   Accessed: {entry.access_count} times")
        lines.append("")
    
    return "\n".join(lines)


def memory_context(
    task: str,
    limit: int = 5,
    recent_hours: int = 24
) -> str:
    """
    現在のタスクに関連する記憶コンテキストを取得
    
    Args:
        task: 現在のタスク説明
        limit: 取得する記憶数
        recent_hours: 最近の記憶を取得する時間範囲
    
    Returns:
        LLMプロンプトに組み込める形式のコンテキスト文字列
    
    Example:
        memory_context(task="Discord Botの実装", limit=3)
    """
    mem = get_memory()
    entries = mem.get_context_memories(task, recent_hours=recent_hours, limit=limit)
    
    if not entries:
        return "📭 No relevant context memories found."
    
    lines = [f"🧠 Relevant Context ({len(entries)} memories):\n"]
    
    for entry in entries:
        type_emoji = {
            MemoryType.FACT: "📚",
            MemoryType.EXPERIENCE: "💡",
            MemoryType.DECISION: "⚡",
            MemoryType.ERROR: "❌",
            MemoryType.CODE: "💻",
            MemoryType.GOAL: "🎯",
            MemoryType.RELATIONSHIP: "👥",
            MemoryType.CONVERSATION: "💬"
        }.get(entry.memory_type, "📝")
        
        lines.append(f"{type_emoji} [{entry.memory_type.value}] {entry.content[:200]}{'...' if len(entry.content) > 200 else ''}")
    
    return "\n".join(lines)


def memory_get(
    memory_id: str,
    include_related: bool = True
) -> str:
    """
    特定の記憶をIDで取得
    
    Args:
        memory_id: 記憶ID（完全または先頭8文字以上）
        include_related: 関連記憶も含める
    
    Returns:
        記憶の詳細情報
    """
    mem = get_memory()
    
    # 部分一致で検索
    entry = mem.get_by_id(memory_id)
    
    if not entry:
        # 部分一致検索を試行
        results = mem.recall(memory_id, limit=1)
        if results:
            entry = results[0]
        else:
            return f"❌ Memory not found: {memory_id}"
    
    lines = [f"🧠 Memory Details:\n"]
    lines.append(f"ID: {entry.id}")
    lines.append(f"Type: {entry.memory_type.value}")
    lines.append(f"Importance: {entry.importance.value}/5")
    lines.append(f"Created: {entry.created_at.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Updated: {entry.updated_at.strftime('%Y-%m-%d %H:%M')}")
    if entry.expires_at:
        lines.append(f"Expires: {entry.expires_at.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Access Count: {entry.access_count}")
    if entry.last_accessed:
        lines.append(f"Last Accessed: {entry.last_accessed.strftime('%Y-%m-%d %H:%M')}")
    if entry.tags:
        lines.append(f"Tags: {', '.join(entry.tags)}")
    lines.append(f"\nContent:\n{entry.content}")
    
    if entry.context:
        lines.append(f"\nContext:")
        for k, v in entry.context.items():
            lines.append(f"  {k}: {v}")
    
    if include_related and entry.related_ids:
        related = mem.get_related(entry.id)
        if related:
            lines.append(f"\n🔗 Related Memories ({len(related)}):")
            for r in related:
                lines.append(f"  - [{r.memory_type.value}] {r.content[:80]}...")
    
    return "\n".join(lines)


def memory_update(
    memory_id: str,
    content: str = "",
    importance: int = 0,
    tags: str = ""
) -> str:
    """
    既存の記憶を更新
    
    Args:
        memory_id: 更新する記憶ID
        content: 新しい内容（省略時は更新しない）
        importance: 新しい重要度（0=変更なし、1-5）
        tags: 新しいタグ（カンマ区切り、省略時は変更なし）
    
    Returns:
        更新結果
    """
    mem = get_memory()
    
    # 現在のエントリを確認
    entry = mem.get_by_id(memory_id)
    if not entry:
        return f"❌ Memory not found: {memory_id}"
    
    updates = {}
    if content:
        updates["content"] = content
    if importance > 0:
        updates["importance"] = ImportanceLevel(importance)
    if tags:
        updates["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    
    if not updates:
        return "⚠️ No updates specified"
    
    success = mem.update(entry.id, **updates)
    
    if success:
        return f"✅ Memory updated: {memory_id}"
    else:
        return f"❌ Failed to update memory"


def memory_link(
    memory_id1: str,
    memory_id2: str
) -> str:
    """
    2つの記憶を相互にリンク
    
    Args:
        memory_id1: 最初の記憶ID
        memory_id2: 2番目の記憶ID
    
    Returns:
        リンク結果
    """
    mem = get_memory()
    
    success = mem.link_memories(memory_id1, memory_id2)
    
    if success:
        return f"✅ Linked memories:\n  - {memory_id1[:12]}...\n  - {memory_id2[:12]}..."
    else:
        return f"❌ Failed to link memories. Check that both IDs exist."


def memory_forget(
    dry_run: bool = True,
    include_compressed: bool = False
) -> str:
    """
    期限切れ・不要な記憶を整理
    
    Args:
        dry_run: Trueの場合、実際には削除せずにプレビューのみ表示
        include_compressed: 些細な記憶の圧縮も実行
    
    Returns:
        整理結果のレポート
    """
    mem = get_memory()
    
    lines = ["🧹 Memory Cleanup Report\n"]
    
    # 期限切れ記憶の確認
    stats_before = mem.get_stats()
    
    if dry_run:
        lines.append("⚠️ DRY RUN MODE (no actual changes)\n")
    
    # 期限切れ削除
    if not dry_run:
        expired_count = mem.forget_expired()
        lines.append(f"🗑️ Deleted {expired_count} expired memories")
    else:
        lines.append(f"📊 Currently {stats_before.get('expired', 0)} expired memories pending deletion")
    
    # 圧縮
    if include_compressed:
        if not dry_run:
            compressed_count = mem.compress_trivial_memories()
            lines.append(f"📦 Compressed {compressed_count} trivial memories")
        else:
            lines.append("📦 Trivial memories compression: READY")
    
    # 統計
    stats_after = mem.get_stats() if not dry_run else stats_before
    lines.append(f"\n📊 Memory Statistics:")
    lines.append(f"  Total memories: {stats_after.get('total_memories', 0)}")
    lines.append(f"  By type: {stats_after.get('by_type', {})}")
    lines.append(f"  Created (last 7 days): {stats_after.get('created_last_7_days', 0)}")
    
    if not dry_run:
        lines.append("\n✅ Cleanup completed")
    else:
        lines.append("\n💡 Run with dry_run=false to apply changes")
    
    return "\n".join(lines)


def memory_stats() -> str:
    """
    記憶システムの統計を表示
    
    Returns:
        詳細な統計情報
    """
    mem = get_memory()
    stats = mem.get_stats()
    
    importance_labels = {
        5: "🔴 Critical",
        4: "🟠 High",
        3: "🟡 Medium",
        2: "🟢 Low",
        1: "⚪ Trivial"
    }
    
    lines = ["📊 Memory System Statistics\n"]
    lines.append(f"Total Memories: {stats.get('total_memories', 0)}")
    lines.append(f"Expired (pending cleanup): {stats.get('expired', 0)}")
    lines.append(f"Created (last 7 days): {stats.get('created_last_7_days', 0)}")
    
    lines.append("\n📁 By Type:")
    for mem_type, count in sorted(stats.get('by_type', {}).items()):
        lines.append(f"  - {mem_type}: {count}")
    
    lines.append("\n⭐ By Importance:")
    for imp, count in sorted(stats.get('by_importance', {}).items(), reverse=True):
        label = importance_labels.get(imp, f"Level {imp}")
        lines.append(f"  {label}: {count}")
    
    return "\n".join(lines)


def memory_export(
    filepath: str = "data/memory_export.json",
    memory_type: str = ""
) -> str:
    """
    記憶をJSONファイルにエクスポート
    
    Args:
        filepath: 出力ファイルパス
        memory_type: 特定のタイプのみエクスポート（省略時は全て）
    
    Returns:
        エクスポート結果
    """
    mem = get_memory()
    
    mem_type = None
    if memory_type:
        try:
            mem_type = MemoryType(memory_type.lower())
        except ValueError:
            return f"❌ Invalid memory type: {memory_type}"
    
    try:
        mem.export_to_json(filepath, mem_type)
        
        # ファイルサイズを確認
        import os
        size = os.path.getsize(filepath)
        
        return f"✅ Memory exported to {filepath}\n   Size: {size:,} bytes"
    except Exception as e:
        return f"❌ Export failed: {e}"


# コマンドラインインターフェース
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Memory Tools")
    parser.add_argument("command", choices=["store", "recall", "context", "get", "stats", "forget", "link"])
    parser.add_argument("args", nargs="*", help="Command arguments")
    
    # Optional flags
    parser.add_argument("--type", "-t", default="fact", help="Memory type")
    parser.add_argument("--importance", "-i", type=int, default=3, help="Importance (1-5)")
    parser.add_argument("--tags", default="", help="Comma-separated tags")
    parser.add_argument("--limit", "-l", type=int, default=5, help="Result limit")
    parser.add_argument("--query", "-q", help="Search query")
    
    args = parser.parse_args()
    
    if args.command == "store":
        if not args.args:
            print("❌ Content required")
            sys.exit(1)
        result = memory_store(
            content=args.args[0],
            memory_type=args.type,
            importance=args.importance,
            tags=args.tags
        )
        print(result)
    
    elif args.command == "recall":
        query = args.query or (args.args[0] if args.args else "")
        if not query:
            print("❌ Query required")
            sys.exit(1)
        result = memory_recall(query=query, limit=args.limit)
        print(result)
    
    elif args.command == "context":
        task = args.args[0] if args.args else ""
        if not task:
            print("❌ Task description required")
            sys.exit(1)
        result = memory_context(task=task, limit=args.limit)
        print(result)
    
    elif args.command == "get":
        if not args.args:
            print("❌ Memory ID required")
            sys.exit(1)
        result = memory_get(memory_id=args.args[0])
        print(result)
    
    elif args.command == "stats":
        result = memory_stats()
        print(result)
    
    elif args.command == "forget":
        result = memory_forget(dry_run="--apply" not in sys.argv)
        print(result)
    
    elif args.command == "link":
        if len(args.args) < 2:
            print("❌ Two memory IDs required")
            sys.exit(1)
        result = memory_link(args.args[0], args.args[1])
        print(result)
    
    else:
        print(f"Unknown command: {args.command}")
