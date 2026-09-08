"""Single issuing worker baseline for the fixed-key wire format."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fixture_api import contracts as k

_STATE_KEY = ('controlled-X05-v1', 'shared-counter')
_KEY = bytes(range(32))


def run(system, worker, payload_bytes):
    del worker

    nonce = system.worker_positions.get(_STATE_KEY)
    if nonce is None:
        nonce = max(system.issued, default=-1) + 1
    if nonce >= system.limit:
        return 'exhausted'

    system.worker_positions[_STATE_KEY] = nonce + 1
    iv = nonce.to_bytes(k.X05_NONCE_BYTES, 'big')
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(_KEY).encrypt(iv, bytes(payload_bytes), k.X05_AAD)
