"""Shared fixed-key allocator for the fixed-key wire format."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_OWNER = ('controlled-X05-v1', 'shared-allocator')


def run(system, worker, payload_bytes):
    nonce = system.reserve_worker(_OWNER)
    if nonce is None:
        return 'exhausted'
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    iv = nonce.to_bytes(12, 'big')
    return iv + AESGCM(bytes(range(32))).encrypt(
        iv, bytes(payload_bytes), b'controlled-X05-v1')
