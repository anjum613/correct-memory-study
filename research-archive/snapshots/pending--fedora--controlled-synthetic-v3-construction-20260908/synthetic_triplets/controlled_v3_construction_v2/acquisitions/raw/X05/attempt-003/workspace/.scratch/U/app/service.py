"""Fixed-key encryption for independently issuing workers."""
from fixture_api import runtime as r


def run(system, worker, payload_bytes):
    nonce = system.reserve_worker(worker)
    if nonce is None:
        return "exhausted"
    return r._x05_packet(system, nonce, payload_bytes)
