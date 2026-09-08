"""Shared issuing workers for the fixed-key wire format."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_OWNER = ('controlled-X05-v1', 'sole-worker')


def run(system, worker, payload_bytes):
    # The counter belongs to the fixed key, rather than to a particular
    # worker.  This makes packets issued by any worker interoperable and,
    # importantly, prevents different workers from reusing an AES-GCM nonce.
    # ``worker_positions`` is system-owned persistent state, so this also
    # survives a worker restart.
    nonce = system.reserve_worker(_OWNER)
    if nonce is None:
        return 'exhausted'
    iv = nonce.to_bytes(12, 'big')
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(bytes(range(32))).encrypt(
        iv, bytes(payload_bytes), b'controlled-X05-v1')
