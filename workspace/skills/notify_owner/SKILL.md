---
name: notify_owner
description: Owner notification utility for AI Collaboration Platform
tools:
  - notify_owner
  - notify_task_complete
  - notify_error
  - notify_progress
---

# notify_owner

AI Collaboration Platform owner notification skill.

## Tools

- notify_owner(message, level, title, metadata)
- notify_task_complete(task_id, task_name, result, details)
- notify_error(error_message, context, task_id)
- notify_progress(task_name, progress, next_action)

## Environment Variables

- SLACK_WEBHOOK_URL: Optional Slack webhook URL

## Output

Notifications are appended to OWNER_MESSAGES.md in the workspace root.
