"""Pattern Analyzer Module

経験データからパターンを分析・識別するエンジン。
ExperienceCollectorと連携し、学習データを入力としてパターンを抽出する。

主要機能:
1. 成功パターン識別（頻出する成功要因）
2. 失敗パターン分類（エラータイプ別集計）
3. 相関分析（実行時間と成功率の関係等）
4. トレンド検出（時系列での変化）
"""

import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, asdict
from collections import defaultdict
from enum import Enum
import math
from statistics import mean, median, stdev

from services.experience_collector import ExperienceCollector, TaskExecutionRecord, TaskResult
from services.entity_memory import EntityMemory, MemoryType, ImportanceLevel, get_memory


class PatternType(Enum):
    """パターンタイプ"""
    SUCCESS = "success"
    FAILURE = "failure"
    PERFORMANCE = "performance"
    RESOURCE = "resource"
    TEMPORAL = "temporal"


class ErrorCategory(Enum):
    """エラーカテゴリ"""
    NETWORK = "network"
    TIMEOUT = "timeout"
    AUTHENTICATION = "authentication"
    VALIDATION = "validation"
    RESOURCE = "resource"
    LOGIC = "logic"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


@dataclass
class CorrelationResult:
    """相関分析結果"""
    variable1: str
    variable2: str
    correlation_coefficient: float  # -1.0 to 1.0
    sample_size: int
    significance: float  # p-value
    interpretation: str
    
    def to_dict(self) -> Dict:
        return {
            "variable1": self.variable1,
            "variable2": self.variable2,
            "correlation_coefficient": self.correlation_coefficient,
            "sample_size": self.sample_size,
            "significance": self.significance,
            "interpretation": self.interpretation
        }


@dataclass
class TrendAnalysis:
    """トレンド分析結果"""
    metric_name: str
    trend_direction: str  # "increasing", "decreasing", "stable"
    slope: float
    change_percentage: float
    time_period_days: int
    data_points: int
    prediction: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "metric_name": self.metric_name,
            "trend_direction": self.trend_direction,
            "slope": self.slope,
            "change_percentage": self.change_percentage,
            "time_period_days": self.time_period_days,
            "data_points": self.data_points,
            "prediction": self.prediction
        }


@dataclass
class IdentifiedPattern:
    """識別されたパターン"""
    pattern_id: str
    pattern_type: PatternType
    name: str
    description: str
    confidence: float  # 0.0 to 1.0
    occurrence_count: int
    supporting_data: List[Dict]
    metadata: Dict[str, Any]
    identified_at: datetime
    
    def to_dict(self) -> Dict:
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type.value,
            "name": self.name,
            "description": self.description,
            "confidence": self.confidence,
            "occurrence_count": self.occurrence_count,
            "supporting_data": self.supporting_data,
            "metadata": self.metadata,
            "identified_at": self.identified_at.isoformat()
        }


@dataclass
class FailurePattern:
    """失敗パターン"""
    pattern_id: str
    error_category: ErrorCategory
    error_subcategory: str
    error_signature: str  # 正規化されたエラーメッセージ
    occurrence_count: int
    affected_task_types: Set[str]
    common_contexts: List[str]
    recommended_actions: List[str]
    first_seen: datetime
    last_seen: datetime
    
    def to_dict(self) -> Dict:
        return {
            "pattern_id": self.pattern_id,
            "error_category": self.error_category.value,
            "error_subcategory": self.error_subcategory,
            "error_signature": self.error_signature,
            "occurrence_count": self.occurrence_count,
            "affected_task_types": list(self.affected_task_types),
            "common_contexts": self.common_contexts,
            "recommended_actions": self.recommended_actions,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat()
        }


