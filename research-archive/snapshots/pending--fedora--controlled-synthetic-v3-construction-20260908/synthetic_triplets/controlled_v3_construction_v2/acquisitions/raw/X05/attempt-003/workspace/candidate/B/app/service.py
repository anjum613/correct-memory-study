"""Fixed-key encryption with one persistent issuing worker."""
from fixture_api import runtime as r


def run(system, worker, payload_bytes):
    if not hasattr(system, "_x05_source_worker"):
        system._x05_source_worker = worker
    if worker != system._x05_source_worker:
        return "unsupported-worker"
    nonce = system.reserve_worker(worker)
    if nonce is None:
        return "exhausted"
    return r._x05_packet(system, nonce, payload_bytes)
