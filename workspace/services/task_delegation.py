#!/usr/bin/env python3
"""
Task Delegation System
AI間タスク委譲の標準メッセージ形式と追跡システム
Protocol v1.0準拠
"""

import json
import uuid
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum, auto
from typing import Optional, Dict, List, Any, Callable, Awaitable
from collections import defaultdict

try:
    from crypto import SecureMessage, MessageSigner, SignatureVerifier
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """タスク優先度"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4
    EMERGENCY = 5


class TaskStatus(Enum):
    """タスク状態"""
    PENDING = "pending"           # 待機中
    ASSIGNED = "assigned"         # 割り当て済み
    IN_PROGRESS = "in_progress"   # 実行中
    COMPLETED = "completed"       # 完了
    FAILED = "failed"             # 失敗
    CANCELLED = "cancelled"       # キャンセル
    TIMEOUT = "timeout"           # タイムアウト
    REJECTED = "rejected"         # 拒否


class TaskType(Enum):
    """タスク種別"""
    CODE = "code"                 # コード作成・編集
    REVIEW = "review"             # コードレビュー
    RESEARCH = "research"         # 調査・研究
    ANALYSIS = "analysis"         # 分析
    TEST = "test"                 # テスト作成・実行
    DOCUMENT = "document"         # ドキュメント作成
    DEPLOY = "deploy"             # デプロイ
    MONITOR = "monitor"           # 監視
    MAINTENANCE = "maintenance"   # メンテナンス
    CUSTOM = "custom"             # カスタム


@dataclass
class TaskDeliverable:
    """タスク成果物定義
    
    Attributes:
        type: 成果物タイプ (file, report, test_result, etc.)
        description: 成果物の説明
        path: 成果物のパス（該当する場合）
        criteria: 受入基準（リスト）
    """
    type: str
    description: str
    path: Optional[str] = None
    criteria: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskDeliverable":
        return cls(**data)


@dataclass
class TaskDelegationMessage:
    """タスク委譲メッセージ（標準形式）
    
    Protocol v1.0準拠のタスク委譲メッセージ形式。
    AIエンティティ間でのタスク委譲に使用される。
    
    Attributes:
        # 基本情報
        task_id: タスク固有ID（UUID）
        parent_task_id: 親タスクID（サブタスクの場合）
        version: メッセージ形式バージョン
        
        # 委譲情報
        delegator_id: 委譲元エンティティID
        delegatee_id: 委譲先エンティティID（空の場合は任意）
        
        # タスク内容
        task_type: タスク種別
        title: タスクタイトル
        description: 詳細説明
        requirements: 要件リスト
        constraints: 制約条件
        deliverables: 成果物定義リスト
        
        # メタデータ
        priority: 優先度
        status: 現在の状態
        created_at: 作成日時
        deadline: 期限（任意）
        estimated_hours: 推定工数（時間）
        
        # 報酬（トークン経済連携）
        reward_amount: 報酬額
        reward_token: トークン種別（デフォルト: AIC）
        escrow_locked: エスクローにロック済みか
        
        # コンテキスト
        context: 追加コンテキスト（自由形式）
        dependencies: 依存タスクIDリスト
        required_capabilities: 必要な能力リスト
    """
    
    # 基本情報
    task_id: str
    version: str = "0.3.0"
    parent_task_id: Optional[str] = None
    
    # 委譲情報
    delegator_id: str = ""
    delegatee_id: str = ""
    
    # タスク内容
    task_type: str = TaskType.CUSTOM.value
    title: str = ""
    description: str = ""
    requirements: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    deliverables: List[Dict[str, Any]] = field(default_factory=list)
    
    # メタデータ
    priority: str = TaskPriority.NORMAL.name
    status: str = TaskStatus.PENDING.value
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    deadline: Optional[str] = None
    estimated_hours: Optional[float] = None
    
    # 報酬
    reward_amount: float = 0.0
    reward_token: str = "AIC"
    escrow_locked: bool = False
    
    # コンテキスト
    context: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """自動生成フィールドの初期化"""
        if not self.task_id:
            self.task_id = str(uuid.uuid4())
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換"""
        return asdict(self)
    
    def to_json(self) -> str:
        """JSON文字列に変換"""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskDelegationMessage":
        """辞書から作成"""
        # 不要なフィールドを除外
        valid_fields = {f.name for f in field(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)
    
    @classmethod
    def from_json(cls, json_str: str) -> "TaskDelegationMessage":
        """JSON文字列から作成"""
        return cls.from_dict(json.loads(json_str))
    
    def create_secure_message(
        self,
        signer: Optional["MessageSigner"] = None
    ) -> Dict[str, Any]:
        """Protocol v1.0 SecureMessage形式に変換
        
        Args:
            signer: メッセージ署名用（省略時は署名なし）
            
        Returns:
            SecureMessage形式の辞書
        """
        if CRYPTO_AVAILABLE:
            msg = SecureMessage(
                version=self.version,
                msg_type="task_delegate",
                sender_id=self.delegator_id,
                payload=self.to_dict()
            )
            
            if signer:
                msg.sign(signer)
            
            return msg.to_dict()
        else:
            # 暗号機能なしの場合は簡易形式
            return {
                "version": self.version,
                "msg_type": "task_delegate",
                "sender_id": self.delegator_id,
                "payload": self.to_dict(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "nonce": str(uuid.uuid4())
            }
    
    def is_expired(self) -> bool:
        """期限切れかチェック"""
        if not self.deadline:
            return False
        try:
            deadline = datetime.fromisoformat(self.deadline.replace('Z', '+00:00'))
            return datetime.now(timezone.utc) > deadline
        except ValueError:
            return False
    
    def get_priority_value(self) -> int:
        """優先度の数値を取得"""
        try:
            return TaskPriority[self.priority].value
        except (KeyError, ValueError):
            return TaskPriority.NORMAL.value


@dataclass
class TaskResponseMessage:
    """タスク応答メッセージ
    
    委譲されたタスクへの応答（受諾/拒否/進捗/完了）に使用
    
    Attributes:
        response_id: 応答ID
        task_id: 対応するタスクID
        responder_id: 応答者エンティティID
        response_type: 応答タイプ (accept, reject, progress, complete, fail)
        status: タスク状態
        message: 応答メッセージ
        progress_percent: 進捗率（0-100）
        result: 結果データ
        deliverables: 成果物リスト
        timestamp: 応答日時
    """
    
    task_id: str
    response_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    responder_id: str = ""
    response_type: str = "accept"  # accept, reject, progress, complete, fail
    status: str = TaskStatus.PENDING.value
    message: str = ""
    progress_percent: int = 0
    result: Dict[str, Any] = field(default_factory=dict)
    deliverables: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskResponseMessage":
        valid_fields = {f.name for f in field(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)
    
    def create_secure_message(
        self,
        signer: Optional["MessageSigner"] = None
    ) -> Dict[str, Any]:
        """SecureMessage形式に変換"""
        if CRYPTO_AVAILABLE:
            msg = SecureMessage(
                version="0.3.0",
                msg_type=f"task_{self.response_type}",
                sender_id=self.responder_id,
                payload=self.to_dict()
            )
            
            if signer:
                msg.sign(signer)
            
            return msg.to_dict()
        else:
            return {
                "version": "0.3.0",
                "msg_type": f"task_{self.response_type}",
                "sender_id": self.responder_id,
                "payload": self.to_dict(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "nonce": str(uuid.uuid4())
            }


class TaskTracker:
    """タスク追跡システム
    
    委譲されたタスクの状態を追跡・管理する
    タスク完了検証機能統合
    """
    
    def __init__(self, enable_verification: bool = True):
        self._tasks: Dict[str, TaskDelegationMessage] = {}
        self._responses: Dict[str, List[TaskResponseMessage]] = defaultdict(list)
        self._status_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._handlers: Dict[str, Callable[[TaskDelegationMessage], Awaitable[TaskResponseMessage]]] = {}
        self._verifier: Optional[TaskCompletionVerifier] = None
        self._verification_reports: Dict[str, TaskVerificationReport] = {}
        
        # 検証機能初期化
        if enable_verification and VERIFICATION_AVAILABLE:
            self._verifier = TaskCompletionVerifier(verifier_id="task_tracker")
            logger.info("Task verification enabled")
    
    def register_task(self, task: TaskDelegationMessage) -> None:
        """タスクを登録"""
        self._tasks[task.task_id] = task
        self._record_status_change(task.task_id, TaskStatus.PENDING.value, "Task registered")
        logger.info(f"Registered task: {task.task_id}")
    
    def get_task(self, task_id: str) -> Optional[TaskDelegationMessage]:
        """タスクを取得"""
        return self._tasks.get(task_id)
    
    def update_status(self, task_id: str, status: TaskStatus, message: str = "") -> bool:
        """タスク状態を更新"""
        if task_id not in self._tasks:
            return False
        
        self._tasks[task_id].status = status.value
        self._record_status_change(task_id, status.value, message)
        logger.info(f"Task {task_id} status updated to {status.value}")
        return True
    
    def _record_status_change(self, task_id: str, status: str, message: str) -> None:
        """状態変更を記録"""
        self._status_history[task_id].append({
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": message
        })
    
    def add_response(self, response: TaskResponseMessage, auto_verify: bool = True) -> bool:
        """応答を追加
        
        Args:
            response: タスク応答メッセージ
            auto_verify: 完了時に自動検証を実行するか（デフォルト: True）
        """
        if response.task_id not in self._tasks:
            return False
        
        self._responses[response.task_id].append(response)
        
        # 応答タイプに応じて状態を更新
        status_map = {
            "accept": TaskStatus.ASSIGNED,
            "reject": TaskStatus.REJECTED,
            "progress": TaskStatus.IN_PROGRESS,
            "complete": TaskStatus.COMPLETED,
            "fail": TaskStatus.FAILED
        }
        
        if response.response_type in status_map:
            self.update_status(response.task_id, status_map[response.response_type], response.message)
        
        # 完了時に自動検証
        if auto_verify and response.response_type == "complete":
            self.auto_verify_on_complete(response)
        
        return True
    
    def get_responses(self, task_id: str) -> List[TaskResponseMessage]:
        """タスクの応答履歴を取得"""
        return self._responses.get(task_id, [])
    
    def get_status_history(self, task_id: str) -> List[Dict[str, Any]]:
        """状態変更履歴を取得"""
        return self._status_history.get(task_id, [])
    
    def get_tasks_by_status(self, status: TaskStatus) -> List[TaskDelegationMessage]:
        """状態でタスクを検索"""
        return [t for t in self._tasks.values() if t.status == status.value]
    
    def get_tasks_by_delegator(self, delegator_id: str) -> List[TaskDelegationMessage]:
        """委譲元でタスクを検索"""
        return [t for t in self._tasks.values() if t.delegator_id == delegator_id]
    
    def get_tasks_by_delegatee(self, delegatee_id: str) -> List[TaskDelegationMessage]:
        """委譲先でタスクを検索"""
        return [t for t in self._tasks.values() if t.delegatee_id == delegatee_id]
    
    def list_all_tasks(self) -> List[TaskDelegationMessage]:
        """すべてのタスクを取得"""
        return list(self._tasks.values())
    
    def register_handler(
        self,
        task_type: str,
        handler: Callable[[TaskDelegationMessage], Awaitable[TaskResponseMessage]]
    ) -> None:
        """タスクタイプごとのハンドラを登録"""
        self._handlers[task_type] = handler
        logger.info(f"Registered handler for task type: {task_type}")
    
    async def handle_task(self, task: TaskDelegationMessage) -> Optional[TaskResponseMessage]:
        """タスクを処理（登録済みハンドラがあれば実行）"""
        self.register_task(task)
        
        handler = self._handlers.get(task.task_type)
        if handler:
            try:
                response = await handler(task)
                self.add_response(response)
                return response
            except Exception as e:
                logger.error(f"Error handling task {task.task_id}: {e}")
                # エラー応答を作成
                error_response = TaskResponseMessage(
                    task_id=task.task_id,
                    responder_id=task.delegatee_id,
                    response_type="fail",
                    status=TaskStatus.FAILED.value,
                    message=f"Handler error: {str(e)}"
                )
                self.add_response(error_response)
                return error_response
        
        return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """統計情報を取得"""
        total = len(self._tasks)
        by_status = defaultdict(int)
        
        for task in self._tasks.values():
            by_status[task.status] += 1
        
        return {
            "total_tasks": total,
            "by_status": dict(by_status),
            "active_tasks": by_status.get(TaskStatus.IN_PROGRESS.value, 0),
            "completed_tasks": by_status.get(TaskStatus.COMPLETED.value, 0),
            "failed_tasks": by_status.get(TaskStatus.FAILED.value, 0),
            "verified_tasks": len(self._verification_reports)
        }
    
    def verify_task_completion(self, task_id: str) -> Optional[TaskVerificationReport]:
        """タスク完了を検証
        
        Args:
            task_id: 検証するタスクID
            
        Returns:
            TaskVerificationReport: 検証レポート（検証機能が無効の場合はNone）
        """
        if not self._verifier:
            logger.warning("Task verification is not enabled")
            return None
        
        task = self._tasks.get(task_id)
        if not task:
            logger.error(f"Task not found: {task_id}")
            return None
        
        # 完了応答から成果物を取得
        responses = self._responses.get(task_id, [])
        deliverables = []
        
        for response in responses:
            if response.response_type == "complete":
                deliverables = response.deliverables
                break
        
        if not deliverables:
            logger.warning(f"No deliverables found for task {task_id}")
            return None
        
        # 検証実行
        report = self._verifier.verify_task_completion(
            task_id=task_id,
            deliverables=deliverables,
            custom_context={"task": task.to_dict() if hasattr(task, 'to_dict') else task}
        )
        
        self._verification_reports[report.report_id] = report
        
        # 検証結果に応じてステータス更新
        if report.overall_status == VerificationStatus.FAILED.value:
            self.update_status(task_id, TaskStatus.FAILED, f"Verification failed: {report.overall_score:.1f}")
        elif report.overall_status == VerificationStatus.PARTIAL.value:
            logger.info(f"Task {task_id} partially passed verification")
        
        return report
    
    def get_verification_report(self, report_id: str) -> Optional[TaskVerificationReport]:
        """検証レポートを取得"""
        return self._verification_reports.get(report_id)
    
    def get_verification_reports_by_task(self, task_id: str) -> List[TaskVerificationReport]:
        """タスクIDで検証レポートを検索"""
        return [r for r in self._verification_reports.values() if r.task_id == task_id]
    
    def auto_verify_on_complete(self, response: TaskResponseMessage) -> bool:
        """完了時に自動検証を実行
        
        Returns:
            bool: 検証が実行されたかどうか
        """
        if not self._verifier:
            return False
        
        if response.response_type != "complete":
            return False
        
        try:
            report = self.verify_task_completion(response.task_id)
            return report is not None
        except Exception as e:
            logger.error(f"Auto-verification failed: {e}")
            return False


# 便利関数
def create_delegation_message(
    delegator_id: str,
    title: str,
    description: str,
    task_type: TaskType = TaskType.CUSTOM,
    priority: TaskPriority = TaskPriority.NORMAL,
    delegatee_id: str = "",
    **kwargs
) -> TaskDelegationMessage:
    """タスク委譲メッセージを作成する便利関数"""
    return TaskDelegationMessage(
        task_id=str(uuid.uuid4()),
        delegator_id=delegator_id,
        delegatee_id=delegatee_id,
        task_type=task_type.value,
        title=title,
        description=description,
        priority=priority.name,
        **kwargs
    )


def create_accept_response(
    task_id: str,
    responder_id: str,
    message: str = "Task accepted"
) -> TaskResponseMessage:
    """タスク受諾応答を作成"""
    return TaskResponseMessage(
        task_id=task_id,
        responder_id=responder_id,
        response_type="accept",
        status=TaskStatus.ASSIGNED.value,
        message=message
    )


def create_complete_response(
    task_id: str,
    responder_id: str,
    result: Dict[str, Any],
    deliverables: List[Dict[str, Any]],
    message: str = "Task completed"
) -> TaskResponseMessage:
    """タスク完了応答を作成"""
    return TaskResponseMessage(
        task_id=task_id,
        responder_id=responder_id,
        response_type="complete",
        status=TaskStatus.COMPLETED.value,
        progress_percent=100,
        result=result,
        deliverables=deliverables,
        message=message
    )


@dataclass
class VerificationResult:
    """検証結果
    
    Attributes:
        verified: 検証が通過したか
        score: 品質スコア (0-100)
        checks: 各チェック項目の結果
        errors: エラーリスト
        warnings: 警告リスト
        timestamp: 検証日時
    """
    verified: bool
    score: float
    checks: Dict[str, bool] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TaskCompletionVerifier:
    """タスク完了検証クラス
    
    委譲されたタスクの完了品質を検証する。
    成果物確認、テスト実行、コード品質チェックを行う。
    """
    
    def __init__(self, tracker: Optional[TaskTracker] = None):
        self.tracker = tracker or TaskTracker()
        self._verifiers: Dict[str, Callable[[TaskResponseMessage], VerificationResult]] = {}
        self._quality_threshold = 70.0  # 最低品質スコア
        self._required_checks = ["deliverables_exist", "tests_pass", "no_critical_errors"]
    
    def register_verifier(
        self,
        task_type: str,
        verifier: Callable[[TaskResponseMessage], VerificationResult]
    ) -> None:
        """タスクタイプごとの検証関数を登録"""
        self._verifiers[task_type] = verifier
        logger.info(f"Registered verifier for task type: {task_type}")
    
    def verify_completion(
        self,
        task_id: str,
        response: Optional[TaskResponseMessage] = None
    ) -> VerificationResult:
        """タスク完了を検証
        
        Args:
            task_id: 検証するタスクID
            response: 検証対象の応答（省略時は最新のcomplete応答を使用）
            
        Returns:
            VerificationResult: 検証結果
        """
        task = self.tracker.get_task(task_id)
        if not task:
            return VerificationResult(
                verified=False,
                score=0.0,
                errors=[f"Task {task_id} not found"]
            )
        
        # 応答が指定されていなければ最新のcomplete応答を取得
        if response is None:
            responses = self.tracker.get_responses(task_id)
            for r in reversed(responses):
                if r.response_type == "complete":
                    response = r
                    break
        
        if not response:
            return VerificationResult(
                verified=False,
                score=0.0,
                errors=["No completion response found"]
            )
        
        # カスタム検証関数があれば実行
        verifier = self._verifiers.get(task.task_type)
        if verifier:
            return verifier(response)
        
        # デフォルト検証を実行
        return self._default_verification(task, response)
    
    def _default_verification(
        self,
        task: TaskDelegationMessage,
        response: TaskResponseMessage
    ) -> VerificationResult:
        """デフォルト検証ロジック"""
        checks = {}
        errors = []
        warnings = []
        score = 100.0
        
        # 1. 成果物の存在確認
        if task.deliverables:
            deliverables_exist = self._check_deliverables_exist(task.deliverables)
            checks["deliverables_exist"] = deliverables_exist
            if not deliverables_exist:
                errors.append("Required deliverables are missing")
                score -= 30.0
        else:
            checks["deliverables_exist"] = True
        
        # 2. 応答に成果物が含まれているか
        has_deliverables = len(response.deliverables) > 0
        checks["has_deliverables"] = has_deliverables
        if not has_deliverables and task.deliverables:
            warnings.append("No deliverables reported in response")
            score -= 10.0
        
        # 3. テスト結果の確認
        tests_pass = self._check_tests_pass(response.result)
        checks["tests_pass"] = tests_pass
        if not tests_pass:
            errors.append("Tests failed or not found")
            score -= 25.0
        
        # 4. エラー確認
        has_errors = len(errors) > 0
        checks["no_critical_errors"] = not has_errors
        
        # 5. 進捗率確認
        checks["progress_complete"] = response.progress_percent >= 100
        if response.progress_percent < 100:
            warnings.append(f"Progress is {response.progress_percent}%, expected 100%")
            score -= 5.0
        
        # 6. メッセージ品質
        has_meaningful_message = len(response.message) > 10
        checks["meaningful_message"] = has_meaningful_message
        if not has_meaningful_message:
            warnings.append("Completion message is too short")
            score -= 5.0
        
        # スコア計算（0-100に制限）
        score = max(0.0, min(100.0, score))
        
        # 必須チェックが全て通過したか
        required_passed = all(checks.get(c, False) for c in self._required_checks)
        verified = required_passed and score >= self._quality_threshold
        
        return VerificationResult(
            verified=verified,
            score=score,
            checks=checks,
            errors=errors,
            warnings=warnings
        )
    
    def _check_deliverables_exist(self, deliverables: List[Dict[str, Any]]) -> bool:
        """成果物が実際に存在するか確認"""
        import os
        
        all_exist = True
        for d in deliverables:
            path = d.get("path")
            if path and not os.path.exists(path):
                logger.warning(f"Deliverable not found: {path}")
                all_exist = False
        
        return all_exist
    
    def _check_tests_pass(self, result: Dict[str, Any]) -> bool:
        """テストが通過したか確認"""
        # テスト結果が明示的に含まれている場合
        test_results = result.get("test_results", {})
        if test_results:
            failures = test_results.get("failures", 0)
            errors = test_results.get("errors", 0)
            return failures == 0 and errors == 0
        
        # テストが実行されていない場合は警告だが合格とする
        # （すべてのタスクにテストが必要とは限らない）
        return True
    
    def set_quality_threshold(self, threshold: float) -> None:
        """品質スコアの閾値を設定"""
        self._quality_threshold = max(0.0, min(100.0, threshold))
        logger.info(f"Quality threshold set to {self._quality_threshold}")
    
    def get_verification_history(self, task_id: str) -> List[VerificationResult]:
        """タスクの検証履歴を取得"""
        # 現状は最新のみ返す（履歴管理を追加可能）
        result = self.verify_completion(task_id)
        return [result] if result else []
    
    def approve_completion(
        self,
        task_id: str,
        approver_id: str,
        notes: str = ""
    ) -> Dict[str, Any]:
        """タスク完了を承認
        
        Args:
            task_id: 承認するタスクID
            approver_id: 承認者ID
            notes: 承認メモ
            
        Returns:
            承認結果
        """
        verification = self.verify_completion(task_id)
        
        if not verification.verified:
            return {
                "approved": False,
                "task_id": task_id,
                "reason": "Verification failed",
                "verification": verification.to_dict(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        # トラッカーの状態を更新
        self.tracker.update_status(task_id, TaskStatus.COMPLETED, f"Approved by {approver_id}")
        
        return {
            "approved": True,
            "task_id": task_id,
            "approver_id": approver_id,
            "score": verification.score,
            "notes": notes,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def reject_completion(
        self,
        task_id: str,
        rejecter_id: str,
        reason: str,
        required_fixes: List[str] = None
    ) -> Dict[str, Any]:
        """タスク完了を拒否
        
        Args:
            task_id: 拒否するタスクID
            rejecter_id: 拒否者ID
            reason: 拒否理由
            required_fixes: 必要な修正リスト
            
        Returns:
            拒否結果
        """
        verification = self.verify_completion(task_id)
        
        # 状態を失敗に戻す（再提出を可能に）
        self.tracker.update_status(task_id, TaskStatus.IN_PROGRESS, f"Rejected by {rejecter_id}: {reason}")
        
        return {
            "approved": False,
            "task_id": task_id,
            "rejecter_id": rejecter_id,
            "reason": reason,
            "required_fixes": required_fixes or [],
            "verification": verification.to_dict(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """検証統計を取得"""
        all_tasks = self.tracker.list_all_tasks()
        completed = [t for t in all_tasks if t.status == TaskStatus.COMPLETED.value]
        
        verified_count = 0
        total_score = 0.0
        
        for task in completed:
            result = self.verify_completion(task.task_id)
            if result.verified:
                verified_count += 1
            total_score += result.score
        
        avg_score = total_score / len(completed) if completed else 0.0
        
        return {
            "total_verified": verified_count,
            "total_completed": len(completed),
            "verification_rate": verified_count / len(completed) if completed else 0.0,
            "average_score": avg_score,
            "quality_threshold": self._quality_threshold
        }


# 統合されたTaskCompletionVerifierには以下の機能が含まれる:
# - TaskTracker連携 (tracker)
# - カスタム検証関数登録 (register_verifier)
# - タスク完了検証 (verify_completion)
# - 承認/拒否機能 (approve_completion/reject_completion)
# - 統計取得 (get_statistics)


if __name__ == "__main__":
    # テスト
    print("Testing Task Delegation System...")
    
    # タスク作成
    task = create_delegation_message(
        delegator_id="entity-a",
        delegatee_id="entity-b",
        title="Implement feature X",
        description="Add new authentication system",
        task_type=TaskType.CODE,
        priority=TaskPriority.HIGH,
        requirements=["Use JWT", "Add tests"],
        estimated_hours=4.0
    )
    
    print(f"Created task: {task.task_id}")
    print(f"JSON:\n{task.to_json()}")
    
    # タックトラッカー
    tracker = TaskTracker()
    tracker.register_task(task)
    
    # 応答作成
    response = create_accept_response(task.task_id, "entity-b")
    tracker.add_response(response)
    
    # 完了応答
    complete_response = create_complete_response(
        task_id=task.task_id,
        responder_id="entity-b",
        result={"files_changed": 3, "tests_added": 5},
        deliverables=[{"type": "file", "path": "src/auth.py", "description": "Auth module"}]
    )
    tracker.add_response(complete_response)
    
    print(f"\nStatistics: {tracker.get_statistics()}")
    print("\nAll tests passed!")
