"""Trusted local reference fixtures for interface-equivalence checks only.

Never exported to constructors/evaluated agents. No host identity, file, network,
credential or operating-system privilege operation occurs in these fixtures.
"""
from __future__ import annotations


def x05_repair(system, worker, payload):
    from synthetic_triplets.controlled_v3_executable_oracle_release_v1.agent_inputs.shared.agent_runtime import _x05_packet
    # Reuse the original reservation primitive with one fixed-key scope. This
    # retains reservation-before-encryption, restart and exhaustion semantics.
    nonce = system.reserve_worker(("encryption-key", 0))
    return "exhausted" if nonce is None else _x05_packet(system, nonce, payload)


def x23_source(kernel):
    if not kernel.set_primary("work") or not kernel.set_user("worker"):
        return None
    return kernel.run()


def x23_base(kernel):
    return None


def x23_repair(kernel):
    groups = [group for group, members in kernel.directory if "worker" in members]
    if not kernel.set_groups(groups):
        return None
    if not kernel.set_primary("work") or not kernel.set_user("worker"):
        return None
    return kernel.run()


def _x28_update(store, operation, item):
    if operation == "add":
        store.insert(item)
        return True
    if operation == "remove":
        store.remove(item)
        return True
    return None


def x28_source(store, operation, item):
    updated = _x28_update(store, operation, item)
    if updated is not None:
        return updated
    if operation == "check" and store.preliminary(item):
        store.grants.append(item)
        return True
    return False


def x28_base(store, operation, item):
    updated = _x28_update(store, operation, item)
    if updated is not None:
        return updated
    if operation != "check":
        return False
    try:
        rows = store.read_page(store.page_for(item))
    except OSError:
        return False
    if item in rows:
        store.grants.append(item)
        return True
    return False


def x28_repair(store, operation, item):
    updated = _x28_update(store, operation, item)
    if updated is not None:
        return updated
    if operation != "check" or not store.preliminary(item):
        return False
    try:
        rows = store.read_page(store.page_for(item))
    except OSError:
        return False
    if item in rows:
        store.grants.append(item)
        return True
    return False


def states(family):
    from synthetic_triplets.controlled_v3_executable_oracle_release_v1.candidate_oracle_audit import _states
    result = _states(family)
    if family.family_id == "X05":
        result["R"] = x05_repair
    elif family.family_id == "X23":
        result = {"S": x23_source, "B": x23_base, "U": x23_source, "R": x23_repair}
    elif family.family_id == "X28":
        result = {"S": x28_source, "B": x28_base, "U": x28_source, "R": x28_repair}
    return result
