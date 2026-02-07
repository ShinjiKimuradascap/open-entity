---
name: amp-tools
description: Agent Messaging Protocol (AMP) tools for inter-agent communication, identity management, and message exchange. Use when the user asks to send messages between agents, manage AMP identities, or discover peers.
disable-model-invocation: false
user-invocable: true
allowed-tools: amp_cli, amp_send, amp_history, amp_discover, amp_identity_list, amp_identity_show, amp_identity_create, amp_identity_import, amp_identity_use, amp_identity_delete, amp_identity_export, amp_identity_reset
version: 1.0.0
tools:
  amp_cli:
    description: Run AMP CLI command directly
  amp_send:
    description: Send message via AMP
  amp_history:
    description: View AMP message history
  amp_discover:
    description: Discover AMP agents
  amp_identity_list:
    description: List AMP identities
  amp_identity_show:
    description: Show AMP identity details
  amp_identity_create:
    description: Create new AMP identity
  amp_identity_import:
    description: Import AMP identity (handles private key)
  amp_identity_use:
    description: Switch active AMP identity
  amp_identity_delete:
    description: Delete AMP identity (destructive)
  amp_identity_export:
    description: Export AMP identity (outputs private key)
  amp_identity_reset:
    description: Reset AMP identity (destructive)
---

# AMP Tools

Agent Messaging Protocol tools for inter-agent communication.
Use these tools for sending messages between agents, managing identities, and discovering peers.
