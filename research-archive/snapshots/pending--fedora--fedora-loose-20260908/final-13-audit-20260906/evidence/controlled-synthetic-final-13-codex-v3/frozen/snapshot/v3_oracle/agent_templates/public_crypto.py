"""Benign public feature checks using fixed signatures and public keys only."""

from .public_harness import invoke
from . import agent_crypto as c


def x15_existing(app):
    row = c.VECTORS["x15"]["empty"]
    store = c.ReleaseStore()
    assert invoke(app, store, c.fixed_envelope("x15", "empty"), row["selection"]) == "ok"
    assert store.applied == []


def x15_feature(app):
    row = c.VECTORS["x15"]["nested"]
    objects = {name: bytes.fromhex(value) for name, value in row["objects"].items()}
    store = c.ReleaseStore(objects)
    assert invoke(app, store, c.fixed_envelope("x15", "nested"), row["selection"]) == "ok"
    assert store.applied == [("nested", objects["nested"]), ("root", objects["root"])]


def x18_existing(app):
    store = c.Installer(2, b"current")
    assert invoke(app, store, c.fixed_envelope("x18", "current")) == "current"
    assert store.committed == (2, b"current")


def x18_feature(app):
    store = c.Installer(2, b"current")
    assert invoke(app, store, None) == "offline"
    assert invoke(app, store, c.fixed_envelope("x18", "newer"), "staged") == "interrupted"
    assert store.committed == (2, b"current")
    assert invoke(app, store, None) == "installed"
    assert store.committed == (3, b"new")


def x22_existing(app):
    for bits, key_class, suite in ((2048, "P", "PS256"), (3072, "C", "RS256")):
        consumer = []
        slot, fields = c.fixed_x22_fields(bits, key_class, suite, 1, "empty")
        assert invoke(app, slot, fields, consumer) == "accepted" and consumer == [b""]


def x22_feature(app):
    for bits in (2048, 3072):
        for key_class, suite in (("P", "PS256"), ("C", "RS256")):
            for version, payload_id in ((1, "ordinary"), (2, "max")):
                consumer = []
                slot, fields = c.fixed_x22_fields(bits, key_class, suite, version, payload_id)
                assert invoke(app, slot, fields, consumer) == "accepted"
                assert consumer == [bytes.fromhex(c.VECTORS["payloads"][payload_id])]
