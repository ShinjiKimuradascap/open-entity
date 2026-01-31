# Kademlia DHT Design

## Overview
Kademlia-based DHT for peer discovery and key-value storage.

## Parameters
- k=20 bucket size
- alpha=3 parallel lookups
- ID=160 bits SHA256

## Components
1. KademliaNode - node representation
2. RoutingTable - 160 k-buckets
3. KBucket - k-size node list
4. KademliaDHT - main interface

## RPCs
- PING, STORE, FIND_NODE, FIND_VALUE

## Key Structure
peer_key = SHA256("peer:" + entity_id)

## Files
- services/kademlia_dht.py
- services/kademlia_rpc.py

---
Created: 2026-02-01
