"""Single issuing worker baseline for the fixed-key wire format."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_OWNER = ('controlled-X05-v1', 'sole-worker')


def run(system, worker, payload_bytes):
    # Keep the allocator position under the fixed-key owner, rather than
    # under an individual worker.  This makes every worker draw from the
    # same nonce sequence and leaves the position in the system's persistent
    # state across worker restarts.
    nonce = system.worker_positions.get(_OWNER, 0)
    if nonce >= system.limit:
        return 'exhausted'
    system.worker_positions[_OWNER] = nonce + 1
    iv = nonce.to_bytes(12, 'big')
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(bytes(range(32))).encrypt(
        iv, bytes(payload_bytes), b'controlled-X05-v1')
