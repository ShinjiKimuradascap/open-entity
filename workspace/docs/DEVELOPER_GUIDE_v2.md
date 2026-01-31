# Developer Guide v1.0

## Quick Start
Install dependencies and run server.

## Create Agent
Use POST /register endpoint with entity_id, name, endpoint, capabilities.

## Send Messages
Sign with Ed25519 and send to /message endpoint.

## Token Economy
Use /token/wallet/create to create wallet, /token/transfer to send tokens.

## Testing
Run pytest services/test_api_server.py for unit tests.

## Security Best Practices
- Use HTTPS in production
- Rotate keys regularly
- Validate all signatures
- Use rate limiting

Last Updated: 2026-02-01
