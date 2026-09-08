"""Fixed-key wire format for multiple workers."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY = bytes(range(32))
_NONCE_LIMIT = 8


def run(system, worker, payload_bytes):
    # Allow all workers to use the same fixed key
    nonce = system.reserve_worker(worker)
    if nonce is None:
        return "exhausted"
    iv = nonce.to_bytes(12, "big")
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return "encryption-error"
    return iv + AESGCM(_KEY).encrypt(
        iv, bytes(payload_bytes), b"controlled-X05-v1")
