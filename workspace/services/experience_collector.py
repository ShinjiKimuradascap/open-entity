"""Experience Collector Module

タスク実行結果を記録し、成功/失敗パターンの分析、学習データのエクスポート機能を提供する。
EntityMemoryのMemoryType.EXPERIENCEを使用して経験を蓄積する。
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib

from services.entity_memory import EntityMemory, MemoryType, ImportanceLevel, get_memory


class TaskResult(Enum):
    """タスク実行結果"""
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"  # 部分的成功
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class TaskExecutionRecord:
    """タスク実行記録"""
    task_id: str
    task_type: str  # タスクの種類（コード生成、調査、etc.）
    result: TaskResult
    duration_seconds: float
    resources: Dict[str, Any]  # メモリ使用量、APIコール回数等
    error_message: Optional[str] = None
    retry_count: int = 0
    context: Dict[str, Any] = None  # 追加コンテキスト
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.context is None:
            self.context = {}
    
    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "result": self.result.value,
            "duration_seconds": self.duration_seconds,
            "resources": self.resources,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "context": self.context,
            "timestamp": self.timestamp.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "TaskExecutionRecord":
        return cls(
            task_id=data["task_id"],
            task_type=data["task_type"],
            result=TaskResult(data["result"]),
            duration_seconds=data["duration_seconds"],
            resources=data["resources"],
            error_message=data.get("error_message"),
            retry_count=data.get("retry_count", 0),
            context=data.get("context", {}),
            timestamp=datetime.fromisoformat(data["timestamp"])
        )


@dataclass
class SuccessPattern:
    """成功パターン"""
    pattern_id: str
    task_type: str
    avg_duration: float
    common_resources: Dict[str, Any]
    success_count: int
    common_tags: List[str]
    last_success: datetime
    
    def to_dict(self) -> Dict:
        return {
            "pattern_id": self.pattern_id,
            "task_type": self.task_type,
            "avg_duration": self.avg_duration,
            "common_resources": self.common_resources,
            "success_count": self.success_count,
            "common_tags": self.common_tags,
            "last_success": self.last_success.isoformat()
        }


@dataclass
class FailureAnalysis:
    """失敗分析"""
    analysis_id: str
    task_type: str
    failure_count: int
    common_errors: List[Dict[str, Any]]  # エラーメッセージと回数
    avg_duration_before_failure: float
    common_resource_patterns: Dict[str, Any]
    recommended_actions: List[str]
    last_failure: datetime
    
    def to_dict(self) -> Dict:
        return {
            "analysis_id": self.analysis_id,
            "task_type": self.task_type,
            "failure_count": self.failure_count,
            "common_errors": self.common_errors,
            "avg_duration_before_failure": self.avg_duration_before_failure,
            "common_resource_patterns": self.common_resource_patterns,
            "recommended_actions": self.recommended_actions,
            "last_failure": self.last_failure.isoformat()
        }


class ExperienceCollector:
    """経験収集・分析クラス
    
    タスク実行結果を記録し、成功パターンの抽出と失敗分析を行う。
    EntityMemoryをバックエンドとして使用。
    """
    
    def __init__(self, memory: Optional[EntityMemory] = None):
        """
        Args:
            memory: EntityMemoryインスタンス（Noneの場合はグローバルインスタンス使用）
        """
        self.memory = memory or get_memory()
        self._local_cache: List[TaskExecutionRecord] = []  # 最近の記録キャッシュ
        self._max_cache_size = 1000
    
    def record_task_execution(
        self,
        task_id: str,
        result: TaskResult,
        duration: float,
        resources: Dict[str, Any],
        task_type: str = "general",
        error_message: Optional[str] = None,
        retry_count: int = 0,
        context: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        タスク実行結果を記録
        
        Args:
            task_id: タスクID
            result: 実行結果（SUCCESS/FAILURE/PARTIAL/TIMEOUT/CANCELLED）
            duration: 実行時間（秒）
            resources: 使用リソース（memory_mb, api_calls, tokens等）
            task_type: タスク種別
            error_message: エラーメッセージ（失敗時）
            retry_count: リトライ回数
            context: 追加コンテキスト
            tags: タグリスト
        
        Returns:
            記録ID
        """
        record = TaskExecutionRecord(
            task_id=task_id,
            task_type=task_type,
            result=result,
            duration_seconds=duration,
            resources=resources,
            error_message=error_message,
            retry_count=retry_count,
            context=context or {}
        )
        
        # キャッシュに追加
        self._local_cache.append(record)
        if len(self._local_cache) > self._max_cache_size:
            self._local_cache.pop(0)
        
        # 重要度を結果に応じて設定
        importance = self._determine_importance(result, retry_count)
        
        # タグ生成
        auto_tags = self._generate_tags(record)
        if tags:
            auto_tags.extend(tags)
        
        # EntityMemoryに保存
        content = self._format_record_content(record)
        memory_id = self.memory.store(
            content=content,
            memory_type=MemoryType.EXPERIENCE,
            importance=importance,
            tags=list(set(auto_tags)),  # 重複除去
            context=record.to_dict()
        )
        
        return memory_id
    
    def _determine_importance(self, result: TaskResult, retry_count: int) -> ImportanceLevel:
        """結果に基づいて重要度を決定"""
        if result == TaskResult.FAILURE:
            return ImportanceLevel.HIGH if retry_count == 0 else ImportanceLevel.CRITICAL
        elif result == TaskResult.PARTIAL:
            return ImportanceLevel.MEDIUM
        elif result == TaskResult.TIMEOUT:
            return ImportanceLevel.HIGH
        elif retry_count > 0:
            return ImportanceLevel.HIGH  # リトライが必要だった成功も重要
        else:
            return ImportanceLevel.MEDIUM
    
    def _generate_tags(self, record: TaskExecutionRecord) -> List[str]:
        """記録からタグを自動生成"""
        tags = [
            f"task_type:{record.task_type}",
            f"result:{record.result.value}",
        ]
        
        # リソース使用状況に基づくタグ
        if record.resources.get("memory_mb", 0) > 500:
            tags.append("high_memory")
        if record.resources.get("api_calls", 0) > 10:
            tags.append("high_api_usage")
        
        # 実行時間に基づくタグ
        if record.duration_seconds > 60:
            tags.append("long_running")
        elif record.duration_seconds < 1:
            tags.append("fast_execution")
        
        return tags
    
    def _format_record_content(self, record: TaskExecutionRecord) -> str:
        """記録内容をフォーマット"""
        status_emoji = {
            TaskResult.SUCCESS: "✅",
            TaskResult.FAILURE: "❌",
            TaskResult.PARTIAL: "⚠️",
            TaskResult.TIMEOUT: "⏱️",
            TaskResult.CANCELLED: "🚫"
        }
        
        content_parts = [
            f"{status_emoji.get(record.result, '❓')} Task {record.task_id} ({record.task_type})",
            f"Result: {record.result.value}",
            f"Duration: {record.duration_seconds:.2f}s",
            f"Resources: {json.dumps(record.resources, ensure_ascii=False)}"
        ]
        
        if record.error_message:
            content_parts.append(f"Error: {record.error_message[:200]}")
        
        return " | ".join(content_parts)
    
    def get_success_patterns(
        self,
        task_type: Optional[str] = None,
        min_success_count: int = 3,
        days_back: int = 30
    ) -> List[SuccessPattern]:
        """
        成功パターンを抽出
        
        Args:
            task_type: 特定のタスク種別でフィルタ（Noneの場合全種別）
            min_success_count: 最小成功回数
            days_back: 遡る日数
        
        Returns:
            成功パターンリスト
        """
        # EntityMemoryから成功記録を検索
        since = datetime.now() - timedelta(days=days_back)
        
        # キャッシュとメモリからデータ収集
        records = self._get_records_in_period(since)
        
        # 成功記録のみフィルタ
        success_records = [
            r for r in records 
            if r.result == TaskResult.SUCCESS and 
            (task_type is None or r.task_type == task_type)
        ]
        
        # タスク種別ごとに集計
        patterns_by_type: Dict[str, List[TaskExecutionRecord]] = {}
        for record in success_records:
            if record.task_type not in patterns_by_type:
                patterns_by_type[record.task_type] = []
            patterns_by_type[record.task_type].append(record)
        
        # パターン生成
        patterns = []
        for ttype, type_records in patterns_by_type.items():
            if len(type_records) >= min_success_count:
                pattern = self._analyze_success_pattern(ttype, type_records)
                patterns.append(pattern)
        
        # 成功回数でソート
        patterns.sort(key=lambda p: p.success_count, reverse=True)
        return patterns
    
    def _get_records_in_period(self, since: datetime) -> List[TaskExecutionRecord]:
        """指定期間内の記録を取得"""
        records = []
        
        # キャッシュから取得
        for record in self._local_cache:
            if record.timestamp >= since:
                records.append(record)
        
        # EntityMemoryからも検索（EXPERIENCEタイプ）
        memory_entries = self.memory.recall(
            query="Task",
            memory_type=MemoryType.EXPERIENCE,
            limit=1000,
            include_expired=False
        )
        
        for entry in memory_entries:
            if entry.created_at >= since:
                try:
                    context = entry.context
                    if context and "task_id" in context:
                        record = TaskExecutionRecord.from_dict(context)
                        # キャッシュにないものだけ追加
                        if not any(r.task_id == record.task_id for r in records):
                            records.append(record)
                except (KeyError, ValueError):
                    continue
        
        return records
    
    def _analyze_success_pattern(
        self, 
        task_type: str, 
        records: List[TaskExecutionRecord]
    ) -> SuccessPattern:
        """成功記録からパターンを分析"""
        # 平均実行時間
        avg_duration = sum(r.duration_seconds for r in records) / len(records)
        
        # 共通リソースパターン
        common_resources = self._extract_common_resources(records)
        
        # 共通タグ
        all_tags = []
        for r in records:
            all_tags.extend(self._generate_tags(r))
        tag_counts = {}
        for tag in all_tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        common_tags = [tag for tag, count in tag_counts.items() if count >= len(records) * 0.5]
        
        # 最終成功日時
        last_success = max(r.timestamp for r in records)
        
        return SuccessPattern(
            pattern_id=hashlib.md5(f"{task_type}:success".encode()).hexdigest()[:12],
            task_type=task_type,
            avg_duration=avg_duration,
            common_resources=common_resources,
            success_count=len(records),
            common_tags=common_tags,
            last_success=last_success
        )
    
    def _extract_common_resources(self, records: List[TaskExecutionRecord]) -> Dict[str, Any]:
        """共通リソースパターンを抽出"""
        if not records:
            return {}
        
        # 数値リソースの平均値を計算
        numeric_keys = ["memory_mb", "api_calls", "tokens", "cpu_percent"]
        common = {}
        
        for key in numeric_keys:
            values = [r.resources.get(key) for r in records if key in r.resources]
            if values:
                common[f"avg_{key}"] = sum(values) / len(values)
                common[f"max_{key}"] = max(values)
                common[f"min_{key}"] = min(values)
        
        return common
    
    def get_failure_analysis(
        self,
        task_type: Optional[str] = None,
        days_back: int = 30
    ) -> List[FailureAnalysis]:
        """
        失敗分析を実行
        
        Args:
            task_type: 特定のタスク種別でフィルタ（Noneの場合全種別）
            days_back: 遡る日数
        
        Returns:
            失敗分析リスト
        """
        since = datetime.now() - timedelta(days=days_back)
        records = self._get_records_in_period(since)
        
        # 失敗記録のみフィルタ
        failure_records = [
            r for r in records 
            if r.result in [TaskResult.FAILURE, TaskResult.TIMEOUT] and 
            (task_type is None or r.task_type == task_type)
        ]
        
        # タスク種別ごとに集計
        failures_by_type: Dict[str, List[TaskExecutionRecord]] = {}
        for record in failure_records:
            if record.task_type not in failures_by_type:
                failures_by_type[record.task_type] = []
            failures_by_type[record.task_type].append(record)
        
        # 分析生成
        analyses = []
        for ttype, type_records in failures_by_type.items():
            analysis = self._analyze_failures(ttype, type_records)
            analyses.append(analysis)
        
        # 失敗回数でソート
        analyses.sort(key=lambda a: a.failure_count, reverse=True)
        return analyses
    
    def _analyze_failures(
        self, 
        task_type: str, 
        records: List[TaskExecutionRecord]
    ) -> FailureAnalysis:
        """失敗記録から分析を生成"""
        # エラーメッセージの集計
        error_counts: Dict[str, int] = {}
        for r in records:
            if r.error_message:
                # エラーメッセージを簡略化（最初の50文字）
                error_key = r.error_message[:50]
                error_counts[error_key] = error_counts.get(error_key, 0) + 1
        
        common_errors = [
            {"message": msg, "count": count}
            for msg, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        ]
        
        # 失敗前の平均実行時間
        avg_duration = sum(r.duration_seconds for r in records) / len(records)
        
        # リソースパターン
        resource_patterns = self._extract_common_resources(records)
        
        # 推奨アクション生成
        recommended_actions = self._generate_recommendations(task_type, records, common_errors)
        
        # 最終失敗日時
        last_failure = max(r.timestamp for r in records)
        
        return FailureAnalysis(
            analysis_id=hashlib.md5(f"{task_type}:failure".encode()).hexdigest()[:12],
            task_type=task_type,
            failure_count=len(records),
            common_errors=common_errors,
            avg_duration_before_failure=avg_duration,
            common_resource_patterns=resource_patterns,
            recommended_actions=recommended_actions,
            last_failure=last_failure
        )
    
    def _generate_recommendations(
        self, 
        task_type: str, 
        records: List[TaskExecutionRecord],
        common_errors: List[Dict[str, Any]]
    ) -> List[str]:
        """推奨アクションを生成"""
        recommendations = []
        
        # タイムアウトが多い場合
        timeout_count = sum(1 for r in records if r.result == TaskResult.TIMEOUT)
        if timeout_count > len(records) * 0.3:
            recommendations.append(f"Increase timeout threshold for {task_type} tasks")
        
        # メモリ使用量が多い場合
        high_memory = sum(1 for r in records if r.resources.get("memory_mb", 0) > 1000)
        if high_memory > len(records) * 0.3:
            recommendations.append(f"Optimize memory usage for {task_type} tasks")
        
        # リトライが多い場合
        high_retry = sum(1 for r in records if r.retry_count > 2)
        if high_retry > len(records) * 0.2:
            recommendations.append(f"Add pre-validation for {task_type} tasks to reduce retries")
        
        # エラーメッセージに基づく推奨
        for error in common_errors[:3]:
            msg = error["message"].lower()
            if "timeout" in msg or "timed out" in msg:
                recommendations.append("Implement circuit breaker pattern for external API calls")
            elif "memory" in msg or "oom" in msg:
                recommendations.append("Implement chunked processing for large datasets")
            elif "permission" in msg or "unauthorized" in msg:
                recommendations.append("Review and refresh authentication credentials")
            elif "rate limit" in msg:
                recommendations.append("Implement exponential backoff for rate-limited APIs")
        
        # デフォルト推奨
        if not recommendations:
            recommendations.append(f"Review {task_type} task implementation for error handling")
        
        return list(set(recommendations))  # 重複除去
    
    def export_learning_data(
        self,
        filepath: Optional[str] = None,
        days_back: int = 90,
        include_patterns: bool = True,
        include_failures: bool = True
    ) -> str:
        """
        学習データをエクスポート
        
        Args:
            filepath: 出力ファイルパス（Noneの場合は自動生成）
            days_back: 遡る日数
            include_patterns: 成功パターンを含める
            include_failures: 失敗分析を含める
        
        Returns:
            出力ファイルパス
        """
        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"data/experience_learning_data_{timestamp}.json"
        
        # 出力ディレクトリ作成
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        
        # データ収集
        export_data = {
            "export_info": {
                "exported_at": datetime.now().isoformat(),
                "days_back": days_back,
                "total_records": len(self._local_cache)
            },
            "success_patterns": [],
            "failure_analyses": [],
            "raw_records": []
        }
        
        # 成功パターン
        if include_patterns:
            patterns = self.get_success_patterns(days_back=days_back)
            export_data["success_patterns"] = [p.to_dict() for p in patterns]
        
        # 失敗分析
        if include_failures:
            analyses = self.get_failure_analysis(days_back=days_back)
            export_data["failure_analyses"] = [a.to_dict() for a in analyses]
        
        # 生データも含める（最近のもののみ）
        since = datetime.now() - timedelta(days=days_back)
        recent_records = [r for r in self._local_cache if r.timestamp >= since]
        export_data["raw_records"] = [r.to_dict() for r in recent_records[-100:]]  # 最新100件
        
        # ファイル出力
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        return filepath
    
    def get_task_statistics(self, days_back: int = 30) -> Dict[str, Any]:
        """
        タスク実行統計を取得
        
        Args:
            days_back: 遡る日数
        
        Returns:
            統計データ
        """
        since = datetime.now() - timedelta(days=days_back)
        records = self._get_records_in_period(since)
        
        if not records:
            return {
                "period_days": days_back,
                "total_tasks": 0,
                "success_rate": 0.0,
                "avg_duration": 0.0
            }
        
        # 基本統計
        total = len(records)
        successes = sum(1 for r in records if r.result == TaskResult.SUCCESS)
        failures = sum(1 for r in records if r.result == TaskResult.FAILURE)
        timeouts = sum(1 for r in records if r.result == TaskResult.TIMEOUT)
        
        # タスク種別別
        by_type: Dict[str, Dict[str, Any]] = {}
        for r in records:
            if r.task_type not in by_type:
                by_type[r.task_type] = {"total": 0, "success": 0, "failure": 0}
            by_type[r.task_type]["total"] += 1
            if r.result == TaskResult.SUCCESS:
                by_type[r.task_type]["success"] += 1
            elif r.result == TaskResult.FAILURE:
                by_type[r.task_type]["failure"] += 1
        
        # 成功率計算
        for ttype, stats in by_type.items():
            stats["success_rate"] = stats["success"] / stats["total"] if stats["total"] > 0 else 0.0
        
        return {
            "period_days": days_back,
            "total_tasks": total,
            "success_count": successes,
            "failure_count": failures,
            "timeout_count": timeouts,
            "success_rate": successes / total if total > 0 else 0.0,
            "avg_duration": sum(r.duration_seconds for r in records) / total,
            "by_task_type": by_type,
            "total_retries": sum(r.retry_count for r in records),
            "unique_task_types": len(by_type)
        }
    
    def get_recent_experiences(
        self,
        limit: int = 10,
        result_filter: Optional[TaskResult] = None
    ) -> List[TaskExecutionRecord]:
        """
        最近の経験を取得
        
        Args:
            limit: 取得件数
            result_filter: 結果でフィルタ
        
        Returns:
            経験記録リスト
        """
        records = self._local_cache.copy()
        
        if result_filter:
            records = [r for r in records if r.result == result_filter]
        
        # 時間順でソート（新しい順）
        records.sort(key=lambda r: r.timestamp, reverse=True)
        
        return records[:limit]


