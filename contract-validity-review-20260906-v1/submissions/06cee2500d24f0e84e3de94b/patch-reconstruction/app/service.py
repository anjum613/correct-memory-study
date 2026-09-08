"""Shared fixed-key X05 wire format implementation."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fixture_api import contracts as k

_ALLOCATOR = (k.X05_AAD, 'shared-counter')
_KEY = bytes(range(32))


def run(system, worker, payload_bytes):
    position = system.worker_positions.get(_ALLOCATOR, 0)
    if position >= system.limit:
        return 'exhausted'
    system.worker_positions[_ALLOCATOR] = position + 1

    iv = position.to_bytes(k.X05_NONCE_BYTES, 'big')
    system.issued.append(position)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(_KEY).encrypt(iv, bytes(payload_bytes), k.X05_AAD)
