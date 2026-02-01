"""SMS notification utility for AI Collaboration Platform.

This module provides functions to send SMS messages using various providers:
- Twilio (primary)
- Vonage/Nexmo (alternative)
- Textbelt (simple, no signup required for testing)

For testing without API keys, a mock mode is available that logs messages
instead of sending them.

Usage:
    from sms import send_sms, SMSService
    
    # Send via Twilio
    send_sms("+1234567890", "Hello from AI Platform!")
    
    # Or use service class for more control
    service = SMSService(provider="twilio")
    service.send("+1234567890", "Test message")
"""

import json
import os
import urllib.request
import urllib.error
import urllib.parse
import base64
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SMSProvider(Enum):
    """Supported SMS providers."""
    TWILIO = "twilio"
    VONAGE = "vonage"
    TEXTBELT = "textbelt"
    MOCK = "mock"


@dataclass
class SMSMessage:
    """SMS message data."""
    to: str
    body: str
    from_number: Optional[str] = None
    message_id: Optional[str] = None
    status: Optional[str] = None
    sent_at: Optional[datetime] = None
    provider: Optional[str] = None


@dataclass
class SMSSendResult:
    """Result of SMS send operation."""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[Dict] = None


class BaseSMSProvider:
    """Base class for SMS providers."""
    
    def __init__(self, config: Dict[str, str]):
        self.config = config
    
    def send(self, to: str, body: str, from_number: Optional[str] = None) -> SMSSendResult:
        raise NotImplementedError
    
    def validate_number(self, number: str) -> bool:
        """Basic phone number validation."""
        # Remove common separators and check if remaining is digits
        cleaned = number.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
        return cleaned.isdigit() and len(cleaned) >= 8


class TwilioProvider(BaseSMSProvider):
    """Twilio SMS provider."""
    
    API_BASE = "https://api.twilio.com/2010-04-01"
    
    def __init__(self, config: Dict[str, str]):
        super().__init__(config)
        self.account_sid = config.get("TWILIO_ACCOUNT_SID", "")
        self.auth_token = config.get("TWILIO_AUTH_TOKEN", "")
        self.from_number = config.get("TWILIO_FROM_NUMBER", "")
    
    def is_configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.from_number)
    
    def send(self, to: str, body: str, from_number: Optional[str] = None) -> SMSSendResult:
        if not self.is_configured():
            return SMSSendResult(
                success=False,
                error="Twilio not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER."
            )
        
        if not self.validate_number(to):
            return SMSSendResult(success=False, error=f"Invalid phone number: {to}")
        
        from_num = from_number or self.from_number
        
        # Build request
        url = f"{self.API_BASE}/Accounts/{self.account_sid}/Messages.json"
        
        data = urllib.parse.urlencode({
            "To": to,
            "From": from_num,
            "Body": body
        }).encode()
        
        # Create auth header
        credentials = base64.b64encode(
            f"{self.account_sid}:{self.auth_token}".encode()
        ).decode()
        
        headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode())
                
                return SMSSendResult(
                    success=result.get("status") in ("queued", "sending", "sent"),
                    message_id=result.get("sid"),
                    raw_response=result
                )
                
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            try:
                error_json = json.loads(error_body)
                error_msg = error_json.get("message", error_body)
            except:
                error_msg = error_body or str(e)
            
            return SMSSendResult(success=False, error=error_msg)
            
        except Exception as e:
            return SMSSendResult(success=False, error=str(e))


class VonageProvider(BaseSMSProvider):
    """Vonage (formerly Nexmo) SMS provider."""
    
    API_BASE = "https://rest.nexmo.com/sms/json"
    
    def __init__(self, config: Dict[str, str]):
        super().__init__(config)
        self.api_key = config.get("VONAGE_API_KEY", "")
        self.api_secret = config.get("VONAGE_API_SECRET", "")
        self.from_name = config.get("VONAGE_FROM_NAME", "AI-Platform")
    
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_secret)
    
    def send(self, to: str, body: str, from_number: Optional[str] = None) -> SMSSendResult:
        if not self.is_configured():
            return SMSSendResult(
                success=False,
                error="Vonage not configured. Set VONAGE_API_KEY and VONAGE_API_SECRET."
            )
        
        if not self.validate_number(to):
            return SMSSendResult(success=False, error=f"Invalid phone number: {to}")
        
        from_name = from_number or self.from_name
        
        data = json.dumps({
            "api_key": self.api_key,
            "api_secret": self.api_secret,
            "to": to,
            "from": from_name,
            "text": body
        }).encode()
        
        headers = {"Content-Type": "application/json"}
        
        try:
            req = urllib.request.Request(
                self.API_BASE,
                data=data,
                headers=headers,
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode())
                
                messages = result.get("messages", [])
                if messages and messages[0].get("status") == "0":
                    return SMSSendResult(
                        success=True,
                        message_id=messages[0].get("message-id"),
                        raw_response=result
                    )
                else:
                    return SMSSendResult(
                        success=False,
                        error=messages[0].get("error-text", "Unknown error"),
                        raw_response=result
                    )
                    
        except Exception as e:
            return SMSSendResult(success=False, error=str(e))


