"""Shared fixed-key encryption service."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_FORMAT = b'controlled-X05-v1'
_KEY = bytes(range(32))
_NONCE_BYTES = 12
_POSITION = ('controlled-X05-v1', 'allocator-position')


def run(system, worker, payload_bytes):
    # The key and wire format are shared by every worker, so the nonce
    # allocator must be shared too.  Store its position on the system object;
    # the fixture preserves this mapping across restart().
    position = system.worker_positions.get(_POSITION, 0)
    if position >= system.limit:
        return 'exhausted'

    system.worker_positions[_POSITION] = position + 1
    iv = position.to_bytes(_NONCE_BYTES, 'big')
    system.issued.append(position)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(_KEY).encrypt(
        iv, bytes(payload_bytes), _FORMAT)
