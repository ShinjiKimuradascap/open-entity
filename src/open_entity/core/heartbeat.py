"""
Heartbeat Runner - OpenClaw 風のプロアクティブ監視機構。
定期的に HEARTBEAT.md をエージェントに渡し、注意すべき事項があれば通知する。
"""
import asyncio
import logging
import os
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Optional, Callable, Any, Dict, List
import re

logger = logging.getLogger(__name__)


class HeartbeatConfig:
    """Heartbeat 設定を管理するクラス"""

    def __init__(self, profile_config: Dict[str, Any]):
        hb = profile_config.get("heartbeat", {})
        self.enabled: bool = self._parse_enabled(hb.get("enabled", False))
        self.interval_seconds: int = self._parse_interval(hb.get("interval", "30m"))
        self.active_hours: Optional[tuple] = self._parse_active_hours(
            hb.get("active_hours")
        )
        self.timezone: str = hb.get("timezone", "UTC")
        self.ack_token: str = hb.get("ack_token", "HEARTBEAT_OK")
        self.ack_max_chars: int = int(hb.get("ack_max_chars", 300))
        self.model: Optional[str] = hb.get("model", None)
        self.evolve_every: int = int(hb.get("evolve_every", 5))

        # 環境変数によるオーバーライド
        env_enabled = os.getenv("MOCO_HEARTBEAT_ENABLED")
        if env_enabled is not None:
            self.enabled = env_enabled.lower() in ("1", "true", "yes", "on")
        env_interval = os.getenv("MOCO_HEARTBEAT_INTERVAL")
        if env_interval:
            self.interval_seconds = self._parse_interval(env_interval)

    @staticmethod
    def _parse_enabled(value) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    @staticmethod
    def _parse_interval(value: str) -> int:
        """'30m', '1h', '300' のような文字列を秒に変換"""
        s = str(value).strip().lower()
        if s.endswith("m"):
            return int(s[:-1]) * 60
        if s.endswith("h"):
            return int(s[:-1]) * 3600
        if s.endswith("s"):
            return int(s[:-1])
        return int(s)

    @staticmethod
    def _parse_active_hours(value: Optional[str]) -> Optional[tuple]:
        """'09:00-22:00' を (dt_time(9,0), dt_time(22,0)) に変換"""
        if not value:
            return None
        parts = str(value).split("-")
        if len(parts) != 2:
            return None
        start = dt_time(*[int(x) for x in parts[0].strip().split(":")])
        end = dt_time(*[int(x) for x in parts[1].strip().split(":")])
        return (start, end)


