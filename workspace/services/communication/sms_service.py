#!/usr/bin/env python3
"""
SMS Service - MVP Implementation

Twilio API連携によるSMS送受信・電話番号管理
SQLiteストレージ連携

Features:
- Twilio SMS送受信
- 電話番号購入・管理
- メッセージテンプレート
- 受信Webhookハンドラ
- SQLite永続化

Usage:
    service = SMSService()
    await service.initialize()
    
    # Buy phone number
    number = await service.buy_phone_number(area_code="415")
    
    # Send SMS
    msg = await service.send_sms(
        from_number=number.phone_number,
        to_number="+1234567890",
        message="Hello from AI!"
    )
    
    # Fetch messages
    messages = await service.fetch_messages(phone_number=number.phone_number)
    
    # Handle incoming webhook
    response = await service.handle_incoming_webhook(webhook_data)

Environment Variables:
    TWILIO_ACCOUNT_SID: Twilio Account SID
    TWILIO_AUTH_TOKEN: Twilio Auth Token
    TWILIO_WEBHOOK_URL: Webhook URL for incoming messages
"""

import asyncio
import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from uuid import uuid4

# Twilio SDK (install with: pip install twilio)
try:
    from twilio.rest import Client as TwilioClient
    from twilio.base.exceptions import TwilioRestException
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    TwilioClient = None  # type: ignore
    TwilioRestException = Exception  # type: ignore


logger = logging.getLogger(__name__)


