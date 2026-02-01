#!/usr/bin/env python3
"""
Communication Package - Human-like Communication Services

人間のように振る舞うためのコミュニケーション基盤
- Email Service: Gmail/Outlook等のメール送受信
- SMS Service: TwilioによるSMS送受信・電話番号管理

Usage:
    from services.communication import EmailService, SMSService
    
    email = EmailService()
    await email.initialize()
    
    sms = SMSService()
    await sms.initialize()
"""

__version__ = "0.1.0"
__author__ = "AI Collaboration Platform"

# Import main services
from services.communication.email_service import EmailService
from services.communication.sms_service import SMSService
from services.communication.sns_service import SNSService


__all__ = [
    "EmailService",
    "SMSService",
    "SNSService",
]
