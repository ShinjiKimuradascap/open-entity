"""Disposable email utility using mail.tm API.

This module provides functions to create temporary email addresses
and receive emails via the mail.tm API. Useful for automated testing,
verification flows, and temporary communications.

Usage:
    from email import create_email_account, get_messages, wait_for_email
    
    # Create temporary email
    account = create_email_account()
    print(f"Email: {account['address']}")
    
    # Wait for verification email
    messages = wait_for_email(account, timeout=60)
    for msg in messages:
        print(f"From: {msg['from']}, Subject: {msg['subject']}")
"""

import json
import time
import urllib.request
import urllib.error
import uuid
import secrets
import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime


MAILTM_API_BASE = "https://api.mail.tm"


@dataclass
class EmailAccount:
    """Temporary email account data."""
    address: str
    password: str
    token: str
    id: str
    created_at: datetime


@dataclass
class EmailMessage:
    """Email message data."""
    id: str
    from_address: str
    to_address: str
    subject: str
    intro: str
    text: Optional[str]
    html: Optional[str]
    created_at: datetime


class MailTMClient:
    """Client for mail.tm API."""
    
    def __init__(self, base_url: str = MAILTM_API_BASE):
        self.base_url = base_url
    
    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Make API request to mail.tm."""
        url = f"{self.base_url}{endpoint}"
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AI-Collaboration-Platform/1.0"
        }
        
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        try:
            if data:
                req_data = json.dumps(data).encode("utf-8")
            else:
                req_data = None
            
            req = urllib.request.Request(
                url,
                data=req_data,
                headers=headers,
                method=method
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status in (200, 201):
                    return json.loads(response.read().decode("utf-8"))
                else:
                    return {"success": False, "status": response.status}
                    
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            try:
                error_json = json.loads(error_body)
                return {"success": False, "error": error_json, "status": e.code}
            except:
                return {"success": False, "error": error_body, "status": e.code}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_domains(self) -> List[Dict[str, str]]:
        """Get available email domains."""
        result = self._request("GET", "/domains")
        if "hydra:member" in result:
            return [
                {"id": d["id"], "domain": d["domain"]}
                for d in result["hydra:member"]
            ]
        return []
    
    def create_account(self, address: str, password: str) -> Optional[EmailAccount]:
        """Create a new email account."""
        data = {"address": address, "password": password}
        result = self._request("POST", "/accounts", data)
        
        if "id" in result:
            # Get auth token
            auth_result = self._request("POST", "/token", {
                "address": address,
                "password": password
            })
            
            if "token" in auth_result:
                return EmailAccount(
                    address=address,
                    password=password,
                    token=auth_result["token"],
                    id=result["id"],
                    created_at=datetime.now()
                )
        
        return None
    
    def get_messages(self, token: str) -> List[EmailMessage]:
        """Get messages for an account."""
        result = self._request("GET", "/messages", token=token)
        
        messages = []
        if "hydra:member" in result:
            for msg in result["hydra:member"]:
                messages.append(EmailMessage(
                    id=msg["id"],
                    from_address=msg.get("from", {}).get("address", "unknown"),
                    to_address=msg.get("to", [{}])[0].get("address", "unknown"),
                    subject=msg.get("subject", "No Subject"),
                    intro=msg.get("intro", ""),
                    text=None,  # Will be fetched separately
                    html=None,
                    created_at=datetime.fromisoformat(
                        msg["createdAt"].replace("Z", "+00:00")
                    )
                ))
        
        return messages
    
    def get_message(self, token: str, message_id: str) -> Optional[EmailMessage]:
        """Get full message content."""
        result = self._request("GET", f"/messages/{message_id}", token=token)
        
        if "id" in result:
            return EmailMessage(
                id=result["id"],
                from_address=result.get("from", {}).get("address", "unknown"),
                to_address=result.get("to", [{}])[0].get("address", "unknown"),
                subject=result.get("subject", "No Subject"),
                intro=result.get("intro", ""),
                text=result.get("text"),
                html=result.get("html"),
                created_at=datetime.fromisoformat(
                    result["createdAt"].replace("Z", "+00:00")
                )
            )
        
        return None
    
    def delete_account(self, token: str, account_id: str) -> bool:
        """Delete an email account."""
        result = self._request("DELETE", f"/accounts/{account_id}", token=token)
        return result.get("success", True)


# Global client instance
_client: Optional[MailTMClient] = None


def get_client() -> MailTMClient:
    """Get or create mail.tm client."""
    global _client
    if _client is None:
        _client = MailTMClient()
    return _client


def generate_random_address() -> str:
    """Generate a random email address."""
    client = get_client()
    domains = client.get_domains()
    
    if not domains:
        raise RuntimeError("No email domains available from mail.tm")
    
    domain = domains[0]["domain"]
    local_part = f"ai-{uuid.uuid4().hex[:12]}"
    return f"{local_part}@{domain}"


def create_email_account(password: Optional[str] = None) -> Optional[EmailAccount]:
    """
    Create a new temporary email account.
    
    Args:
        password: Optional password (random if not provided)
    
    Returns:
        EmailAccount object or None if creation failed
    
    Example:
        >>> account = create_email_account()
        >>> print(f"Email: {account.address}")
        Email: ai-a1b2c3d4e5f6@example.com
    """
    client = get_client()
    address = generate_random_address()
    
    if password is None:
        password = secrets.token_urlsafe(16)
    
    return client.create_account(address, password)


def get_messages(account: EmailAccount) -> List[EmailMessage]:
    """
    Get all messages for an account.
    
    Args:
        account: EmailAccount object
    
    Returns:
        List of EmailMessage objects
    """
    client = get_client()
    return client.get_messages(account.token)


def get_message_content(account: EmailAccount, message_id: str) -> Optional[EmailMessage]:
    """
    Get full content of a specific message.
    
    Args:
        account: EmailAccount object
        message_id: Message ID
    
    Returns:
        EmailMessage with full content or None
    """
    client = get_client()
    return client.get_message(account.token, message_id)


def wait_for_email(
    account: EmailAccount,
    timeout: int = 60,
    poll_interval: int = 5,
    subject_contains: Optional[str] = None
) -> List[EmailMessage]:
    """
    Wait for emails to arrive.
    
    Args:
        account: EmailAccount object
        timeout: Maximum time to wait in seconds
        poll_interval: Time between checks in seconds
        subject_contains: Optional filter for subject line
    
    Returns:
        List of received EmailMessage objects
    
    Example:
        >>> account = create_email_account()
        >>> # Use email for registration...
        >>> messages = wait_for_email(account, timeout=120, subject_contains="verification")
        >>> for msg in messages:
        ...     print(f"Verification email: {msg.subject}")
    """
    client = get_client()
    start_time = time.time()
    seen_ids = set()
    
    while time.time() - start_time < timeout:
        messages = client.get_messages(account.token)
        new_messages = []
        
        for msg in messages:
            if msg.id not in seen_ids:
                seen_ids.add(msg.id)
                
                # Filter by subject if specified
                if subject_contains is None or subject_contains.lower() in msg.subject.lower():
                    # Fetch full content
                    full_msg = client.get_message(account.token, msg.id)
                    if full_msg:
                        new_messages.append(full_msg)
        
        if new_messages:
            return new_messages
        
        time.sleep(poll_interval)
    
    return []


def delete_account(account: EmailAccount) -> bool:
    """
    Delete a temporary email account.
    
    Args:
        account: EmailAccount to delete
    
    Returns:
        True if deleted successfully
    """
    client = get_client()
    return client.delete_account(account.token, account.id)


def extract_verification_code(message: EmailMessage, pattern: Optional[str] = None) -> Optional[str]:
    """
    Extract verification code from email content.
    
    Args:
        message: EmailMessage to parse
        pattern: Optional regex pattern (default: 4-8 digit numbers)
    
    Returns:
        Extracted code or None
    """
    text = message.text or message.intro or ""
    
    if pattern:
        match = re.search(pattern, text)
    else:
        # Look for common verification code patterns
        # 4-8 digit numbers
        match = re.search(r'\b\d{4,8}\b', text)
    
    return match.group(0) if match else None


# Convenience functions for common use cases

def create_and_wait(
    timeout: int = 60,
    subject_contains: Optional[str] = None
) -> tuple[Optional[EmailAccount], List[EmailMessage]]:
    """
    Create email account and wait for messages.
    
    Returns:
        Tuple of (account, messages)
    """
    account = create_email_account()
    if not account:
        return None, []
    
    messages = wait_for_email(account, timeout, subject_contains=subject_contains)
    return account, messages


def quick_email_check(address: str, token: str) -> List[Dict[str, str]]:
    """
    Quick check for messages using address and token.
    
    Args:
        address: Email address
        token: Auth token
    
    Returns:
        List of message summaries
    """
    # Create temporary account object
    account = EmailAccount(
        address=address,
        password="",
        token=token,
        id="",
        created_at=datetime.now()
    )
    
    messages = get_messages(account)
    return [
        {
            "id": m.id,
            "from": m.from_address,
            "subject": m.subject,
            "created": m.created_at.isoformat()
        }
        for m in messages
    ]


def _run_test():
    """Run basic tests for the email module."""
    print("=" * 60)
    print("Disposable Email Tool - Test Mode")
    print("=" * 60)
    
    try:
        # Test 1: Get domains
        print("\n1. Getting available domains...")
        client = get_client()
        domains = client.get_domains()
        if domains:
            print(f"   ✓ Found {len(domains)} domain(s)")
            for d in domains[:3]:
                print(f"     - {d['domain']}")
        else:
            print("   ✗ No domains available")
            return
        
        # Test 2: Create account
        print("\n2. Creating temporary email account...")
        account = create_email_account()
        if account:
            print(f"   ✓ Created: {account.address}")
            print(f"   ✓ Account ID: {account.id[:20]}...")
        else:
            print("   ✗ Failed to create account")
            return
        
        # Test 3: Check messages (will be empty)
        print("\n3. Checking for messages...")
        messages = get_messages(account)
        print(f"   ✓ Found {len(messages)} message(s)")
        
        # Test 4: Wait with short timeout
        print("\n4. Waiting for messages (5s timeout)...")
        messages = wait_for_email(account, timeout=5, poll_interval=1)
        print(f"   ✓ Received {len(messages)} message(s) during wait")
        
        # Test 5: Delete account
        print("\n5. Cleaning up - deleting account...")
        if delete_account(account):
            print("   ✓ Account deleted successfully")
        else:
            print("   ⚠ Account deletion may have failed")
        
        print("\n" + "=" * 60)
        print("Test completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n   ✗ Error during test: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    _run_test()
