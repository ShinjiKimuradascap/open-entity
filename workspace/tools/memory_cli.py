"""Memory CLI - Interactive Memory Management Tool

長期記憶システムの対話型管理ツール。
 - 記憶の検索・保存・整理
 - コンテキスト自動取得
 - 統計表示
 - バッチ操作
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import argparse
import json
from datetime import datetime
from typing import Optional

from services.entity_memory import get_memory, MemoryType, ImportanceLevel
from services.semantic_memory import get_semantic_memory


class MemoryCLI:
    """メモリ管理CLI"""
    
    def __init__(self):
        self.mem = get_memory()
        self.sem = get_semantic_memory()
    
    def interactive_store(self):
        """対話式で記憶を保存"""
        print("📝 Store New Memory\n")
        
        content = input("Content: ").strip()
        if not content:
            print("❌ Content is required")
            return
        
        print("\nMemory Types:")
        for i, mt in enumerate(MemoryType, 1):
            print(f"  {i}. {mt.value}")
        
        type_choice = input("\nType (number or name) [1=fact]: ").strip() or "1"
        try:
            if type_choice.isdigit():
                mem_type = list(MemoryType)[int(type_choice) - 1]
            else:
                mem_type = MemoryType(type_choice)
        except:
            mem_type = MemoryType.FACT
        
        print("\nImportance:")
        print("  5. 🔴 Critical (permanent)")
        print("  4. 🟠 High (1 year)")
        print("  3. 🟡 Medium (90 days)")
        print("  2. 🟢 Low (30 days)")
        print("  1. ⚪ Trivial (7 days)")
        
        imp_choice = input("\nImportance [3]: ").strip() or "3"
        try:
            importance = ImportanceLevel(int(imp_choice))
        except:
            importance = ImportanceLevel.MEDIUM
        
        tags_input = input("Tags (comma-separated): ").strip()
        tags = [t.strip() for t in tags_input.split(",") if t.strip()]
        
        memory_id = self.mem.store(
            content=content,
            memory_type=mem_type,
            importance=importance,
            tags=tags
        )
        
        print(f"\n✅ Memory stored!")
        print(f"   ID: {memory_id}")
        print(f"   Type: {mem_type.value}")
        print(f"   Importance: {importance.value}/5")
    
    def interactive_search(self):
        """対話式で記憶を検索"""
        print("🔍 Search Memories\n")
        
        query = input("Query: ").strip()
        if not query:
            print("❌ Query is required")
            return
        
        print("\nSearch Options:")
        print("  1. Keyword search (memory only)")
        print("  2. Semantic search (documents)")
        print("  3. Hybrid search (both)")
        
        mode = input("\nMode [3]: ").strip() or "3"
        limit = int(input("Limit [5]: ").strip() or "5")
        
        if mode == "1":
            results = self.mem.recall(query, limit=limit)
            self._print_memory_results(results)
        elif mode == "2":
            results = self.sem.search_by_semantic_similarity(query, top_k=limit)
            self._print_semantic_results(results)
        else:
            results = self.sem.hybrid_search(query, top_k=limit)
            self._print_hybrid_results(results)
    
    def _print_memory_results(self, results):
        """Memory検索結果を表示"""
        if not results:
            print("\n📭 No memories found")
            return
        
        print(f"\n🧠 Found {len(results)} memory(s):\n")
        
        for i, entry in enumerate(results, 1):
            importance_emoji = "🔴" if entry.importance.value == 5 else \
                              "🟠" if entry.importance.value == 4 else \
                              "🟡" if entry.importance.value == 3 else \
                              "🟢" if entry.importance.value == 2 else "⚪"
            
            print(f"{i}. {importance_emoji} [{entry.memory_type.value.upper()}] {entry.id[:12]}...")
            print(f"   {entry.content}")
            if entry.tags:
                print(f"   Tags: {', '.join(entry.tags)}")
            print(f"   Accessed: {entry.access_count} times | Created: {entry.created_at.strftime('%Y-%m-%d')}")
            print()
    
    def _print_semantic_results(self, results):
        """Semantic検索結果を表示"""
        if not results:
            print("\n📭 No documents found")
            return
        
        print(f"\n📄 Found {len(results)} document(s):\n")
        
        for i, result in enumerate(results, 1):
            sim_pct = result.get('similarity', 0) * 100
            print(f"{i}. 📄 [{result.get('type', 'doc')}] Similarity: {sim_pct:.1f}%")
            print(f"   {result['content']}")
            if result.get('source'):
                print(f"   Source: {result['source']}")
            print()
    
    def _print_hybrid_results(self, results):
        """Hybrid検索結果を表示"""
        if not results:
            print("\n📭 No results found")
            return
        
        print(f"\n🔍 Found {len(results)} result(s):\n")
        
        for i, result in enumerate(results, 1):
            source_icon = "🧠" if result.get('source') == 'memory' else "📄"
            print(f"{i}. {source_icon} [{result.get('type', 'unknown')}] Score: {result.get('score', 0):.2f}")
            print(f"   {result['content'][:300]}...")
            if result.get('tags'):
                print(f"   Tags: {', '.join(result['tags'])}")
            print()
    
    def show_stats(self):
        """統計を表示"""
        stats = self.mem.get_stats()
        
        print("📊 Memory System Statistics\n")
        print(f"Total Memories: {stats.get('total_memories', 0)}")
        print(f"Expired (pending): {stats.get('expired', 0)}")
        print(f"Created (last 7 days): {stats.get('created_last_7_days', 0)}")
        
        print("\n📁 By Type:")
        for mem_type, count in sorted(stats.get('by_type', {}).items()):
            print(f"  {mem_type}: {count}")
        
        print("\n⭐ By Importance:")
        importance_labels = {5: "🔴 Critical", 4: "🟠 High", 3: "🟡 Medium", 2: "🟢 Low", 1: "⚪ Trivial"}
        for imp, count in sorted(stats.get('by_importance', {}).items(), reverse=True):
            print(f"  {importance_labels.get(imp, f'Level {imp}')}: {count}")
    
    def cleanup(self, dry_run: bool = True):
        """記憶を整理"""
        print(f"🧹 Memory Cleanup {'(DRY RUN)' if dry_run else ''}\n")
        
        stats_before = self.mem.get_stats()
        print(f"Before: {stats_before.get('total_memories', 0)} memories")
        
        if not dry_run:
            expired = self.mem.forget_expired()
            compressed = self.mem.compress_trivial_memories()
            print(f"\nDeleted: {expired} expired")
            print(f"Compressed: {compressed} trivial")
            
            stats_after = self.mem.get_stats()
            print(f"\nAfter: {stats_after.get('total_memories', 0)} memories")
        else:
            print(f"\nWould delete: {stats_before.get('expired', 0)} expired memories")
            print("Run with --apply to execute")
    
    def export_memories(self, filepath: str, mem_type: Optional[str] = None):
        """記憶をエクスポート"""
        mem_type_enum = None
        if mem_type:
            try:
                mem_type_enum = MemoryType(mem_type)
            except ValueError:
                print(f"❌ Invalid memory type: {mem_type}")
                return
        
        self.mem.export_to_json(filepath, mem_type_enum)
        
        import os
        size = os.path.getsize(filepath)
        print(f"✅ Exported to {filepath}")
        print(f"   Size: {size:,} bytes")
    
    def run(self):
        """対話モードを実行"""
        print("""