class HeartbeatRunner:
    """
    Heartbeat 実行ループ。
    MocoScheduler と同じ asyncio.create_task パターンで動作するが、
    HTTP ではなく Orchestrator を直接呼び出す。
    """

    def __init__(
        self,
        config: HeartbeatConfig,
        orchestrator_factory: Callable,
        profile: str = "default",
        heartbeat_md_path: Optional[str] = None,
        after_heartbeat_callback: Optional[Callable] = None,
    ):
        self.config = config
        self.orchestrator_factory = orchestrator_factory
        self.profile = profile
        self.after_heartbeat_callback = after_heartbeat_callback
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._session_id: Optional[str] = None
        self._beat_count: int = 0
        self._history: List[Dict[str, Any]] = []  # 直近の heartbeat 結果を記録

        # HEARTBEAT.md のパスを解決
        if heartbeat_md_path:
            self._heartbeat_md = Path(heartbeat_md_path)
        else:
            self._heartbeat_md = self._resolve_heartbeat_md(profile)

    @staticmethod
    def _resolve_heartbeat_md(profile: str) -> Path:
        """プロファイルディレクトリまたは作業ディレクトリから HEARTBEAT.md を解決"""
        from ..tools.discovery import _find_profiles_dir

        # 1. プロファイルディレクトリ
        profiles_dir = _find_profiles_dir()
        candidate = Path(profiles_dir) / profile / "HEARTBEAT.md"
        if candidate.exists():
            return candidate

        # 2. 作業ディレクトリ
        workdir = Path(os.getenv("MOCO_WORKING_DIRECTORY", os.getcwd()))
        return workdir / "HEARTBEAT.md"

    async def start(self):
        """ハートビートループを開始"""
        if not self.config.enabled:
            logger.info("Heartbeat is disabled in configuration.")
            return
        if self._running:
            logger.warning("Heartbeat runner is already running.")
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"Heartbeat runner started (interval={self.config.interval_seconds}s, "
            f"active_hours={self.config.active_hours}, "
            f"file={self._heartbeat_md})"
        )

    async def stop(self):
        """ハートビートループを停止"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Heartbeat runner stopped.")

    async def _loop(self):
        """メインハートビートループ"""
        # 起動直後は1分待って安定化させる
        await asyncio.sleep(60)

        while self._running:
            try:
                if self._is_within_active_hours():
                    await self._execute_heartbeat()
                else:
                    logger.debug("Heartbeat skipped: outside active hours")
            except Exception as e:
                logger.error(f"Heartbeat error: {e}", exc_info=True)

            await asyncio.sleep(self.config.interval_seconds)

    def _is_within_active_hours(self) -> bool:
        """アクティブ時間帯内かチェック"""
        if not self.config.active_hours:
            return True  # 制限なし

        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(self.config.timezone)
        except Exception:
            tz = None

        now = datetime.now(tz).time() if tz else datetime.now().time()
        start, end = self.config.active_hours

        if start <= end:
            return start <= now <= end
        else:
            # 深夜を跨ぐケース (e.g. 22:00-06:00)
            return now >= start or now <= end

    async def _execute_heartbeat(self):
        """1回のハートビートを実行"""
        # HEARTBEAT.md を読み込む
        checklist = self._load_heartbeat_md()
        if not checklist:
            logger.debug("Heartbeat skipped: HEARTBEAT.md is empty or missing")
            return

        self._beat_count += 1
        logger.info(f"Heartbeat #{self._beat_count} executing...")
        print(f"    💓 Heartbeat #{self._beat_count} executing...")

        # Orchestrator を生成（ファクトリ経由）
        orchestrator = self.orchestrator_factory()

        # 専用セッションの作成（初回のみ、以降は継続）
        if not self._session_id:
            self._session_id = orchestrator.create_session(
                title="Heartbeat Monitor"
            )

        # ハートビートプロンプトを構築
        prompt = self._build_prompt(checklist)

        # Orchestrator 経由で実行
        try:
            response = await orchestrator.run(prompt, session_id=self._session_id)
        except Exception as e:
            logger.error(f"Heartbeat orchestrator error: {e}")
            return

        # 応答を解析
        is_ok = self._is_ack(response)

        # 履歴に記録（振り返り用）
        self._history.append({
            "beat": self._beat_count,
            "timestamp": datetime.now().isoformat(),
            "is_ok": is_ok,
            "summary": (response or "")[:200],
        })
        # 直近 evolve_every * 2 件だけ保持
        max_history = self.config.evolve_every * 2
        if len(self._history) > max_history:
            self._history = self._history[-max_history:]

        if is_ok:
            logger.info(f"Heartbeat #{self._beat_count}: OK (silent)")
            print(f"    💓 Heartbeat #{self._beat_count}: OK ✓")
        else:
            logger.info(f"Heartbeat #{self._beat_count}: Alert detected, notifying...")
            print(f"    💓 Heartbeat #{self._beat_count}: Alert! Notifying...")
            if self.after_heartbeat_callback:
                try:
                    if asyncio.iscoroutinefunction(self.after_heartbeat_callback):
                        await self.after_heartbeat_callback(response, self._beat_count)
                    else:
                        self.after_heartbeat_callback(response, self._beat_count)
                except Exception as cb_err:
                    logger.error(f"Heartbeat callback error: {cb_err}")

        # N回ごとにチェックリストを振り返り・進化させる
        if (
            self.config.evolve_every > 0
            and self._beat_count % self.config.evolve_every == 0
        ):
            await self._evolve_checklist(orchestrator, checklist)

    def _load_heartbeat_md(self) -> str:
        """HEARTBEAT.md の内容を読み込む。空文字列ならスキップ対象"""
        if not self._heartbeat_md.exists():
            return ""
        try:
            content = self._heartbeat_md.read_text(encoding="utf-8").strip()
            # ヘッダーのみ（実質空）の場合もスキップ
            lines = [
                l.strip() for l in content.splitlines()
                if l.strip() and not l.strip().startswith("#")
            ]
            if not lines:
                return ""
            return content
        except Exception as e:
            logger.warning(f"Failed to read HEARTBEAT.md: {e}")
            return ""

    def _build_prompt(self, checklist: str) -> str:
        """ハートビート用プロンプトを構築"""
        return (
            "[HEARTBEAT CHECK]\n\n"
            "あなたは定期ハートビートチェックを実行中です。\n"
            "以下のチェックリストの **各項目を必ずツールを使って1つずつ確認** してください。\n\n"
            "## 重要な実行ルール\n"
            "- まずチェックリストの全項目を TODO リストとして作成すること\n"
            "- チェック項目ごとに適切なツールを呼び出して実際の状態を確認すること\n"
            "- ツールを使わずに推測で OK と判断してはいけない\n"
            "- 各チェック項目の結果を踏まえてから最終判断すること\n\n"
            "## チェックリスト\n"
            f"{checklist}\n\n"
            "## 応答ルール\n"
            f"- 全項目をチェックした結果、通知不要の場合: 「{self.config.ack_token}」とだけ回答してください\n"
            f"- 注意が必要な項目がある場合: {self.config.ack_max_chars}文字以内で簡潔に報告してください\n"
            "- 冗長な説明は不要です。要点のみ伝えてください"
        )

    def _is_ack(self, response: str) -> bool:
        """応答がACK（正常・通知不要）かどうかを判定"""
        if not response:
            return True  # 空応答はOK扱い
        cleaned = response.strip()
        # ACKトークンが先頭または末尾にある
        if cleaned.startswith(self.config.ack_token) or cleaned.endswith(self.config.ack_token):
            # トークンを除いた残りが ack_max_chars 以下ならACK
            remainder = cleaned.replace(self.config.ack_token, "").strip()
            if len(remainder) <= self.config.ack_max_chars:
                return True
        # トークンが応答のどこかに含まれ、全体が短い場合もOK
        if self.config.ack_token in cleaned and len(cleaned) <= self.config.ack_max_chars:
            return True
        return False

    async def _evolve_checklist(self, orchestrator, current_checklist: str):
        """過去の heartbeat 結果を振り返り、HEARTBEAT.md を更新する"""
        logger.info(f"Heartbeat evolution triggered (every {self.config.evolve_every} beats)")
        print(f"    💓 Heartbeat evolution triggered (rewriting HEARTBEAT.md...)")

        prompt = self._build_evolve_prompt(current_checklist)

        try:
            response = await orchestrator.run(prompt, session_id=self._session_id)
        except Exception as e:
            logger.error(f"Heartbeat evolution error: {e}")
            return

        if not response or len(response.strip()) < 20:
            logger.warning("Heartbeat evolution returned empty/short response, skipping update")
            return

        new_content = self._parse_evolve_response(response)
        if new_content:
            self._write_heartbeat_md(new_content)
            logger.info(f"HEARTBEAT.md updated by evolution (beat #{self._beat_count})")
            print(f"    💓 HEARTBEAT.md evolved ✓ (beat #{self._beat_count})")
        else:
            logger.warning("Could not parse evolution response, skipping update")

    def _build_evolve_prompt(self, current_checklist: str) -> str:
        """振り返り用プロンプトを構築"""
        # 履歴サマリーを構築
        history_lines = []
        for h in self._history:
            status = "OK" if h["is_ok"] else "ALERT"
            summary = h["summary"][:100] if not h["is_ok"] else ""
            history_lines.append(f"  #{h['beat']} [{status}] {summary}".rstrip())
        history_text = "\n".join(history_lines) if history_lines else "  (まだ履歴がありません)"

        return (
            "[HEARTBEAT EVOLUTION]\n\n"
            "あなたはハートビートチェックリストの振り返りを行います。\n"
            f"これまでの {len(self._history)} 回の結果を踏まえ、チェックリストを改善してください。\n\n"
            "## 直近の結果\n"
            f"{history_text}\n\n"
            "## 現在のチェックリスト\n"
            f"{current_checklist}\n\n"
            "## 判断基準\n"
            "- 毎回 OK だった項目 → 頻度を下げるか削除を検討\n"
            "- アラートが多かった項目 → より具体的な条件に改善\n"
            "- チェックリストに無いが気になった事項 → 新規追加\n"
            "- ユーザーの活動パターンに合わせた調整\n\n"
            "## 出力形式\n"
            "更新後の HEARTBEAT.md の内容をそのまま出力してください。\n"
            "マークダウン形式で、コードブロック(```)で囲まず、ファイル内容だけを返してください。"
        )

    @staticmethod
    def _parse_evolve_response(response: str) -> Optional[str]:
        """進化レスポンスから HEARTBEAT.md の内容を抽出"""
        content = response.strip()

        # コードブロックで囲まれている場合は中身を抽出
        fence_match = re.search(r'```(?:markdown)?\s*\n(.*?)\n```', content, re.DOTALL)
        if fence_match:
            content = fence_match.group(1).strip()

        # マークダウンのヘッダーが含まれているか確認（最低限のバリデーション）
        if "#" not in content:
            return None

        return content + "\n"

    def _write_heartbeat_md(self, content: str):
        """HEARTBEAT.md を書き込む"""
        try:
            self._heartbeat_md.parent.mkdir(parents=True, exist_ok=True)
            self._heartbeat_md.write_text(content, encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to write HEARTBEAT.md: {e}")

    async def trigger_once(self) -> str:
        """手動で1回ハートビートを実行（CLI用）。結果を返す"""
        checklist = self._load_heartbeat_md()
        if not checklist:
            return "HEARTBEAT.md is empty or not found."

        orchestrator = self.orchestrator_factory()
        if not self._session_id:
            self._session_id = orchestrator.create_session(
                title="Heartbeat Monitor"
            )

        prompt = self._build_prompt(checklist)
        response = await orchestrator.run(prompt, session_id=self._session_id)
        return response or "(no response)"

    def get_status(self) -> Dict[str, Any]:
        """ハートビートの状態を返す"""
        return {
            "running": self._running,
            "enabled": self.config.enabled,
            "interval_seconds": self.config.interval_seconds,
            "active_hours": (
                f"{self.config.active_hours[0].strftime('%H:%M')}-"
                f"{self.config.active_hours[1].strftime('%H:%M')}"
                if self.config.active_hours else None
            ),
            "timezone": self.config.timezone,
            "heartbeat_md": str(self._heartbeat_md),
            "heartbeat_md_exists": self._heartbeat_md.exists(),
            "beat_count": self._beat_count,
            "session_id": self._session_id,
        }
