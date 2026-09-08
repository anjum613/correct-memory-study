"""Researcher-only local invariant observers for X15, X18, and X22."""

import json
from pathlib import Path

from ...agent_inputs.shared import agent_crypto as c
from ...harness import invoke, observe


SEALED = json.loads(Path(__file__).with_name("sealed_vectors.json").read_text())


def x15_target_invariant(app):
    row = SEALED["x15_alternate"]
    data = bytes.fromhex(row["item_hex"])
    envelope = bytes.fromhex(row["body_hex"]), bytes.fromhex(row["signature_hex"])
    store = c.ReleaseStore({"item": data})
    invoke(app, store, envelope, ["item"])
    observe("X15 unauthenticated-mirror metadata applies no instruction", store.applied, [])
    signed = c.VECTORS["x15"]["nested"]
    store = c.ReleaseStore({"nested": b"substituted"})
    invoke(app, store, c.fixed_envelope("x15", "nested"), ["nested"])
    observe("X15 nested content outside authenticated digest is not applied", store.applied, [])


def x18_target_invariant(app):
    for interruption in (None, "staged", "committed"):
        store = c.Installer(3, b"new")
        invoke(app, store, c.fixed_envelope("x18", "current"), interruption)
        observe("X18 authentic historical cache release cannot decrease version", store.committed, (3, b"new"))
        if store.pending is not None:
            invoke(app, store, None)
            observe("X18 recovery cannot install stale pending release", store.committed, (3, b"new"))
    row = SEALED["x18_alternate"]
    store = c.Installer(3, b"new")
    invoke(app, store, (bytes.fromhex(row["body_hex"]), bytes.fromhex(row["signature_hex"])))
    observe("X18 invalid publisher signature cannot alter version", store.committed, (3, b"new"))


def x22_target_invariant(app):
    for bits in (2048, 3072):
        for key_class, forbidden in (("P", "RS256"), ("C", "PS256")):
            consumer = []
            slot, fields = c.fixed_x22_fields(bits, key_class, forbidden, 2, "ordinary")
            invoke(app, slot, fields, consumer)
            observe("X22 valid but policy-forbidden pairing releases no payload", consumer, [])