@dataclass
class PhoneNumber:
    """Phone number model"""
    id: str
    phone_number: str  # E.164 format: +1234567890
    friendly_name: str
    account_sid: str
    status: str = "active"  # "active", "suspended", "released"
    capabilities: List[str] = field(default_factory=lambda: ["SMS"])
    area_code: Optional[str] = None
    region: Optional[str] = None
    monthly_cost: float = 0.0
    webhook_url: Optional[str] = None
    fallback_url: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Optional[str] = None
    released_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SMSMessage:
    """SMS message model"""
    id: str
    message_sid: Optional[str]  # Twilio Message SID
    account_sid: str
    from_number: str
    to_number: str
    body: str
    direction: str  # "outbound", "inbound"
    status: str = "pending"  # "pending", "queued", "sent", "delivered", "failed", "received"
    num_segments: int = 1
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    price: Optional[float] = None
    price_unit: str = "USD"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sent_at: Optional[str] = None
    delivered_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SMSTemplate:
    """SMS template model"""
    id: str
    name: str
    content: str
    description: str = ""
    variables: List[str] = field(default_factory=list)
    is_active: bool = True
    usage_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Optional[str] = None
    
    def render(self, **kwargs) -> str:
        """Render template with variables"""
        result = self.content
        for key, value in kwargs.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WebhookLog:
    """Webhook request log"""
    id: str
    webhook_type: str  # "incoming", "status"
    phone_number: str
    payload: Dict[str, Any]
    processed: bool = False
    response_status: int = 200
    error_message: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SMSStorage:
    """SQLite storage for SMS service"""
    
    def __init__(self, db_path: str = "data/sms_service.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(str(self.db_path))
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection
    
    def initialize(self) -> None:
        """Create database tables"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Phone numbers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS phone_numbers (
                id TEXT PRIMARY KEY,
                phone_number TEXT UNIQUE NOT NULL,
                friendly_name TEXT,
                account_sid TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                capabilities TEXT,
                area_code TEXT,
                region TEXT,
                monthly_cost REAL DEFAULT 0.0,
                webhook_url TEXT,
                fallback_url TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                released_at TEXT
            )
        """)
        
        # Messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sms_messages (
                id TEXT PRIMARY KEY,
                message_sid TEXT,
                account_sid TEXT NOT NULL,
                from_number TEXT NOT NULL,
                to_number TEXT NOT NULL,
                body TEXT,
                direction TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                num_segments INTEGER DEFAULT 1,
                error_code TEXT,
                error_message TEXT,
                price REAL,
                price_unit TEXT DEFAULT 'USD',
                created_at TEXT NOT NULL,
                sent_at TEXT,
                delivered_at TEXT,
                updated_at TEXT
            )
        """)
        
        # Templates table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sms_templates (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL,
                description TEXT,
                variables TEXT,
                is_active INTEGER DEFAULT 1,
                usage_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
        """)
        
        # Webhook logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS webhook_logs (
                id TEXT PRIMARY KEY,
                webhook_type TEXT NOT NULL,
                phone_number TEXT NOT NULL,
                payload TEXT NOT NULL,
                processed INTEGER DEFAULT 0,
                response_status INTEGER DEFAULT 200,
                error_message TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_from ON sms_messages(from_number)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_to ON sms_messages(to_number)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_created ON sms_messages(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_logs_phone ON webhook_logs(phone_number)")
        
        conn.commit()
        logger.info("SMS storage initialized")
    
    def save_phone_number(self, number: PhoneNumber) -> None:
        """Save phone number to storage"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO phone_numbers (
                id, phone_number, friendly_name, account_sid, status, capabilities,
                area_code, region, monthly_cost, webhook_url, fallback_url,
                created_at, updated_at, released_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            number.id, number.phone_number, number.friendly_name, number.account_sid,
            number.status, json.dumps(number.capabilities), number.area_code,
            number.region, number.monthly_cost, number.webhook_url, number.fallback_url,
            number.created_at, number.updated_at, number.released_at
        ))
        conn.commit()
    
    def get_phone_number(self, number_id: str) -> Optional[PhoneNumber]:
        """Get phone number by ID"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM phone_numbers WHERE id = ?", (number_id,))
        row = cursor.fetchone()
        if row:
            return self._row_to_phone_number(row)
        return None
    
    def get_phone_number_by_twilio_sid(self, account_sid: str) -> Optional[PhoneNumber]:
        """Get phone number by Twilio Account SID"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM phone_numbers WHERE account_sid = ?", (account_sid,))
        row = cursor.fetchone()
        if row:
            return self._row_to_phone_number(row)
        return None
    
    def get_phone_number_by_e164(self, phone_number: str) -> Optional[PhoneNumber]:
        """Get phone number by E.164 format"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM phone_numbers WHERE phone_number = ?", (phone_number,))
        row = cursor.fetchone()
        if row:
            return self._row_to_phone_number(row)
        return None
    
    def get_all_phone_numbers(self, status: Optional[str] = None) -> List[PhoneNumber]:
        """Get all phone numbers, optionally filtered by status"""
        conn = self._get_connection()
        cursor = conn.cursor()
        if status:
            cursor.execute("SELECT * FROM phone_numbers WHERE status = ? ORDER BY created_at DESC", (status,))
        else:
            cursor.execute("SELECT * FROM phone_numbers ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [self._row_to_phone_number(row) for row in rows]
    
    def _row_to_phone_number(self, row: sqlite3.Row) -> PhoneNumber:
        """Convert database row to PhoneNumber"""
        return PhoneNumber(
            id=row['id'],
            phone_number=row['phone_number'],
            friendly_name=row['friendly_name'],
            account_sid=row['account_sid'],
            status=row['status'],
            capabilities=json.loads(row['capabilities']) if row['capabilities'] else ["SMS"],
            area_code=row['area_code'],
            region=row['region'],
            monthly_cost=row['monthly_cost'] or 0.0,
            webhook_url=row['webhook_url'],
            fallback_url=row['fallback_url'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            released_at=row['released_at']
        )
    
    def save_message(self, message: SMSMessage) -> None:
        """Save SMS message to storage"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO sms_messages (
                id, message_sid, account_sid, from_number, to_number, body,
                direction, status, num_segments, error_code, error_message,
                price, price_unit, created_at, sent_at, delivered_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            message.id, message.message_sid, message.account_sid, message.from_number,
            message.to_number, message.body, message.direction, message.status,
            message.num_segments, message.error_code, message.error_message,
            message.price, message.price_unit, message.created_at, message.sent_at,
            message.delivered_at, message.updated_at
        ))
        conn.commit()
    
    def get_message(self, message_id: str) -> Optional[SMSMessage]:
        """Get message by ID"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sms_messages WHERE id = ?", (message_id,))
        row = cursor.fetchone()
        if row:
            return self._row_to_message(row)
        return None
    
    def get_messages_by_phone(self, phone_number: str, direction: Optional[str] = None, limit: int = 100) -> List[SMSMessage]:
        """Get messages for a phone number"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if direction:
            cursor.execute("""
                SELECT * FROM sms_messages 
                WHERE (from_number = ? OR to_number = ?) AND direction = ?
                ORDER BY created_at DESC LIMIT ?
            """, (phone_number, phone_number, direction, limit))
        else:
            cursor.execute("""
                SELECT * FROM sms_messages 
                WHERE from_number = ? OR to_number = ?
                ORDER BY created_at DESC LIMIT ?
            """, (phone_number, phone_number, limit))
        
        rows = cursor.fetchall()
        return [self._row_to_message(row) for row in rows]
    
    def get_conversation(self, phone_number1: str, phone_number2: str, limit: int = 100) -> List[SMSMessage]:
        """Get conversation between two phone numbers"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM sms_messages 
            WHERE (from_number = ? AND to_number = ?) OR (from_number = ? AND to_number = ?)
            ORDER BY created_at DESC LIMIT ?
        """, (phone_number1, phone_number2, phone_number2, phone_number1, limit))
        rows = cursor.fetchall()
        return [self._row_to_message(row) for row in rows]
    
    def _row_to_message(self, row: sqlite3.Row) -> SMSMessage:
        """Convert database row to SMSMessage"""
        return SMSMessage(
            id=row['id'],
            message_sid=row['message_sid'],
            account_sid=row['account_sid'],
            from_number=row['from_number'],
            to_number=row['to_number'],
            body=row['body'] or "",
            direction=row['direction'],
            status=row['status'],
            num_segments=row['num_segments'] or 1,
            error_code=row['error_code'],
            error_message=row['error_message'],
            price=row['price'],
            price_unit=row['price_unit'] or "USD",
            created_at=row['created_at'],
            sent_at=row['sent_at'],
            delivered_at=row['delivered_at'],
            updated_at=row['updated_at']
        )
    
    def save_template(self, template: SMSTemplate) -> None:
        """Save SMS template to storage"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO sms_templates (
                id, name, content, description, variables, is_active,
                usage_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            template.id, template.name, template.content, template.description,
            json.dumps(template.variables), 1 if template.is_active else 0,
            template.usage_count, template.created_at, template.updated_at
        ))
        conn.commit()
    
    def get_template(self, template_id: str) -> Optional[SMSTemplate]:
        """Get template by ID"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sms_templates WHERE id = ?", (template_id,))
        row = cursor.fetchone()
        if row:
            return self._row_to_template(row)
        return None
    
    def get_template_by_name(self, name: str) -> Optional[SMSTemplate]:
        """Get template by name"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sms_templates WHERE name = ?", (name,))
        row = cursor.fetchone()
        if row:
            return self._row_to_template(row)
        return None
    
    def get_all_templates(self, active_only: bool = True) -> List[SMSTemplate]:
        """Get all templates"""
        conn = self._get_connection()
        cursor = conn.cursor()
        if active_only:
            cursor.execute("SELECT * FROM sms_templates WHERE is_active = 1 ORDER BY name")
        else:
            cursor.execute("SELECT * FROM sms_templates ORDER BY name")
        rows = cursor.fetchall()
        return [self._row_to_template(row) for row in rows]
    
    def _row_to_template(self, row: sqlite3.Row) -> SMSTemplate:
        """Convert database row to SMSTemplate"""
        return SMSTemplate(
            id=row['id'],
            name=row['name'],
            content=row['content'],
            description=row['description'] or "",
            variables=json.loads(row['variables']) if row['variables'] else [],
            is_active=bool(row['is_active']),
            usage_count=row['usage_count'] or 0,
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )
    
    def log_webhook(self, log: WebhookLog) -> None:
        """Log webhook request"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO webhook_logs (
                id, webhook_type, phone_number, payload, processed,
                response_status, error_message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            log.id, log.webhook_type, log.phone_number, json.dumps(log.payload),
            1 if log.processed else 0, log.response_status, log.error_message,
            log.created_at
        ))
        conn.commit()
    
    def get_webhook_logs(self, phone_number: Optional[str] = None, limit: int = 100) -> List[WebhookLog]:
        """Get webhook logs"""
        conn = self._get_connection()
        cursor = conn.cursor()
        if phone_number:
            cursor.execute("""
                SELECT * FROM webhook_logs WHERE phone_number = ? ORDER BY created_at DESC LIMIT ?
            """, (phone_number, limit))
        else:
            cursor.execute("SELECT * FROM webhook_logs ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [self._row_to_webhook_log(row) for row in rows]
    
    def _row_to_webhook_log(self, row: sqlite3.Row) -> WebhookLog:
        """Convert database row to WebhookLog"""
        return WebhookLog(
            id=row['id'],
            webhook_type=row['webhook_type'],
            phone_number=row['phone_number'],
            payload=json.loads(row['payload']),
            processed=bool(row['processed']),
            response_status=row['response_status'],
            error_message=row['error_message'],
            created_at=row['created_at']
        )


import threading


class TwilioClientWrapper:
    """Twilio API wrapper with error handling"""
    
    def __init__(self, account_sid: Optional[str] = None, auth_token: Optional[str] = None):
        self.account_sid = account_sid or os.getenv('TWILIO_ACCOUNT_SID')
        self.auth_token = auth_token or os.getenv('TWILIO_AUTH_TOKEN')
        self.webhook_url = os.getenv('TWILIO_WEBHOOK_URL', '')
        
        if not self.account_sid or not self.auth_token:
            logger.warning("Twilio credentials not configured. SMS service will be in demo mode.")
            self.client = None
            self._demo_mode = True
        elif not TWILIO_AVAILABLE:
            logger.warning("Twilio SDK not installed. Install with: pip install twilio")
            self.client = None
            self._demo_mode = True
        else:
            try:
                self.client = TwilioClient(self.account_sid, self.auth_token)
                self._demo_mode = False
                logger.info("Twilio client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Twilio client: {e}")
                self.client = None
                self._demo_mode = True
    
    @property
    def is_demo_mode(self) -> bool:
        return self._demo_mode
    
    async def send_sms(self, from_number: str, to_number: str, body: str) -> Dict[str, Any]:
        """Send SMS via Twilio API"""
        if self._demo_mode:
            # Demo mode - simulate sending
            logger.info(f"[DEMO] Would send SMS from {from_number} to {to_number}: {body[:50]}...")
            return {
                'sid': f'DEMO_{uuid4().hex[:16]}',
                'status': 'sent',
                'price': 0.0075,
                'error': None
            }
        
        try:
            # Run Twilio API call in thread pool
            loop = asyncio.get_event_loop()
            message = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    body=body,
                    from_=from_number,
                    to=to_number,
                    status_callback=self.webhook_url if self.webhook_url else None
                )
            )
            
            return {
                'sid': message.sid,
                'status': message.status,
                'price': float(message.price) if message.price else None,
                'error': None
            }
        except TwilioRestException as e:
            logger.error(f"Twilio error sending SMS: {e}")
            return {
                'sid': None,
                'status': 'failed',
                'price': None,
                'error': {'code': e.code, 'message': str(e)}
            }
        except Exception as e:
            logger.error(f"Unexpected error sending SMS: {e}")
            return {
                'sid': None,
                'status': 'failed',
                'price': None,
                'error': {'code': None, 'message': str(e)}
            }
    
    async def buy_phone_number(self, area_code: Optional[str] = None, 
                               capabilities: List[str] = None) -> Optional[Dict[str, Any]]:
        """Buy a phone number from Twilio"""
        if self._demo_mode:
            logger.info(f"[DEMO] Would buy phone number with area_code={area_code}")
            return {
                'phone_number': f'+1{area_code or "415"}555{uuid4().hex[:4]}',
                'friendly_name': f'AI Agent Number {uuid4().hex[:4]}',
                'sid': f'DEMO_PN_{uuid4().hex[:16]}',
                'capabilities': capabilities or ['SMS'],
                'monthly_cost': 1.15
            }
        
        try:
            # Search for available numbers
            loop = asyncio.get_event_loop()
            local_numbers = await loop.run_in_executor(
                None,
                lambda: list(self.client.available_phone_numbers('US').local.list(
                    area_code=area_code,
                    sms_enabled='SMS' in (capabilities or ['SMS']),
                    voice_enabled='Voice' in (capabilities or []),
                    limit=1
                ))
            )
            
            if not local_numbers:
                logger.error(f"No available phone numbers found for area code {area_code}")
                return None
            
            # Purchase the first available number
            number = local_numbers[0]
            purchased = await loop.run_in_executor(
                None,
                lambda: self.client.incoming_phone_numbers.create(
                    phone_number=number.phone_number,
                    friendly_name=f'AI Agent Number {number.phone_number}',
                    sms_url=self.webhook_url if self.webhook_url else None,
                    sms_method='POST'
                )
            )
            
            return {
                'phone_number': purchased.phone_number,
                'friendly_name': purchased.friendly_name,
                'sid': purchased.sid,
                'capabilities': capabilities or ['SMS'],
                'monthly_cost': 1.15
            }
        except Exception as e:
            logger.error(f"Error buying phone number: {e}")
            return None
    
    async def fetch_messages(self, phone_number: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch message history for a phone number"""
        if self._demo_mode:
            return []
        
        try:
            loop = asyncio.get_event_loop()
            messages = await loop.run_in_executor(
                None,
                lambda: list(self.client.messages.list(
                    from_=phone_number,
                    limit=limit
                ))
            )
            
            return [{
                'sid': msg.sid,
                'from': msg.from_,
                'to': msg.to,
                'body': msg.body,
                'status': msg.status,
                'direction': msg.direction,
                'date_sent': msg.date_sent.isoformat() if msg.date_sent else None
            } for msg in messages]
        except Exception as e:
            logger.error(f"Error fetching messages: {e}")
            return []
    
    async def release_phone_number(self, phone_number_sid: str) -> bool:
        """Release a phone number"""
        if self._demo_mode:
            logger.info(f"[DEMO] Would release phone number {phone_number_sid}")
            return True
        
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.incoming_phone_numbers(phone_number_sid).delete()
            )
            return True
        except Exception as e:
            logger.error(f"Error releasing phone number: {e}")
            return False