🧠 Entity Memory CLI
====================
Commands:
  store    - Store a new memory
  search   - Search memories
  stats    - Show statistics
  cleanup  - Clean up expired memories
  export   - Export memories to JSON
  quit     - Exit
        """)
        
        while True:
            try:
                cmd = input("\nmemory> ").strip().lower()
                
                if cmd == "store":
                    self.interactive_store()
                elif cmd == "search":
                    self.interactive_search()
                elif cmd == "stats":
                    self.show_stats()
                elif cmd == "cleanup":
                    apply = input("Apply changes? (yes/no): ").strip().lower() == "yes"
                    self.cleanup(dry_run=not apply)
                elif cmd == "export":
                    filepath = input("Filepath [data/memory_export.json]: ").strip() or "data/memory_export.json"
                    mem_type = input("Filter by type (optional): ").strip() or None
                    self.export_memories(filepath, mem_type)
                elif cmd in ("quit", "exit", "q"):
                    print("👋 Goodbye!")
                    break
                else:
                    print("Unknown command. Type 'quit' to exit.")
                    
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")


def main():
    """メインエントリポイント"""
    parser = argparse.ArgumentParser(description="Entity Memory Management Tool")
    parser.add_argument("command", choices=[
        "store", "recall", "context", "stats", "cleanup", "export", "interactive"
    ], help="Command to execute")
    
    # Store args
    parser.add_argument("--content", "-c", help="Memory content")
    parser.add_argument("--type", "-t", default="fact", help="Memory type")
    parser.add_argument("--importance", "-i", type=int, default=3, help="Importance level (1-5)")
    parser.add_argument("--tags", help="Comma-separated tags")
    
    # Search args
    parser.add_argument("--query", "-q", help="Search query")
    parser.add_argument("--limit", "-l", type=int, default=5, help="Result limit")
    
    # Cleanup args
    parser.add_argument("--apply", action="store_true", help="Apply cleanup (not dry-run)")
    
    # Export args
    parser.add_argument("--output", "-o", default="data/memory_export.json", help="Output file")
    
    args = parser.parse_args()
    
    cli = MemoryCLI()
    
    if args.command == "interactive":
        cli.run()
    
    elif args.command == "store":
        if not args.content:
            print("❌ --content is required")
            return
        
        tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
        
        try:
            mem_type = MemoryType(args.type)
        except ValueError:
            print(f"❌ Invalid type: {args.type}")
            return
        
        try:
            importance = ImportanceLevel(args.importance)
        except ValueError:
            print(f"❌ Invalid importance: {args.importance}")
            return
        
        memory_id = cli.mem.store(
            content=args.content,
            memory_type=mem_type,
            importance=importance,
            tags=tags
        )
        print(f"✅ Stored: {memory_id}")
    
    elif args.command == "recall":
        if not args.query:
            print("❌ --query is required")
            return
        
        results = cli.sem.hybrid_search(args.query, top_k=args.limit)
        cli._print_hybrid_results(results)
    
    elif args.command == "context":
        if not args.query:
            print("❌ --query is required")
            return
        
        from services.semantic_memory import get_enhanced_context
        context = get_enhanced_context(args.query, max_results=args.limit)
        print(context)
    
    elif args.command == "stats":
        cli.show_stats()
    
    elif args.command == "cleanup":
        cli.cleanup(dry_run=not args.apply)
    
    elif args.command == "export":
        cli.export_memories(args.output, args.type if args.type != "fact" else None)


if __name__ == "__main__":
    main()
