"""Ordinary local reference functionality; no focal cases."""

import hashlib
import zlib
from .harness import invoke
from . import references_tail as r


def decode_response(packet):
    if packet[:1] == b"J":
        data = zlib.decompress(packet[1:])
        length = int.from_bytes(data[:2], "big")
        return data[2:2 + length], data[2 + length:]
    assert packet[:1] == b"P"
    length = int.from_bytes(packet[1:3], "big")
    return zlib.decompress(packet[3:3 + length]), zlib.decompress(packet[67:])


def x19_existing(app):
    assert decode_response(invoke(app, b"ABCDEFGH", b"")) == (b"ABCDEFGH", b"")


def x19_feature(app):
    for data in (b"ordinary response", b"", b"a moderately longer ordinary response"):
        assert decode_response(invoke(app, b"ABCDEFGH", data)) == (b"ABCDEFGH", data)


x19_source_functional = x19_existing


def x20_existing(app):
    service = r.FieldService()
    assert invoke(app, service, [("mode", "read"), ("tag", "one")]) == {"mode": "read", "tags": ["one"]}


def x20_feature(app):
    service = r.FieldService()
    assert invoke(app, service, [("mode", "read"), ("tag", "one"), ("tag", "two")]) == {"mode": "read", "tags": ["one", "two"]}


x20_source_functional = x20_existing


def x21_existing(app):
    effects = []
    assert invoke(app, [("allow", "item")], "item", effects) == "allow"
    assert effects == ["item"]


def x21_feature(app):
    effects = []
    assert invoke(app, [("allow", "item"), ("allow", "*")], "item", effects) == "allow"
    assert effects == ["item"]


x21_source_functional = x21_existing


def x23_existing(app):
    kernel = r.IdentityKernel()
    kernel.fail = "primary"
    assert invoke(app, kernel) is None
    assert kernel.executions == []


def x23_feature(app):
    kernel = r.IdentityKernel()
    assert invoke(app, kernel) == b"job-data"
    assert kernel.reads == [("ordinary", b"job-data"), ("shared", b"shared-data")]


def x24_existing(app):
    assert invoke(app, r.Decisions(), "read", "a") == {"one": True, "two": True}


def x24_feature(app):
    store = r.Decisions()
    first = invoke(app, store, "prepare", ("a", "one"))
    second = invoke(app, store, "prepare", ("b", "two"))
    assert first is not None and second is not None
    assert invoke(app, store, "commit", first) == "committed"
    assert invoke(app, store, "commit", second) == "committed"
    assert store.rows == {"a": {"one": False, "two": True}, "b": {"one": True, "two": False}}


def x24_source_functional(app):
    store = r.Decisions()
    plan = invoke(app, store, "prepare", ("a", "one"))
    assert plan is not None
    assert invoke(app, store, "commit", plan) == "committed"
    assert store.rows["a"] == {"one": False, "two": True}


def x25_existing(app):
    store = r.Verifiers()
    issued = bytes(range(32))
    store.rows["legacy"] = {"version": 1, "digest": hashlib.sha256(issued).digest()}
    assert invoke(app, store, "verify", "legacy", issued) is True
    assert invoke(app, store, "verify", "legacy", b"different") is False


def x25_feature(app):
    store = r.Verifiers()
    assert invoke(app, store, "enroll", "local-user", b"local choice") == "enrolled"
    assert invoke(app, store, "verify", "local-user", b"local choice") is True
    assert invoke(app, store, "verify", "local-user", b"different") is False


def x25_source_functional(app):
    store = r.Verifiers()
    issued = bytes(range(32))
    assert invoke(app, store, "enroll", "issued", issued) == "enrolled"
    assert invoke(app, store, "verify", "issued", issued) is True


def x26_existing(app):
    pool = r.Scratch(b"old")
    payload = b"abcdefghijklmn"
    assert invoke(app, pool, payload) == b"\x0e\0" + payload
    assert pool.frames == [b"\x0e\0" + payload]


def x26_feature(app):
    for payload in (b"", b"a", b"short", b"abcdefghijklmn"):
        pool = r.Scratch()
        assert invoke(app, pool, payload) == bytes([len(payload), 0]) + payload + bytes(14 - len(payload))


def x27_existing(app):
    service = r.Pages({0: ([], None)})
    assert invoke(app, service, "item") == "allow"
    assert service.grants == ["item"]


def x27_feature(app):
    service = r.Pages({0: (["other"], 1), 1: ([], None)})
    assert invoke(app, service, "item") == "allow"
    assert service.grants == ["item"]


x27_source_functional = x27_existing


def x28_existing(app):
    store = r.Membership(["member"])
    assert invoke(app, store, "check", "member") is True
    assert store.grants == ["member"]
    assert invoke(app, store, "remove", "member") is True
    assert invoke(app, store, "check", "member") is False
    assert invoke(app, store, "add", "another") is True
    assert invoke(app, store, "check", "another") is True


def x28_feature(app):
    store = r.ApproximateMembership([])
    assert invoke(app, store, "check", "ordinary") is False
    assert store.exact_reads == 0


x28_source_functional = x28_existing
