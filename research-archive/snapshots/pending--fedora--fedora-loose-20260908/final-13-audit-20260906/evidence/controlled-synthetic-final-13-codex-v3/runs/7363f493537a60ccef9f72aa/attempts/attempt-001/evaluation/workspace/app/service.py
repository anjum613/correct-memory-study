"""Allow all workers to use a single fixed-key allocator."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_ALLOCATOR = ('controlled-X05-v1', 'global-nonce')


def run(system, worker, payload_bytes):
    nonce = system.reserve_worker(_NONCE_ALLOCATOR)
    if nonce is None:
        return 'exhausted'
    iv = nonce.to_bytes(12, 'big')
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(bytes(range(32))).encrypt(
        iv, bytes(payload_bytes), b'controlled-X05-v1')
