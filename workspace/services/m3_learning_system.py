"""
M3 Autonomous Learning System
M3自律学習システム

Entityが自己の行動・経験から学び、継続的に改善するためのシステム。
EntityMemory、PerformanceMonitor、RootCauseAnalyzerを統合して
自律的な学習ループを実現する。

機能:
- 経験データの自動収集と分類
- 行動パターンの分析と改善提案
- エラー・失敗からの学習
- パフォーマンス傾向の分析
- 定期的な自己分析レポート生成
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging

# プロジェクトルートを追加
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.entity_memory import (
    EntityMemory, MemoryType, ImportanceLevel, 
    get_memory, remember, recall_memories
)
from services.ai_performance_monitor import (
    AIPerformanceMonitor, get_performance_monitor, AlertLevel
)
from services.root_cause_analyzer import RootCauseAnalyzer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LearningEventType(Enum):
    """学習イベントタイプ"""
    SUCCESS = "success"              # 成功体験
    FAILURE = "failure"              # 失敗・エラー
    PATTERN = "pattern"              # パターン発見
    INSIGHT = "insight"              # 洞察・気づき
    DECISION = "decision"            # 重要な決定
    PERFORMANCE = "performance"      # パフォーマンス変化


@dataclass
class LearningEvent:
    """学習イベント"""
    id: str
    event_type: LearningEventType
    timestamp: datetime
    context: Dict[str, Any]           # イベントの文脈
    action_taken: str                 # 取った行動
    result: str                       # 結果
    lessons_learned: List[str]        # 学んだ教訓
    improvement_suggestions: List[str]  # 改善提案
    related_memory_ids: List[str]     # 関連する記憶ID


@dataclass
class BehaviorPattern:
    """行動パターン"""
    pattern_id: str
    pattern_type: str                 # 'success', 'failure', 'efficiency'
    description: str
    frequency: int                    # 発生頻度
    avg_outcome: float                # 平均結果スコア
    last_observed: datetime
    confidence: float                 # 信頼度 (0-1)


@dataclass
class SelfAnalysisReport:
    """自己分析レポート"""
    report_id: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    
    # サマリー統計
    total_actions: int
    success_count: int
    failure_count: int
    success_rate: float
    
    # パフォーマンス傾向
    performance_trend: str            # 'improving', 'stable', 'declining'
    avg_response_time: float
    error_rate: float
    
    # 学習成果
    new_patterns_discovered: int
    lessons_learned: List[str]
    applied_improvements: int
    
    # 主要な洞察
    key_insights: List[Dict[str, str]]
    
    # 改善提案
    improvement_recommendations: List[Dict[str, Any]]
    
    # 次のアクション
    next_actions: List[str]


class M3LearningSystem:
    """
    M3自律学習システム
    
    Entityが自己の経験から継続的に学び、パフォーマンスを改善する
    ための中心的システム。
    """
    
    def __init__(
        self,
        memory: Optional[EntityMemory] = None,
        monitor: Optional[AIPerformanceMonitor] = None,
        data_dir: str = None
    ):
        self.memory = memory or get_memory()
        self.monitor = monitor or get_performance_monitor()
        self.analyzer = RootCauseAnalyzer()
        
        self.data_dir = data_dir or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            "data", "learning"
        )
        os.makedirs(self.data_dir, exist_ok=True)
        
        # 学習データ
        self.learning_events: List[LearningEvent] = []
        self.behavior_patterns: Dict[str, BehaviorPattern] = {}
        
        # 学習ループ制御
        self._learning_task: Optional[asyncio.Task] = None
        self._running = False
        
        # コールバック
        self.report_callbacks: List[Callable[[SelfAnalysisReport], None]] = []
        
        logger.info("🧠 M3 Learning System initialized")
    
    def start_continuous_learning(self, interval_minutes: int = 30):
        """継続的学習を開始"""
        if self._running:
            logger.warning("Learning system is already running")
            return
        
        self._running = True
        self._learning_task = asyncio.create_task(
            self._learning_loop(interval_minutes)
        )
        logger.info(f"🔄 Continuous learning started (interval: {interval_minutes}min)")
    
    async def stop(self):
        """学習システムを停止"""
        if not self._running:
            return
        
        self._running = False
        if self._learning_task:
            self._learning_task.cancel()
            try:
                await self._learning_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 M3 Learning System stopped")
    
    async def _learning_loop(self, interval_minutes: int):
        """学習メインループ"""
        while self._running:
            try:
                # 1. パフォーマンスデータ収集
                await self._collect_performance_data()
                
                # 2. エラー・失敗から学習
                await self._learn_from_failures()
                
                # 3. パターン発見
                await self._discover_patterns()
                
                # 4. 定期的レポート生成（毎回は生成しない）
                if datetime.now().minute % 60 < interval_minutes:
                    report = await self.generate_self_analysis_report()
                    await self._save_report(report)
                    await self._notify_report(report)
                
                # 待機
                await asyncio.sleep(interval_minutes * 60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Learning loop error: {e}")
                await asyncio.sleep(60)
    
    async def _collect_performance_data(self):
        """パフォーマンスデータを収集して記憶に保存"""
        try:
            # パフォーマンススナップショット取得
            snapshot = self.monitor.get_snapshot()
            
            # 重要なパフォーマンス変化を記憶
            if snapshot.system.cpu_percent > 80:
                self.memory.store(
                    content=f"CPU使用率が高い状態を検出: {snapshot.system.cpu_percent:.1f}%",
                    memory_type=MemoryType.EXPERIENCE,
                    importance=ImportanceLevel.MEDIUM,
                    tags=["performance", "cpu", "monitoring"],
                    context={
                        "cpu_percent": snapshot.system.cpu_percent,
                        "memory_percent": snapshot.system.memory_percent,
                        "error_rate": snapshot.error_rate
                    }
                )
            
            # エラー率の記録
            if snapshot.error_rate > 5:
                self.memory.store(
                    content=f"エラー率上昇を検出: {snapshot.error_rate:.1f}%",
                    memory_type=MemoryType.ERROR,
                    importance=ImportanceLevel.HIGH,
                    tags=["error", "performance", "alert"],
                    context={"error_rate": snapshot.error_rate}
                )
            
            logger.debug("✅ Performance data collected")
            
        except Exception as e:
            logger.error(f"Performance data collection error: {e}")
    
    async def _learn_from_failures(self):
        """失敗・エラーから学習"""
        try:
            # 最近のエラー記憶を検索
            recent_errors = self.memory.recall(
                query="",
                memory_type=MemoryType.ERROR,
                limit=10
            )
            
            for error in recent_errors:
                # 既に学習済みかチェック
                if error.context.get("learned", False):
                    continue
                
                # 教訓を抽出
                lessons = self._extract_lessons(error)
                
                # 学習イベント作成
                event = LearningEvent(
                    id=f"learn_{error.id}",
                    event_type=LearningEventType.FAILURE,
                    timestamp=datetime.now(),
                    context=error.context,
                    action_taken=error.content,
                    result="failure",
                    lessons_learned=lessons,
                    improvement_suggestions=self._generate_improvements(error),
                    related_memory_ids=[error.id]
                )
                
                self.learning_events.append(event)
                
                # 記憶にマーク
                self.memory.update(
                    error.id,
                    context={**error.context, "learned": True, "lessons": lessons}
                )
                
                # 学習成果を保存
                self.memory.store(
                    content=f"エラーから学習: {error.content[:100]}... 教訓: {'; '.join(lessons)}",
                    memory_type=MemoryType.EXPERIENCE,
                    importance=ImportanceLevel.HIGH,
                    tags=["learning", "error", "improvement"],
                    related_ids=[error.id]
                )
            
            logger.debug(f"✅ Learned from {len(recent_errors)} failures")
            
        except Exception as e:
            logger.error(f"Learning from failures error: {e}")
    
    def _extract_lessons(self, error_entry) -> List[str]:
        """エラーから教訓を抽出"""
        lessons = []
        content = error_entry.content.lower()
        
        # パターンに基づく教訓抽出
        if "timeout" in content or "timed out" in content:
            lessons.append("タイムアウト設定を見直し、より長い待機時間を設定する")
        
        if "connection" in content or "refused" in content:
            lessons.append("接続前にヘルスチェックを実施する")
        
        if "memory" in content or "memoryerror" in content:
            lessons.append("メモリ使用量を監視し、大きなデータは分割処理する")
        
        if "permission" in content or "access" in content:
            lessons.append("ファイル操作前にパーミッションを確認する")
        
        if not lessons:
            lessons.append("このエラーのパターンを監視し、再発時に対応を検討する")
        
        return lessons
    
    def _generate_improvements(self, error_entry) -> List[str]:
        """改善提案を生成"""
        improvements = []
        content = error_entry.content.lower()
        
        if "timeout" in content:
            improvements.append("retryロジックに指数関数的バックオフを実装")
        
        if "api" in content:
            improvements.append("APIクライアントにサーキットブレーカーを追加")
        
        if "database" in content or "sqlite" in content:
            improvements.append("DB接続プールの最適化")
        
        return improvements
    
    async def _discover_patterns(self):
        """行動パターンを発見"""
        try:
            # 成功パターンの検索
            successes = self.memory.recall(
                query="",
                memory_type=MemoryType.EXPERIENCE,
                importance_min=ImportanceLevel.HIGH,
                limit=50
            )
            
            # タグベースでグループ化
            tag_groups: Dict[str, List] = {}
            for entry in successes:
                for tag in entry.tags:
                    if tag not in tag_groups:
                        tag_groups[tag] = []
                    tag_groups[tag].append(entry)
            
            # 頻出パターンを特定
            for tag, entries in tag_groups.items():
                if len(entries) >= 3:  # 3回以上の繰り返し
                    pattern_id = f"pattern_{tag}_{datetime.now().strftime('%Y%m%d')}"
                    
                    if pattern_id not in self.behavior_patterns:
                        pattern = BehaviorPattern(
                            pattern_id=pattern_id,
                            pattern_type="success",
                            description=f"'{tag}'に関連する高頻度成功パターン",
                            frequency=len(entries),
                            avg_outcome=sum(e.importance.value for e in entries) / len(entries),
                            last_observed=datetime.now(),
                            confidence=min(1.0, len(entries) / 10)
                        )
                        
                        self.behavior_patterns[pattern_id] = pattern
                        
                        # 記憶に保存
                        self.memory.store(
                            content=f"新しい行動パターンを発見: {pattern.description}",
                            memory_type=MemoryType.EXPERIENCE,
                            importance=ImportanceLevel.MEDIUM,
                            tags=["pattern", "discovery", tag],
                            context=asdict(pattern)
                        )
            
            logger.debug(f"✅ Discovered {len(self.behavior_patterns)} patterns")
            
        except Exception as e:
            logger.error(f"Pattern discovery error: {e}")
    
    async def generate_self_analysis_report(
        self,
        period_hours: int = 24
    ) -> SelfAnalysisReport:
        """自己分析レポートを生成"""
        
        now = datetime.now()
        period_start = now - timedelta(hours=period_hours)
        
        # 1. 期間内の活動統計
        all_memories = self.memory.recall(
            query="",
            limit=1000,
            include_expired=True
        )
        
        period_memories = [
            m for m in all_memories
            if m.created_at >= period_start
        ]
        
        # 2. 成功・失敗カウント
        errors = [m for m in period_memories if m.memory_type == MemoryType.ERROR]
        successes = [m for m in period_memories if m.memory_type == MemoryType.EXPERIENCE]
        
        total = len(period_memories)
        success_count = len(successes)
        failure_count = len(errors)
        success_rate = (success_count / total * 100) if total > 0 else 0
        
        # 3. パフォーマンス傾向
        snapshot = self.monitor.get_snapshot()
        
        # 傾向判定
        if success_rate > 80:
            trend = "improving"
        elif success_rate > 60:
            trend = "stable"
        else:
            trend = "declining"
        
        # 4. 洞察の抽出
        insights = []
        for pattern in self.behavior_patterns.values():
            if pattern.confidence > 0.7:
                insights.append({
                    "type": "pattern",
                    "content": f"高確信度パターン: {pattern.description}",
                    "confidence": f"{pattern.confidence:.1%}"
                })
        
        # 最近の学習イベントから洞察
        recent_events = [
            e for e in self.learning_events
            if e.timestamp >= period_start
        ]
        
        for event in recent_events[:3]:
            for lesson in event.lessons_learned:
                insights.append({
                    "type": "lesson",
                    "content": lesson,
                    "source": event.event_type.value
                })
        
        # 5. 改善提案
        recommendations = []
        
        if snapshot.error_rate > 5:
            recommendations.append({
                "priority": "high",
                "area": "error_handling",
                "action": "エラーハンドリングの強化",
                "reason": f"エラー率が{snapshot.error_rate:.1f}%と高い"
            })
        
        if snapshot.system.cpu_percent > 70:
            recommendations.append({
                "priority": "medium",
                "area": "performance",
                "action": "CPU負荷軽減の検討",
                "reason": f"CPU使用率が{snapshot.system.cpu_percent:.1f}%"
            })
        
        # 6. 次のアクション
        next_actions = [
            "過去のエラーパターンをレビュー",
            "高頻度の成功パターンを標準化",
            "パフォーマンスメトリクスの継続監視"
        ]
        
        # レポート作成
        report = SelfAnalysisReport(
            report_id=f"report_{now.strftime('%Y%m%d_%H%M%S')}",
            generated_at=now,
            period_start=period_start,
            period_end=now,
            total_actions=total,
            success_count=success_count,
            failure_count=failure_count,
            success_rate=success_rate,
            performance_trend=trend,
            avg_response_time=snapshot.api_summary.get("avg_response_time_ms", 0),
            error_rate=snapshot.error_rate,
            new_patterns_discovered=len([p for p in self.behavior_patterns.values() if p.last_observed >= period_start]),
            lessons_learned=[lesson for event in recent_events for lesson in event.lessons_learned],
            applied_improvements=len([e for e in recent_events if e.improvement_suggestions]),
            key_insights=insights,
            improvement_recommendations=recommendations,
            next_actions=next_actions
        )
        
        return report
    
    async def _save_report(self, report: SelfAnalysisReport):
        """レポートをファイルに保存"""
        filepath = os.path.join(
            self.data_dir,
            f"self_analysis_{report.report_id}.json"
        )
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(asdict(report), f, ensure_ascii=False, indent=2, default=str)
        
        logger.info(f"📊 Self-analysis report saved: {filepath}")
    
    async def _notify_report(self, report: SelfAnalysisReport):
        """レポート通知"""
        for callback in self.report_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(report)
                else:
                    callback(report)
            except Exception as e:
                logger.error(f"Report callback error: {e}")
    
    def register_report_callback(self, callback: Callable[[SelfAnalysisReport], None]):
        """レポートコールバックを登録"""
        self.report_callbacks.append(callback)
    
    def record_experience(
        self,
        action: str,
        result: str,
        outcome: str,
        tags: List[str] = None,
        importance: ImportanceLevel = ImportanceLevel.MEDIUM
    ) -> str:
        """
        経験を記録（簡易インターフェース）
        
        Args:
            action: 取った行動
            result: 結果（'success', 'failure', 'partial'）
            outcome: 結果の詳細
            tags: タグリスト
            importance: 重要度
        
        Returns:
            記憶ID
        """
        memory_type = MemoryType.EXPERIENCE if result == "success" else MemoryType.ERROR
        
        content = f"[経験] {action} → {outcome}"
        
        memory_id = self.memory.store(
            content=content,
            memory_type=memory_type,
            importance=importance,
            tags=tags or ["experience", result],
            context={
                "action": action,
                "result": result,
                "outcome": outcome,
                "recorded_by": "m3_learning_system"
            }
        )
        
        return memory_id
    
    def get_learning_stats(self) -> Dict[str, Any]:
        """学習統計を取得"""
        return {
            "total_learning_events": len(self.learning_events),
            "discovered_patterns": len(self.behavior_patterns),
            "memory_stats": self.memory.get_stats(),
            "running": self._running
        }


# グローバルインスタンス
_learning_system: Optional[M3LearningSystem] = None


def get_learning_system() -> M3LearningSystem:
    """グローバル学習システムインスタンスを取得"""
    global _learning_system
    if _learning_system is None:
        _learning_system = M3LearningSystem()
    return _learning_system


# 便利なショートカット関数
def record_success(action: str, outcome: str, tags: List[str] = None):
    """成功体験を記録"""
    ls = get_learning_system()
    return ls.record_experience(
        action=action,
        result="success",
        outcome=outcome,
        tags=tags,
        importance=ImportanceLevel.MEDIUM
    )


def record_failure(action: str, outcome: str, tags: List[str] = None):
    """失敗を記録"""
    ls = get_learning_system()
    return ls.record_experience(
        action=action,
        result="failure",
        outcome=outcome,
        tags=tags,
        importance=ImportanceLevel.HIGH
    )


async def generate_report(period_hours: int = 24) -> SelfAnalysisReport:
    """自己分析レポートを生成"""
    ls = get_learning_system()
    return await ls.generate_self_analysis_report(period_hours)


# メイン実行
async def main():
    """デモ実行"""
    print("🚀 M3 Learning System Demo")
    
    # 学習システム初期化
    ls = get_learning_system()
    
    # いくつかの経験を記録
    print("\n📚 Recording experiences...")
    
    record_success(
        action="APIエンドポイントの最適化",
        outcome="レスポンスタイムが200msから50msに改善",
        tags=["optimization", "api", "performance"]
    )
    
    record_failure(
        action="DB接続プールの設定変更",
        outcome="接続数超過でエラー発生",
        tags=["database", "configuration", "error"]
    )
    
    record_success(
        action="キャッシュ戦略の導入",
        outcome="リクエスト処理速度が3倍に向上",
        tags=["cache", "optimization", "performance"]
    )
    
    # レポート生成
    print("\n📊 Generating self-analysis report...")
    report = await generate_report(period_hours=24)
    
    print(f"\n{'='*60}")
    print(f"📝 Self-Analysis Report: {report.report_id}")
    print(f"{'='*60}")
    print(f"Period: {report.period_start} ~ {report.period_end}")
    print(f"\n📈 Summary:")
    print(f"  Total Actions: {report.total_actions}")
    print(f"  Success Rate: {report.success_rate:.1f}%")
    print(f"  Performance Trend: {report.performance_trend}")
    print(f"\n💡 Key Insights:")
    for insight in report.key_insights:
        print(f"  - [{insight['type']}] {insight['content']}")
    print(f"\n🎯 Recommendations:")
    for rec in report.improvement_recommendations:
        print(f"  - [{rec['priority'].upper()}] {rec['action']}")
    print(f"\n➡️  Next Actions:")
    for action in report.next_actions:
        print(f"  - {action}")
    
    # 統計表示
    print(f"\n📊 Learning Stats:")
    stats = ls.get_learning_stats()
    print(f"  - Total Learning Events: {stats['total_learning_events']}")
    print(f"  - Discovered Patterns: {stats['discovered_patterns']}")
    
    print("\n✨ Demo completed!")


if __name__ == "__main__":
    asyncio.run(main())
