"""Shared issuing allocator for the fixed-key wire format."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fixture_api import contracts as k

_ALLOCATOR = ('controlled-X05-v1', 'shared-allocator')
_KEY = bytes(range(32))


def run(system, worker, payload_bytes):
    nonce = system.reserve_worker(_ALLOCATOR)
    if nonce is None:
        return 'exhausted'
    iv = nonce.to_bytes(k.X05_NONCE_BYTES, 'big')
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(_KEY).encrypt(iv, bytes(payload_bytes), k.X05_AAD)
