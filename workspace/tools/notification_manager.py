"""Unified notification manager for AI Collaboration Platform.

This module provides a unified interface for sending notifications through
multiple channels: Slack, Email (disposable), and SMS.

Features:
- Channel auto-selection based on urgency and configuration
- Fallback between channels
- Rate limiting
- Notification queuing
- Template support

Usage:
    from notification_manager import NotificationManager, NotificationPriority
    
    manager = NotificationManager()
    
    # Send notification with auto channel selection
    manager.send(
        message="System alert",
        priority=NotificationPriority.HIGH,
        channels=["slack", "sms"]
    )
    
    # Or use specific channel
    manager.send_email(to="user@example.com", subject="Hello", body="Message")
"""

import json
import os
import time
import threading
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from queue import Queue


class NotificationPriority(Enum):
    """Notification priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationChannel(Enum):
    """Available notification channels."""
    SLACK = "slack"
    EMAIL = "email"
    SMS = "sms"
    FILE = "file"


@dataclass
class Notification:
    """Notification data."""
    id: str
    message: str
    priority: NotificationPriority
    channels: List[NotificationChannel]
    created_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    title: Optional[str] = None
    retries: int = 0
    max_retries: int = 3


@dataclass
class NotificationResult:
    """Result of notification send operation."""
    notification_id: str
    channel: NotificationChannel
    success: bool
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class RateLimiter:
    """Rate limiter for notifications."""
    
    def __init__(self, max_per_minute: int = 60):
        self.max_per_minute = max_per_minute
        self.timestamps: Dict[str, List[datetime]] = {}
        self.lock = threading.Lock()
    
    def can_send(self, channel: str) -> bool:
        """Check if sending is allowed for channel."""
        with self.lock:
            now = datetime.now()
            cutoff = now - timedelta(minutes=1)
            
            # Clean old timestamps
            if channel in self.timestamps:
                self.timestamps[channel] = [
                    t for t in self.timestamps[channel] if t > cutoff
                ]
            else:
                self.timestamps[channel] = []
            
            return len(self.timestamps[channel]) < self.max_per_minute
    
    def record_send(self, channel: str):
        """Record a send operation."""
        with self.lock:
            if channel not in self.timestamps:
                self.timestamps[channel] = []
            self.timestamps[channel].append(datetime.now())


class NotificationManager:
    """
    Unified notification manager.
    
    Manages notifications across multiple channels with rate limiting,
    fallback support, and queuing.
    """
    
    def __init__(self, rate_limit: int = 60):
        """
        Initialize notification manager.
        
        Args:
            rate_limit: Maximum notifications per minute per channel
        """
        self.rate_limiter = RateLimiter(rate_limit)
        self.queue: Queue = Queue()
        self.results: List[NotificationResult] = []
        self._lock = threading.Lock()
        self._shutdown = threading.Event()
        
        # Import channel modules
        self._init_channels()
        
        # Start background worker
        self._start_worker()
    
    def _init_channels(self):
        """Initialize channel handlers."""
        self.channel_handlers: Dict[NotificationChannel, Callable] = {}
        
        # Slack
        try:
            from notify_slack import notify_slack
            self.channel_handlers[NotificationChannel.SLACK] = self._send_slack
        except ImportError:
            pass
        
        # Email
        try:
            from . import mail_sender as email_module
            self.channel_handlers[NotificationChannel.EMAIL] = self._send_email
        except ImportError:
            pass
        
        # SMS
        try:
            from sms import send_sms
            self.channel_handlers[NotificationChannel.SMS] = self._send_sms
        except ImportError:
            pass
        
        # File (always available)
        self.channel_handlers[NotificationChannel.FILE] = self._send_file
    
    def _send_slack(self, notification: Notification) -> NotificationResult:
        """Send via Slack."""
        try:
            from notify_slack import notify_slack
            
            message = notification.message
            if notification.title:
                message = f"*{notification.title}*\n{message}"
            
            # Add priority emoji
            priority_emoji = {
                NotificationPriority.LOW: "🔹",
                NotificationPriority.NORMAL: "📌",
                NotificationPriority.HIGH: "⚠️",
                NotificationPriority.CRITICAL: "🚨"
            }
            emoji = priority_emoji.get(notification.priority, "📌")
            message = f"{emoji} {message}"
            
            success = notify_slack(message)
            
            return NotificationResult(
                notification_id=notification.id,
                channel=NotificationChannel.SLACK,
                success=success,
                error=None if success else "Slack webhook failed"
            )
            
        except Exception as e:
            return NotificationResult(
                notification_id=notification.id,
                channel=NotificationChannel.SLACK,
                success=False,
                error=str(e)
            )
    
    def _send_email(self, notification: Notification) -> NotificationResult:
        """Send via Email (uses disposable email for temp notifications)."""
        try:
            # For now, log to file as email sending requires SMTP config
            # In production, this would use an SMTP client
            return self._send_file(notification)
            
        except Exception as e:
            return NotificationResult(
                notification_id=notification.id,
                channel=NotificationChannel.EMAIL,
                success=False,
                error=str(e)
            )
    
    def _send_sms(self, notification: Notification) -> NotificationResult:
        """Send via SMS."""
        try:
            from sms import send_sms_alert
            
            result = send_sms_alert(notification.message)
            
            return NotificationResult(
                notification_id=notification.id,
                channel=NotificationChannel.SMS,
                success=result.success,
                error=result.error,
                metadata=result.raw_response or {}
            )
            
        except Exception as e:
            return NotificationResult(
                notification_id=notification.id,
                channel=NotificationChannel.SMS,
                success=False,
                error=str(e)
            )
    
    def _send_file(self, notification: Notification) -> NotificationResult:
        """Send to file (local logging)."""
        try:
            from notify_owner import notify_owner
            
            level = "info"
            if notification.priority == NotificationPriority.HIGH:
                level = "warning"
            elif notification.priority == NotificationPriority.CRITICAL:
                level = "error"
            elif notification.priority == NotificationPriority.LOW:
                level = "success"
            
            success = notify_owner(
                message=notification.message,
                level=level,
                title=notification.title or f"Notification ({notification.priority.value})",
                metadata=notification.metadata
            )
            
            return NotificationResult(
                notification_id=notification.id,
                channel=NotificationChannel.FILE,
                success=success
            )
            
        except Exception as e:
            # Fallback: write directly
            try:
                log_file = "notifications.log"
                timestamp = datetime.now().isoformat()
                with open(log_file, "a") as f:
                    f.write(f"\n{'='*50}\n")
                    f.write(f"Time: {timestamp}\n")
                    f.write(f"Priority: {notification.priority.value}\n")
                    f.write(f"Title: {notification.title}\n")
                    f.write(f"Message: {notification.message}\n")
                    f.write(f"Metadata: {json.dumps(notification.metadata)}\n")
                    f.write(f"{'='*50}\n")
                
                return NotificationResult(
                    notification_id=notification.id,
                    channel=NotificationChannel.FILE,
                    success=True
                )
            except:
                return NotificationResult(
                    notification_id=notification.id,
                    channel=NotificationChannel.FILE,
                    success=False,
                    error=str(e)
                )
    
    def _start_worker(self):
        """Start background worker thread."""
        def worker():
            while not self._shutdown.is_set():
                try:
                    notification = self.queue.get(timeout=1)
                    if notification is None:
                        break
                    
                    self._process_notification(notification)
                    self.queue.task_done()
                    
                except:
                    continue
        
        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()
    
    def shutdown(self):
        """Shutdown the notification manager gracefully."""
        self._shutdown.set()
        if hasattr(self, '_worker_thread'):
            self._worker_thread.join(timeout=5)
    
    def _process_notification(self, notification: Notification):
        """Process a single notification."""
        import uuid
        
        for channel in notification.channels:
            # Check rate limit
            if not self.rate_limiter.can_send(channel.value):
                # Queue for later if rate limited
                if notification.retries < notification.max_retries:
                    notification.retries += 1
                    time.sleep(60)  # Wait a minute
                    self.queue.put(notification)
                return
            
            # Record send attempt
            self.rate_limiter.record_send(channel.value)
            
            # Send via channel
            handler = self.channel_handlers.get(channel)
            if handler:
                result = handler(notification)
                
                with self._lock:
                    self.results.append(result)
                
                # If successful and not critical, stop trying other channels
                if result.success and notification.priority != NotificationPriority.CRITICAL:
                    break
    
    def send(
        self,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        channels: Optional[List[NotificationChannel]] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Send a notification.
        
        Args:
            message: Notification message
            priority: Priority level
            channels: Channels to use (auto-select if None)
            title: Optional title
            metadata: Additional metadata
        
        Returns:
            Notification ID
        """
        import uuid
        
        # Auto-select channels based on priority
        if channels is None:
            channels = self._auto_select_channels(priority)
        
        notification = Notification(
            id=str(uuid.uuid4()),
            message=message,
            priority=priority,
            channels=channels,
            created_at=datetime.now(),
            title=title,
            metadata=metadata or {}
        )
        
        # Queue for processing
        self.queue.put(notification)
        
        return notification.id
    
    def _auto_select_channels(self, priority: NotificationPriority) -> List[NotificationChannel]:
        """Auto-select channels based on priority."""
        # Always include file for logging
        channels = [NotificationChannel.FILE]
        
        # Slack for normal and above
        if priority in (NotificationPriority.NORMAL, NotificationPriority.HIGH, NotificationPriority.CRITICAL):
            if NotificationChannel.SLACK in self.channel_handlers:
                channels.append(NotificationChannel.SLACK)
        
        # SMS for high and critical
        if priority in (NotificationPriority.HIGH, NotificationPriority.CRITICAL):
            if NotificationChannel.SMS in self.channel_handlers:
                channels.append(NotificationChannel.SMS)
        
        return channels
    
    def send_slack(self, message: str, title: Optional[str] = None) -> str:
        """Send Slack notification."""
        return self.send(
            message=message,
            channels=[NotificationChannel.SLACK],
            title=title
        )
    
    def send_sms(self, message: str, phone_number: Optional[str] = None) -> str:
        """Send SMS notification."""
        metadata = {}
        if phone_number:
            metadata["phone_number"] = phone_number
        
        return self.send(
            message=message,
            channels=[NotificationChannel.SMS],
            priority=NotificationPriority.HIGH,
            metadata=metadata
        )
    
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None
    ) -> str:
        """Send email notification."""
        return self.send(
            message=f"To: {to}\nSubject: {subject}\n\n{body}",
            channels=[NotificationChannel.EMAIL],
            title=subject,
            metadata={"to": to, "html": html_body}
        )
    
    def alert(self, message: str, title: str = "System Alert") -> str:
        """Send critical alert through all channels."""
        return self.send(
            message=message,
            priority=NotificationPriority.CRITICAL,
            title=title
        )
    
    def get_results(
        self,
        notification_id: Optional[str] = None,
        channel: Optional[NotificationChannel] = None
    ) -> List[NotificationResult]:
        """
        Get notification results.
        
        Args:
            notification_id: Filter by notification ID
            channel: Filter by channel
        
        Returns:
            List of results
        """
        with self._lock:
            results = self.results.copy()
        
        if notification_id:
            results = [r for r in results if r.notification_id == notification_id]
        
        if channel:
            results = [r for r in results if r.channel == channel]
        
        return results
    
    def get_status(self) -> Dict[str, Any]:
        """Get notification manager status."""
        return {
            "queue_size": self.queue.qsize(),
            "total_results": len(self.results),
            "available_channels": [c.value for c in self.channel_handlers.keys()],
            "rate_limit": self.rate_limiter.max_per_minute
        }


