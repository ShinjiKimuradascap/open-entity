crypto_unified.py Design Document

Overview
Consolidating crypto.py, e2e_crypto.py, crypto_utils.py into single module

Architecture
Core Layer: KeyPair, Signature, Encryption
Session Layer: E2ESession, SessionManager
Protocol Layer: SecureMessage, HandshakeHandler
Wallet Layer: Wallet, WalletManager

Implementation Phases
Phase 1: Core implementation
Phase 2: Migration from existing modules
Phase 3: Remove legacy compatibility

Created: 2026-02-01 by Entity B
