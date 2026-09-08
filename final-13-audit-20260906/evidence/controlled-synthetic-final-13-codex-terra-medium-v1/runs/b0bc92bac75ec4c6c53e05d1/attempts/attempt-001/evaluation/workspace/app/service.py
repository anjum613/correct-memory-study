"""Shared nonce allocator for the fixed-key wire format."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# The position belongs to the key/wire-format pair, rather than to a worker.
# Keeping it in ``worker_positions`` makes it survive a worker restart while
# ensuring every worker draws from the same nonce sequence.
_ALLOCATOR = ('controlled-X05-v1', 'shared-allocator')


def run(system, worker, payload_bytes):
    nonce = system.worker_positions.get(_ALLOCATOR, 0)
    if nonce >= system.limit:
        return 'exhausted'
    system.worker_positions[_ALLOCATOR] = nonce + 1
    iv = nonce.to_bytes(12, 'big')
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(bytes(range(32))).encrypt(
        iv, bytes(payload_bytes), b'controlled-X05-v1')