class TextbeltProvider(BaseSMSProvider):
    """
    Textbelt SMS provider.
    
    Textbelt offers a simple API that doesn't require signup for testing
    (limited free quota). For production use, an API key is required.
    
    Website: https://textbelt.com
    """
    
    API_BASE = "https://textbelt.com/text"
    
    def __init__(self, config: Dict[str, str]):
        super().__init__(config)
        self.api_key = config.get("TEXTBELT_API_KEY", "textbelt")  # "textbelt" = free tier
    
    def send(self, to: str, body: str, from_number: Optional[str] = None) -> SMSSendResult:
        if not self.validate_number(to):
            return SMSSendResult(success=False, error=f"Invalid phone number: {to}")
        
        data = json.dumps({
            "phone": to,
            "message": body,
            "key": self.api_key
        }).encode()
        
        headers = {"Content-Type": "application/json"}
        
        try:
            req = urllib.request.Request(
                self.API_BASE,
                data=data,
                headers=headers,
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode())
                
                return SMSSendResult(
                    success=result.get("success", False),
                    message_id=result.get("textId"),
                    error=result.get("error"),
                    raw_response=result
                )
                
        except Exception as e:
            return SMSSendResult(success=False, error=str(e))


class MockProvider(BaseSMSProvider):
    """
    Mock SMS provider for testing.
    
    Instead of sending actual SMS, it logs messages to a file.
    Useful for testing without API credentials.
    """
    
    def __init__(self, config: Dict[str, str]):
        super().__init__(config)
        self.log_file = config.get("MOCK_SMS_LOG", "mock_sms_log.txt")
        self.messages: List[SMSMessage] = []
    
    def send(self, to: str, body: str, from_number: Optional[str] = None) -> SMSSendResult:
        message = SMSMessage(
            to=to,
            body=body,
            from_number=from_number or "MOCK",
            message_id=f"mock-{datetime.now().timestamp()}",
            status="sent",
            sent_at=datetime.now(),
            provider="mock"
        )
        
        self.messages.append(message)
        
        # Log to file
        try:
            with open(self.log_file, "a") as f:
                f.write(f"\n{'='*50}\n")
                f.write(f"Time: {message.sent_at}\n")
                f.write(f"To: {message.to}\n")
                f.write(f"From: {message.from_number}\n")
                f.write(f"Body: {message.body}\n")
                f.write(f"{'='*50}\n")
        except:
            pass
        
        print(f"[MOCK SMS] To: {to}, Body: {body[:50]}...")
        
        return SMSSendResult(
            success=True,
            message_id=message.message_id,
            raw_response={"mock": True, "logged": True}
        )