# グローバルインスタンス
_experience_collector_instance: Optional[ExperienceCollector] = None


def get_experience_collector() -> ExperienceCollector:
    """グローバルExperienceCollectorインスタンスを取得"""
    global _experience_collector_instance
    if _experience_collector_instance is None:
        _experience_collector_instance = ExperienceCollector()
    return _experience_collector_instance


# 便利なショートカット関数
def record_task(
    task_id: str,
    success: bool,
    duration: float,
    resources: Dict[str, Any],
    task_type: str = "general",
    error: Optional[str] = None,
    **kwargs
) -> str:
    """
    タスク実行を記録する簡易関数
    
    Args:
        task_id: タスクID
        success: 成功したかどうか
        duration: 実行時間（秒）
        resources: 使用リソース
        task_type: タスク種別
        error: エラーメッセージ（失敗時）
        **kwargs: 追加コンテキスト
    
    Returns:
        記録ID
    """
    collector = get_experience_collector()
    result = TaskResult.SUCCESS if success else TaskResult.FAILURE
    
    return collector.record_task_execution(
        task_id=task_id,
        result=result,
        duration=duration,
        resources=resources,
        task_type=task_type,
        error_message=error,
        context=kwargs
    )


def get_learning_insights(task_type: Optional[str] = None) -> Dict[str, Any]:
    """
    学習インサイトを取得する簡易関数
    
    Returns:
        成功パターンと失敗分析の要約
    """
    collector = get_experience_collector()
    
    patterns = collector.get_success_patterns(task_type=task_type)
    analyses = collector.get_failure_analysis(task_type=task_type)
    stats = collector.get_task_statistics()
    
    return {
        "success_patterns": [
            {
                "task_type": p.task_type,
                "count": p.success_count,
                "avg_duration": p.avg_duration
            }
            for p in patterns[:5]
        ],
        "top_failure_issues": [
            {
                "task_type": a.task_type,
                "count": a.failure_count,
                "top_error": a.common_errors[0]["message"] if a.common_errors else None
            }
            for a in analyses[:3]
        ],
        "overall_stats": stats
    }


