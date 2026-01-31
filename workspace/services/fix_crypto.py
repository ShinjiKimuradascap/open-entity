#!/usr/bin/env python3
"""Script to replace crypto.py with wrapper version"""

content = '''#!/usr/bin/env python3
"""
Cryptographic utilities for peer communication - Compatibility Wrapper
Ed25519 signatures and AES-256-GCM encryption

This module is a compatibility wrapper around crypto_utils.py.
All new code should use crypto_utils directly.
"""

# Import all from crypto_utils to maintain backward compatibility
from crypto_utils import (
    # Classes
    CryptoManager,
    SecureMessage,
    WalletManager,
    # Functions
    generate_entity_keypair,
    # Constants
    TIMESTAMP_TOLERANCE_SECONDS,
    JWT_EXPIRY_MINUTES,
    NONCE_SIZE_BYTES,
    AES_KEY_SIZE_BYTES,
    REPLAY_WINDOW_SECONDS,
)

# Maintain backward compatibility: generate_keypair is an alias for generate_entity_keypair
generate_keypair = generate_entity_keypair

# Re-export everything for backward compatibility
__all__ = [
    # Classes from crypto_utils
    "CryptoManager",
    "SecureMessage",
    "WalletManager",
    # Functions
    "generate_entity_keypair",
    "generate_keypair",  # Backward compatibility alias
    # Constants
    "TIMESTAMP_TOLERANCE_SECONDS",
    "JWT_EXPIRY_MINUTES",
    "NONCE_SIZE_BYTES",
    "AES_KEY_SIZE_BYTES",
    "REPLAY_WINDOW_SECONDS",
]
'''

with open('crypto.py', 'w') as f:
    f.write(content)

print("crypto.py has been updated to wrapper version")