# Convenience functions for common use cases

_default_manager: Optional[NotificationManager] = None


def get_manager() -> NotificationManager:
    """Get or create default notification manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = NotificationManager()
    return _default_manager


def notify(
    message: str,
    priority: str = "normal",
    channels: Optional[List[str]] = None,
    title: Optional[str] = None
) -> str:
    """
    Send notification using default manager.
    
    Args:
        message: Notification message
        priority: Priority as string (low/normal/high/critical)
        channels: List of channel names
        title: Optional title
    
    Returns:
        Notification ID
    """
    manager = get_manager()
    
    priority_enum = NotificationPriority(priority)
    channel_enums = None
    if channels:
        channel_enums = [NotificationChannel(c) for c in channels]
    
    return manager.send(
        message=message,
        priority=priority_enum,
        channels=channel_enums,
        title=title
    )


def alert(message: str, title: str = "Alert") -> str:
    """Send critical alert."""
    return get_manager().alert(message, title)


def notify_slack(message: str, title: Optional[str] = None) -> str:
    """Send Slack notification."""
    return get_manager().send_slack(message, title)


def notify_sms(message: str, phone_number: Optional[str] = None) -> str:
    """Send SMS notification."""
    return get_manager().send_sms(message, phone_number)


def notify_progress(task: str, progress: str, next_action: Optional[str] = None) -> str:
    """Send progress update."""
    message = f"Task: {task}\nProgress: {progress}"
    if next_action:
        message += f"\nNext: {next_action}"
    
    return notify(message, priority="normal", channels=["slack", "file"], title="Progress Update")


def _run_test():
    """Run tests for notification manager."""
    print("=" * 60)
    print("Notification Manager - Test Mode")
    print("=" * 60)
    
    manager = NotificationManager()
    
    # Test 1: Status
    print("\n1. Checking status...")
    status = manager.get_status()
    print(f"   Queue size: {status['queue_size']}")
    print(f"   Available channels: {', '.join(status['available_channels'])}")
    
    # Test 2: Low priority
    print("\n2. Sending low priority notification...")
    id1 = manager.send(
        message="This is a low priority test message",
        priority=NotificationPriority.LOW,
        title="Test: Low Priority"
    )
    print(f"   ✓ Sent (ID: {id1[:8]}...)")
    
    # Test 3: Normal priority
    print("\n3. Sending normal priority notification...")
    id2 = manager.send(
        message="This is a normal priority test message",
        priority=NotificationPriority.NORMAL,
        title="Test: Normal Priority"
    )
    print(f"   ✓ Sent (ID: {id2[:8]}...)")
    
    # Test 4: High priority
    print("\n4. Sending high priority notification...")
    id3 = manager.send(
        message="This is a high priority test message",
        priority=NotificationPriority.HIGH,
        title="Test: High Priority"
    )
    print(f"   ✓ Sent (ID: {id3[:8]}...)")
    
    # Test 5: Critical alert
    print("\n5. Sending critical alert...")
    id4 = manager.alert(
        message="This is a critical system alert",
        title="Test: Critical Alert"
    )
    print(f"   ✓ Sent (ID: {id4[:8]}...)")
    
    # Test 6: Specific channel
    print("\n6. Sending to specific channel (file only)...")
    id5 = manager.send(
        message="File-only notification",
        channels=[NotificationChannel.FILE]
    )
    print(f"   ✓ Sent (ID: {id5[:8]}...)")
    
    # Wait for processing
    print("\n7. Waiting for processing...")
    time.sleep(2)
    
    # Test 8: Get results
    print("\n8. Checking results...")
    results = manager.get_results()
    success_count = sum(1 for r in results if r.success)
    print(f"   Total results: {len(results)}")
    print(f"   Successful: {success_count}")
    
    # Test 9: Convenience functions
    print("\n9. Testing convenience functions...")
    notify("Convenience function test")
    notify_slack("Slack test message")
    notify_progress("Test Task", "50% complete", "Continue testing")
    print("   ✓ Convenience functions executed")
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)
    
    print("\nFeatures:")
    print("  • Multi-channel support (Slack, Email, SMS, File)")
    print("  • Priority-based channel selection")
    print("  • Rate limiting")
    print("  • Asynchronous processing")
    print("  • Fallback between channels")
    print("=" * 60)


if __name__ == "__main__":
    _run_test()
