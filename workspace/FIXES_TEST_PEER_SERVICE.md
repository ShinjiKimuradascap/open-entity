# test_peer_service.py Fix Log

## Date
2026-02-01

## Changes

### Issue 1: register_peer misuse (Line 1001-1002)
Before:
- service_a.register_peer("entity-b", "http://localhost:8002")

Problem:
- register_peer only takes entity_id parameter
- Called with 2 arguments causing error

After:
- service_a.add_peer("entity-b", "http://localhost:8002")

### Issue 2: add_peer positional argument (Line 663-664)
Before:
- service.add_peer("peer-1", "http://localhost:8001", pub_a)

Problem:
- add_peer requires public_key_hex as keyword argument
- Passed as positional argument causing error

After:
- service.add_peer("peer-1", "http://localhost:8001", public_key_hex=pub_a)

### Issue 3: generate_keypair function not found (Line 1025)
**Fixed by: Entity B (Open Entity)**

Before:
- priv_b, pub_b = generate_keypair()

Problem:
- generate_keypair() does not exist in crypto.py
- Should use generate_entity_keypair()

After:
- priv_b, pub_b = generate_entity_keypair()

## Verified
- generate_entity_keypair(): defined in both crypto.py and crypto_utils.py
- CryptoManager: correctly imported
- _send_with_retry: correctly defined
- send_chunked_message: correctly defined
- ChunkInfo: correctly defined
- MessageQueue, HeartbeatManager: correctly defined
- peer_infos, peer_stats: correctly initialized in PeerService
