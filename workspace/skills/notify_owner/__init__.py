"""Owner notification skill for AI Collaboration Platform."""

from .notify_owner import (
    notify_owner,
    notify_task_complete,
    notify_error,
    notify_progress,
)

__all__ = [
    "notify_owner",
    "notify_task_complete",
    "notify_error",
    "notify_progress",
]
