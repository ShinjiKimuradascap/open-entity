"""Semantic Memory Integration

EntityMemoryとsemantic.dbを統合し、意味検索機能を提供する。
キーワード検索だけでなく、意味的な類似性に基づく記憶検索を可能にする。
"""

import sqlite3
import os
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import numpy as np

SEMANTIC_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "semantic.db")
MEMORY_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "memory_advanced.db")


class SemanticMemory:
    """意味検索統合メモリシステム"""
    
    def __init__(self):
        self.semantic_db = SEMANTIC_DB_PATH
        self.memory_db = MEMORY_DB_PATH
    
    def search_by_semantic_similarity(
        self,
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        意味的類似性に基づく記憶検索
        
        semantic.dbの内容とキーワードマッチングで近似
        （将来的にベクトル埋め込みを統合）
        """
        # クエリをトークン化
        query_tokens = set(query.lower().split())
        
        conn = sqlite3.connect(self.semantic_db)
        cursor = conn.cursor()
        
        # semantic.dbのテーブル構造を確認
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        results = []
        
        if "documents" in tables:
            # documentsテーブルから検索
            cursor.execute("""
                SELECT id, content, metadata, file_path 
                FROM documents 
                WHERE content LIKE ?
                LIMIT ?
            """, (f"%{query}%", top_k * 2))
            
            for row in cursor.fetchall():
                content = row[1]
                content_tokens = set(content.lower().split())
                
                # 簡易的な類似度計算（Jaccard類似度）
                intersection = query_tokens & content_tokens
                union = query_tokens | content_tokens
                similarity = len(intersection) / len(union) if union else 0
                
                if similarity >= similarity_threshold:
                    results.append({
                        "id": row[0],
                        "content": content[:300],
                        "metadata": json.loads(row[2]) if row[2] else {},
                        "source": row[3],
                        "similarity": similarity,
                        "type": "document"
                    })
        
        elif "chunks" in tables:
            # chunksテーブルから検索
            cursor.execute("""
                SELECT c.id, c.content, d.file_path 
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.content LIKE ?
                LIMIT ?
            """, (f"%{query}%", top_k * 2))
            
            for row in cursor.fetchall():
                content = row[1]
                content_tokens = set(content.lower().split())
                
                intersection = query_tokens & content_tokens
                union = query_tokens | content_tokens
                similarity = len(intersection) / len(union) if union else 0
                
                if similarity >= similarity_threshold:
                    results.append({
                        "id": row[0],
                        "content": content[:300],
                        "source": row[2],
                        "similarity": similarity,
                        "type": "chunk"
                    })
        
        conn.close()
        
        # 類似度でソート
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]
    
    def hybrid_search(
        self,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        ハイブリッド検索（キーワード + 意味）
        
        EntityMemoryとsemantic.dbの両方を検索し、
        結果をマージしてランキングする
        """
        from services.entity_memory import get_memory
        
        mem = get_memory()
        
        # 1. キーワード検索（EntityMemory）
        keyword_results = mem.recall(query, limit=top_k)
        
        # 2. 意味検索（semantic.db）
        semantic_results = self.search_by_semantic_similarity(query, top_k=top_k)
        
        # 3. 結果をマージ
        combined = []
        
        # EntityMemory結果を追加
        for entry in keyword_results:
            combined.append({
                "id": entry.id,
                "content": entry.content,
                "type": entry.memory_type.value,
                "importance": entry.importance.value,
                "source": "memory",
                "tags": entry.tags,
                "score": entry.importance.value * 0.2  # 重要度をスコアに反映
            })
        
        # Semantic結果を追加（重複チェック）
        existing_contents = {c["content"][:100] for c in combined}
        for result in semantic_results:
            content_preview = result["content"][:100]
            if content_preview not in existing_contents:
                combined.append({
                    "id": result["id"],
                    "content": result["content"],
                    "type": result["type"],
                    "importance": 3,
                    "source": result.get("source", "unknown"),
                    "similarity": result.get("similarity", 0),
                    "score": result.get("similarity", 0) * 5  # 類似度をスコアに
                })
                existing_contents.add(content_preview)
        
        # スコアでソート
        combined.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        return combined[:top_k]
    
    def index_memory_to_semantic(self, memory_id: str) -> bool:
        """
        EntityMemoryの記憶をsemantic.dbにインデックス
        （双方向検索を可能にする）
        """
        from services.entity_memory import get_memory
        
        mem = get_memory()
        entry = mem.get_by_id(memory_id)
        
        if not entry:
            return False
        
        conn = sqlite3.connect(self.semantic_db)
        cursor = conn.cursor()
        
        # documentsテーブルがなければ作成
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entity_memories (
                id TEXT PRIMARY KEY,
                content TEXT,
                memory_type TEXT,
                tags TEXT,
                importance INTEGER,
                created_at TIMESTAMP,
                metadata TEXT
            )
        """)
        
        # 挿入または更新
        cursor.execute("""
            INSERT OR REPLACE INTO entity_memories 
            (id, content, memory_type, tags, importance, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.id,
            entry.content,
            entry.memory_type.value,
            json.dumps(entry.tags),
            entry.importance.value,
            entry.created_at.isoformat(),
            json.dumps(entry.context)
        ))
        
        conn.commit()
        conn.close()
        
        return True
    
    def find_related_context(
        self,
        current_context: str,
        max_results: int = 3
    ) -> str:
        """
        現在のコンテキストに関連する情報を自動的に検索し、
        LLMプロンプトに組み込める形式で返す
        """
        results = self.hybrid_search(current_context, top_k=max_results)
        
        if not results:
            return ""
        
        sections = ["## 🔍 Related Knowledge & Memories\n"]
        
        for i, result in enumerate(results, 1):
            source_icon = "🧠" if result.get("source") == "memory" else "📄"
            sections.append(f"{i}. {source_icon} [{result.get('type', 'unknown')}]")
            sections.append(f"   {result['content'][:250]}...")
            if result.get("tags"):
                sections.append(f"   Tags: {', '.join(result['tags'])}")
            sections.append("")
        
        return "\n".join(sections)


# グローバルインスタンス
_semantic_memory_instance: Optional[SemanticMemory] = None


def get_semantic_memory() -> SemanticMemory:
    """グローバルSemanticMemoryインスタンスを取得"""
    global _semantic_memory_instance
    if _semantic_memory_instance is None:
        _semantic_memory_instance = SemanticMemory()
    return _semantic_memory_instance


def semantic_search(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """意味検索の簡易関数"""
    sm = get_semantic_memory()
    return sm.search_by_semantic_similarity(query, top_k=top_k)


def hybrid_memory_search(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """ハイブリッド検索の簡易関数"""
    sm = get_semantic_memory()
    return sm.hybrid_search(query, top_k=top_k)


def get_enhanced_context(task_description: str, max_results: int = 3) -> str:
    """
    強化されたコンテキスト取得（semantic + memory）
    """
    sm = get_semantic_memory()
    return sm.find_related_context(task_description, max_results=max_results)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    
    print("🔍 Semantic Memory Test")
    
    sm = get_semantic_memory()
    
    # テスト検索
    results = sm.hybrid_search("API authentication", top_k=5)
    
    print(f"\nFound {len(results)} results:")
    for r in results:
        print(f"\n[{r.get('type', 'unknown')}] Score: {r.get('score', 0):.2f}")
        print(f"Content: {r['content'][:150]}...")
    
    print("\n✅ Test completed")
