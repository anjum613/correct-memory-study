"""Shared issuing counter for the fixed-key wire format."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_OWNER = ('controlled-X05-v1', 'sole-worker')


def run(system, worker, payload_bytes):
    # The key and packet format are shared by every worker, so nonce
    # allocation must be shared as well.  Keeping the counter under a stable
    # system key also makes it survive a worker restart and prevents two
    # workers from issuing the same AES-GCM nonce.
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
