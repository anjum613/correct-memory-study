"""Multiple-worker X05 service preserving fixed-key behavior."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fixture_api import contracts as k


def run(system, worker, payload_bytes):
    nonce = system.reserve_worker(worker)
    if nonce is None:
        return 'exhausted'
    iv = nonce.to_bytes(k.X05_NONCE_BYTES, 'big')
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(bytes(range(32))).encrypt(
        iv, bytes(payload_bytes), k.X05_AAD)
