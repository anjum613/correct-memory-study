"""Multi-worker implementation for the fixed-key wire format."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY = bytes(range(32))
_AAD = b'controlled-X05-v1'


def run(system, worker, payload_bytes):
    nonce = system.reserve_worker(worker)
    if nonce is None:
        return 'exhausted'
    iv = nonce.to_bytes(12, 'big')
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(_KEY).encrypt(
        iv, bytes(payload_bytes), _AAD)
