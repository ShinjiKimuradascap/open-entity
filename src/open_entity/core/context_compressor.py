"""
コンテキスト圧縮モジュール。

会話履歴がトークン上限に近づいた際に、古いメッセージを要約して圧縮する。

圧縮戦略:
- システムメッセージは常に保持
- 現在の run 内のメッセージ（最後の user メッセージ以降）は全件保持
- run 前の古い履歴のみを要約で圧縮
"""

import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

# トークン推定の統一係数（プロジェクト全体で使用）
TOKEN_ESTIMATE_RATIO = 1.5


def estimate_tokens(text: str) -> int:
    """文字数ベースのトークン推定（統一関数）。

    日本語は1文字≒1.5トークン、英語は1単語≒1.3トークン。
    安全マージンを含めて文字数の1.5倍で推定。
    """
    return int(len(text) * TOKEN_ESTIMATE_RATIO)


class ContextCompressor:
    """
    会話履歴の自動圧縮を行うクラス。

    トークン数がしきい値を超えた場合、run 前の古いメッセージのみを
    要約して圧縮する。run 内のメッセージは全件保持する。
    """

    def __init__(
        self,
        max_tokens: int = 200000,
        summary_model: Optional[str] = None,
    ):
        """
        Args:
            max_tokens: 圧縮を開始するトークン数のしきい値
            summary_model: 要約に使用するモデル名（省略時は自動選択）
        """
        from .llm_provider import get_analyzer_model
        self.max_tokens = max_tokens
        self.summary_model = summary_model or get_analyzer_model()

    def estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """メッセージリストのトークン数を推定する。"""
        total_chars = 0

        for msg in messages:
            # OpenAI形式: {"role": "...", "content": "..."}
            if "content" in msg:
                content = msg.get("content", "")
                if content:
                    total_chars += len(str(content))

            # Gemini形式: {"role": "...", "parts": [...]}
            if "parts" in msg:
                parts = msg.get("parts", [])
                for part in parts:
                    if isinstance(part, str):
                        total_chars += len(part)
                    elif isinstance(part, dict) and "text" in part:
                        total_chars += len(part["text"])
                    elif hasattr(part, "text") and part.text:
                        total_chars += len(part.text)

            # ツール呼び出し結果なども考慮
            if "tool_calls" in msg:
                for tc in msg.get("tool_calls", []):
                    if isinstance(tc, dict) and "function" in tc:
                        args = tc["function"].get("arguments", "")
                        total_chars += len(str(args))

        return int(total_chars * TOKEN_ESTIMATE_RATIO)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_run_boundary(self, messages: List[Dict[str, Any]]) -> int:
        """現在の run の開始位置を見つける。

        最後の user メッセージのインデックスを返す。
        それ以降が「現在の run」として保護される。
        """
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                return i
        # user メッセージがない場合は全件保護
        return 0

    def _extract_content(self, msg: Dict[str, Any]) -> str:
        """メッセージからテキストコンテンツを抽出"""
        # OpenAI形式
        if "content" in msg and msg["content"]:
            return str(msg["content"])

        # Gemini形式
        if "parts" in msg:
            parts = msg.get("parts", [])
            texts = []
            for part in parts:
                if isinstance(part, str):
                    texts.append(part)
                elif isinstance(part, dict) and "text" in part:
                    texts.append(part["text"])
                elif hasattr(part, "text") and part.text:
                    texts.append(part.text)
            return "\n".join(texts)

        return ""

    def _is_system_message(self, msg: Dict[str, Any]) -> bool:
        """システムメッセージかどうかを判定"""
        return msg.get("role", "") == "system"

    def _format_messages_for_summary(self, messages: List[Dict[str, Any]]) -> str:
        """要約用にメッセージを整形"""
        formatted = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = self._extract_content(msg)
            if content:
                if len(content) > 2000:
                    content = content[:2000] + "...(省略)"
                formatted.append(f"[{role}]: {content}")
        return "\n\n".join(formatted)

    def _generate_summary(self, messages: List[Dict[str, Any]], provider: str) -> str:
        """メッセージリストの構造化要約を生成する。"""
        conversation_text = self._format_messages_for_summary(messages)

        if not conversation_text.strip():
            return ""

        prompt = f"""以下の会話履歴を構造化された要約にしてください。

## 必須カテゴリ（該当するものだけ出力）
### 1. 主要リクエスト・目的
### 2. 実行されたアクション（ツール呼び出し結果の要点）
### 3. 技術的な決定事項・発見
### 4. エラーと対処
### 5. 未完了タスク
### 6. 記憶インデックス
- キーワード: 重要な用語・技術名・固有名詞
- トピック: 議論テーマ・意思決定のトピック
- エンティティ: クラス名・ファイル名・サービス名
※ 詳細が必要な場合は memory_recall(query="...") で長期記憶を検索可能

## ルール
- 各カテゴリは箇条書きで簡潔に
- ファイルパス、関数名、エラーメッセージなど具体的な情報は保持
- 不要な挨拶や繰り返しは省略
- 記憶インデックスは詳細を書かず、キーワードのみ

## 会話履歴
{conversation_text}

## 要約"""

        from .llm_provider import generate_text, get_analyzer_model
        provider_name = provider or "openrouter"
        model_name = self.summary_model or get_analyzer_model(provider_name)
        try:
            return generate_text(
                prompt=prompt,
                provider=provider_name,
                model=model_name,
                max_tokens=2000,
                temperature=0.3,
            )
        except Exception as e:
            logger.warning(f"Failed to summarize with provider={provider_name}: {e}")
            return ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compress_if_needed(
        self,
        messages: List[Dict[str, Any]],
        provider: str = "openrouter"
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """
        必要に応じてメッセージリストを圧縮する。

        圧縮戦略:
        1. システムメッセージは常に保持
        2. 現在の run 内のメッセージ（最後の user 以降）は全件保持
        3. run 前の古い会話履歴のみを要約で圧縮

        Args:
            messages: 元のメッセージリスト
            provider: LLMプロバイダ名

        Returns:
            (圧縮後のメッセージリスト, 圧縮が行われたかどうか)
        """
        if not messages:
            return messages, False

        estimated_tokens = self.estimate_tokens(messages)

        if estimated_tokens <= self.max_tokens:
            logger.debug(f"No compression needed: {estimated_tokens} tokens <= {self.max_tokens}")
            return messages, False

        logger.info(f"Compressing context: {estimated_tokens} tokens > {self.max_tokens}")

        # システムメッセージを分離
        system_messages = []
        non_system_messages = []
        for msg in messages:
            if self._is_system_message(msg):
                system_messages.append(msg)
            else:
                non_system_messages.append(msg)

        # 現在の run の境界を検出
        run_boundary = self._find_run_boundary(non_system_messages)

        # run 内メッセージ（保護対象）
        run_messages = non_system_messages[run_boundary:]

        # run 前メッセージ（圧縮対象）
        pre_run_messages = non_system_messages[:run_boundary]

        # 圧縮対象が少なすぎる場合はスキップ
        if len(pre_run_messages) < 3:
            logger.debug("Too few pre-run messages to compress")
            return messages, False

        # run 前メッセージを要約
        summary = self._generate_summary(pre_run_messages, provider)

        if not summary:
            logger.warning("Failed to generate summary, returning original messages")
            return messages, False

        # 圧縮後のメッセージリストを構築
        compressed_messages = list(system_messages)

        # 要約を system メッセージとして追加
        compressed_messages.append({
            "role": "system",
            "content": f"[以前の会話の要約]\n{summary}\n[要約ここまで]"
        })

        # run 内メッセージを全件追加
        compressed_messages.extend(run_messages)

        new_token_count = self.estimate_tokens(compressed_messages)
        logger.info(
            f"Compressed: {estimated_tokens} -> {new_token_count} tokens "
            f"({len(messages)} -> {len(compressed_messages)} messages, "
            f"run messages preserved: {len(run_messages)})"
        )

        return compressed_messages, True
