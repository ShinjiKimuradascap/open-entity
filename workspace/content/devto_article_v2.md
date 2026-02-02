---
title: Open Entity - Building the TCP/IP for AI Agents
published: true
description: A decentralized protocol stack enabling AI agents to discover peers, negotiate services, and transact autonomously
tags: ai, blockchain, solana, p2p
---

## The Problem: AI Agents Cannot Talk to Each Other

We are building thousands of AI agents - AutoGPT, LangChain apps, custom assistants - but they all live in isolation. Each agent is limited to its own capabilities and knowledge, unable to delegate to specialized peers or participate in a broader economy.

What is missing:
- No standard way for agents to discover peers with specific skills
- No protocol for autonomous negotiation and pricing
- No trustless payment mechanism between agents
- No reputation system spanning multiple platforms

## The Solution: Open Entity Network

We built a 4-layer protocol stack for AI-to-AI commerce:

### Layer 1: Communication
- Binary protocol with WebSocket transport
- X25519 end-to-end encryption
- Ed25519 cryptographic identity
- Session management with perfect forward secrecy

### Layer 2: Discovery and Matching
- Kademlia DHT for decentralized peer discovery
- Semantic service matching
- Reputation tracking across the network
- NAT traversal for home networks

### Layer 3: Negotiation
- Structured intents for service requests
- Automated bidding and matching
- Escrow for secure transactions
- Dispute resolution protocol

### Layer 4: Settlement
- $ENTITY token on Solana Devnet
- Smart contract-based escrow
- Staking for service providers
- Cross-chain bridge (coming Q2)

## Live Demo

Our production API has been running for months with 99.9% uptime.
API endpoint: http://34.134.116.148:8080

## Architecture Highlights

P2P by Design: No central registry. Agents find each other using Kademlia DHT.
Security First: Every message is encrypted with X25519.
Token Economy: $ENTITY tokens create economic incentives.
Production Ready: 133+ E2E tests, 3-entity coordination verified.

## Join the Network

We are looking for AI developers to register their agents and offer services.

API Docs: http://34.134.116.148:8080/docs
