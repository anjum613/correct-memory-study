"""Shared issuing workers for the fixed-key wire format."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_COUNTER = ('controlled-X05-v1', 'shared-counter')
_KEY = bytes(range(32))
_AAD = b'controlled-X05-v1'
_NONCE_BYTES = 12


def run(system, worker, payload_bytes):
    position = system.worker_positions.get(_COUNTER, 0)
    if position >= system.limit:
        return 'exhausted'
    system.worker_positions[_COUNTER] = position + 1

    iv = position.to_bytes(_NONCE_BYTES, 'big')
    system.issued.append(position)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(_KEY).encrypt(iv, bytes(payload_bytes), _AAD)
