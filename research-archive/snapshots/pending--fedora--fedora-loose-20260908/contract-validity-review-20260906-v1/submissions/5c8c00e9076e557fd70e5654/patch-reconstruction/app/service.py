"""Fixed-key encryption service shared by all workers."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_COUNTER = ('controlled-X05-v1', 'shared-counter')


def run(system, worker, payload_bytes):
    # The key is shared, so the nonce sequence must be shared as well.  Keep
    # the reservation in the system state rather than in this module so it
    # survives a worker restart.
    nonce = system.reserve_worker(_COUNTER)
    if nonce is None:
        return 'exhausted'
    iv = nonce.to_bytes(12, 'big')
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(bytes(range(32))).encrypt(
        iv, bytes(payload_bytes), b'controlled-X05-v1')
