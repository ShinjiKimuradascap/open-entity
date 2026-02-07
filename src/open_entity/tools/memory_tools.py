"""
記憶検索ツール。

MemoryService の recall() をラップし、LLM がツールコールで
長期記憶を能動的に検索できるようにする。
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# MemoryService のシングルトン参照（Orchestrator が設定する）
_memory_service = None


def set_memory_service(service) -> None:
    """Orchestrator から MemoryService を注入する。"""
    global _memory_service
    _memory_service = service


def memory_recall(query: str, top_k: int = 5) -> str:
    """
    長期記憶を検索します。過去の会話で学んだ知識、技術的な決定事項、
    エラーと解決策などを思い出すことができます。

    要約や会話の中で「以前議論した」「前に決めた」などのヒントを見つけたら、
    このツールで詳細を検索してください。

    Args:
        query: 検索クエリ（キーワード、トピック、質問文など）
        top_k: 返す記憶の最大数（デフォルト: 5）

    Returns:
        関連する記憶のリスト。見つからない場合はその旨を返す。

    Examples:
        memory_recall("JWT認証の実装方針")
        memory_recall("ContextCompressor のバグ修正")
        memory_recall("ユーザーの好み コーディングスタイル")
    """
    if _memory_service is None:
        return "Error: Memory service is not available. (MOCO_MEMORY_SERVICE=off or not initialized)"

    try:
        results = _memory_service.recall(query, top_k=top_k)
    except Exception as e:
        logger.error(f"memory_recall failed: {e}")
        return f"Error: Memory recall failed: {e}"

    if not results:
        return f"No relevant memories found for: {query}"

    lines = [f"Found {len(results)} relevant memories:\n"]
    for i, mem in enumerate(results, 1):
        content = mem.get("content", "")
        mem_type = mem.get("type", "unknown")
        score = mem.get("score", 0)
        # 長すぎる内容は切り詰め
        if len(content) > 500:
            content = content[:500] + "..."
        lines.append(f"--- Memory {i} (type={mem_type}, relevance={score:.2f}) ---")
        lines.append(content)
        lines.append("")

    return "\n".join(lines)
