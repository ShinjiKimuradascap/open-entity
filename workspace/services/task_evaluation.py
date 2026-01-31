#!/usr/bin/env python3
"""
Task Evaluation System
タスク完了検証・評価システム
Protocol v0.3準拠
"""

import json
import uuid
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, List, Any, Callable
from collections import defaultdict

from task_delegation import (
    TaskDelegationMessage, TaskResponseMessage, 
    TaskStatus, TaskDeliverable, TaskTracker
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EvaluationStatus(Enum):
    """評価状態"""
    PENDING = "pending"           # 評価待ち
    IN_REVIEW = "in_review"       # レビュー中
    APPROVED = "approved"         # 承認済み
    REJECTED = "rejected"         # 却下
    NEEDS_REVISION = "needs_revision"  # 修正必要
    DISPUTED = "disputed"         # 異議あり
    FINALIZED = "finalized"       # 確定


class EvaluationCriteriaType(Enum):
    """評価基準タイプ"""
    COMPLETENESS = "completeness"     # 完全性（要件満たしているか）
    QUALITY = "quality"               # 品質
    TIMELINESS = "timeliness"         # 時間遵守
    DOCUMENTATION = "documentation"   # ドキュメント
    TESTING = "testing"               # テスト
    CODE_QUALITY = "code_quality"     # コード品質
    CUSTOM = "custom"                 # カスタム


@dataclass
class EvaluationCriterion:
    """評価基準
    
    Attributes:
        type: 基準タイプ
        name: 基準名
        description: 説明
        weight: 重み（0-1）
        passing_score: 合格点（0-100）
        auto_check: 自動チェック可能か
        check_script: 自動チェックスクリプト（任意）
    """
    type: str
    name: str
    description: str = ""
    weight: float = 1.0
    passing_score: int = 70
    auto_check: bool = False
    check_script: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluationCriterion":
        return cls(**data)


@dataclass
class CriterionScore:
    """基準ごとのスコア
    
    Attributes:
        criterion: 評価基準
        score: スコア（0-100）
        notes: 評価メモ
        checked_at: 評価日時
        checked_by: 評価者ID
    """
    criterion: EvaluationCriterion
    score: int
    notes: str = ""
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    checked_by: str = ""
    
    @property
    def weighted_score(self) -> float:
        """重み付きスコア"""
        return self.score * self.criterion.weight
    
    @property
    def is_passing(self) -> bool:
        """合格かどうか"""
        return self.score >= self.criterion.passing_score


@dataclass
class TaskEvaluation:
    """タスク評価結果
    
    Attributes:
        evaluation_id: 評価ID
        task_id: 対象タスクID
        evaluator_id: 評価者エンティティID
        status: 評価状態
        criterion_scores: 基準ごとのスコアリスト
        overall_score: 総合スコア（0-100）
        verdict: 判定（pass/fail/partial）
        feedback: フィードバック
        revision_required: 修正が必要か
        revision_notes: 修正指示
        reward_recommendation: 推奨報酬額
        penalty_recommendation: 推奨ペナルティ額
        created_at: 作成日時
        finalized_at: 確定日時
    """
    
    task_id: str
    evaluation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    evaluator_id: str = ""
    status: str = EvaluationStatus.PENDING.value
    criterion_scores: List[Dict[str, Any]] = field(default_factory=list)
    overall_score: float = 0.0
    verdict: str = "pending"  # pass, fail, partial
    feedback: str = ""
    revision_required: bool = False
    revision_notes: str = ""
    reward_recommendation: float = 0.0
    penalty_recommendation: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finalized_at: Optional[str] = None
    
    def calculate_overall_score(self) -> float:
        """総合スコアを計算"""
        if not self.criterion_scores:
            return 0.0
        
        total_weight = sum(cs["criterion"]["weight"] for cs in self.criterion_scores)
        if total_weight == 0:
            return 0.0
        
        weighted_sum = sum(
            cs["score"] * cs["criterion"]["weight"] 
            for cs in self.criterion_scores
        )
        
        self.overall_score = weighted_sum / total_weight
        return self.overall_score
    
    def determine_verdict(self, passing_threshold: float = 70.0) -> str:
        """判定を決定"""
        self.calculate_overall_score()
        
        if self.overall_score >= 90:
            self.verdict = "pass"
        elif self.overall_score >= passing_threshold:
            self.verdict = "partial"
        else:
            self.verdict = "fail"
        
        return self.verdict
    
    def add_criterion_score(self, criterion: EvaluationCriterion, score: int, notes: str = "", checked_by: str = "") -> None:
        """基準スコアを追加"""
        self.criterion_scores.append({
            "criterion": criterion.to_dict(),
            "score": score,
            "notes": notes,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "checked_by": checked_by
        })
        self.calculate_overall_score()
    
    def finalize(self) -> None:
        """評価を確定"""
        self.determine_verdict()
        self.status = EvaluationStatus.FINALIZED.value
        self.finalized_at = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskEvaluation":
        valid_fields = {f.name for f in field(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)


class DeliverableVerifier:
    """成果物検証クラス
    
    タスクの成果物が要件を満たしているか検証する
    """
    
    def __init__(self):
        self._verifiers: Dict[str, Callable[[Dict[str, Any]], tuple[bool, str]]] = {}
        self._register_default_verifiers()
    
    def _register_default_verifiers(self) -> None:
        """デフォルトの検証関数を登録"""
        
        def verify_file(deliverable: Dict[str, Any]) -> tuple[bool, str]:
            """ファイル存在検証"""
            path = deliverable.get("path", "")
            # 実際のファイルシステムチェックはここに実装
            # 現在はシミュレーション
            return True, f"File {path} verified"
        
        def verify_test_result(deliverable: Dict[str, Any]) -> tuple[bool, str]:
            """テスト結果検証"""
            results = deliverable.get("test_results", {})
            passed = results.get("passed", 0)
            failed = results.get("failed", 0)
            
            if failed > 0:
                return False, f"Tests failed: {failed}/{passed + failed}"
            return True, f"All tests passed: {passed}"
        
        def verify_report(deliverable: Dict[str, Any]) -> tuple[bool, str]:
            """レポート検証"""
            content = deliverable.get("content", "")
            min_length = deliverable.get("min_length", 100)
            
            if len(content) < min_length:
                return False, f"Report too short: {len(content)} < {min_length}"
            return True, f"Report length: {len(content)} chars"
        
        self._verifiers["file"] = verify_file
        self._verifiers["test_result"] = verify_test_result
        self._verifiers["report"] = verify_report
    
    def register_verifier(
        self, 
        deliverable_type: str, 
        verifier: Callable[[Dict[str, Any]], tuple[bool, str]]
    ) -> None:
        """検証関数を登録"""
        self._verifiers[deliverable_type] = verifier
    
    def verify(self, deliverable: Dict[str, Any]) -> tuple[bool, str]:
        """成果物を検証"""
        deliverable_type = deliverable.get("type", "unknown")
        
        verifier = self._verifiers.get(deliverable_type)
        if verifier:
            return verifier(deliverable)
        
        return True, f"No verifier for type: {deliverable_type}"
    
    def verify_all(self, deliverables: List[Dict[str, Any]]) -> Dict[str, Any]:
        """すべての成果物を検証"""
        results = {
            "verified_count": 0,
            "failed_count": 0,
            "total_count": len(deliverables),
            "details": []
        }
        
        for deliverable in deliverables:
            success, message = self.verify(deliverable)
            results["details"].append({
                "type": deliverable.get("type"),
                "success": success,
                "message": message
            })
            
            if success:
                results["verified_count"] += 1
            else:
                results["failed_count"] += 1
        
        results["all_passed"] = results["failed_count"] == 0
        return results


class TaskEvaluator:
    """タスク評価マネージャー
    
    タスクの完了を評価し、報酬を決定する
    """
    
    # デフォルト評価基準
    DEFAULT_CRITERIA = [
        EvaluationCriterion(
            type=EvaluationCriteriaType.COMPLETENESS.value,
            name="要件充足度",
            description="すべての要件が満たされているか",
            weight=0.3,
            passing_score=80
        ),
        EvaluationCriterion(
            type=EvaluationCriteriaType.QUALITY.value,
            name="品質",
            description="成果物の品質は適切か",
            weight=0.25,
            passing_score=70
        ),
        EvaluationCriterion(
            type=EvaluationCriteriaType.TIMELINESS.value,
            name="時間遵守",
            description="期限内に完了したか",
            weight=0.2,
            passing_score=100  # 期限は厳守
        ),
        EvaluationCriterion(
            type=EvaluationCriteriaType.DOCUMENTATION.value,
            name="ドキュメント",
            description="適切に文書化されているか",
            weight=0.15,
            passing_score=60
        ),
        EvaluationCriterion(
            type=EvaluationCriteriaType.TESTING.value,
            name="テスト",
            description="十分にテストされているか",
            weight=0.1,
            passing_score=70
        )
    ]
    
    def __init__(self):
        self._evaluations: Dict[str, TaskEvaluation] = {}
        self._verifier = DeliverableVerifier()
        self._criteria: Dict[str, List[EvaluationCriterion]] = defaultdict(list)
        self._setup_default_criteria()
    
    def _setup_default_criteria(self) -> None:
        """デフォルト評価基準を設定"""
        self._criteria["default"] = self.DEFAULT_CRITERIA.copy()
    
    def set_criteria(self, task_type: str, criteria: List[EvaluationCriterion]) -> None:
        """タスクタイプごとの評価基準を設定"""
        self._criteria[task_type] = criteria
    
    def get_criteria(self, task_type: str = "default") -> List[EvaluationCriterion]:
        """評価基準を取得"""
        return self._criteria.get(task_type, self._criteria["default"])
    
    def create_evaluation(
        self,
        task_id: str,
        evaluator_id: str,
        task_type: str = "default"
    ) -> TaskEvaluation:
        """新規評価を作成"""
        evaluation = TaskEvaluation(
            task_id=task_id,
            evaluator_id=evaluator_id,
            status=EvaluationStatus.IN_REVIEW.value
        )
        
        self._evaluations[evaluation.evaluation_id] = evaluation
        logger.info(f"Created evaluation {evaluation.evaluation_id} for task {task_id}")
        
        return evaluation
    
    def get_evaluation(self, evaluation_id: str) -> Optional[TaskEvaluation]:
        """評価を取得"""
        return self._evaluations.get(evaluation_id)
    
    def get_evaluation_by_task(self, task_id: str) -> Optional[TaskEvaluation]:
        """タスクIDで評価を検索"""
        for evaluation in self._evaluations.values():
            if evaluation.task_id == task_id:
                return evaluation
        return None
    
    def evaluate_deliverables(
        self,
        evaluation_id: str,
        deliverables: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """成果物を評価"""
        evaluation = self._evaluations.get(evaluation_id)
        if not evaluation:
            return {"error": "Evaluation not found"}
        
        # 成果物を検証
        verification_results = self._verifier.verify_all(deliverables)
        
        # 完全性スコアを計算
        completeness_score = 100 if verification_results["all_passed"] else (
            verification_results["verified_count"] / max(verification_results["total_count"], 1) * 100
        )
        
        # 完全性基準を追加
        completeness_criterion = next(
            (c for c in self.DEFAULT_CRITERIA if c.type == EvaluationCriteriaType.COMPLETENESS.value),
            None
        )
        if completeness_criterion:
            evaluation.add_criterion_score(
                completeness_criterion,
                int(completeness_score),
                f"Deliverables: {verification_results['verified_count']}/{verification_results['total_count']} verified",
                evaluator_id=evaluation.evaluator_id
            )
        
        return {
            "evaluation_id": evaluation_id,
            "verification": verification_results,
            "current_score": evaluation.overall_score
        }
    
    def score_criterion(
        self,
        evaluation_id: str,
        criterion_type: str,
        score: int,
        notes: str = ""
    ) -> bool:
        """特定の基準を採点"""
        evaluation = self._evaluations.get(evaluation_id)
        if not evaluation:
            return False
        
        # 基準を検索
        criteria = self.get_criteria()
        criterion = next((c for c in criteria if c.type == criterion_type), None)
        
        if not criterion:
            return False
        
        evaluation.add_criterion_score(
            criterion,
            score,
            notes,
            evaluator_id=evaluation.evaluator_id
        )
        
        return True
    
    def auto_evaluate(
        self,
        evaluation_id: str,
        task: TaskDelegationMessage,
        response: TaskResponseMessage
    ) -> TaskEvaluation:
        """自動評価を実行"""
        evaluation = self._evaluations.get(evaluation_id)
        if not evaluation:
            raise ValueError("Evaluation not found")
        
        criteria = self.get_criteria(task.task_type)
        
        # 成果物評価
        if response.deliverables:
            self.evaluate_deliverables(evaluation_id, response.deliverables)
        
        # 時間遵守評価
        timeliness_criterion = next(
            (c for c in criteria if c.type == EvaluationCriteriaType.TIMELINESS.value),
            None
        )
        if timeliness_criterion and task.deadline:
            # 期限チェック
            deadline = datetime.fromisoformat(task.deadline.replace('Z', '+00:00'))
            completed_at = datetime.fromisoformat(response.timestamp.replace('Z', '+00:00'))
            
            if completed_at <= deadline:
                timeliness_score = 100
            else:
                # 遅延に応じて減点
                delay_hours = (completed_at - deadline).total_seconds() / 3600
                timeliness_score = max(0, 100 - int(delay_hours * 5))  # 1時間遅延で5点減点
            
            evaluation.add_criterion_score(
                timeliness_criterion,
                timeliness_score,
                f"Completed at {response.timestamp}, deadline was {task.deadline}",
                evaluator_id="auto"
            )
        
        # その他の基準はデフォルトスコアで仮埋め
        for criterion in criteria:
            existing = next(
                (cs for cs in evaluation.criterion_scores 
                 if cs["criterion"]["type"] == criterion.type),
                None
            )
            if not existing:
                evaluation.add_criterion_score(
                    criterion,
                    70,  # デフォルトスコア
                    "Auto-filled default score",
                    evaluator_id="auto"
                )
        
        evaluation.determine_verdict()
        return evaluation
    
    def finalize_evaluation(
        self,
        evaluation_id: str,
        feedback: str = "",
        reward_adjustment: float = 0.0
    ) -> Optional[TaskEvaluation]:
        """評価を確定"""
        evaluation = self._evaluations.get(evaluation_id)
        if not evaluation:
            return None
        
        evaluation.feedback = feedback
        evaluation.finalize()
        
        # 報酬計算
        base_reward = 100  # デフォルト報酬
        if evaluation.verdict == "pass":
            evaluation.reward_recommendation = base_reward * (evaluation.overall_score / 100)
        elif evaluation.verdict == "partial":
            evaluation.reward_recommendation = base_reward * (evaluation.overall_score / 100) * 0.7
        else:
            evaluation.reward_recommendation = 0
            evaluation.penalty_recommendation = base_reward * 0.1  # 失敗ペナルティ
        
        # 調整適用
        evaluation.reward_recommendation += reward_adjustment
        
        logger.info(f"Finalized evaluation {evaluation_id}: {evaluation.verdict} (score: {evaluation.overall_score:.1f})")
        
        return evaluation
    
    def request_revision(
        self,
        evaluation_id: str,
        revision_notes: str
    ) -> Optional[TaskEvaluation]:
        """修正を要求"""
        evaluation = self._evaluations.get(evaluation_id)
        if not evaluation:
            return None
        
        evaluation.status = EvaluationStatus.NEEDS_REVISION.value
        evaluation.revision_required = True
        evaluation.revision_notes = revision_notes
        
        return evaluation
    
    def get_statistics(self) -> Dict[str, Any]:
        """統計情報を取得"""
        total = len(self._evaluations)
        by_status = defaultdict(int)
        by_verdict = defaultdict(int)
        
        for evaluation in self._evaluations.values():
            by_status[evaluation.status] += 1
            by_verdict[evaluation.verdict] += 1
        
        return {
            "total_evaluations": total,
            "by_status": dict(by_status),
            "by_verdict": dict(by_verdict),
            "average_score": sum(e.overall_score for e in self._evaluations.values()) / max(total, 1)
        }


# 便利関数
def create_standard_evaluation(
    task_id: str,
    evaluator_id: str,
    task_type: str = "default"
) -> TaskEvaluation:
    """標準的な評価を作成"""
    evaluator = TaskEvaluator()
    return evaluator.create_evaluation(task_id, evaluator_id, task_type)


def quick_evaluate(
    task: TaskDelegationMessage,
    response: TaskResponseMessage,
    evaluator_id: str = "auto"
) -> TaskEvaluation:
    """クイック評価（自動評価のみ）"""
    evaluator = TaskEvaluator()
    evaluation = evaluator.create_evaluation(task.task_id, evaluator_id, task.task_type)
    evaluator.auto_evaluate(evaluation.evaluation_id, task, response)
    return evaluation


if __name__ == "__main__":
    # テスト
    print("Testing Task Evaluation System...")
    
    from task_delegation import create_delegation_message, TaskType, TaskPriority
    
    # タスク作成
    task = create_delegation_message(
        delegator_id="entity-a",
        delegatee_id="entity-b",
        title="Implement feature",
        description="Add login system",
        task_type=TaskType.CODE.value,
        priority=TaskPriority.HIGH,
        estimated_hours=4.0
    )
    
    # 完了応答
    response = TaskResponseMessage(
        task_id=task.task_id,
        responder_id="entity-b",
        response_type="complete",
        status=TaskStatus.COMPLETED.value,
        deliverables=[
            {"type": "file", "path": "src/login.py", "description": "Login module"},
            {"type": "test_result", "test_results": {"passed": 10, "failed": 0}}
        ]
    )
    
    # 評価
    evaluator = TaskEvaluator()
    evaluation = evaluator.create_evaluation(task.task_id, "evaluator-1")
    
    # 自動評価
    evaluator.auto_evaluate(evaluation.evaluation_id, task, response)
    
    print(f"Auto-evaluation score: {evaluation.overall_score:.1f}")
    print(f"Verdict: {evaluation.verdict}")
    
    # 確定
    evaluator.finalize_evaluation(
        evaluation.evaluation_id,
        feedback="Good work! All tests passing."
    )
    
    print(f"Final reward: {evaluation.reward_recommendation:.1f} AIC")
    print(f"\nStatistics: {evaluator.get_statistics()}")
    print("\nAll tests passed!")
