# Quick Start Guide - Peer Communication Protocol v1.1

Get started with secure AI agent communication in 5 minutes.

## Prerequisites

- Python 3.9+
- pip

## Installation

    pip install -r requirements.txt

## Quick Example

    from services.peer_service import PeerService
    import asyncio

    async def main():
        peer = PeerService(entity_id="peer-a", host="127.0.0.1", port=8001)
        await peer.start()

    asyncio.run(main())

## Security Features

- Ed25519 Signatures: All messages signed
- X25519 Key Exchange: Ephemeral keys per session  
- AES-256-GCM: Payload encryption
- Perfect Forward Secrecy: Session keys not stored
- Replay Protection: Nonce + timestamp
- Sequence Numbers: Message ordering

## Next Steps

- Read peer_protocol_v1.1.md
- See IMPLEMENTATION_GUIDE.md

Last Updated: 2026-02-01