class SMSService:
    """
    Unified SMS service that supports multiple providers.
    
    Automatically selects the best available provider based on configuration.
    """
    
    def __init__(self, provider: Optional[str] = None, config: Optional[Dict] = None):
        """
        Initialize SMS service.
        
        Args:
            provider: Provider name ("twilio", "vonage", "textbelt", "mock")
                     If None, auto-detects from environment variables
            config: Optional configuration dictionary
        """
        self.config = config or self._load_config_from_env()
        self.provider_name = provider or self._detect_provider()
        self.provider = self._create_provider()
    
    def _load_config_from_env(self) -> Dict[str, str]:
        """Load configuration from environment variables."""
        return {
            # Twilio
            "TWILIO_ACCOUNT_SID": os.environ.get("TWILIO_ACCOUNT_SID", ""),
            "TWILIO_AUTH_TOKEN": os.environ.get("TWILIO_AUTH_TOKEN", ""),
            "TWILIO_FROM_NUMBER": os.environ.get("TWILIO_FROM_NUMBER", ""),
            # Vonage
            "VONAGE_API_KEY": os.environ.get("VONAGE_API_KEY", ""),
            "VONAGE_API_SECRET": os.environ.get("VONAGE_API_SECRET", ""),
            "VONAGE_FROM_NAME": os.environ.get("VONAGE_FROM_NAME", "AI-Platform"),
            # Textbelt
            "TEXTBELT_API_KEY": os.environ.get("TEXTBELT_API_KEY", "textbelt"),
            # Mock
            "MOCK_SMS_LOG": os.environ.get("MOCK_SMS_LOG", "mock_sms_log.txt"),
        }
    
    def _detect_provider(self) -> str:
        """Auto-detect provider from configuration."""
        # Check Twilio
        if self.config.get("TWILIO_ACCOUNT_SID") and self.config.get("TWILIO_AUTH_TOKEN"):
            return "twilio"
        
        # Check Vonage
        if self.config.get("VONAGE_API_KEY") and self.config.get("VONAGE_API_SECRET"):
            return "vonage"
        
        # Default to mock for testing
        return "mock"
    
    def _create_provider(self) -> BaseSMSProvider:
        """Create provider instance."""
        providers = {
            "twilio": TwilioProvider,
            "vonage": VonageProvider,
            "textbelt": TextbeltProvider,
            "mock": MockProvider,
        }
        
        provider_class = providers.get(self.provider_name, MockProvider)
        return provider_class(self.config)
    
    def send(self, to: str, body: str, from_number: Optional[str] = None) -> SMSSendResult:
        """
        Send an SMS message.
        
        Args:
            to: Destination phone number (E.164 format recommended)
            body: Message text
            from_number: Optional sender number (uses default if not set)
        
        Returns:
            SMSSendResult with success status and details
        """
        return self.provider.send(to, body, from_number)
    
    def get_provider_name(self) -> str:
        """Get current provider name."""
        return self.provider_name


# Convenience functions for simple use cases

def send_sms(
    to: str,
    body: str,
    provider: Optional[str] = None,
    from_number: Optional[str] = None
) -> SMSSendResult:
    """
    Send an SMS message using the specified or auto-detected provider.
    
    Args:
        to: Destination phone number
        body: Message text (max 1600 chars for most providers)
        provider: Provider name (auto-detect if None)
        from_number: Optional sender number
    
    Returns:
        SMSSendResult with success status
    
    Example:
        >>> result = send_sms("+1234567890", "Hello from AI!")
        >>> if result.success:
        ...     print(f"Sent! ID: {result.message_id}")
        ... else:
        ...     print(f"Failed: {result.error}")
    """
    service = SMSService(provider=provider)
    return service.send(to, body, from_number)


def send_sms_alert(message: str, phone_number: Optional[str] = None) -> SMSSendResult:
    """
    Send an alert SMS to the configured alert number.
    
    Args:
        message: Alert message
        phone_number: Optional override number (uses ALERT_PHONE_NUMBER env var if not set)
    """
    to = phone_number or os.environ.get("ALERT_PHONE_NUMBER", "")
    
    if not to:
        return SMSSendResult(
            success=False,
            error="No phone number configured. Set ALERT_PHONE_NUMBER environment variable."
        )
    
    body = f"🚨 AI Platform Alert\n\n{message}\n\n{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    return send_sms(to, body)


def send_sms_notification(
    title: str,
    message: str,
    phone_number: Optional[str] = None
) -> SMSSendResult:
    """
    Send a notification SMS.
    
    Args:
        title: Notification title
        message: Notification body
        phone_number: Optional override number
    """
    to = phone_number or os.environ.get("NOTIFICATION_PHONE_NUMBER", "")
    
    if not to:
        return SMSSendResult(
            success=False,
            error="No phone number configured. Set NOTIFICATION_PHONE_NUMBER environment variable."
        )
    
    body = f"📱 {title}\n\n{message}\n\n{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    return send_sms(to, body)


def validate_phone_number(number: str) -> bool:
    """
    Validate a phone number.
    
    Args:
        number: Phone number to validate
    
    Returns:
        True if valid
    """
    service = SMSService(provider="mock")  # Use mock for validation only
    return service.provider.validate_number(number)


