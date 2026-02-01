#!/usr/bin/env python3
"""
Email Service - MVP Implementation

Gmail IMAP/SMTP接続によるメール送受信基本機能
SQLiteストレージ連携

Features:
- Gmail IMAP/SMTP接続
- メール送受信
- SQLite永続化
- 簡易メール解析

Usage:
    service = EmailService()
    await service.initialize()
    
    # Add Gmail account
    account = await service.add_account(
        provider="gmail",
        email="ai@example.com",
        credentials={"password": "app_password"}
    )
    
    # Fetch emails
    emails = await service.fetch_emails(account_id=account.id)
    
    # Send email
    await service.send_email(
        from_account=account.id,
        to=["recipient@example.com"],
        subject="Hello",
        body="This is a test email."
    )
"""

import asyncio
import email
import json
import logging
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header

# Async IMAP/SMTP (will use sync for MVP, async in Phase 2)
import imaplib
import smtplib
from ssl import create_default_context


logger = logging.getLogger(__name__)


@dataclass
class EmailAccount:
    """Email account model"""
    id: str
    provider: str  # "gmail", "outlook"
    email_address: str
    credentials: Dict[str, Any]
    status: str = "active"  # "active", "inactive", "suspended"
    imap_server: str = ""
    smtp_server: str = ""
    smtp_port: int = 587
    daily_send_limit: int = 100
    daily_sent_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_used_at: Optional[str] = None
    
    def __post_init__(self):
        if self.provider == "gmail":
            self.imap_server = self.imap_server or "imap.gmail.com"
            self.smtp_server = self.smtp_server or "smtp.gmail.com"


@dataclass
class EmailMessage:
    """Email message model"""
    id: str
    account_id: str
    message_id: str
    thread_id: str
    sender: str
    recipients: List[str]
    cc: List[str] = field(default_factory=list)
    subject: str = ""
    body_text: str = ""
    body_html: Optional[str] = None
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    received_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sent_at: Optional[str] = None
    folder: str = "inbox"
    is_read: bool = False
    labels: List[str] = field(default_factory=list)
    ai_processed: bool = False