class SMSService:
    """
    SMS Service - Main service class for Twilio SMS operations
    
    Features:
    - SMS send/receive via Twilio
    - Phone number management (buy/release)
    - Message templates
    - Webhook handling for incoming messages
    - SQLite persistence
    """
    
    def __init__(self, storage_path: str = "data/sms_service.db"):
        self.storage = SMSStorage(storage_path)
        self.twilio: Optional[TwilioClientWrapper] = None
        self._initialized = False
    
    async def initialize(self, account_sid: Optional[str] = None, 
                         auth_token: Optional[str] = None) -> bool:
        """
        Initialize the SMS service
        
        Args:
            account_sid: Twilio Account SID (or from env TWILIO_ACCOUNT_SID)
            auth_token: Twilio Auth Token (or from env TWILIO_AUTH_TOKEN)
        
        Returns:
            bool: True if initialized successfully
        """
        try:
            # Initialize storage
            self.storage.initialize()
            
            # Initialize Twilio client
            self.twilio = TwilioClientWrapper(account_sid, auth_token)
            
            if self.twilio.is_demo_mode:
                logger.warning("SMS Service running in DEMO mode (no real Twilio API calls)")
            
            self._initialized = True
            logger.info("SMS Service initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize SMS service: {e}")
            return False
    
    async def buy_phone_number(self, area_code: Optional[str] = None,
                               capabilities: List[str] = None) -> Optional[PhoneNumber]:
        """
        Buy a new phone number from Twilio
        
        Args:
            area_code: Optional area code (e.g., "415")
            capabilities: List of capabilities ["SMS", "Voice"]
        
        Returns:
            PhoneNumber: Purchased phone number object or None
        """
        if not self._initialized:
            raise RuntimeError("SMS Service not initialized. Call initialize() first.")
        
        capabilities = capabilities or ["SMS"]
        
        # Call Twilio API
        result = await self.twilio.buy_phone_number(area_code, capabilities)
        
        if not result:
            return None
        
        # Create phone number record
        number = PhoneNumber(
            id=str(uuid4()),
            phone_number=result['phone_number'],
            friendly_name=result['friendly_name'],
            account_sid=result['sid'],
            status="active",
            capabilities=capabilities,
            area_code=area_code,
            monthly_cost=result['monthly_cost'],
            webhook_url=self.twilio.webhook_url if self.twilio else None
        )
        
        # Save to storage
        self.storage.save_phone_number(number)
        logger.info(f"Purchased phone number: {number.phone_number}")
        
        return number
    
    async def send_sms(self, from_number: str, to_number: str, 
                       message: str, template: Optional[str] = None) -> Optional[SMSMessage]:
        """
        Send an SMS message
        
        Args:
            from_number: Sender phone number (E.164 format)
            to_number: Recipient phone number (E.164 format)
            message: Message body or template name if template is True
            template: Template name to use (optional)
        
        Returns:
            SMSMessage: Sent message object or None
        """
        if not self._initialized:
            raise RuntimeError("SMS Service not initialized. Call initialize() first.")
        
        # Apply template if specified
        if template:
            tmpl = self.storage.get_template_by_name(template)
            if tmpl:
                message = tmpl.render(**{'message': message})
                tmpl.usage_count += 1
                tmpl.updated_at = datetime.now(timezone.utc).isoformat()
                self.storage.save_template(tmpl)
        
        # Send via Twilio
        result = await self.twilio.send_sms(from_number, to_number, message)
        
        # Create message record
        msg = SMSMessage(
            id=str(uuid4()),
            message_sid=result['sid'],
            account_sid=self.twilio.account_sid if self.twilio else 'demo',
            from_number=from_number,
            to_number=to_number,
            body=message,
            direction="outbound",
            status=result['status'],
            price=result['price'],
            sent_at=datetime.now(timezone.utc).isoformat() if result['status'] == 'sent' else None
        )
        
        # Save to storage
        self.storage.save_message(msg)
        logger.info(f"SMS sent: {from_number} -> {to_number} (status: {result['status']})")
        
        return msg
    
    async def fetch_messages(self, phone_number: str, limit: int = 100) -> List[SMSMessage]:
        """
        Fetch message history from Twilio and sync to local storage
        
        Args:
            phone_number: Phone number to fetch messages for
            limit: Maximum number of messages to fetch
        
        Returns:
            List[SMSMessage]: List of messages
        """
        if not self._initialized:
            raise RuntimeError("SMS Service not initialized. Call initialize() first.")
        
        # Fetch from Twilio (only if not demo mode)
        if not self.twilio.is_demo_mode:
            twilio_messages = await self.twilio.fetch_messages(phone_number, limit)
            
            # Sync to local storage
            for msg_data in twilio_messages:
                existing = self.storage.get_message(
                    self._get_message_id_by_sid(msg_data['sid'])
                )
                if not existing:
                    msg = SMSMessage(
                        id=str(uuid4()),
                        message_sid=msg_data['sid'],
                        account_sid=self.twilio.account_sid,
                        from_number=msg_data['from'],
                        to_number=msg_data['to'],
                        body=msg_data['body'] or "",
                        direction=msg_data['direction'],
                        status=msg_data['status'],
                        sent_at=msg_data['date_sent']
                    )
                    self.storage.save_message(msg)
        
        # Return from local storage
        return self.storage.get_messages_by_phone(phone_number, limit=limit)
    
    def _get_message_id_by_sid(self, message_sid: str) -> Optional[str]:
        """Get local message ID by Twilio Message SID"""
        conn = self.storage._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM sms_messages WHERE message_sid = ?", (message_sid,))
        row = cursor.fetchone()
        return row['id'] if row else None
    
    async def handle_incoming_webhook(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle incoming webhook from Twilio
        
        Args:
            data: Webhook payload from Twilio
        
        Returns:
            Dict: Response for Twilio (Twiml or empty)
        """
        if not self._initialized:
            raise RuntimeError("SMS Service not initialized. Call initialize() first.")
        
        # Log webhook
        log = WebhookLog(
            id=str(uuid4()),
            webhook_type="incoming",
            phone_number=data.get('To', ''),
            payload=data
        )
        self.storage.log_webhook(log)
        
        # Process incoming message
        message_sid = data.get('MessageSid')
        from_number = data.get('From', '')
        to_number = data.get('To', '')
        body = data.get('Body', '')
        
        # Save message
        msg = SMSMessage(
            id=str(uuid4()),
            message_sid=message_sid,
            account_sid=self.twilio.account_sid if self.twilio else 'demo',
            from_number=from_number,
            to_number=to_number,
            body=body,
            direction="inbound",
            status="received",
            received_at=datetime.now(timezone.utc).isoformat()
        )
        self.storage.save_message(msg)
        
        logger.info(f"Incoming SMS received: {from_number} -> {to_number}")
        
        # Return empty response (no auto-reply)
        return {
            'status': 'ok',
            'message_id': msg.id
        }
    
    async def handle_status_webhook(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle message status callback webhook from Twilio
        
        Args:
            data: Status callback payload
        
        Returns:
            Dict: Acknowledgment
        """
        if not self._initialized:
            raise RuntimeError("SMS Service not initialized. Call initialize() first.")
        
        message_sid = data.get('MessageSid')
        status = data.get('MessageStatus')
        
        # Log webhook
        log = WebhookLog(
            id=str(uuid4()),
            webhook_type="status",
            phone_number=data.get('To', ''),
            payload=data,
            processed=True
        )
        self.storage.log_webhook(log)
        
        # Update message status
        msg_id = self._get_message_id_by_sid(message_sid)
        if msg_id:
            msg = self.storage.get_message(msg_id)
            if msg:
                msg.status = status
                msg.updated_at = datetime.now(timezone.utc).isoformat()
                
                if status == 'delivered':
                    msg.delivered_at = datetime.now(timezone.utc).isoformat()
                
                self.storage.save_message(msg)
                logger.info(f"Message {message_sid} status updated to: {status}")
        
        return {'status': 'ok'}
    
    def get_message_history(self, phone_number: str, limit: int = 100) -> List[SMSMessage]:
        """
        Get message history for a phone number from local storage
        
        Args:
            phone_number: Phone number to get history for
            limit: Maximum number of messages
        
        Returns:
            List[SMSMessage]: List of messages
        """
        if not self._initialized:
            raise RuntimeError("SMS Service not initialized. Call initialize() first.")
        
        return self.storage.get_messages_by_phone(phone_number, limit=limit)
    
    def get_conversation(self, phone_number1: str, phone_number2: str, 
                         limit: int = 100) -> List[SMSMessage]:
        """
        Get conversation between two phone numbers
        
        Args:
            phone_number1: First phone number
            phone_number2: Second phone number
            limit: Maximum number of messages
        
        Returns:
            List[SMSMessage]: List of messages in chronological order
        """
        if not self._initialized:
            raise RuntimeError("SMS Service not initialized. Call initialize() first.")
        
        messages = self.storage.get_conversation(phone_number1, phone_number2, limit)
        return list(reversed(messages))  # Return in chronological order
    
    def get_phone_numbers(self, status: Optional[str] = None) -> List[PhoneNumber]:
        """
        Get all phone numbers
        
        Args:
            status: Filter by status (optional)
        
        Returns:
            List[PhoneNumber]: List of phone numbers
        """
        if not self._initialized:
            raise RuntimeError("SMS Service not initialized. Call initialize() first.")
        
        return self.storage.get_all_phone_numbers(status=status)
    
    async def release_phone_number(self, number_id: str) -> bool:
        """
        Release a phone number
        
        Args:
            number_id: Phone number ID
        
        Returns:
            bool: True if released successfully
        """
        if not self._initialized:
            raise RuntimeError("SMS Service not initialized. Call initialize() first.")
        
        number = self.storage.get_phone_number(number_id)
        if not number:
            logger.error(f"Phone number not found: {number_id}")
            return False
        
        # Release from Twilio
        success = await self.twilio.release_phone_number(number.account_sid)
        
        if success:
            # Update local record
            number.status = "released"
            number.released_at = datetime.now(timezone.utc).isoformat()
            number.updated_at = datetime.now(timezone.utc).isoformat()
            self.storage.save_phone_number(number)
            logger.info(f"Released phone number: {number.phone_number}")
        
        return success
    
    def create_template(self, name: str, content: str, description: str = "",
                        variables: List[str] = None) -> SMSTemplate:
        """
        Create a new SMS template
        
        Args:
            name: Template name (unique)
            content: Template content with {variable} placeholders
            description: Template description
            variables: List of variable names used in template
        
        Returns:
            SMSTemplate: Created template
        """
        if not self._initialized:
            raise RuntimeError("SMS Service not initialized. Call initialize() first.")
        
        # Parse variables from content if not provided
        if variables is None:
            variables = re.findall(r'\{(\w+)\}', content)
        
        template = SMSTemplate(
            id=str(uuid4()),
            name=name,
            content=content,
            description=description,
            variables=list(set(variables))
        )
        
        self.storage.save_template(template)
        logger.info(f"Created SMS template: {name}")
        
        return template
    
    def get_template(self, name: str) -> Optional[SMSTemplate]:
        """Get template by name"""
        if not self._initialized:
            raise RuntimeError("SMS Service not initialized. Call initialize() first.")
        
        return self.storage.get_template_by_name(name)
    
    def get_templates(self) -> List[SMSTemplate]:
        """Get all active templates"""
        if not self._initialized:
            raise RuntimeError("SMS Service not initialized. Call initialize() first.")
        
        return self.storage.get_all_templates(active_only=True)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get SMS service statistics
        
        Returns:
            Dict: Statistics including message counts, phone numbers, etc.
        """
        if not self._initialized:
            raise RuntimeError("SMS Service not initialized. Call initialize() first.")
        
        conn = self.storage._get_connection()
        cursor = conn.cursor()
        
        # Count messages
        cursor.execute("SELECT COUNT(*) as total FROM sms_messages")
        total_messages = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as outbound FROM sms_messages WHERE direction = 'outbound'")
        outbound_messages = cursor.fetchone()['outbound']
        
        cursor.execute("SELECT COUNT(*) as inbound FROM sms_messages WHERE direction = 'inbound'")
        inbound_messages = cursor.fetchone()['inbound']
        
        # Count phone numbers
        cursor.execute("SELECT COUNT(*) as total FROM phone_numbers")
        total_numbers = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as active FROM phone_numbers WHERE status = 'active'")
        active_numbers = cursor.fetchone()['active']
        
        # Calculate costs
        cursor.execute("SELECT SUM(price) as total_cost FROM sms_messages WHERE price IS NOT NULL")
        total_cost = cursor.fetchone()['total_cost'] or 0.0
        
        return {
            'messages': {
                'total': total_messages,
                'outbound': outbound_messages,
                'inbound': inbound_messages
            },
            'phone_numbers': {
                'total': total_numbers,
                'active': active_numbers
            },
            'estimated_costs': {
                'sms': round(total_cost, 4),
                'monthly_numbers': round(active_numbers * 1.15, 2)  # Approximate Twilio pricing
            },
            'demo_mode': self.twilio.is_demo_mode if self.twilio else True
        }


# Backwards compatibility
TwilioClient = TwilioClientWrapper


__all__ = [
    'SMSService',
    'TwilioClient',
    'TwilioClientWrapper',
    'SMSStorage',
    'PhoneNumber',
    'SMSMessage',
    'SMSTemplate',
    'WebhookLog'
]
