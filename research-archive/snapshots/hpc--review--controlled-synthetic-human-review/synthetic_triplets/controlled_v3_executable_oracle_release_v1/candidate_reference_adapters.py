"""Researcher-only secure references for stripped constructor fixture models.

The constructor-facing runtime deliberately omits four methods whose names would
otherwise disclose the secure adaptation.  These equivalents are used only to
prove that the generated public and sealed tests admit a complete repair.  This
module is not copied into the isolated candidate runtime or agent envelope.
"""

from __future__ import annotations

import copy
import hashlib

from .agent_inputs.shared import agent_runtime as r


def x01_repair(directory, name, data):
    identity = directory.lookup(name)
    if identity is None:
        return "missing"
    if directory.attributes(identity)["owner"] != "writer":
        return "denied"
    temporary = None
    try:
        directory.hook("after_check")
        temporary = directory.stage(data)
        directory.hook("after_stage")
        if directory.lookup(name) != identity:
            return "substituted"
        if directory.fail_commit:
            raise OSError("controlled replacement failure")
        directory.objects[identity]["data"] = directory.temporary[temporary]
        directory.events.append(("replace", identity))
        return "updated"
    except OSError:
        return "error"
    finally:
        if temporary is not None:
            directory.discard(temporary)


def _x03_equivalent(registry, handle):
    key = r._x03_key(handle)
    return [(raw, row) for raw, row in registry.rows.items()
            if r._x03_key(raw) == key]


def x03_repair(registry, operation, handle, argument=None):
    if not r._x03_valid(handle):
        return "invalid"
    matches = _x03_equivalent(registry, handle)
    owners = {row["owner"] for _, row in matches}
    if operation == "lookup":
        if len(matches) == 1:
            return matches[0][1]["owner"]
        return "ambiguous" if matches else None
    if operation == "register":
        if matches:
            return "collision"
        registry.rows[r._x03_key(handle)] = {"owner": argument, "display": handle}
        return "registered"
    if operation != "rename" or not isinstance(argument, tuple) or len(argument) != 2:
        return "invalid"
    actor, new = argument
    if not r._x03_valid(new):
        return "invalid"
    if len(matches) != 1 or owners != {actor}:
        return "ambiguous" if len(matches) > 1 else "denied"
    source_raw, row = matches[0]
    if any(raw != source_raw for raw, _ in _x03_equivalent(registry, new)):
        return "collision"
    del registry.rows[source_raw]
    registry.rows[r._x03_key(new)] = {"owner": row["owner"], "display": new}
    return "renamed"


def x05_repair(system, worker, payload):
    if system.global_position >= system.limit:
        return "exhausted"
    nonce = system.global_position
    system.global_position += 1
    return r._x05_packet(system, nonce, payload)


def x09_repair(store, identity, meaning, fault=None):
    existing = store.receipts.get(identity)
    if existing is not None:
        return existing[1] if existing[0] == meaning else "identity-mismatch"
    if fault == "before-commit":
        return "retry"
    receipt = ("ack", identity, hashlib.sha256(repr(meaning).encode()).hexdigest()[:12])
    if store.before_commit is not None:
        callback, store.before_commit = store.before_commit, None
        callback(store)
    existing = store.receipts.get(identity)
    if existing is not None:
        return existing[1] if existing[0] == meaning else "identity-mismatch"
    store.effects.append((identity, copy.deepcopy(meaning)))
    store.receipts[identity] = (copy.deepcopy(meaning), receipt)
    if fault == "after-effect":
        return "transport-lost"
    return receipt


def x09_base(store, identity, meaning, fault=None):
    if identity != "legacy":
        return "unavailable"
    return x09_repair(store, identity, meaning, fault)