if __name__ == "__main__":
    # テスト実行
    print("🧠 Experience Collector Test")
    
    collector = get_experience_collector()
    
    # テストデータ記録
    test_tasks = [
        ("task_001", TaskResult.SUCCESS, 2.5, {"memory_mb": 100, "api_calls": 3}, "code_generation"),
        ("task_002", TaskResult.SUCCESS, 3.0, {"memory_mb": 120, "api_calls": 4}, "code_generation"),
        ("task_003", TaskResult.FAILURE, 5.0, {"memory_mb": 500, "api_calls": 10}, "code_generation", "Timeout error"),
        ("task_004", TaskResult.SUCCESS, 1.5, {"memory_mb": 80, "api_calls": 2}, "data_analysis"),
        ("task_005", TaskResult.SUCCESS, 2.0, {"memory_mb": 90, "api_calls": 2}, "data_analysis"),
    ]
    
    for task_data in test_tasks:
        task_id, result, duration, resources, task_type = task_data[:5]
        error = task_data[5] if len(task_data) > 5 else None
        
        memory_id = collector.record_task_execution(
            task_id=task_id,
            result=result,
            duration=duration,
            resources=resources,
            task_type=task_type,
            error_message=error
        )
        print(f"✅ Recorded: {task_id} -> {memory_id}")
    
    # 成功パターン取得
    print("\n📊 Success Patterns:")
    patterns = collector.get_success_patterns(min_success_count=2)
    for p in patterns:
        print(f"  - {p.task_type}: {p.success_count} successes, avg {p.avg_duration:.2f}s")
    
    # 失敗分析取得
    print("\n🔍 Failure Analysis:")
    analyses = collector.get_failure_analysis()
    for a in analyses:
        print(f"  - {a.task_type}: {a.failure_count} failures")
        print(f"    Recommended: {a.recommended_actions[0] if a.recommended_actions else 'N/A'}")
    
    # 統計取得
    print("\n📈 Statistics:")
    stats = collector.get_task_statistics()
    print(f"  Total tasks: {stats['total_tasks']}")
    print(f"  Success rate: {stats['success_rate']*100:.1f}%")
    
    # エクスポートテスト
    print("\n💾 Exporting learning data...")
    export_path = collector.export_learning_data()
    print(f"  Exported to: {export_path}")
    
    print("\n✨ Test completed!")
