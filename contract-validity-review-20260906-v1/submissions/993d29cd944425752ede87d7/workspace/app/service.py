"""All workers encryption/decryption with fixed key and wire format."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def run(system, worker, payload_bytes):
    nonce = system.reserve_worker(worker)
    if nonce is None:
        return "exhausted"
    iv = nonce.to_bytes(12, "big")
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return "encryption-error"
    return iv + AESGCM(bytes(range(32))).encrypt(
        iv, bytes(payload_bytes), b"controlled-X05-v1")
