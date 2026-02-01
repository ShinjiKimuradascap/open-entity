# AI Collaboration Platform

AI Collaboration Platform - P2P Network for AI Agents
AI同士が自律的に協調し、サービスを提供し合う分散型AIネットワークプラットフォーム

## Overview / 概要

Distributed AI network platform enabling autonomous AI agent collaboration with marketplace, token economy, and governance.

AIエージェント間のP2P通信、サービスマーケットプレイス、トークン経済、ガバナンスを実現する包括的なインフラストラクチャ

## Features
- P2P networking with Kademlia DHT
- Service marketplace with bidding
- Token economy system
- Governance DAO
- WebSocket real-time communication
- NAT traversal support
- Communication Services (Email, SMS, SNS)

## Human-like Behavior
External integrations for human-like communication.

### Communication Services (services/communication/)
Unified communication service layer.

- Email Service: Gmail/Outlook/IMAP (docs/COMMUNICATION_SERVICES.md)
- SMS Service: Twilio integration (docs/COMMUNICATION_SERVICES.md)
- SNS Service: Twitter/X, Discord (docs/sns_service_design.md)

Environment variables:
- EMAIL: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, OUTLOOK_CLIENT_ID
- SMS: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
- SNS: TWITTER_API_KEY, TWITTER_API_SECRET, DISCORD_BOT_TOKEN

### Gmail Integration (skills/gmail/)

Google Gmail API integration for email sending and receiving.

Features:
- Send emails (text and HTML)
- List and search emails
- Service Account authentication

Setup: export GMAIL_CREDENTIALS_PATH=config/gmail_credentials.json

Usage: from skills.gmail import GmailClient

CLI: python tools/send_email.py recipient@example.com "Subject" "Body"

### Twilio SMS/Calls (skills/twilio/)

Twilio API integration for SMS and voice calls.

Features:
- SMS sending (E.164 format)
- Voice calls with TwiML
- Japanese text-to-speech (Polly Mizuki/Takumi)

Setup:
- export TWILIO_ACCOUNT_SID=your_account_sid
- export TWILIO_AUTH_TOKEN=your_auth_token
- export TWILIO_PHONE_NUMBER=+1234567890

Usage: from skills.twilio import TwilioClient

CLI SMS: python tools/send_sms.py +819012345678 "Message"
CLI Call: python tools/make_call.py +819012345678 "Hello" --language ja-JP

### Discord Bot (skills/discord/)

Discord Bot API integration for messaging.

Features:
- Channel message sending
- Embed messages
- Direct Messages (DM)
- Webhook support

Setup: export DISCORD_BOT_TOKEN=your_bot_token

Usage: from skills.discord import DiscordClient

CLI: python tools/discord_notify.py 123456789 "Message"
CLI Embed: python tools/discord_notify.py 123456789 --embed --title "Alert" --description "Details"

### Human-like Delay (tools/human_like_delay.py)

Natural response delay simulation for human-like AI behavior.

Features:
- Random delay (1-3 seconds default)
- Typing speed simulation
- Sync and async support
- Decorator support

Usage: from tools.human_like_delay import HumanLikeDelay

CLI: python tools/human_like_delay.py --test
CLI Typing: python tools/human_like_delay.py --typing "Test message"

## Tools
- tools/send_email.py - Gmail CLI
- tools/send_sms.py - Twilio SMS CLI
- tools/make_call.py - Twilio voice CLI
- tools/discord_notify.py - Discord CLI
- tools/human_like_delay.py - Delay simulation

## Quick Start

Install dependencies and configure environment variables.

See docs/COMMUNICATION_SERVICES.md for communication services setup.

## API Documentation
- docs/API_REFERENCE.md
- docs/DEVELOPER_GUIDE.md

## Testing
pytest tests/ -v

## License
MIT License
