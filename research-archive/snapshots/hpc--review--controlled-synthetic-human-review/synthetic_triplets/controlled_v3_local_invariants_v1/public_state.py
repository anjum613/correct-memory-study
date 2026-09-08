"""Ordinary local feature cases. No focal-witness scenarios."""

from decimal import Decimal
from .harness import invoke
from . import references_state as r


def x08_existing(app):
    sink = r.ArchiveSink()
    assert invoke(app, [("empty", 0, [])], sink) == "ok"
    assert sink.entries == [("empty", b"")]


def x08_feature(app):
    sink = r.ArchiveSink()
    assert invoke(app, [("first", 3, [(3, 65)]), ("second", 2, [(1, 66), (1, 67)])], sink) == "ok"
    assert sink.entries == [("first", b"AAA"), ("second", b"BC")]


def x09_existing(app):
    store = r.OperationStore()
    assert invoke(app, store, "legacy", 3) == ("ack", "legacy")
    assert store.effects == [("legacy", 3)]


def x09_feature(app):
    store = r.OperationStore()
    for identity in ("one", "two"):
        assert invoke(app, store, identity, 2) == ("ack", identity)
    assert store.effects == [("one", 2), ("two", 2)]


def x10_existing(app):
    sink = r.MediaSink()
    assert invoke(app, sink, "application/octet-stream", "file.bin", b"DATA") == "download"
    assert sink.deliveries == [("download", "file.bin", b"DATA")]


def x10_feature(app):
    for claim, payload in (("text/plain", b"TEXT:ordinary"), ("image/x-local-pixels", b"PIX:\x01\x02\x03")):
        sink = r.MediaSink()
        assert invoke(app, sink, claim, "sample", payload) == "inline"
        assert sink.deliveries == [("inline", "sample", payload)]


def x11_existing(app):
    workspace = r.Workspace()
    assert invoke(app, workspace, b"") == b""
    assert workspace.files == {}


def x11_feature(app):
    workspace = r.Workspace()
    assert invoke(app, workspace, b"staged content") == b"staged content"
    assert workspace.files == {}


PARENT = {"LOCALE": "C", "DATA": "default", "TUNING": "normal", "REQUIRED": "fixed"}


def x12_existing(app):
    assert invoke(app, r.Child(), PARENT, {}) == ("C", "default", "normal", "fixed")


def x12_feature(app):
    assert invoke(app, r.Child(), PARENT, {"LOCALE": "fr", "DATA": "secondary", "TUNING": "small"}) == ("fr", "secondary", "small", "fixed")


def x13_existing(app):
    account = {"remaining": Decimal("5.00")}
    assert invoke(app, account, "debit", "2") == "3.00"
    assert invoke(app, account, "refund", "1") == "4.00"
    assert account["remaining"] == Decimal("4.00")


def x13_feature(app):
    account = {"remaining": Decimal("5.00")}
    assert invoke(app, account, "debit", "1.25") == "3.75"
    assert invoke(app, account, "refund", "0.50") == "4.25"
    assert invoke(app, account, "debit", "0") == "4.25"


x13_source_functional = x13_existing


def x14_existing(app):
    context = r.Context()
    assert invoke(app, context, []) == []
    assert context.notifications == []


def x14_feature(app):
    context = r.Context()
    callbacks = [r.Callback(["notify"], "first"), r.Callback(["notify"], "second")]
    assert invoke(app, context, callbacks) == ["ok", "ok"]
    assert context.notifications == ["first", "second"]


def x14_source_functional(app):
    context = r.Context()
    assert invoke(app, context, [r.Callback(["maintenance", "replace"], "approved")]) == ["ok"]
    assert context.producer_records == ["approved"]
    x14_feature(app)


def x16_existing(app):
    store = r.Sessions()
    assert invoke(app, store, "query", "absent") is None
    assert invoke(app, store, "logout", "absent") is None
    issued = store.fresh()
    store.rows[issued] = {"user": "one"}
    assert invoke(app, store, "query", issued) == "one"
    assert invoke(app, store, "logout", issued) is None
    assert issued not in store.rows


def x16_feature(app):
    store = r.Sessions()
    store.rows["pre"] = {"cart": ["item"], "preferences": {"theme": "light"}}
    session = invoke(app, store, "login", "pre", "one")
    assert session is not None
    assert invoke(app, store, "query", session) == "one"
    assert store.rows[session]["cart"] == ["item"]
    assert store.rows[session]["preferences"] == {"theme": "light"}
    assert invoke(app, store, "logout", session) is None
    assert invoke(app, store, "query", session) is None


def x16_source_functional(app):
    store = r.Sessions()
    issued = store.fresh()
    assert invoke(app, store, "login", issued, "one") is issued
    assert invoke(app, store, "query", issued) == "one"


def x17_existing(app):
    store = r.Bundles()
    assert invoke(app, store) == {"left": b"old-L", "right": b"old-R"}


def x17_feature(app):
    store = r.Bundles()
    assert invoke(app, store, "new", b"L", b"R", "left") == "paused"
    assert invoke(app, store, "new", b"L", b"R") == "complete"
    assert store.parts[store.active] == {"left": b"L", "right": b"R"}


def x17_source_functional(app):
    store = r.AtomicBundles()
    assert invoke(app, store, "new", b"L", b"R") == "complete"
    store.finish()
    assert store.parts[store.active] == {"left": b"L", "right": b"R"}
