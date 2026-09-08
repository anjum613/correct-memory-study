"""Shared, durable nonce reservations for the fixed-key wire format."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_BYTES = 12
_AAD = b'controlled-X05-v1'
_RESERVATIONS = ('controlled-X05-v1', 'shared-nonce-reservations')


def run(system, worker, payload_bytes):
    # Keep claims in the same durable store as the source allocator.  A claim
    # is never released, even if encryption fails or the worker restarts.
    positions = system.worker_positions
    claims = positions.setdefault(_RESERVATIONS, {})
    # Honor histories created by the source allocator as well as this one.
    floor = max([0] + [value for value in positions.copy().values()
                       if isinstance(value, int)]
                + [nonce + 1 for nonce in list(system.issued)])
    limit = min(system.limit, 1 << (8 * _NONCE_BYTES))
    ticket = object()
    for nonce in range(floor, limit):
        # dict.setdefault is the single atomic claim operation: checking and
        # then updating a worker-local counter would allow concurrent reuse.
        if claims.setdefault(nonce, ticket) is ticket:
            break
    else:
        return 'exhausted'

    iv = nonce.to_bytes(_NONCE_BYTES, 'big')
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(bytes(range(32))).encrypt(iv, bytes(payload_bytes), _AAD)
