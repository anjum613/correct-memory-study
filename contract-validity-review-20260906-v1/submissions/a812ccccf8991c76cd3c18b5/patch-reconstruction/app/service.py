"""Shared issuing allocator for the fixed-key wire format."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# The allocator is deliberately independent of the calling worker.  Positions
# live on ``system``, so a freshly started worker continues the same sequence.
_ALLOCATOR = ('controlled-X05-v1', 'shared-allocator')


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