@dataclass
class AIAnalysis:
    """AI analysis result for email"""
    message_id: str
    sentiment: str = "neutral"  # "positive", "negative", "neutral"
    category: str = "unknown"   # "inquiry", "complaint", "spam", "personal", "marketing"
    priority: int = 3           # 1-5
    requires_response: bool = False
    suggested_response: Optional[str] = None
    entities: Dict[str, List[str]] = field(default_factory=dict)
    analyzed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EmailStorage:
    """SQLite storage for email service"""
    
    def __init__(self, db_path: str = "data/communication/email.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS email_accounts (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    email_address TEXT UNIQUE NOT NULL,
                    credentials TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    imap_server TEXT,
                    smtp_server TEXT,
                    smtp_port INTEGER DEFAULT 587,
                    daily_send_limit INTEGER DEFAULT 100,
                    daily_sent_count INTEGER DEFAULT 0,
                    created_at TEXT,
                    last_used_at TEXT
                );
                
                CREATE TABLE IF NOT EXISTS email_messages (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    message_id TEXT,
                    thread_id TEXT,
                    sender TEXT,
                    recipients TEXT,  -- JSON array
                    cc TEXT,  -- JSON array
                    subject TEXT,
                    body_text TEXT,
                    body_html TEXT,
                    attachments TEXT,  -- JSON array
                    received_at TEXT,
                    sent_at TEXT,
                    folder TEXT DEFAULT 'inbox',
                    is_read BOOLEAN DEFAULT 0,
                    labels TEXT,  -- JSON array
                    ai_processed BOOLEAN DEFAULT 0,
                    FOREIGN KEY (account_id) REFERENCES email_accounts(id)
                );
                
                CREATE TABLE IF NOT EXISTS ai_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    sentiment TEXT,
                    category TEXT,
                    priority INTEGER,
                    requires_response BOOLEAN,
                    suggested_response TEXT,
                    entities TEXT,  -- JSON
                    analyzed_at TEXT
                );
                
                CREATE INDEX IF NOT EXISTS idx_messages_account 
                    ON email_messages(account_id);
                CREATE INDEX IF NOT EXISTS idx_messages_folder 
                    ON email_messages(folder);
                CREATE INDEX IF NOT EXISTS idx_messages_received 
                    ON email_messages(received_at);
            """)
    
    def save_account(self, account: EmailAccount) -> bool:
        """Save or update email account"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO email_accounts
                    (id, provider, email_address, credentials, status,
                     imap_server, smtp_server, smtp_port,
                     daily_send_limit, daily_sent_count, created_at, last_used_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    account.id, account.provider, account.email_address,
                    json.dumps(account.credentials), account.status,
                    account.imap_server, account.smtp_server, account.smtp_port,
                    account.daily_send_limit, account.daily_sent_count,
                    account.created_at, account.last_used_at
                ))
            return True
        except Exception as e:
            logger.error(f"Failed to save account: {e}")
            return False
    
    def get_account(self, account_id: str) -> Optional[EmailAccount]:
        """Get account by ID"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM email_accounts WHERE id = ?",
                (account_id,)
            ).fetchone()
            if row:
                return self._row_to_account(row)
        return None
    
    def get_account_by_email(self, email: str) -> Optional[EmailAccount]:
        """Get account by email address"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM email_accounts WHERE email_address = ?",
                (email,)
            ).fetchone()
            if row:
                return self._row_to_account(row)
        return None
    
    def get_all_accounts(self) -> List[EmailAccount]:
        """Get all accounts"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM email_accounts WHERE status = 'active'"
            ).fetchall()
            return [self._row_to_account(row) for row in rows]
    
    def _row_to_account(self, row) -> EmailAccount:
        """Convert DB row to EmailAccount"""
        return EmailAccount(
            id=row[0],
            provider=row[1],
            email_address=row[2],
            credentials=json.loads(row[3]),
            status=row[4],
            imap_server=row[5],
            smtp_server=row[6],
            smtp_port=row[7],
            daily_send_limit=row[8],
            daily_sent_count=row[9],
            created_at=row[10],
            last_used_at=row[11]
        )
    
    def save_message(self, message: EmailMessage) -> bool:
        """Save email message"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO email_messages
                    (id, account_id, message_id, thread_id, sender, recipients, cc,
                     subject, body_text, body_html, attachments, received_at, sent_at,
                     folder, is_read, labels, ai_processed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    message.id, message.account_id, message.message_id,
                    message.thread_id, message.sender,
                    json.dumps(message.recipients),
                    json.dumps(message.cc),
                    message.subject, message.body_text, message.body_html,
                    json.dumps(message.attachments),
                    message.received_at, message.sent_at,
                    message.folder, message.is_read,
                    json.dumps(message.labels),
                    message.ai_processed
                ))
            return True
        except Exception as e:
            logger.error(f"Failed to save message: {e}")
            return False
    
    def get_messages(
        self,
        account_id: Optional[str] = None,
        folder: str = "inbox",
        limit: int = 100,
        unread_only: bool = False
    ) -> List[EmailMessage]:
        """Get messages with filters"""
        query = "SELECT * FROM email_messages WHERE folder = ?"
        params = [folder]
        
        if account_id:
            query += " AND account_id = ?"
            params.append(account_id)
        if unread_only:
            query += " AND is_read = 0"
        
        query += " ORDER BY received_at DESC LIMIT ?"
        params.append(limit)
        
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_message(row) for row in rows]
    
    def _row_to_message(self, row) -> EmailMessage:
        """Convert DB row to EmailMessage"""
        return EmailMessage(
            id=row[0],
            account_id=row[1],
            message_id=row[2],
            thread_id=row[3],
            sender=row[4],
            recipients=json.loads(row[5]),
            cc=json.loads(row[6]) if row[6] else [],
            subject=row[7] or "",
            body_text=row[8] or "",
            body_html=row[9],
            attachments=json.loads(row[10]) if row[10] else [],
            received_at=row[11],
            sent_at=row[12],
            folder=row[13],
            is_read=bool(row[14]),
            labels=json.loads(row[15]) if row[15] else [],
            ai_processed=bool(row[16])
        )
    
    def mark_as_read(self, message_id: str) -> bool:
        """Mark message as read"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE email_messages SET is_read = 1 WHERE id = ?",
                    (message_id,)
                )
            return True
        except Exception as e:
            logger.error(f"Failed to mark as read: {e}")
            return False


class EmailService:
    """
    Email Service - Main service class
    
    Handles Gmail/Outlook email operations with SQLite storage.
    """
    
    def __init__(self, db_path: str = "data/communication/email.db"):
        self.storage = EmailStorage(db_path)
        self._connected_clients: Dict[str, Any] = {}
        logger.info("EmailService initialized")
    
    async def initialize(self) -> None:
        """Initialize service - storage already initialized"""
        logger.info("EmailService ready")
    
    async def add_account(
        self,
        provider: str,
        email_address: str,
        credentials: Dict[str, Any],
        imap_server: Optional[str] = None,
        smtp_server: Optional[str] = None,
        smtp_port: int = 587
    ) -> Optional[EmailAccount]:
        """
        Add new email account
        
        Args:
            provider: "gmail" or "outlook"
            email_address: Email address
            credentials: Dict with "password" or OAuth tokens
            imap_server: IMAP server (auto-set for known providers)
            smtp_server: SMTP server (auto-set for known providers)
            smtp_port: SMTP port (default 587)
        
        Returns:
            EmailAccount or None if failed
        """
        import uuid
        
        account_id = str(uuid.uuid4())[:16]
        
        # Auto-configure known providers
        if provider == "gmail":
            imap_server = imap_server or "imap.gmail.com"
            smtp_server = smtp_server or "smtp.gmail.com"
        elif provider == "outlook":
            imap_server = imap_server or "outlook.office365.com"
            smtp_server = smtp_server or "smtp.office365.com"
        
        account = EmailAccount(
            id=account_id,
            provider=provider,
            email_address=email_address,
            credentials=credentials,
            imap_server=imap_server or "",
            smtp_server=smtp_server or "",
            smtp_port=smtp_port
        )
        
        if self.storage.save_account(account):
            logger.info(f"Added account: {email_address}")
            return account
        return None
    
    async def fetch_emails(
        self,
        account_id: Optional[str] = None,
        folder: str = "inbox",
        since: Optional[datetime] = None,
        limit: int = 50,
        mark_as_read: bool = False
    ) -> List[EmailMessage]:
        """
        Fetch emails from IMAP server
        
        Args:
            account_id: Specific account or None for all accounts
            folder: IMAP folder (inbox, sent, etc.)
            since: Fetch emails since this date
            limit: Max emails to fetch
            mark_as_read: Mark emails as read on server
        
        Returns:
            List of EmailMessage
        """
        messages = []
        
        accounts = []
        if account_id:
            account = self.storage.get_account(account_id)
            if account:
                accounts.append(account)
        else:
            accounts = self.storage.get_all_accounts()
        
        for account in accounts:
            try:
                account_messages = await self._fetch_from_account(
                    account, folder, since, limit, mark_as_read
                )
                messages.extend(account_messages)
            except Exception as e:
                logger.error(f"Failed to fetch from {account.email_address}: {e}")
        
        return messages
    
    async def _fetch_from_account(
        self,
        account: EmailAccount,
        folder: str,
        since: Optional[datetime],
        limit: int,
        mark_as_read: bool
    ) -> List[EmailMessage]:
        """Fetch emails from single account"""
        import uuid
        
        messages = []
        password = account.credentials.get("password", "")
        
        try:
            # Connect to IMAP
            mail = imaplib.IMAP4_SSL(account.imap_server)
            mail.login(account.email_address, password)
            mail.select(folder)
            
            # Search criteria
            if since:
                date_str = since.strftime("%d-%b-%Y")
                status, data = mail.search(None, f'(SINCE "{date_str}")')
            else:
                status, data = mail.search(None, "UNSEEN")
            
            if status != "OK":
                return messages
            
            email_ids = data[0].split()[-limit:]  # Get last N
            
            for eid in email_ids:
                status, msg_data = mail.fetch(eid, "(RFC822)")
                if status != "OK":
                    continue
                
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                # Parse message
                message_id = str(uuid.uuid4())[:16]
                subject = self._decode_header(msg.get("Subject", ""))
                sender = msg.get("From", "")
                recipients = [msg.get("To", "")]
                
                # Extract body
                body_text = ""
                body_html = None
                
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        if content_type == "text/plain":
                            body_text = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        elif content_type == "text/html":
                            body_html = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                else:
                    body_text = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                
                email_msg = EmailMessage(
                    id=message_id,
                    account_id=account.id,
                    message_id=msg.get("Message-ID", ""),
                    thread_id=msg.get("Thread-Topic", ""),
                    sender=sender,
                    recipients=recipients,
                    subject=subject,
                    body_text=body_text[:10000],  # Limit size
                    body_html=body_html[:50000] if body_html else None,
                    received_at=datetime.now(timezone.utc).isoformat(),
                    folder=folder,
                    is_read=mark_as_read
                )
                
                # Save to storage
                self.storage.save_message(email_msg)
                messages.append(email_msg)
                
                if mark_as_read:
                    mail.store(eid, "+FLAGS", "\\Seen")
            
            mail.close()
            mail.logout()
            
            # Update last used
            account.last_used_at = datetime.now(timezone.utc).isoformat()
            self.storage.save_account(account)
            
        except Exception as e:
            logger.error(f"IMAP error for {account.email_address}: {e}")
            raise
        
        return messages
    
    def _decode_header(self, header: str) -> str:
        """Decode email header"""
        if not header:
            return ""
        decoded_parts = decode_header(header)
        result = ""
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                result += part.decode(charset or "utf-8", errors="ignore")
            else:
                result += part
        return result
    
    async def send_email(
        self,
        from_account: str,
        to: List[str],
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        html_body: Optional[str] = None,
        attachments: Optional[List[str]] = None
    ) -> bool:
        """
        Send email via SMTP
        
        Args:
            from_account: Account ID to send from
            to: Recipient list
            subject: Email subject
            body: Plain text body
            cc: CC recipients
            html_body: HTML version (optional)
            attachments: File paths (optional)
        
        Returns:
            True if sent successfully
        """
        import uuid
        
        account = self.storage.get_account(from_account)
        if not account:
            logger.error(f"Account not found: {from_account}")
            return False
        
        # Check daily limit
        if account.daily_sent_count >= account.daily_send_limit:
            logger.warning(f"Daily limit reached for {account.email_address}")
            return False
        
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = account.email_address
            msg["To"] = ", ".join(to)
            if cc:
                msg["Cc"] = ", ".join(cc)
            
            # Attach parts
            msg.attach(MIMEText(body, "plain"))
            if html_body:
                msg.attach(MIMEText(html_body, "html"))
            
            # Send via SMTP
            context = create_default_context()
            with smtplib.SMTP(account.smtp_server, account.smtp_port) as server:
                server.starttls(context=context)
                server.login(
                    account.email_address,
                    account.credentials.get("password", "")
                )
                server.send_message(msg)
            
            # Save to sent folder
            sent_msg = EmailMessage(
                id=str(uuid.uuid4())[:16],
                account_id=account.id,
                message_id=msg.get("Message-ID", ""),
                thread_id="",
                sender=account.email_address,
                recipients=to,
                cc=cc or [],
                subject=subject,
                body_text=body,
                body_html=html_body,
                sent_at=datetime.now(timezone.utc).isoformat(),
                folder="sent",
                is_read=True
            )
            self.storage.save_message(sent_msg)
            
            # Update counter
            account.daily_sent_count += 1
            account.last_used_at = datetime.now(timezone.utc).isoformat()
            self.storage.save_account(account)
            
            logger.info(f"Email sent from {account.email_address} to {to}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    async def get_messages(
        self,
        account_id: Optional[str] = None,
        folder: str = "inbox",
        limit: int = 100,
        unread_only: bool = False
    ) -> List[EmailMessage]:
        """Get messages from storage"""
        return self.storage.get_messages(account_id, folder, limit, unread_only)
    
    async def mark_as_read(self, message_id: str) -> bool:
        """Mark message as read"""
        return self.storage.mark_as_read(message_id)
    
    async def get_account(self, account_id: str) -> Optional[EmailAccount]:
        """Get account by ID"""
        return self.storage.get_account(account_id)
    
    async def get_all_accounts(self) -> List[EmailAccount]:
        """Get all active accounts"""
        return self.storage.get_all_accounts()
    
    async def analyze_email(self, message_id: str) -> Optional[AIAnalysis]:
        """
        Analyze email content (placeholder for AI integration)
        
        Phase 3: Integrate with OpenAI/Gemini for real analysis
        """
        # Placeholder implementation
        return AIAnalysis(
            message_id=message_id,
            sentiment="neutral",
            category="inquiry",
            priority=3,
            requires_response=True,
            suggested_response="Thank you for your email. We will respond shortly."
        )