def format_international(number: str, country_code: str = "1") -> str:
    """
    Format a phone number to international format (E.164).
    
    Args:
        number: Phone number
        country_code: Country code (default: 1 for US)
    
    Returns:
        Formatted number with + prefix
    """
    # Remove all non-digit characters
    digits = ''.join(c for c in number if c.isdigit())
    
    # Add country code if not present
    if not digits.startswith(country_code) or len(digits) < 10:
        digits = country_code + digits
    
    return f"+{digits}"


def get_provider_status() -> Dict[str, Any]:
    """
    Get status of all SMS providers.
    
    Returns:
        Dictionary with provider statuses
    """
    config = {
        "TWILIO_ACCOUNT_SID": os.environ.get("TWILIO_ACCOUNT_SID", ""),
        "TWILIO_AUTH_TOKEN": os.environ.get("TWILIO_AUTH_TOKEN", ""),
        "TWILIO_FROM_NUMBER": os.environ.get("TWILIO_FROM_NUMBER", ""),
        "VONAGE_API_KEY": os.environ.get("VONAGE_API_KEY", ""),
        "VONAGE_API_SECRET": os.environ.get("VONAGE_API_SECRET", ""),
        "TEXTBELT_API_KEY": os.environ.get("TEXTBELT_API_KEY", ""),
    }
    
    return {
        "twilio": {
            "configured": bool(config["TWILIO_ACCOUNT_SID"] and config["TWILIO_AUTH_TOKEN"]),
            "has_from_number": bool(config["TWILIO_FROM_NUMBER"])
        },
        "vonage": {
            "configured": bool(config["VONAGE_API_KEY"] and config["VONAGE_API_SECRET"])
        },
        "textbelt": {
            "configured": bool(config["TEXTBELT_API_KEY"]),
            "using_free_tier": config["TEXTBELT_API_KEY"] == "textbelt" or not config["TEXTBELT_API_KEY"]
        },
        "mock": {
            "configured": True,
            "note": "Always available for testing"
        }
    }


def _run_test():
    """Run basic tests for the SMS module."""
    print("=" * 60)
    print("SMS Notification Tool - Test Mode")
    print("=" * 60)
    
    # Test 1: Provider status
    print("\n1. Checking provider configuration...")
    status = get_provider_status()
    for provider, info in status.items():
        configured = info.get("configured", False)
        symbol = "✓" if configured else "✗"
        print(f"   {symbol} {provider}: {'Configured' if configured else 'Not configured'}")
    
    # Test 2: Phone number validation
    print("\n2. Testing phone number validation...")
    test_numbers = [
        "+1234567890",
        "123-456-7890",
        "1234567890",
        "invalid",
        "+1 (555) 123-4567"
    ]
    for num in test_numbers:
        valid = validate_phone_number(num)
        symbol = "✓" if valid else "✗"
        print(f"   {symbol} {num}: {'Valid' if valid else 'Invalid'}")
    
    # Test 3: International formatting
    print("\n3. Testing international formatting...")
    test_formats = [
        "1234567890",
        "(555) 123-4567",
        "555.123.4567"
    ]
    for num in test_formats:
        formatted = format_international(num)
        print(f"   {num} → {formatted}")
    
    # Test 4: Mock SMS send
    print("\n4. Testing mock SMS send...")
    service = SMSService(provider="mock")
    result = service.send("+1234567890", "Test message from AI Platform")
    if result.success:
        print(f"   ✓ Mock SMS sent (ID: {result.message_id})")
    else:
        print(f"   ✗ Mock SMS failed: {result.error}")
    
    # Test 5: Alert function
    print("\n5. Testing alert function (will use mock)...")
    # Temporarily set a mock alert number
    os.environ["ALERT_PHONE_NUMBER"] = "+1234567890"
    result = send_sms_alert("This is a test alert")
    if result.success:
        print(f"   ✓ Alert sent successfully")
    else:
        print(f"   ⚠ Alert not sent (expected if using mock): {result.error}")
    del os.environ["ALERT_PHONE_NUMBER"]
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("\nTo use real SMS:")
    print("  - Twilio: Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER")
    print("  - Vonage: Set VONAGE_API_KEY, VONAGE_API_SECRET")
    print("  - Textbelt: Set TEXTBELT_API_KEY (or use 'textbelt' for free tier)")
    print("=" * 60)


if __name__ == "__main__":
    _run_test()
