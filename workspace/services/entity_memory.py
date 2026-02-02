"""Entity Long-Term Memory System

高度な長期記憶管理システム。構造化記憶、意味検索、重要度管理、
コンテキスト自動取得、記憶間リンク機能を提供する。
"""

import json
import os
import sqlite3
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np

# パス設定
MEMORY_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "memory_advanced.db")
SEMANTIC_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "semantic.db")


class MemoryType(Enum):
    """記憶タイプ"""
    FACT = "fact"              # 事実・知識
    EXPERIENCE = "experience"  # 経験・学習
    DECISION = "decision"      # 決定事項
    RELATIONSHIP = "relationship"  # 人間関係
    GOAL = "goal"              # 目標
    ERROR = "error"            # 失敗・エラー
    CODE = "code"              # コードスニペット
    CONVERSATION = "conversation"  # 会話履歴


class ImportanceLevel(Enum):
    """重要度レベル"""
    CRITICAL = 5    # 批判的（永続保存）
    HIGH = 4        # 高（長期保存）
    MEDIUM = 3      # 中（標準保存期間）
    LOW = 2         # 低（短期保存）
    TRIVIAL = 1     # 些細（圧縮対象）


@dataclass
class MemoryEntry:
    """記憶エントリ"""
    id: str
    content: str
    memory_type: MemoryType
    importance: ImportanceLevel
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime]
    tags: List[str]
    related_ids: List[str]  # 関連記憶ID
    context: Dict[str, Any]  # メタデータ
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "importance": self.importance.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "tags": self.tags,
            "related_ids": self.related_ids,
            "context": self.context,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "MemoryEntry":
        return cls(
            id=data["id"],
            content=data["content"],
            memory_type=MemoryType(data["memory_type"]),
            importance=ImportanceLevel(data["importance"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data["expires_at"] else None,
            tags=data["tags"],
            related_ids=data["related_ids"],
            context=data["context"],
            access_count=data.get("access_count", 0),
            last_accessed=datetime.fromisoformat(data["last_accessed"]) if data.get("last_accessed") else None
        )


class EntityMemory:
    """エンティティ長期記憶システム"""
    
    def __init__(self, db_path: str = MEMORY_DB_PATH):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """データベース初期化"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # メインメモリテーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                importance INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                tags TEXT,  -- JSON array
                related_ids TEXT,  -- JSON array
                context TEXT,  -- JSON object
                access_count INTEGER DEFAULT 0,
                last_accessed TIMESTAMP,
                embedding BLOB  -- ベクトル埋め込み（将来的に使用）
            )
        """)
        
        # インデックス作成
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_type ON memories(memory_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_importance ON memories(importance)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_created ON memories(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_expires ON memories(expires_at)")
        
        # タグ検索用テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_tags (
                memory_id TEXT,
                tag TEXT,
                FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tag ON memory_tags(tag)")
        
        # アクセスログ
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_access_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id TEXT,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                query_context TEXT,
                FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
            )
        """)
        
        conn.commit()
        conn.close()
    
    def _generate_id(self, content: str) -> str:
        """コンテンツから一意IDを生成"""
        hash_obj = hashlib.sha256(f"{content}:{datetime.now().isoformat()}".encode())
        return hash_obj.hexdigest()[:16]
    
    def store(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.FACT,
        importance: ImportanceLevel = ImportanceLevel.MEDIUM,
        tags: List[str] = None,
        related_ids: List[str] = None,
        context: Dict[str, Any] = None,
        expires_in_days: Optional[int] = None
    ) -> str:
        """
        記憶を保存
        
        Args:
            content: 記憶内容
            memory_type: 記憶タイプ
            importance: 重要度
            tags: タグリスト
            related_ids: 関連記憶ID
            context: 追加コンテキスト
            expires_in_days: 有効期限（日数）
        
        Returns:
            記憶ID
        """
        memory_id = self._generate_id(content)
        now = datetime.now()
        
        if expires_in_days:
            expires_at = now + timedelta(days=expires_in_days)
        else:
            # 重要度に基づくデフォルト期限
            default_days = {
                ImportanceLevel.CRITICAL: None,  # 永続
                ImportanceLevel.HIGH: 365,
                ImportanceLevel.MEDIUM: 90,
                ImportanceLevel.LOW: 30,
                ImportanceLevel.TRIVIAL: 7
            }
            days = default_days.get(importance, 90)
            expires_at = now + timedelta(days=days) if days else None
        
        entry = MemoryEntry(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
            tags=tags or [],
            related_ids=related_ids or [],
            context=context or {}
        )
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO memories 
            (id, content, memory_type, importance, created_at, updated_at, expires_at, tags, related_ids, context)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.id, entry.content, entry.memory_type.value, entry.importance.value,
            entry.created_at, entry.updated_at, entry.expires_at,
            json.dumps(entry.tags), json.dumps(entry.related_ids), json.dumps(entry.context)
        ))
        
        # タグを別テーブルにも保存
        for tag in entry.tags:
            cursor.execute(
                "INSERT INTO memory_tags (memory_id, tag) VALUES (?, ?)",
                (entry.id, tag.lower())
            )
        
        conn.commit()
        conn.close()
        
        return memory_id
    
    def recall(
        self,
        query: str,
        memory_type: Optional[MemoryType] = None,
        tags: List[str] = None,
        importance_min: Optional[ImportanceLevel] = None,
        limit: int = 10,
        include_expired: bool = False
    ) -> List[MemoryEntry]:
        """
        記憶を検索（単純キーワード検索）
        
        Args:
            query: 検索クエリ
            memory_type: 記憶タイプでフィルタ
            tags: タグでフィルタ
            importance_min: 最小重要度
            limit: 取得件数
            include_expired: 期限切れも含める
        
        Returns:
            記憶エントリリスト
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        conditions = ["(content LIKE ? OR id = ?)"]
        params = [f"%{query}%", query]
        
        if memory_type:
            conditions.append("memory_type = ?")
            params.append(memory_type.value)
        
        if importance_min:
            conditions.append("importance >= ?")
            params.append(importance_min.value)
        
        if not include_expired:
            conditions.append("(expires_at IS NULL OR expires_at > datetime('now'))")
        
        if tags:
            tag_conditions = []
            for tag in tags:
                tag_conditions.append("tag = ?")
                params.append(tag.lower())
            
            tag_subquery = f"""
                AND id IN (
                    SELECT memory_id FROM memory_tags 
                    WHERE {' OR '.join(tag_conditions)}
                )
            """
        else:
            tag_subquery = ""
        
        where_clause = " AND ".join(conditions)
        
        cursor.execute(f"""
            SELECT * FROM memories 
            WHERE {where_clause} {tag_subquery}
            ORDER BY importance DESC, access_count DESC, created_at DESC
            LIMIT ?
        """, params + [limit])
        
        rows = cursor.fetchall()
        conn.close()
        
        entries = []
        for row in rows:
            entry = self._row_to_entry(row)
            entries.append(entry)
            self._update_access_count(entry.id)
        
        return entries
    
    def get_by_id(self, memory_id: str) -> Optional[MemoryEntry]:
        """IDで記憶を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            entry = self._row_to_entry(row)
            self._update_access_count(entry.id)
            return entry
        return None
    
    def get_related(self, memory_id: str) -> List[MemoryEntry]:
        """関連記憶を取得"""
        entry = self.get_by_id(memory_id)
        if not entry or not entry.related_ids:
            return []
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        placeholders = ','.join('?' * len(entry.related_ids))
        cursor.execute(f"""
            SELECT * FROM memories 
            WHERE id IN ({placeholders})
            AND (expires_at IS NULL OR expires_at > datetime('now'))
        """, entry.related_ids)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_entry(row) for row in rows]
    
    def get_context_memories(
        self,
        current_task: str,
        recent_hours: int = 24,
        limit: int = 5
    ) -> List[MemoryEntry]:
        """
        現在のタスクに関連するコンテキスト記憶を自動取得
        
        Args:
            current_task: 現在のタスク説明
            recent_hours: 最近の記憶を取得する時間範囲
            limit: 取得件数
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = datetime.now() - timedelta(hours=recent_hours)
        
        # 最近のアクセスが多い記憶 + 最近作成された重要な記憶
        cursor.execute("""
            SELECT * FROM memories 
            WHERE (last_accessed > ? OR created_at > ?)
            AND (expires_at IS NULL OR expires_at > datetime('now'))
            AND importance >= ?
            ORDER BY access_count DESC, importance DESC, created_at DESC
            LIMIT ?
        """, (since, since, ImportanceLevel.MEDIUM.value, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        entries = []
        for row in rows:
            entry = self._row_to_entry(row)
            entries.append(entry)
        
        return entries
    
    def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        importance: Optional[ImportanceLevel] = None,
        tags: Optional[List[str]] = None,
        related_ids: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """記憶を更新"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        updates = ["updated_at = datetime('now')"]
        params = []
        
        if content is not None:
            updates.append("content = ?")
            params.append(content)
        
        if importance is not None:
            updates.append("importance = ?")
            params.append(importance.value)
        
        if tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(tags))
            # タグテーブルも更新
            cursor.execute("DELETE FROM memory_tags WHERE memory_id = ?", (memory_id,))
            for tag in tags:
                cursor.execute(
                    "INSERT INTO memory_tags (memory_id, tag) VALUES (?, ?)",
                    (memory_id, tag.lower())
                )
        
        if related_ids is not None:
            updates.append("related_ids = ?")
            params.append(json.dumps(related_ids))
        
        if context is not None:
            # 既存コンテキストとマージ
            cursor.execute("SELECT context FROM memories WHERE id = ?", (memory_id,))
            row = cursor.fetchone()
            if row:
                existing = json.loads(row[0]) if row[0] else {}
                existing.update(context)
                updates.append("context = ?")
                params.append(json.dumps(existing))
        
        params.append(memory_id)
        
        cursor.execute(f"""
            UPDATE memories SET {', '.join(updates)} WHERE id = ?
        """, params)
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
    
    def link_memories(self, memory_id1: str, memory_id2: str) -> bool:
        """2つの記憶を相互にリンク"""
        entry1 = self.get_by_id(memory_id1)
        entry2 = self.get_by_id(memory_id2)
        
        if not entry1 or not entry2:
            return False
        
        # 相互に関連IDを追加
        if memory_id2 not in entry1.related_ids:
            entry1.related_ids.append(memory_id2)
        
        if memory_id1 not in entry2.related_ids:
            entry2.related_ids.append(memory_id1)
        
        self.update(memory_id1, related_ids=entry1.related_ids)
        self.update(memory_id2, related_ids=entry2.related_ids)
        
        return True
    
    def forget_expired(self) -> int:
        """期限切れ記憶を削除"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM memories 
            WHERE expires_at IS NOT NULL 
            AND expires_at < datetime('now')
            AND importance < ?
        """, (ImportanceLevel.HIGH.value,))
        
        count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return count
    
    def compress_trivial_memories(self) -> int:
        """些細な記憶を要約・圧縮"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 低重要度・古い・アクセスの少ない記憶を取得
        cutoff = datetime.now() - timedelta(days=30)
        
        cursor.execute("""
            SELECT * FROM memories 
            WHERE importance = ?
            AND created_at < ?
            AND access_count < 3
            AND (expires_at IS NULL OR expires_at > datetime('now'))
        """, (ImportanceLevel.TRIVIAL.value, cutoff))
        
        rows = cursor.fetchall()
        compressed_count = 0
        
        for row in rows:
            entry = self._row_to_entry(row)
            # 要約としてタグのみ保持、コンテンツは圧縮
            summary = f"[圧縮] {entry.content[:100]}..."
            self.update(
                entry.id,
                content=summary,
                context={**entry.context, "compressed": True, "original_length": len(entry.content)}
            )
            compressed_count += 1
        
        conn.close()
        return compressed_count
    
    def get_stats(self) -> Dict[str, Any]:
        """記憶統計を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {}
        
        # 総数
        cursor.execute("SELECT COUNT(*) FROM memories")
        stats["total_memories"] = cursor.fetchone()[0]
        
        # タイプ別
        cursor.execute("SELECT memory_type, COUNT(*) FROM memories GROUP BY memory_type")
        stats["by_type"] = {row[0]: row[1] for row in cursor.fetchall()}
        
        # 重要度別
        cursor.execute("SELECT importance, COUNT(*) FROM memories GROUP BY importance")
        stats["by_importance"] = {row[0]: row[1] for row in cursor.fetchall()}
        
        # 期限切れ予定
        cursor.execute("""
            SELECT COUNT(*) FROM memories 
            WHERE expires_at IS NOT NULL 
            AND expires_at < datetime('now')
        """)
        stats["expired"] = cursor.fetchone()[0]
        
        # 最近の作成
        week_ago = datetime.now() - timedelta(days=7)
        cursor.execute("""
            SELECT COUNT(*) FROM memories WHERE created_at > ?
        """, (week_ago,))
        stats["created_last_7_days"] = cursor.fetchone()[0]
        
        conn.close()
        return stats
    
    def export_to_json(self, filepath: str, memory_type: Optional[MemoryType] = None):
        """記憶をJSONエクスポート"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if memory_type:
            cursor.execute("SELECT * FROM memories WHERE memory_type = ?", (memory_type.value,))
        else:
            cursor.execute("SELECT * FROM memories")
        
        rows = cursor.fetchall()
        conn.close()
        
        entries = [self._row_to_entry(row).to_dict() for row in rows]
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
    
    def _row_to_entry(self, row) -> MemoryEntry:
        """DB行をMemoryEntryに変換"""
        return MemoryEntry(
            id=row[0],
            content=row[1],
            memory_type=MemoryType(row[2]),
            importance=ImportanceLevel(row[3]),
            created_at=datetime.fromisoformat(row[4]),
            updated_at=datetime.fromisoformat(row[5]),
            expires_at=datetime.fromisoformat(row[6]) if row[6] else None,
            tags=json.loads(row[7]) if row[7] else [],
            related_ids=json.loads(row[8]) if row[8] else [],
            context=json.loads(row[9]) if row[9] else {},
            access_count=row[10] or 0,
            last_accessed=datetime.fromisoformat(row[11]) if row[11] else None
        )
    
    def _update_access_count(self, memory_id: str):
        """アクセスカウントを更新"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE memories 
            SET access_count = access_count + 1, last_accessed = datetime('now')
            WHERE id = ?
        """, (memory_id,))
        
        # アクセスログも記録
        cursor.execute("""
            INSERT INTO memory_access_log (memory_id, query_context)
            VALUES (?, ?)
        """, (memory_id, json.dumps({"timestamp": datetime.now().isoformat()})))
        
        conn.commit()
        conn.close()


# グローバルインスタンス
_memory_instance: Optional[EntityMemory] = None


def get_memory() -> EntityMemory:
    """グローバルメモリインスタンスを取得"""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = EntityMemory()
    return _memory_instance


# 便利なショートカット関数
def remember(
    content: str,
    memory_type: str = "fact",
    importance: int = 3,
    tags: List[str] = None,
    **kwargs
) -> str:
    """記憶を保存する簡易関数"""
    mem = get_memory()
    return mem.store(
        content=content,
        memory_type=MemoryType(memory_type),
        importance=ImportanceLevel(importance),
        tags=tags,
        **kwargs
    )


def recall_memories(
    query: str,
    limit: int = 5,
    **kwargs
) -> List[MemoryEntry]:
    """記憶を検索する簡易関数"""
    mem = get_memory()
    return mem.recall(query, limit=limit, **kwargs)


def get_relevant_context(task: str, limit: int = 3) -> str:
    """
    タスクに関連する記憶を取得して文字列として返す
    （LLMプロンプトに組み込む用）
    """
    mem = get_memory()
    entries = mem.get_context_memories(task, limit=limit)
    
    if not entries:
        return ""
    
    context_parts = ["## 関連する過去の記憶:"]
    for entry in entries:
        context_parts.append(f"- [{entry.memory_type.value}] {entry.content[:200]}")
    
    return "\n".join(context_parts)


if __name__ == "__main__":
    # テスト
    print("🧠 Entity Memory System Test")
    
    mem = get_memory()
    
    # テスト記憶の保存
    id1 = mem.store(
        content="Gmail APIはService Account認証が推奨される",
        memory_type=MemoryType.FACT,
        importance=ImportanceLevel.HIGH,
        tags=["gmail", "api", "authentication"]
    )
    print(f"✅ Stored memory: {id1}")
    
    id2 = mem.store(
        content="Twitter APIは有料化されて$100/月が必要",
        memory_type=MemoryType.EXPERIENCE,
        importance=ImportanceLevel.HIGH,
        tags=["twitter", "api", "pricing"]
    )
    print(f"✅ Stored memory: {id2}")
    
    # リンク
    mem.link_memories(id1, id2)
    print(f"✅ Linked memories")
    
    # 検索
    results = mem.recall("API", tags=["gmail"])
    print(f"\n🔍 Search results for 'API' with tag 'gmail':")
    for r in results:
        print(f"  - {r.content[:50]}... (importance: {r.importance.value})")
    
    # 統計
    stats = mem.get_stats()
    print(f"\n📊 Memory stats: {stats}")
    
    print("\n✨ Test completed!")
