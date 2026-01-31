"""Slack notification utility for AI Collaboration Platform.

This module provides functions to send messages to Slack via Incoming Webhook.
Notifications can be used for alerts, task completions, errors, and more.

Usage:
    from notify_slack import notify_slack
    notify_slack("Hello from AI Collaboration Platform!")
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime
from typing import Optional


def get_slack_webhook_url() -> Optional[str]:
    """Get Slack webhook URL from environment variable."""
    return os.environ.get("SLACK_WEBHOOK_URL")


def notify_slack(
    message: str,
    username: str = "AI Collaboration Platform",
    icon_emoji: str = ":robot_face:",
    channel: Optional[str] = None
) -> bool:
    """
    Send a message to Slack via Incoming Webhook.
    
    Args:
        message: The message text to send
        username: Bot username (default: "AI Collaboration Platform")
        icon_emoji: Emoji icon for the bot (default: ":robot_face:")
        channel: Override channel (optional, uses webhook default if not set)
    
    Returns:
        bool: True if message sent successfully, False otherwise
    
    Example:
        >>> notify_slack("Task completed successfully!")
        True
        >>> notify_slack("Error occurred", icon_emoji=":warning:")
        True
    """
    webhook_url = get_slack_webhook_url()
    
    if not webhook_url:
        print("[ERROR] SLACK_WEBHOOK_URL environment variable not set")
        print("[INFO] Set it in .env file or export SLACK_WEBHOOK_URL=...")
        return False
    
    # Build payload
    payload = {
        "text": message,
        "username": username,
        "icon_emoji": icon_emoji
    }
    
    # Add channel override if specified
    if channel:
        payload["channel"] = channel
    
    # Send request
    try:
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AI-Collaboration-Platform/1.0"
        }
        
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers=headers,
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            # Slack returns 200 with "ok" body on success
            if response.status == 200:
                print(f"[NOTIFY] Slack message sent successfully")
                return True
            else:
                print(f"[ERROR] Slack returned status {response.status}")
                return False
                
    except urllib.error.HTTPError as e:
        print(f"[ERROR] HTTP Error {e.code}: {e.reason}")
        try:
            error_body = e.read().decode("utf-8")
            print(f"[ERROR] Response: {error_body}")
        except:
            pass
        return False
        
    except urllib.error.URLError as e:
        print(f"[ERROR] URL Error: {e.reason}")
        return False
        
    except Exception as e:
        print(f"[ERROR] Failed to send Slack notification: {e}")
        return False


def notify_slack_success(message: str, title: Optional[str] = None) -> bool:
    """
    Send a success notification to Slack.
    
    Args:
        message: The message text
        title: Optional title/header
    
    Returns:
        bool: True if sent successfully
    """
    if title:
        full_message = f"✅ *{title}*\n{message}"
    else:
        full_message = f"✅ {message}"
    
    return notify_slack(full_message, icon_emoji=":white_check_mark:")


def notify_slack_warning(message: str, title: Optional[str] = None) -> bool:
    """
    Send a warning notification to Slack.
    
    Args:
        message: The message text
        title: Optional title/header
    
    Returns:
        bool: True if sent successfully
    """
    if title:
        full_message = f"⚠️ *{title}*\n{message}"
    else:
        full_message = f"⚠️ {message}"
    
    return notify_slack(full_message, icon_emoji=":warning:")


def notify_slack_error(message: str, title: Optional[str] = None) -> bool:
    """
    Send an error notification to Slack.
    
    Args:
        message: The message text
        title: Optional title/header
    
    Returns:
        bool: True if sent successfully
    """
    if title:
        full_message = f"🚨 *{title}*\n{message}"
    else:
        full_message = f"🚨 {message}"
    
    return notify_slack(full_message, icon_emoji=":x:")


def notify_slack_progress(
    task_name: str,
    progress: str,
    next_action: Optional[str] = None
) -> bool:
    """
    Send a progress update to Slack.
    
    Args:
        task_name: Name of the task
        progress: Current progress description
        next_action: Optional next action description
    
    Returns:
        bool: True if sent successfully
    """
    message = f"📊 *Progress: {task_name}*\nCurrent Status: {progress}"
    if next_action:
        message += f"\nNext Action: {next_action}"
    
    return notify_slack(message, icon_emoji=":chart_with_upwards_trend:")


# Simple test
def _run_test():
    """Run basic tests for the notify_slack module."""
    print("=" * 50)
    print("Slack Notification Tool - Test Mode")
    print("=" * 50)
    
    # Check environment
    webhook_url = get_slack_webhook_url()
    if webhook_url:
        print(f"✓ SLACK_WEBHOOK_URL is set ({len(webhook_url)} chars)")
    else:
        print("✗ SLACK_WEBHOOK_URL is NOT set")
        print("  Set it with: export SLACK_WEBHOOK_URL=...")
        print("  Or add to .env file")
        print()
        print("Test mode - messages will be printed but not sent")
    
    print()
    print("Test Messages:")
    print("-" * 50)
    
    # Test different notification types
    test_cases = [
        ("Simple message", lambda: notify_slack("This is a test message")),
        ("Success notification", lambda: notify_slack_success("Task completed!", "Deployment")),
        ("Warning notification", lambda: notify_slack_warning("Disk space low", "System Alert")),
        ("Error notification", lambda: notify_slack_error("Connection failed", "API Error")),
        ("Progress update", lambda: notify_slack_progress("Data Migration", "50% complete", "Continue batch processing")),
    ]
    
    for name, func in test_cases:
        print(f"\n{name}:")
        try:
            result = func()
            print(f"  Result: {'Sent' if result else 'Failed/Skipped'}")
        except Exception as e:
            print(f"  Error: {e}")
    
    print()
    print("=" * 50)
    print("Test completed")
    print("=" * 50)


if __name__ == "__main__":
    _run_test()