class PatternAnalyzer:
    """パターン分析エンジン"""
    
    def __init__(self, experience_collector: Optional[ExperienceCollector] = None):
        self.experience_collector = experience_collector or ExperienceCollector()
        self.memory = get_memory()
        self._pattern_cache: Dict[str, IdentifiedPattern] = {}
        self._correlation_cache: Dict[str, CorrelationResult] = {}
    
    # =========================================================================
    # 1. 成功パターン識別
    # =========================================================================
    
    def _get_records(self, days_back: int = 90) -> List[TaskExecutionRecord]:
        """ExperienceCollectorから記録を取得"""
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        # _local_cacheと_get_records_in_periodの両方を使用
        if hasattr(self.experience_collector, '_local_cache'):
            return [
                r for r in self.experience_collector._local_cache
                if r.timestamp >= cutoff_date
            ]
        elif hasattr(self.experience_collector, 'records'):
            return [
                r for r in self.experience_collector.records
                if r.timestamp >= cutoff_date
            ]
        else:
            # _get_records_in_periodメソッドを使用
            return self.experience_collector._get_records_in_period(cutoff_date)
    
    def identify_success_patterns(
        self,
        min_occurrences: int = 3,
        min_confidence: float = 0.7,
        days_back: int = 90
    ) -> List[IdentifiedPattern]:
        """
        成功パターンを識別する
        
        Args:
            min_occurrences: 最小発生回数
            min_confidence: 最小信頼度
            days_back: 分析対象期間（日）
            
        Returns:
            識別された成功パターンのリスト
        """
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        # 全記録を取得
        all_records = self._get_records(days_back)
        
        # 成功した記録を取得
        success_records = [
            r for r in all_records
            if r.result == TaskResult.SUCCESS and r.timestamp >= cutoff_date
        ]
        
        patterns = []
        
        # タスクタイプ別の成功パターン分析
        by_type: Dict[str, List[TaskExecutionRecord]] = defaultdict(list)
        for record in success_records:
            by_type[record.task_type].append(record)
        
        for task_type, type_records in by_type.items():
            if len(type_records) < min_occurrences:
                continue
            
            # 平均実行時間を計算
            durations = [r.duration_seconds for r in type_records]
            avg_duration = mean(durations)
            
            # 共通のタグを抽出
            all_tags = []
            for r in type_records:
                all_tags.extend(r.context.get("tags", []))
            tag_counts = defaultdict(int)
            for tag in all_tags:
                tag_counts[tag] += 1
            common_tags = [
                tag for tag, count in tag_counts.items()
                if count >= len(type_records) * 0.5  # 50%以上に含まれるタグ
            ]
            
            # 共通のリソースパターン
            resource_patterns = self._extract_common_resources(type_records)
            
            # 全記録から成功率を計算
            all_type_records = [r for r in all_records if r.task_type == task_type]
            success_rate = len(type_records) / len(all_type_records) if all_type_records else 0
            
            pattern = IdentifiedPattern(
                pattern_id=f"success_{task_type}_{hash(task_type) % 10000}",
                pattern_type=PatternType.SUCCESS,
                name=f"{task_type}成功パターン",
                description=f"{task_type}タスクの成功パターン（平均{avg_duration:.2f}秒）",
                confidence=min(1.0, len(type_records) / 10),
                occurrence_count=len(type_records),
                supporting_data=[r.to_dict() for r in type_records[:5]],
                metadata={
                    "avg_duration": avg_duration,
                    "common_tags": common_tags,
                    "common_resources": resource_patterns,
                    "success_rate": success_rate
                },
                identified_at=datetime.now()
            )
            patterns.append(pattern)
        
        # 信頼度でフィルタリング
        patterns = [p for p in patterns if p.confidence >= min_confidence]
        
        # キャッシュに保存
        for pattern in patterns:
            self._pattern_cache[pattern.pattern_id] = pattern
        
        return patterns
    
    def _analyze_task_type_success_patterns(
        self,
        records: List[TaskExecutionRecord],
        min_occurrences: int
    ) -> List[IdentifiedPattern]:
        """タスクタイプ別の成功パターンを分析"""
        patterns = []
        
        # タスクタイプ別にグループ化
        by_type: Dict[str, List[TaskExecutionRecord]] = defaultdict(list)
        for record in records:
            by_type[record.task_type].append(record)
        
        for task_type, type_records in by_type.items():
            if len(type_records) < min_occurrences:
                continue
            
            # 平均実行時間を計算
            durations = [r.duration_seconds for r in type_records]
            avg_duration = mean(durations)
            
            # 共通のタグを抽出
            all_tags = []
            for r in type_records:
                all_tags.extend(r.context.get("tags", []))
            tag_counts = defaultdict(int)
            for tag in all_tags:
                tag_counts[tag] += 1
            common_tags = [
                tag for tag, count in tag_counts.items()
                if count >= len(type_records) * 0.5  # 50%以上に含まれるタグ
            ]
            
            # 共通のリソースパターン
            resource_patterns = self._extract_common_resources(type_records)
            
            # 成功率を計算（渡された記録から）
            all_type_records = [r for r in records if r.task_type == task_type]
            success_rate = len(type_records) / len(all_type_records) if all_type_records else 0
            
            pattern = IdentifiedPattern(
                pattern_id=f"success_{task_type}_{hash(task_type) % 10000}",
                pattern_type=PatternType.SUCCESS,
                name=f"{task_type}成功パターン",
                description=f"{task_type}タスクの成功パターン（平均{avg_duration:.2f}秒）",
                confidence=min(1.0, len(type_records) / 10),
                occurrence_count=len(type_records),
                supporting_data=[r.to_dict() for r in type_records[:5]],
                metadata={
                    "avg_duration": avg_duration,
                    "common_tags": common_tags,
                    "common_resources": resource_patterns,
                    "success_rate": success_rate
                },
                identified_at=datetime.now()
            )
            patterns.append(pattern)
        
        return patterns
    
    def _analyze_resource_success_patterns(
        self,
        records: List[TaskExecutionRecord],
        min_occurrences: int
    ) -> List[IdentifiedPattern]:
        """リソース使用の成功パターンを分析"""
        patterns = []
        
        # メモリ使用パターン
        memory_ranges = self._categorize_memory_usage(records)
        for range_name, range_records in memory_ranges.items():
            if len(range_records) >= min_occurrences:
                pattern = IdentifiedPattern(
                    pattern_id=f"success_memory_{range_name}",
                    pattern_type=PatternType.RESOURCE,
                    name=f"メモリ使用パターン: {range_name}",
                    description=f"メモリ使用量{range_name}での高成功率パターン",
                    confidence=min(1.0, len(range_records) / 10),
                    occurrence_count=len(range_records),
                    supporting_data=[r.to_dict() for r in range_records[:5]],
                    metadata={
                        "memory_range": range_name,
                        "avg_duration": mean([r.duration_seconds for r in range_records]),
                        "task_types": list(set(r.task_type for r in range_records))
                    },
                    identified_at=datetime.now()
                )
                patterns.append(pattern)
        
        return patterns
    
    def _analyze_temporal_success_patterns(
        self,
        records: List[TaskExecutionRecord],
        min_occurrences: int
    ) -> List[IdentifiedPattern]:
        """時間帯別の成功パターンを分析"""
        patterns = []
        
        # 時間帯別にグループ化
        by_hour: Dict[int, List[TaskExecutionRecord]] = defaultdict(list)
        for record in records:
            hour = record.timestamp.hour
            by_hour[hour].append(record)
        
        # 成功率が高い時間帯を特定
        for hour, hour_records in by_hour.items():
            if len(hour_records) >= min_occurrences:
                pattern = IdentifiedPattern(
                    pattern_id=f"success_temporal_hour_{hour}",
                    pattern_type=PatternType.TEMPORAL,
                    name=f"時間帯成功パターン: {hour}:00-{hour+1}:00",
                    description=f"{hour}:00-{hour+1}:00の時間帯での成功パターン",
                    confidence=min(1.0, len(hour_records) / 10),
                    occurrence_count=len(hour_records),
                    supporting_data=[r.to_dict() for r in hour_records[:5]],
                    metadata={
                        "hour": hour,
                        "task_types": list(set(r.task_type for r in hour_records)),
                        "avg_duration": mean([r.duration_seconds for r in hour_records])
                    },
                    identified_at=datetime.now()
                )
                patterns.append(pattern)
        
        return patterns
    
    # =========================================================================
    # 2. 失敗パターン分類
    # =========================================================================
    
    def classify_failure_patterns(
        self,
        days_back: int = 90,
        min_occurrences: int = 2
    ) -> List[FailurePattern]:
        """
        失敗パターンを分類する
        
        Args:
            days_back: 分析対象期間（日）
            min_occurrences: 最小発生回数
            
        Returns:
            分類された失敗パターンのリスト
        """
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        # 全記録を取得
        all_records = self._get_records(days_back)
        
        # 失敗した記録を取得
        failure_records = [
            r for r in all_records
            if r.result == TaskResult.FAILURE and r.timestamp >= cutoff_date
        ]
        
        # エラーメッセージでグループ化
        error_groups: Dict[str, List[TaskExecutionRecord]] = defaultdict(list)
        for record in failure_records:
            error_signature = self._normalize_error_message(record.error_message)
            error_groups[error_signature].append(record)
        
        patterns = []
        for error_signature, records in error_groups.items():
            if len(records) < min_occurrences:
                continue
            
            # エラーカテゴリを特定
            category = self._categorize_error(error_signature)
            subcategory = self._extract_error_subcategory(error_signature)
            
            # 推奨アクションを生成
            recommended_actions = self._generate_recommended_actions(
                category, subcategory, records
            )
            
            pattern = FailurePattern(
                pattern_id=f"failure_{hash(error_signature) % 100000}",
                error_category=category,
                error_subcategory=subcategory,
                error_signature=error_signature[:200],  # 長さ制限
                occurrence_count=len(records),
                affected_task_types=set(r.task_type for r in records),
                common_contexts=self._extract_common_contexts(records),
                recommended_actions=recommended_actions,
                first_seen=min(r.timestamp for r in records),
                last_seen=max(r.timestamp for r in records)
            )
            patterns.append(pattern)
        
        # 発生回数でソート
        patterns.sort(key=lambda p: p.occurrence_count, reverse=True)
        
        return patterns
    
    def _normalize_error_message(self, error_message: Optional[str]) -> str:
        """エラーメッセージを正規化"""
        if not error_message:
            return "unknown_error"
        
        # 動的な部分（ID、タイムスタンプ等）を除去
        normalized = error_message.lower()
        normalized = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '<UUID>', normalized)
        normalized = re.sub(r'0x[0-9a-f]+', '<HEX>', normalized)
        normalized = re.sub(r'\d+', '<NUM>', normalized)
        normalized = re.sub(r"['\"].*?['\"]", '<STR>', normalized)
        
        return normalized[:500]
    
    def _categorize_error(self, error_signature: str) -> ErrorCategory:
        """エラーをカテゴリ分類"""
        error_lower = error_signature.lower()
        
        if any(kw in error_lower for kw in ['timeout', 'timed out', 'deadline']):
            return ErrorCategory.TIMEOUT
        elif any(kw in error_lower for kw in ['network', 'connection', 'socket', 'dns', 'unreachable']):
            return ErrorCategory.NETWORK
        elif any(kw in error_lower for kw in ['auth', 'unauthorized', 'forbidden', 'permission', 'credential']):
            return ErrorCategory.AUTHENTICATION
        elif any(kw in error_lower for kw in ['invalid', 'validation', 'format', 'schema', 'required']):
            return ErrorCategory.VALIDATION
        elif any(kw in error_lower for kw in ['memory', 'resource', 'quota', 'limit', 'exceeded']):
            return ErrorCategory.RESOURCE
        elif any(kw in error_lower for kw in ['api', 'external', 'service', 'third']):
            return ErrorCategory.EXTERNAL
        elif any(kw in error_lower for kw in ['division', 'zero', 'index', 'range', 'keyerror', 'typeerror', 'attribute']):
            return ErrorCategory.LOGIC
        elif any(kw in error_lower for kw in ['error', 'exception', 'failed']):
            return ErrorCategory.LOGIC
        else:
            return ErrorCategory.UNKNOWN
    
    def _extract_error_subcategory(self, error_signature: str) -> str:
        """エラーのサブカテゴリを抽出"""
        # 主要なエラーキーワードを抽出
        keywords = [
            'timeout', 'connection', 'authentication', 'validation',
            'not found', 'conflict', 'rate limit', 'quota', 'parse'
        ]
        
        error_lower = error_signature.lower()
        for keyword in keywords:
            if keyword in error_lower:
                return keyword.replace(' ', '_')
        
        return 'general'
    
    def _generate_recommended_actions(
        self,
        category: ErrorCategory,
        subcategory: str,
        records: List[TaskExecutionRecord]
    ) -> List[str]:
        """推奨アクションを生成"""
        actions = []
        
        if category == ErrorCategory.TIMEOUT:
            actions.append("タイムアウト値を増やして再試行")
            actions.append("非同期処理に変更を検討")
        elif category == ErrorCategory.NETWORK:
            actions.append("ネットワーク接続を確認")
            actions.append("リトライロジックを実装")
            actions.append("バックオフ戦略を適用")
        elif category == ErrorCategory.AUTHENTICATION:
            actions.append("認証情報を更新")
            actions.append("トークンの有効期限を確認")
        elif category == ErrorCategory.VALIDATION:
            actions.append("入力データの検証を強化")
            actions.append("スキーマ定義を確認")
        elif category == ErrorCategory.RESOURCE:
            actions.append("リソース制限を緩和")
            actions.append("メモリ使用量を最適化")
        elif category == ErrorCategory.EXTERNAL:
            actions.append("外部サービスのステータスを確認")
            actions.append("サーキットブレーカーパターンを検討")
        else:
            actions.append("エラーログを詳細に分析")
            actions.append("再現テストを作成")
        
        return actions
    
    def get_error_statistics(self, days_back: int = 90) -> Dict[str, Any]:
        """エラー統計を取得"""
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        # 全記録を取得
        all_records = self._get_records(days_back)
        
        failure_records = [
            r for r in all_records
            if r.result == TaskResult.FAILURE and r.timestamp >= cutoff_date
        ]
        
        if not failure_records:
            return {"total_errors": 0, "categories": {}, "trend": "stable"}
        
        # カテゴリ別集計
        category_counts: Dict[str, int] = defaultdict(int)
        for record in failure_records:
            signature = self._normalize_error_message(record.error_message)
            category = self._categorize_error(signature)
            category_counts[category.value] += 1
        
        # タスクタイプ別集計
        task_type_counts: Dict[str, int] = defaultdict(int)
        for record in failure_records:
            task_type_counts[record.task_type] += 1
        
        return {
            "total_errors": len(failure_records),
            "categories": dict(category_counts),
            "by_task_type": dict(task_type_counts),
            "avg_retry_count": mean([r.retry_count for r in failure_records]),
            "most_common_error": max(category_counts.items(), key=lambda x: x[1])[0] if category_counts else None,
            "trend": self._calculate_error_trend(failure_records)
        }
    
    # =========================================================================
    # 3. 相関分析
    # =========================================================================
    
    def analyze_correlations(
        self,
        days_back: int = 90
    ) -> List[CorrelationResult]:
        """
        実行データの相関分析を行う
        
        Args:
            days_back: 分析対象期間（日）
            
        Returns:
            相関分析結果のリスト
        """
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        # 全記録を取得
        records = self._get_records(days_back)
        
        if len(records) < 5:
            return []
        
        correlations = []
        
        # 実行時間と成功率の相関
        duration_success_corr = self._calculate_duration_success_correlation(records)
        if duration_success_corr:
            correlations.append(duration_success_corr)
        
        # リソース使用量と実行時間の相関
        resource_duration_corr = self._calculate_resource_duration_correlation(records)
        if resource_duration_corr:
            correlations.append(resource_duration_corr)
        
        # リトライ回数と成功率の相関
        retry_success_corr = self._calculate_retry_success_correlation(records)
        if retry_success_corr:
            correlations.append(retry_success_corr)
        
        # キャッシュに保存
        for corr in correlations:
            key = f"{corr.variable1}_{corr.variable2}"
            self._correlation_cache[key] = corr
        
        return correlations
    
    def _calculate_duration_success_correlation(
        self,
        records: List[TaskExecutionRecord]
    ) -> Optional[CorrelationResult]:
        """実行時間と成功率の相関を計算"""
        durations = [r.duration_seconds for r in records]
        successes = [1 if r.result == TaskResult.SUCCESS else 0 for r in records]
        
        if len(durations) < 5:
            return None
        
        correlation = self._pearson_correlation(durations, successes)
        
        interpretation = "実行時間と成功率に相関あり"
        if abs(correlation) < 0.3:
            interpretation = "実行時間と成功率に弱い相関"
        elif correlation < 0:
            interpretation = "実行時間が短いほど成功率が高い傾向"
        
        return CorrelationResult(
            variable1="duration_seconds",
            variable2="success_rate",
            correlation_coefficient=correlation,
            sample_size=len(records),
            significance=0.05,  # 簡易的な実装
            interpretation=interpretation
        )
    
    def _calculate_resource_duration_correlation(
        self,
        records: List[TaskExecutionRecord]
    ) -> Optional[CorrelationResult]:
        """リソース使用量と実行時間の相関を計算"""
        memory_usage = []
        durations = []
        
        for r in records:
            mem = r.resources.get("memory_mb", 0)
            if mem > 0:
                memory_usage.append(mem)
                durations.append(r.duration_seconds)
        
        if len(memory_usage) < 5:
            return None
        
        correlation = self._pearson_correlation(memory_usage, durations)
        
        interpretation = "メモリ使用量と実行時間に相関あり"
        if abs(correlation) < 0.3:
            interpretation = "メモリ使用量と実行時間に弱い相関"
        elif correlation > 0:
            interpretation = "メモリ使用量が多いほど実行時間が長い傾向"
        
        return CorrelationResult(
            variable1="memory_usage_mb",
            variable2="duration_seconds",
            correlation_coefficient=correlation,
            sample_size=len(memory_usage),
            significance=0.05,
            interpretation=interpretation
        )
    
    def _calculate_retry_success_correlation(
        self,
        records: List[TaskExecutionRecord]
    ) -> Optional[CorrelationResult]:
        """リトライ回数と成功率の相関を計算"""
        retries = [r.retry_count for r in records]
        successes = [1 if r.result == TaskResult.SUCCESS else 0 for r in records]
        
        if len(set(retries)) < 2:  # リトライ回数のバリエーションが必要
            return None
        
        correlation = self._pearson_correlation(retries, successes)
        
        interpretation = "リトライ回数と成功率に相関あり"
        if abs(correlation) < 0.3:
            interpretation = "リトライ回数と成功率に弱い相関"
        elif correlation < 0:
            interpretation = "リトライが多いほど成功率が低い傾向（根本的な問題の可能性）"
        else:
            interpretation = "リトライが成功率向上に寄与している傾向"
        
        return CorrelationResult(
            variable1="retry_count",
            variable2="success_rate",
            correlation_coefficient=correlation,
            sample_size=len(records),
            significance=0.05,
            interpretation=interpretation
        )
    
    def _pearson_correlation(self, x: List[float], y: List[float]) -> float:
        """ピアソンの相関係数を計算"""
        n = len(x)
        if n != len(y) or n == 0:
            return 0.0
        
        mean_x = mean(x)
        mean_y = mean(y)
        
        numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        denominator = math.sqrt(
            sum((xi - mean_x) ** 2 for xi in x) *
            sum((yi - mean_y) ** 2 for yi in y)
        )
        
        if denominator == 0:
            return 0.0
        
        return numerator / denominator
    
    # =========================================================================
    # 4. トレンド検出
    # =========================================================================
    
    def detect_trends(
        self,
        metric: str = "success_rate",
        days_back: int = 90,
        interval_days: int = 7
    ) -> List[TrendAnalysis]:
        """
        時系列データのトレンドを検出
        
        Args:
            metric: 分析対象メトリクス
            days_back: 分析対象期間（日）
            interval_days: 集計間隔（日）
            
        Returns:
            トレンド分析結果のリスト
        """
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        # 全記録を取得
        records = self._get_records(days_back)
        
        if not records:
            return []
        
        trends = []
        
        # 時間枠でデータをグループ化
        time_series_data = self._aggregate_by_timeframes(
            records, interval_days, metric
        )
        
        if len(time_series_data) >= 3:
            trend = self._calculate_trend(metric, time_series_data, days_back)
            if trend:
                trends.append(trend)
        
        # タスクタイプ別のトレンド
        task_types = set(r.task_type for r in records)
        for task_type in task_types:
            type_records = [r for r in records if r.task_type == task_type]
            type_data = self._aggregate_by_timeframes(
                type_records, interval_days, metric
            )
            if len(type_data) >= 3:
                trend = self._calculate_trend(
                    f"{task_type}_{metric}", type_data, days_back
                )
                if trend:
                    trends.append(trend)
        
        return trends
    
    def _aggregate_by_timeframes(
        self,
        records: List[TaskExecutionRecord],
        interval_days: int,
        metric: str
    ) -> List[Tuple[datetime, float]]:
        """時間枠でデータを集計"""
        if not records:
            return []
        
        # 時間枠でグループ化
        intervals: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"total": 0, "success": 0})
        
        for record in records:
            interval_key = record.timestamp.strftime(f"%Y-%m-%d")
            # 間隔に丸める
            day_num = record.timestamp.timetuple().tm_yday
            interval_num = day_num // interval_days
            interval_key = f"{record.timestamp.year}-{interval_num}"
            
            intervals[interval_key]["total"] += 1
            if record.result == TaskResult.SUCCESS:
                intervals[interval_key]["success"] += 1
        
        # メトリクス計算
        results = []
        for key, data in sorted(intervals.items()):
            if metric == "success_rate":
                value = data["success"] / data["total"] if data["total"] > 0 else 0
            elif metric == "count":
                value = data["total"]
            else:
                value = data["success"] / data["total"] if data["total"] > 0 else 0
            
            # 日付の概算
            year, interval = key.split("-")
            approx_day = int(interval) * interval_days
            date = datetime(int(year), 1, 1) + timedelta(days=approx_day)
            results.append((date, value))
        
        return results
    
    def _calculate_trend(
        self,
        metric_name: str,
        time_series_data: List[Tuple[datetime, float]],
        time_period_days: int
    ) -> Optional[TrendAnalysis]:
        """トレンドを計算"""
        if len(time_series_data) < 3:
            return None
        
        # 単純な線形回帰
        n = len(time_series_data)
        x_values = list(range(n))
        y_values = [v for _, v in time_series_data]
        
        # 傾きを計算
        mean_x = mean(x_values)
        mean_y = mean(y_values)
        
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, y_values))
        denominator = sum((x - mean_x) ** 2 for x in x_values)
        
        slope = numerator / denominator if denominator != 0 else 0
        
        # 変化率を計算
        if y_values[0] != 0:
            change_pct = ((y_values[-1] - y_values[0]) / y_values[0]) * 100
        else:
            change_pct = 0
        
        # トレンド方向
        if abs(slope) < 0.01:
            direction = "stable"
        elif slope > 0:
            direction = "increasing"
        else:
            direction = "decreasing"
        
        # 予測
        prediction = None
        if direction == "increasing":
            prediction = f"今後も{metric_name}は向上傾向にある可能性"
        elif direction == "decreasing":
            prediction = f"{metric_name}の低下傾向に注意が必要"
        
        return TrendAnalysis(
            metric_name=metric_name,
            trend_direction=direction,
            slope=slope,
            change_percentage=change_pct,
            time_period_days=time_period_days,
            data_points=n,
            prediction=prediction
        )
    
    # =========================================================================
    # ユーティリティメソッド
    # =========================================================================
    
    def generate_analysis_report(self, days_back: int = 90) -> Dict[str, Any]:
        """包括的な分析レポートを生成"""
        return {
            "generated_at": datetime.now().isoformat(),
            "period_days": days_back,
            "success_patterns": [
                p.to_dict() for p in self.identify_success_patterns(days_back=days_back)
            ],
            "failure_patterns": [
                p.to_dict() for p in self.classify_failure_patterns(days_back=days_back)
            ],
            "correlations": [
                c.to_dict() for c in self.analyze_correlations(days_back=days_back)
            ],
            "trends": [
                t.to_dict() for t in self.detect_trends(days_back=days_back)
            ],
            "error_statistics": self.get_error_statistics(days_back=days_back)
        }
    
    def export_analysis(self, filepath: str, days_back: int = 90) -> bool:
        """分析結果をエクスポート"""
        try:
            report = self.generate_analysis_report(days_back)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Export error: {e}")
            return False
    
    def get_insights(self, min_confidence: float = 0.7) -> List[Dict]:
        """重要なインサイトを取得"""
        insights = []
        
        # 成功パターンからのインサイト
        success_patterns = self.identify_success_patterns(min_confidence=min_confidence)
        for pattern in success_patterns[:5]:
            insights.append({
                "type": "success_pattern",
                "title": pattern.name,
                "description": pattern.description,
                "confidence": pattern.confidence,
                "actionable": True
            })
        
        # 失敗パターンからのインサイト
        failure_patterns = self.classify_failure_patterns()
        for pattern in failure_patterns[:5]:
            insights.append({
                "type": "failure_pattern",
                "title": f"{pattern.error_category.value}: {pattern.error_subcategory}",
                "description": f"{pattern.occurrence_count}回発生",
                "recommended_actions": pattern.recommended_actions,
                "actionable": True
            })
        
        # トレンドからのインサイト
        trends = self.detect_trends()
        for trend in trends:
            if trend.trend_direction != "stable":
                insights.append({
                    "type": "trend",
                    "title": f"{trend.metric_name}のトレンド",
                    "description": f"{trend.trend_direction} ({trend.change_percentage:+.1f}%)",
                    "prediction": trend.prediction,
                    "actionable": True
                })
        
        return insights
    
    # =========================================================================
    # ヘルパーメソッド
    # =========================================================================
    
    def _extract_common_resources(
        self,
        records: List[TaskExecutionRecord]
    ) -> Dict[str, Any]:
        """共通のリソースパターンを抽出"""
        if not records:
            return {}
        
        # メモリ使用量の中央値
        memories = [r.resources.get("memory_mb", 0) for r in records if "memory_mb" in r.resources]
        
        result = {}
        if memories:
            result["median_memory_mb"] = median(memories)
        
        return result
    
    def _categorize_memory_usage(
        self,
        records: List[TaskExecutionRecord]
    ) -> Dict[str, List[TaskExecutionRecord]]:
        """メモリ使用量で分類"""
        categories = {
            "low": [],      # < 100MB
            "medium": [],   # 100-500MB
            "high": []      # > 500MB
        }
        
        for record in records:
            mem = record.resources.get("memory_mb", 0)
            if mem < 100:
                categories["low"].append(record)
            elif mem < 500:
                categories["medium"].append(record)
            else:
                categories["high"].append(record)
        
        return categories
    
    def _extract_common_contexts(
        self,
        records: List[TaskExecutionRecord]
    ) -> List[str]:
        """共通のコンテキストを抽出"""
        contexts = []
        for record in records:
            ctx = record.context.get("error_context") or record.context.get("operation")
            if ctx:
                contexts.append(str(ctx))
        
        # 頻出するコンテキストを返す
        context_counts = defaultdict(int)
        for ctx in contexts:
            context_counts[ctx] += 1
        
        sorted_contexts = sorted(context_counts.items(), key=lambda x: x[1], reverse=True)
        return [ctx for ctx, _ in sorted_contexts[:3]]
    
    def _calculate_error_trend(self, records: List[TaskExecutionRecord]) -> str:
        """エラーのトレンドを計算"""
        if len(records) < 6:
            return "insufficient_data"
        
        # 時間でソート
        sorted_records = sorted(records, key=lambda r: r.timestamp)
        mid = len(sorted_records) // 2
        
        first_half = sorted_records[:mid]
        second_half = sorted_records[mid:]
        
        first_rate = len(first_half) / max(1, len(first_half))
        second_rate = len(second_half) / max(1, len(second_half))
        
        if second_rate > first_rate * 1.2:
            return "increasing"
        elif second_rate < first_rate * 0.8:
            return "decreasing"
        else:
            return "stable"


# ============================================================================
# グローバルインスタンスと便利関数
# ============================================================================

_pattern_analyzer: Optional[PatternAnalyzer] = None


def get_pattern_analyzer() -> PatternAnalyzer:
    """グローバルPatternAnalyzerインスタンスを取得"""
    global _pattern_analyzer
    if _pattern_analyzer is None:
        _pattern_analyzer = PatternAnalyzer()
    return _pattern_analyzer


def analyze_patterns(days_back: int = 90) -> Dict[str, Any]:
    """パターン分析のショートカット関数"""
    analyzer = get_pattern_analyzer()
    return analyzer.generate_analysis_report(days_back)


def get_pattern_insights(min_confidence: float = 0.7) -> List[Dict]:
    """パターンインサイト取得のショートカット関数"""
    analyzer = get_pattern_analyzer()
    return analyzer.get_insights(min_confidence)
