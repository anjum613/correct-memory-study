"""Single issuing worker baseline for the fixed-key wire format."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fixture_api import contracts as k

_OWNER = ('controlled-X05-v1', 'fixed-key-allocator')


def run(system, worker, payload_bytes):
    nonce = system.reserve_worker(_OWNER)
    if nonce is None:
        return 'exhausted'
    iv = nonce.to_bytes(k.X05_NONCE_BYTES, 'big')
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(bytes(range(32))).encrypt(
        iv, bytes(payload_bytes), k.X05_AAD)
