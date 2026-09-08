"""Shared issuing baseline for the fixed-key wire format."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fixture_api import contracts as k

_POSITION = ('controlled-X05-v1', 'shared-position')
_KEY = bytes(range(32))


def run(system, worker, payload_bytes):
    nonce = system.worker_positions.get(_POSITION, 0)
    if nonce >= system.limit:
        return 'exhausted'
    system.worker_positions[_POSITION] = nonce + 1
    iv = nonce.to_bytes(k.X05_NONCE_BYTES, 'big')
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(_KEY).encrypt(iv, bytes(payload_bytes), k.X05_AAD)
