#!/usr/bin/env python3
"""
Multi-Agent Coordinator
マルチエージェント協調システム

Features:
- Task delegation between agents
- Collaborative task execution
- Skill matching
- Result aggregation
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Set
from pathlib import Path

from ai_community import AICommunity, CommunityMember, get_community_registry

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """タスク状態"""
    PENDING = "pending"           # 作成直後
    ASSIGNING = "assigning"       # 担当者割当中
    ASSIGNED = "assigned"         # 担当者確定
    IN_PROGRESS = "in_progress"   # 実行中
    REVIEWING = "reviewing"       # レビュー中
    COMPLETED = "completed"       # 完了
    FAILED = "failed"             # 失敗
    CANCELLED = "cancelled"       # キャンセル


class TaskPriority(Enum):
    """タスク優先度"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class SubTask:
    """サブタスク"""
    subtask_id: str
    title: str
    description: str
    required_skills: List[str]
    estimated_effort: int  # 分単位
    assigned_to: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "subtask_id": self.subtask_id,
            "title": self.title,
            "description": self.description,
            "required_skills": self.required_skills,
            "estimated_effort": self.estimated_effort,
            "assigned_to": self.assigned_to,
            "status": self.status.value,
            "result": self.result,
            "created_at": self.created_at,
            "completed_at": self.completed_at
        }


@dataclass
class CollaborativeTask:
    """協調タスク"""
    task_id: str
    title: str
    description: str
    requester_id: str
    community_id: str
    
    # タスク設定
    priority: TaskPriority
    required_skills: List[str]
    estimated_total_effort: int
    deadline: Optional[str] = None
    
    # サブタスク
    subtasks: List[SubTask] = field(default_factory=list)
    
    # 状態管理
    status: TaskStatus = TaskStatus.PENDING
    coordinator_id: Optional[str] = None
    participants: Dict[str, str] = field(default_factory=dict)  # agent_id -> role
    
    # タイムスタンプ
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # 結果
    final_result: Optional[Dict[str, Any]] = None
    aggregated_output: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "requester_id": self.requester_id,
            "community_id": self.community_id,
            "priority": self.priority.value,
            "required_skills": self.required_skills,
            "estimated_total_effort": self.estimated_total_effort,
            "deadline": self.deadline,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "status": self.status.value,
            "coordinator_id": self.coordinator_id,
            "participants": self.participants,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "final_result": self.final_result,
            "aggregated_output": self.aggregated_output
        }


