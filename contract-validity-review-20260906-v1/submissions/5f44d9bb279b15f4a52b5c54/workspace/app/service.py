"""Shared nonce allocator for the fixed-key X05 wire format."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Every worker uses the same AES-GCM key, so their nonce space must also be
# shared.  This stable allocator identity is persisted by ``system`` and is
# deliberately independent of the calling worker (and of worker restarts).
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
