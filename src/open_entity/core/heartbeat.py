"""
Heartbeat Runner - 自律型エージェントの駆動エンジン。
定期的に HEARTBEAT.md のミッションを読み込み、エージェントに自律的に実行させる。
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
        progress = self._parse_progress(response)
        is_stuck = progress.get("stuck", False)

        # 履歴に記録（振り返り用）
        self._history.append({
            "beat": self._beat_count,
            "timestamp": datetime.now().isoformat(),
            "is_ok": not is_stuck,
            "summary": progress.get("done", (response or "")[:200]),
            "output": progress.get("output", ""),
            "next": progress.get("next", ""),
        })
        # 直近 evolve_every * 2 件だけ保持
        max_history = self.config.evolve_every * 2
        if len(self._history) > max_history:
            self._history = self._history[-max_history:]

        if is_stuck:
            logger.info(f"Heartbeat #{self._beat_count}: STUCK — {progress.get('stuck_reason', '?')}")
            print(f"    💓 Heartbeat #{self._beat_count}: STUCK — {progress.get('stuck_reason', '?')}")
            if self.after_heartbeat_callback:
                try:
                    if asyncio.iscoroutinefunction(self.after_heartbeat_callback):
                        await self.after_heartbeat_callback(response, self._beat_count)
                    else:
                        self.after_heartbeat_callback(response, self._beat_count)
                except Exception as cb_err:
                    logger.error(f"Heartbeat callback error: {cb_err}")
        else:
            done_msg = progress.get("done", "completed")
            logger.info(f"Heartbeat #{self._beat_count}: DONE — {done_msg}")
            print(f"    💓 Heartbeat #{self._beat_count}: DONE — {done_msg}")

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

    def _build_prompt(self, mission: str) -> str:
        """ハートビート用プロンプトを構築（ミッション駆動型）"""
        # 前回の成果サマリーを構築
        prev_summary = ""
        if self._history:
            last = self._history[-1]
            prev_summary = (
                f"\n## 前回の成果 (beat #{last['beat']})\n"
                f"{last['summary']}\n"
            )

        return (
            "[HEARTBEAT MISSION]\n\n"
            f"あなたは自律型エージェントです。これは定期実行 #{self._beat_count} 回目です。\n"
            "以下のミッションを読み、**具体的なアウトプットを1つ以上生み出してください。**\n\n"
            "## 実行ルール\n"
            "- まず TODO リストを作成し、今回取り組むタスクを決める\n"
            "- ツールを積極的に使う（web検索、ファイル操作、スキル作成など）\n"
            "- 調査だけで終わらない。必ずコード・スキル・ドキュメントなど形あるものを作る\n"
            "- 前回の続きがあれば、そこから始める\n"
            "- 作ったもの・学んだことは memory に保存する\n\n"
            f"## ミッション\n{mission}\n"
            f"{prev_summary}\n"
            "## 最終レポート\n"
            "実行が終わったら、以下の形式で簡潔に報告してください:\n"
            "```\n"
            "DONE: [今回やったこと（1行）]\n"
            "OUTPUT: [作成・変更したファイルやスキル名]\n"
            "NEXT: [次回やるべきこと]\n"
            "```\n"
            "何も進められなかった場合は STUCK: [理由] と報告してください。"
        )

    @staticmethod
    def _parse_progress(response: str) -> Dict[str, Any]:
        """応答から進捗レポートをパースする"""
        result: Dict[str, Any] = {"stuck": False}
        if not response:
            result["stuck"] = True
            result["stuck_reason"] = "no response"
            return result

        text = response.strip()

        # STUCK パターン
        stuck_match = re.search(r'STUCK:\s*(.+?)(?:\n|$)', text)
        if stuck_match:
            result["stuck"] = True
            result["stuck_reason"] = stuck_match.group(1).strip()
            return result

        # DONE / OUTPUT / NEXT パターン
        done_match = re.search(r'DONE:\s*(.+?)(?:\n|$)', text)
        if done_match:
            result["done"] = done_match.group(1).strip()

        output_match = re.search(r'OUTPUT:\s*(.+?)(?:\n|$)', text)
        if output_match:
            result["output"] = output_match.group(1).strip()

        next_match = re.search(r'NEXT:\s*(.+?)(?:\n|$)', text)
        if next_match:
            result["next"] = next_match.group(1).strip()

        # DONE が無い場合は応答全体の冒頭を要約として使う
        if "done" not in result:
            result["done"] = text[:150]

        return result

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

    def _build_evolve_prompt(self, current_mission: str) -> str:
        """振り返り用プロンプトを構築（ミッション進化）"""
        # 履歴サマリーを構築
        history_lines = []
        for h in self._history:
            status = "DONE" if h["is_ok"] else "STUCK"
            done = h.get("summary", "")[:100]
            output = h.get("output", "")
            next_task = h.get("next", "")
            line = f"  #{h['beat']} [{status}] {done}"
            if output:
                line += f" | output: {output}"
            if next_task:
                line += f" | next: {next_task}"
            history_lines.append(line.rstrip())
        history_text = "\n".join(history_lines) if history_lines else "  (まだ履歴がありません)"

        return (
            "[MISSION EVOLUTION]\n\n"
            "あなたはミッションの振り返りを行います。\n"
            f"これまでの {len(self._history)} 回の実行結果を踏まえ、ミッションを進化させてください。\n\n"
            "## 直近の実行結果\n"
            f"{history_text}\n\n"
            "## 現在のミッション\n"
            f"{current_mission}\n\n"
            "## 判断基準\n"
            "- 達成したスプリント項目 → 新しい目標に置き換える\n"
            "- STUCK が多い項目 → アプローチを変えるか、前提条件を整理する\n"
            "- 新しく発見した可能性 → スプリントに追加する\n"
            "- 長期ビジョンに近づいているか確認し、方向修正する\n\n"
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
