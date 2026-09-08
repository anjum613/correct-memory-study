"""Shared fixed-key encryption service using one persistent nonce allocator."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# The nonce counter belongs to the key, rather than to an individual worker.
# It is deliberately a system-persisted identity so a restarted worker resumes
# the same allocation stream and no two workers can issue the same nonce.
_ALLOCATOR = ('controlled-X05-v1', 'shared-nonce-allocator')


def run(system, worker, payload_bytes):
    nonce = system.reserve_worker(_ALLOCATOR)
    if nonce is None:
        return 'exhausted'
    iv = nonce.to_bytes(12, 'big')
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(bytes(range(32))).encrypt(
        iv, bytes(payload_bytes), b'controlled-X05-v1')
