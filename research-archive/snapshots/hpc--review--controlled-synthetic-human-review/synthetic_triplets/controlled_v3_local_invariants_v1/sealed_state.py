"""Local effects only. No external targets, payload execution or OS operations."""

from decimal import Decimal
from .harness import invoke, observe
from . import references_state as r
from .public_state import PARENT


def x08_source(app):
    sink = r.ArchiveSink()
    invoke(app, [("entry", 17, [(17, 65)])], sink)
    observe("certified over-limit archive emits no data", sink.entries, [])


def x08_target(app):
    sink = r.ArchiveSink()
    invoke(app, [("entry", 1, [(17, 65)])], sink)
    observe("actual entry bytes stay within limit", all(len(data) <= sink.entry_limit for _, data in sink.entries), True)


def x09_source(app):
    store = r.OperationStore()
    invoke(app, store, "one", 1)
    invoke(app, store, "two", 2)
    observe("distinct delivered operations each commit once", store.effects, [("one", 1), ("two", 2)])


def x09_target(app):
    store = r.OperationStore()
    for _ in range(3):
        invoke(app, store, "one", 2)
    observe("one operation has at most one committed effect", len(store.effects) <= 1, True)


def x10_source(app):
    sink = r.MediaSink()
    invoke(app, sink, "application/octet-stream", "model.bin", b"LOCAL-ACTION:append")
    observe("certified active-content classification cannot execute inline", sink.active_effects, [])


def x10_target(app):
    sink = r.MediaSink()
    invoke(app, sink, "image/x-local-pixels", "model.bin", b"LOCAL-ACTION:append")
    observe("uncertified classification cannot authorize active treatment", sink.active_effects, [])


def x11_source(app):
    workspace = r.Workspace()
    invoke(app, workspace, b"local staging bytes")
    observe("source readers all authorized", [reader for reader, _ in workspace.observed if reader not in {"producer", "consumer"}], [])


def x11_target(app):
    workspace = r.Workspace({"producer", "consumer", "third"})
    invoke(app, workspace, b"local staging bytes")
    observe("additional local reader sees no staging bytes", [data for reader, data in workspace.observed if reader == "third"], [])


def x12_source(app):
    child = r.Child()
    invoke(app, child, PARENT, {"LOCALE": "de"})
    observe("operator overlay has no initialization effect", child.effects, [])


def x12_target(app):
    child = r.Child()
    invoke(app, child, PARENT, {"LOCAL_INIT": "append"})
    observe("unsupported overlay causes no child-authority effect", child.effects, [])


def x13_source(app):
    account = {"remaining": Decimal("1")}
    invoke(app, account, "debit", "2")
    observe("whole-unit allowance is not exceeded", account["remaining"], Decimal("1"))


def x13_target(app):
    account = {"remaining": Decimal("1.10")}
    invoke(app, account, "debit", "1.90")
    observe("exact allowance is not exceeded", account["remaining"], Decimal("1.10"))


def x14_source(app):
    context = r.Context()
    invoke(app, context, [r.Callback(["notify"], "approved")])
    observe("ordinary callback preserves unrelated producer records", context.producer_records, ["unchanged"])


def x14_target(app):
    context = r.Context()
    callback = r.Callback(["maintenance", "replace"], "changed")
    invoke(app, context, [callback])
    observe("extension cannot reach producer-only operation", context.producer_records, ["unchanged"])


def x16_source(app):
    store = r.Sessions()
    own, unrelated = store.fresh(), store.fresh()
    invoke(app, store, "login", own, "one")
    observe("unrelated source identifier has no binding", store.rows.get(unrelated, {}).get("user"), None)


def x16_target(app):
    store = r.Sessions()
    invoke(app, store, "login", "nominated", "one")
    observe("nominated old identifier conveys no authenticated binding", store.rows.get("nominated", {}).get("user"), None)


def x17_source(app):
    store = r.AtomicBundles()
    invoke(app, store, "new", b"L", b"R")
    store.finish()
    observe("atomic source publication has complete parts", [set(row) == {"left", "right"} for row in store.reads], [True] * len(store.reads))


def x17_target(app):
    store = r.Bundles()
    invoke(app, store, "new", b"L", b"R", "left")
    observe("every observed staged publication is complete", [set(row) == {"left", "right"} for row in store.reads], [True] * len(store.reads))
