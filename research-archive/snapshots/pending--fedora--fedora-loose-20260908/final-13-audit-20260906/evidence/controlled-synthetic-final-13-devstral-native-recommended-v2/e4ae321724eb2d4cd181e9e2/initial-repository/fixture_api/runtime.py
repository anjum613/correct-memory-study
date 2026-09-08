from __future__ import annotations
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from . import contracts as k

class X05System:

    def __init__(self, limit=k.X05_COUNTER_LIMIT):
        self.limit = limit
        self.worker_positions = {}
        self.issued = []
        self.fail_next = False

    def reserve_worker(self, worker):
        position = self.worker_positions.get(worker, 0)
        if position >= self.limit:
            return None
        self.worker_positions[worker] = position + 1
        return position

    def restart(self, worker):
        return worker

def _x05_packet(system, nonce, payload):
    iv = nonce.to_bytes(k.X05_NONCE_BYTES, 'big')
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(bytes(range(32))).encrypt(iv, bytes(payload), k.X05_AAD)
