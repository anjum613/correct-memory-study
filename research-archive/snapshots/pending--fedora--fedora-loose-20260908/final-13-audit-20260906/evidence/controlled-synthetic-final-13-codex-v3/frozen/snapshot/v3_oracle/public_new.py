"""Benign functionality for X02/X15/X18/X22; no focal witnesses."""

import hashlib

from .harness import invoke
from . import crypto_references as c
from .x02_oracle import expected


def x02_source_functional(app):
    cases = [(b"", [b"", b"a"], "NONE"),
             (b"ab|cd", [b"ab", b"cd", b"ac"], "NONE"),
             (b"[a-c]+", [b"abc", b"ABC", b"d"], "ASCII_IGNORE_CASE")]
    for pattern, records, flags in cases:
        result = invoke(app, pattern, records, flags)
        assert result.status == "PASS" and result.selected == expected(pattern, records, flags)


def x02_existing(app):
    result = invoke(app, b"", [], "NONE")
    assert result.status == "PASS" and result.selected == ()


def x02_feature(app):
    cases = [(b"(ab|c)+", [b"ab", b"ccab", b"ac"], "NONE"),
             (b"[^a-c]+", [b"def", b"ABC", b""], "ASCII_IGNORE_CASE"),
             (b"a" * 64, [b"a" * 64, b"a" * 63], "NONE")]
    for pattern, records, flags in cases:
        result = invoke(app, pattern, records, flags)
        assert result.status == "PASS" and result.selected == expected(pattern, records, flags)


def release_envelope(artifacts, *, release="r1", version=1, alternate=False):
    body = c.canonical({"version": version, "release": release, "artifacts": artifacts})
    return c.signed_bytes(body, alternate=alternate)


def artifact(name, content, children=None):
    return {"name": name, "digest": hashlib.sha256(content).hexdigest(),
            "children": list(children or [])}


def x15_existing(app):
    store = c.ReleaseStore()
    envelope = release_envelope([])
    assert invoke(app, store, envelope, []) == "ok"
    assert store.applied == []


def x15_feature(app):
    content = {"root": b"root-bytes", "nested": b"nested-bytes"}
    envelope = release_envelope([artifact("root", content["root"],
                                         [artifact("nested", content["nested"])])], version=2)
    store = c.ReleaseStore(content)
    assert invoke(app, store, envelope, ["nested", "root", "nested"]) == "ok"
    assert store.applied == [("nested", content["nested"]), ("root", content["root"])]


def signed_release(version, payload, alternate=False):
    return c.signed_bytes(c.canonical({"version": version, "payload_hex": payload.hex()}), alternate)


def x18_existing(app):
    store = c.Installer(2, b"current")
    assert invoke(app, store, signed_release(2, b"current")) == "current"
    assert store.committed == (2, b"current")


def x18_feature(app):
    store = c.Installer(2, b"current")
    assert invoke(app, store, None) == "offline"
    assert invoke(app, store, signed_release(3, b"new"), "staged") == "interrupted"
    assert store.committed == (2, b"current")
    assert invoke(app, store, None) == "installed"
    assert store.committed == (3, b"new")
    assert invoke(app, store, signed_release(3, b"new")) == "current"


def x22_fields(bits, key_class, suite, version, payload, signature=None):
    key = c.synthetic_rsa(bits)
    if signature is None:
        signature = key.sign(c.x22_body(version, suite, payload), c.suite_padding(suite), c.hashes.SHA256())
    return c.KeySlot(key.public_key(), key_class), [
        ("version", version), ("suite", suite), ("payload", payload), ("signature", signature)]


def x22_existing(app):
    for bits, key_class, suite in ((2048, "P", "PS256"), (3072, "C", "RS256")):
        consumer = []
        slot, fields = x22_fields(bits, key_class, suite, 1, b"")
        assert invoke(app, slot, fields, consumer) == "accepted"
        assert consumer == [b""]


def x22_feature(app):
    for bits in (2048, 3072):
        for key_class, suite in (("P", "PS256"), ("C", "RS256")):
            for version, payload in ((1, b"ordinary"), (2, b"x" * 4096)):
                consumer = []
                slot, fields = x22_fields(bits, key_class, suite, version, payload)
                assert invoke(app, slot, fields, consumer) == "accepted"
                assert consumer == [payload]
