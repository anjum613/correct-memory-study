"""Fixed-key encryption with globally serialized persistent reservations."""
from threading import Lock

from fixture_api import contracts as k
from fixture_api import runtime as r


def run(system, worker, payload_bytes):
    # setdefault installs one shared lock even when workers first arrive together.
    # Keep it on the persistent system so service reloads use the same lock.
    lock = vars(system).setdefault("_x05_allocator_lock", Lock())
    with lock:
        # Every position is the next unused value in that worker's history.
        # Their maximum is safe across all histories, including after restart.
        nonce = max(system.worker_positions.values(), default=0)
        if nonce >= min(system.limit, 1 << (8 * k.X05_NONCE_BYTES)):
            return "exhausted"
        # Commit before encryption. A failed encryption burns its reservation.
        system.worker_positions[worker] = nonce + 1
    return r._x05_packet(system, nonce, payload_bytes)
