---
name: peer-tools
description: Peer entity communication tools for talking to, waking up, and monitoring paired entities. Use when the user asks to communicate with a partner entity, check peer status, or restart a peer.
disable-model-invocation: false
user-invocable: true
allowed-tools: talk_to_peer, wake_up_peer, report_to_peer, check_peer_alive, restart_peer
version: 1.0.0
tools:
  talk_to_peer:
    description: Send message to peer entity
  wake_up_peer:
    description: Wake up peer entity (prompt task continuation)
  report_to_peer:
    description: Report progress to peer entity (async, fire-and-forget)
  check_peer_alive:
    description: Check if peer entity is alive
  restart_peer:
    description: Attempt to restart unresponsive peer entity
---

# Peer Tools

Tools for communicating with paired peer entities.
Use these when you need to collaborate with or monitor your partner entity.
