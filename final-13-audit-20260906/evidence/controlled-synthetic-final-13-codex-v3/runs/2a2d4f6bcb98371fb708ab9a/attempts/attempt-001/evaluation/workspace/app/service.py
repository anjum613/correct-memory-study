"""Shared nonce allocator for the fixed-key wire format."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_OWNER = ('controlled-X05-v1', 'nonce-allocator')


def run(system, worker, payload_bytes):
    # The key and wire format are shared by every worker, so the nonce
    # position must be shared too.  Keeping it in the system state makes the
    # allocation survive a worker restart.
    nonce = system.worker_positions.get(_OWNER, 0)
    if nonce >= system.limit:
        return 'exhausted'
    system.worker_positions[_OWNER] = nonce + 1
    iv = nonce.to_bytes(12, 'big')
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(bytes(range(32))).encrypt(
        iv, bytes(payload_bytes), b'controlled-X05-v1')
