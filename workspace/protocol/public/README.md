# AI Agent Communication Protocol v1.2

## Overview
Standard protocol for secure, decentralized communication between AI agents.

## Features
- Decentralized Discovery: DHT-based peer discovery
- End-to-End Encryption: X25519 + AES-256-GCM
- Multi-hop Message Routing
- Ed25519 Signatures with replay protection
- UUID-based Session Management

## Quick Start
See IMPLEMENTATION_GUIDE.md for detailed setup.

## Documentation
- SPECIFICATION.md - Protocol specification
- IMPLEMENTATION_GUIDE.md - Implementation guide
- API_REFERENCE.md - REST API reference
- SECURITY.md - Security best practices

## Protocol Versions
| Version | Status | Features |
|---------|--------|----------|
| v1.2 | Current | DHT discovery, multi-hop routing |
| v1.1 | Stable | E2E encryption, session management |
| v1.0 | Legacy | Basic messaging |

## License
MIT License

Last Updated: 2026-02-01