class MultiAgentCoordinator:
    """マルチエージェント協調システム
    
    複数のAIエージェントが協力してタスクを実行するための調整システム
    """
    
    def __init__(self, data_dir: str = "data/coordinator"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # タスク管理
        self.tasks: Dict[str, CollaborativeTask] = {}
        self.agent_tasks: Dict[str, List[str]] = {}  # agent_id -> [task_ids]
        self.community_tasks: Dict[str, List[str]] = {}  # community_id -> [task_ids]
        
        # スキルインデックス
        self.skill_index: Dict[str, Set[str]] = {}  # skill -> {agent_ids}
        
        # コールバック
        self.task_handlers: Dict[str, Callable] = {}
        self.result_aggregators: Dict[str, Callable] = {}
        
        # 統計
        self.total_tasks_created: int = 0
        self.total_tasks_completed: int = 0
        
        self._load()
        logger.info("MultiAgentCoordinator initialized")
    
    def register_task_handler(self, task_type: str, handler: Callable):
        """タスクタイプ別のハンドラを登録"""
        self.task_handlers[task_type] = handler
        logger.info(f"Task handler registered for {task_type}")
    
    def register_result_aggregator(self, task_type: str, aggregator: Callable):
        """結果集約ハンドラを登録"""
        self.result_aggregators[task_type] = aggregator
        logger.info(f"Result aggregator registered for {task_type}")
    
    def create_collaborative_task(self, title: str, description: str,
                                  requester_id: str, community_id: str,
                                  priority: TaskPriority = TaskPriority.MEDIUM,
                                  required_skills: List[str] = None,
                                  deadline: Optional[str] = None) -> str:
        """協調タスクを作成"""
        task_id = str(uuid.uuid4())
        
        task = CollaborativeTask(
            task_id=task_id,
            title=title,
            description=description,
            requester_id=requester_id,
            community_id=community_id,
            priority=priority,
            required_skills=required_skills or [],
            estimated_total_effort=0,
            deadline=deadline
        )
        
        self.tasks[task_id] = task
        self.total_tasks_created += 1
        
        # コミュニティのタスクリストに追加
        if community_id not in self.community_tasks:
            self.community_tasks[community_id] = []
        self.community_tasks[community_id].append(task_id)
        
        # 依頼者のタスクリストに追加
        if requester_id not in self.agent_tasks:
            self.agent_tasks[requester_id] = []
        self.agent_tasks[requester_id].append(task_id)
        
        logger.info(f"Collaborative task created: {title} ({task_id})")
        self._save()
        return task_id
    
    def add_subtask(self, task_id: str, title: str, description: str,
                    required_skills: List[str], estimated_effort: int) -> Optional[str]:
        """サブタスクを追加"""
        if task_id not in self.tasks:
            logger.warning(f"Task not found: {task_id}")
            return None
        
        task = self.tasks[task_id]
        subtask_id = str(uuid.uuid4())
        
        subtask = SubTask(
            subtask_id=subtask_id,
            title=title,
            description=description,
            required_skills=required_skills,
            estimated_effort=estimated_effort
        )
        
        task.subtasks.append(subtask)
        task.estimated_total_effort += estimated_effort
        
        logger.info(f"Subtask added to {task_id}: {title}")
        self._save()
        return subtask_id
    
    def find_best_agents(self, community_id: str, required_skills: List[str],
                        max_agents: int = 3) -> List[str]:
        """最適なエージェントを検索"""
        registry = get_community_registry()
        community = registry.get_community(community_id)
        
        if not community:
            logger.warning(f"Community not found: {community_id}")
            return []
        
        # スキルマッチングで候補を検索
        candidates = community.find_collaborators(required_skills)
        
        # 評価スコアと空き状況でソート
        # 実際の実装では現在のワークロードも考慮
        sorted_candidates = sorted(
            candidates,
            key=lambda m: (m.reputation_score, -self._get_agent_workload(m.agent_id)),
            reverse=True
        )
        
        return [m.agent_id for m in sorted_candidates[:max_agents]]
    
    def _get_agent_workload(self, agent_id: str) -> int:
        """エージェントの現在のワークロードを取得"""
        task_ids = self.agent_tasks.get(agent_id, [])
        workload = 0
        for task_id in task_ids:
            task = self.tasks.get(task_id)
            if task and task.status in [TaskStatus.IN_PROGRESS, TaskStatus.ASSIGNED]:
                workload += task.estimated_total_effort
        return workload
    
    def assign_subtask(self, task_id: str, subtask_id: str, agent_id: str) -> bool:
        """サブタスクを割り当て"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        subtask = None
        for st in task.subtasks:
            if st.subtask_id == subtask_id:
                subtask = st
                break
        
        if not subtask:
            return False
        
        subtask.assigned_to = agent_id
        subtask.status = TaskStatus.ASSIGNED
        
        # 参加者リストに追加
        task.participants[agent_id] = "contributor"
        
        # エージェントのタスクリストに追加
        if agent_id not in self.agent_tasks:
            self.agent_tasks[agent_id] = []
        if task_id not in self.agent_tasks[agent_id]:
            self.agent_tasks[agent_id].append(task_id)
        
        logger.info(f"Subtask {subtask_id} assigned to {agent_id}")
        self._save()
        return True
    
    def auto_assign_subtasks(self, task_id: str) -> Dict[str, Any]:
        """サブタスクを自動割り当て"""
        if task_id not in self.tasks:
            return {"success": False, "error": "Task not found"}
        
        task = self.tasks[task_id]
        assignments = {}
        
        for subtask in task.subtasks:
            if subtask.assigned_to:
                continue
            
            # 最適なエージェントを検索
            candidates = self.find_best_agents(
                task.community_id,
                subtask.required_skills,
                max_agents=1
            )
            
            if candidates:
                agent_id = candidates[0]
                self.assign_subtask(task_id, subtask.subtask_id, agent_id)
                assignments[subtask.subtask_id] = agent_id
            else:
                assignments[subtask.subtask_id] = None
        
        logger.info(f"Auto-assigned {len([a for a in assignments.values() if a])} subtasks")
        self._save()
        return {"success": True, "assignments": assignments}
    
    def start_task(self, task_id: str, coordinator_id: str) -> bool:
        """タスクを開始"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        if task.status != TaskStatus.PENDING:
            logger.warning(f"Task not in PENDING status: {task.status}")
            return False
        
        task.status = TaskStatus.IN_PROGRESS
        task.coordinator_id = coordinator_id
        task.started_at = datetime.now(timezone.utc).isoformat()
        task.participants[coordinator_id] = "coordinator"
        
        logger.info(f"Task started: {task_id} by coordinator {coordinator_id}")
        self._save()
        return True
    
    def submit_subtask_result(self, task_id: str, subtask_id: str,
                             agent_id: str, result: Dict[str, Any]) -> bool:
        """サブタスク結果を提出"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        subtask = None
        for st in task.subtasks:
            if st.subtask_id == subtask_id:
                subtask = st
                break
        
        if not subtask or subtask.assigned_to != agent_id:
            return False
        
        subtask.result = result
        subtask.status = TaskStatus.COMPLETED
        subtask.completed_at = datetime.now(timezone.utc).isoformat()
        
        logger.info(f"Subtask result submitted: {subtask_id} by {agent_id}")
        
        # 全サブタスクが完了したかチェック
        if all(st.status == TaskStatus.COMPLETED for st in task.subtasks):
            self._aggregate_results(task_id)
        
        self._save()
        return True
    
    def _aggregate_results(self, task_id: str):
        """サブタスク結果を集約"""
        task = self.tasks[task_id]
        
        # カスタム集約ロジックがあれば使用
        task_type = task.title.lower().replace(" ", "_")
        aggregator = self.result_aggregators.get(task_type)
        
        if aggregator:
            try:
                aggregated = aggregator(task)
                task.aggregated_output = aggregated
            except Exception as e:
                logger.error(f"Result aggregation failed: {e}")
                task.aggregated_output = self._default_aggregation(task)
        else:
            task.aggregated_output = self._default_aggregation(task)
        
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc).isoformat()
        task.final_result = {
            "subtask_results": [st.result for st in task.subtasks],
            "participants": list(task.participants.keys()),
            "completion_time": task.completed_at
        }
        
        self.total_tasks_completed += 1
        logger.info(f"Task completed and results aggregated: {task_id}")
    
    def _default_aggregation(self, task: CollaborativeTask) -> str:
        """デフォルトの結果集約"""
        parts = []
        parts.append(f"# {task.title}\n")
        parts.append(f"{task.description}\n")
        parts.append(f"\n## Results\n")
        
        for subtask in task.subtasks:
            parts.append(f"\n### {subtask.title}\n")
            if subtask.result:
                parts.append(f"**By:** {subtask.assigned_to}\n")
                parts.append(f"**Result:** {json.dumps(subtask.result, indent=2)}\n")
            else:
                parts.append("*No result submitted*\n")
        
        return "\n".join(parts)
    
    def get_task(self, task_id: str) -> Optional[CollaborativeTask]:
        """タスクを取得"""
        return self.tasks.get(task_id)
    
    def list_agent_tasks(self, agent_id: str, 
                        status: Optional[TaskStatus] = None) -> List[CollaborativeTask]:
        """エージェントのタスク一覧"""
        task_ids = self.agent_tasks.get(agent_id, [])
        tasks = [self.tasks[tid] for tid in task_ids if tid in self.tasks]
        
        if status:
            tasks = [t for t in tasks if t.status == status]
        
        return tasks
    
    def get_coordinator_stats(self) -> Dict[str, Any]:
        """コーディネーター統計"""
        status_counts = {}
        for task in self.tasks.values():
            status = task.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "total_tasks": len(self.tasks),
            "total_completed": self.total_tasks_completed,
            "status_breakdown": status_counts,
            "active_agents": len(self.agent_tasks),
            "active_communities": len(self.community_tasks)
        }
    
    def cancel_task(self, task_id: str, requester_id: str) -> bool:
        """タスクをキャンセル"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        if task.requester_id != requester_id:
            logger.warning("Only requester can cancel")
            return False
        
        if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            logger.warning("Cannot cancel completed/failed task")
            return False
        
        task.status = TaskStatus.CANCELLED
        logger.info(f"Task cancelled: {task_id}")
        self._save()
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "tasks": {k: v.to_dict() for k, v in self.tasks.items()},
            "agent_tasks": self.agent_tasks,
            "community_tasks": self.community_tasks,
            "total_tasks_created": self.total_tasks_created,
            "total_tasks_completed": self.total_tasks_completed
        }
    
    def _save(self):
        """データを保存"""
        file_path = self.data_dir / "coordinator_state.json"
        with open(file_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    def _load(self):
        """データを読み込み"""
        file_path = self.data_dir / "coordinator_state.json"
        if not file_path.exists():
            return
        
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        self.total_tasks_created = data.get("total_tasks_created", 0)
        self.total_tasks_completed = data.get("total_tasks_completed", 0)
        self.agent_tasks = data.get("agent_tasks", {})
        self.community_tasks = data.get("community_tasks", {})
        
        # タスクを復元
        for task_id, task_data in data.get("tasks", {}).items():
            subtasks = []
            for st_data in task_data.get("subtasks", []):
                subtasks.append(SubTask(
                    subtask_id=st_data["subtask_id"],
                    title=st_data["title"],
                    description=st_data["description"],
                    required_skills=st_data["required_skills"],
                    estimated_effort=st_data["estimated_effort"],
                    assigned_to=st_data.get("assigned_to"),
                    status=TaskStatus(st_data.get("status", "pending")),
                    result=st_data.get("result"),
                    created_at=st_data["created_at"],
                    completed_at=st_data.get("completed_at")
                ))
            
            self.tasks[task_id] = CollaborativeTask(
                task_id=task_data["task_id"],
                title=task_data["title"],
                description=task_data["description"],
                requester_id=task_data["requester_id"],
                community_id=task_data["community_id"],
                priority=TaskPriority(task_data.get("priority", 2)),
                required_skills=task_data.get("required_skills", []),
                estimated_total_effort=task_data.get("estimated_total_effort", 0),
                deadline=task_data.get("deadline"),
                subtasks=subtasks,
                status=TaskStatus(task_data.get("status", "pending")),
                coordinator_id=task_data.get("coordinator_id"),
                participants=task_data.get("participants", {}),
                created_at=task_data["created_at"],
                started_at=task_data.get("started_at"),
                completed_at=task_data.get("completed_at"),
                final_result=task_data.get("final_result"),
                aggregated_output=task_data.get("aggregated_output")
            )


# グローバルインスタンス
_global_coordinator: Optional[MultiAgentCoordinator] = None


def get_coordinator() -> MultiAgentCoordinator:
    """グローバルコーディネーターを取得"""
    global _global_coordinator
    if _global_coordinator is None:
        _global_coordinator = MultiAgentCoordinator()
    return _global_coordinator


if __name__ == "__main__":
    # 簡易テスト
    logging.basicConfig(level=logging.INFO)
    
    coordinator = get_coordinator()
    
    # タスク作成
    task_id = coordinator.create_collaborative_task(
        title="Build AI Feature",
        description="Implement a new AI capability",
        requester_id="agent_001",
        community_id="community_001",
        priority=TaskPriority.HIGH,
        required_skills=["coding", "ai"]
    )
    
    # サブタスク追加
    coordinator.add_subtask(task_id, "Design", "Create design doc", ["design"], 60)
    coordinator.add_subtask(task_id, "Implement", "Write code", ["coding"], 120)
    
    print(f"Task created: {task_id}")
    
    # 統計表示
    stats = coordinator.get_coordinator_stats()
    print(f"Stats: {json.dumps(stats, indent=2)}")
