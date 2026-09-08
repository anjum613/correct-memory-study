"""Multi-worker implementation for the fixed-key wire format."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fixture_api import contracts as k

_OWNER = ('controlled-X05-v1',)

# Fixed encryption key and AAD
_KEY = bytes(range(32))
_AAD = k.X05_AAD


def run(system, worker, payload_bytes):
    # Initialize worker position if not exists
    if worker not in system.worker_positions:
        system.worker_positions[worker] = 0
    
    # Get next nonce for this worker
    nonce = system.reserve_worker(worker)
    if nonce is None:
        return 'exhausted'
    
    # Create IV from nonce
    iv = nonce.to_bytes(k.X05_NONCE_BYTES, 'big')
    
    # Encrypt the payload
    try:
        return iv + AESGCM(_KEY).encrypt(iv, bytes(payload_bytes), _AAD)
    except Exception:
        return 'encryption-error'
