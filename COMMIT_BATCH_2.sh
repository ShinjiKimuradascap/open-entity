#!/bin/bash
# Batch 2: A2A Implementation + Registry Design

git add .

git commit -m "feat: A2A protocol implementation + registry design

A2A Protocol (Phase 1):
- Add a2a/ package with protocol.py and transport.py
- Implement HTTP/WebSocket messaging
- Add AgentIdentity, A2AMessage with HMAC signatures
- Add oe a2a CLI commands (discover, serve, send)

Design Documents:
- docs/A2A_PROTOCOL.md - A2A specification
- docs/DECENTRALIZED_REGISTRY.md - P2P registry design

Infrastructure:
- Add run_local.sh for Docker-free execution
- Update CI/CD for open_entity package
- Fix docker-compose.yml package references
- Add tests/ directory with pytest setup

Commands:
- oe evolve analyze/loop - Self-improvement
- oe a2a serve - Start P2P server
- oe a2a send - Send messages to agents
"