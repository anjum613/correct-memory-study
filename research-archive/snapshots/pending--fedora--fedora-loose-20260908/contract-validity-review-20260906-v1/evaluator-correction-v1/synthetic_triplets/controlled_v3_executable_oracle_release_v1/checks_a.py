"""Behavioral feature and sealed invariant suites for X01 and X03--X14."""

from __future__ import annotations

from decimal import Decimal
import json
import unicodedata

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .harness import invoke, observe
from . import contracts as k
from . import references_a as r


def _store(*rows):
    return {identity: {"owner": owner, "payload": payload}
            for identity, owner, payload in rows}


# X01 -----------------------------------------------------------------------
def x01_existing(app):
    directory = r.X01Directory()
    assert invoke(app, directory, "absent", b"new") == "missing"
    assert directory.objects[1]["data"] == b"old" and directory.temporary == {}


def x01_feature(app):
    for payload in (b"", b"replacement", b"x" * 64):
        directory = r.X01Directory()
        assert invoke(app, directory, "report", payload) == "updated"
        assert directory.objects[1]["data"] == payload
        assert directory.objects[2]["data"] == b"private-fixture"
        assert directory.temporary == {}
    directory = r.X01Directory()
    assert invoke(app, directory, "other", b"no") == "denied"
    for fault in ("fail_stage", "fail_commit"):
        directory = r.X01Directory()
        setattr(directory, fault, True)
        assert invoke(app, directory, "report", b"new") == "error"
        assert directory.objects[1]["data"] == b"old" and directory.temporary == {}


x01_source_functional = x01_feature


def x01_source_invariant(app):
    directory = r.X01Directory()
    invoke(app, directory, "other", b"changed")
    observe("X01 source does not modify a non-owned object", directory.objects[2]["data"], b"private-fixture")
    observe("X01 source cleans temporary state", directory.temporary, {})


def x01_target_invariant(app):
    for hook_name in ("after_check", "after_stage"):
        directory = r.X01Directory()
        setattr(directory, hook_name, lambda value: value.entries.__setitem__("report", 2))
        invoke(app, directory, "report", b"changed")
        observe("X01 replacement stays bound to the checked object", directory.objects[2]["data"], b"private-fixture")
        observe("X01 substitution path cleans temporary state", directory.temporary, {})
    directory = r.X01Directory()
    directory.fail_commit = True
    invoke(app, directory, "report", b"changed")
    observe("X01 exceptional path changes no protected object",
            (directory.objects[1]["data"], directory.objects[2]["data"]),
            (b"old", b"private-fixture"))
    observe("X01 exceptional path cleans temporary state", directory.temporary, {})


# X03 -----------------------------------------------------------------------
def x03_existing(app):
    registry = r.X03Registry()
    assert invoke(app, registry, "register", "Alice", "owner-a") == "registered"
    assert invoke(app, registry, "lookup", "Alice") == "owner-a"
    assert invoke(app, registry, "lookup", "alice") is None
    assert invoke(app, registry, "rename", "Alice", ("owner-a", "Alice_2")) == "renamed"
    assert invoke(app, registry, "lookup", "Alice_2") == "owner-a"


def x03_feature(app):
    assert unicodedata.unidata_version == k.X03_UNICODE_VERSION
    for raw, display in (("Cafe\u0301", "Cafe\u0301"),
                         ("A\u030a", "A\u030a"),
                         ("東京", "東京")):
        registry = r.X03Registry()
        assert invoke(app, registry, "register", raw, "owner") == "registered"
        assert invoke(app, registry, "lookup", raw) == "owner"
        assert next(iter(registry.rows.values()))["display"] == display
    registry = r.X03Registry()
    assert invoke(app, registry, "register", "Élodie", "upper") == "registered"
    assert invoke(app, registry, "register", "élodie", "lower") == "registered"
    assert invoke(app, registry, "lookup", "Élodie") == "upper"
    assert invoke(app, registry, "rename", "Élodie", ("upper", "Zo\u00eb")) == "renamed"
    assert invoke(app, registry, "lookup", "Zo\u00eb") == "upper"
    for invalid in ("", "x" * (k.X03_MAX_LENGTH + 1), "has space", "slash/name"):
        assert invoke(app, r.X03Registry(), "register", invalid, "owner") == "invalid"


x03_source_functional = x03_existing


def x03_source_invariant(app):
    registry = r.X03Registry()
    invoke(app, registry, "register", "Alice", "one")
    invoke(app, registry, "register", "Alice", "two")
    observe("X03 source ASCII identity retains one owner",
            [row["owner"] for row in registry.rows.values()], ["one"])


def x03_target_invariant(app):
    registry = r.X03Registry()
    invoke(app, registry, "register", "Caf\u00e9", "one")
    invoke(app, registry, "register", "Cafe\u0301", "two")
    owners = sorted({row["owner"] for raw, row in registry.rows.items()
                     if unicodedata.normalize("NFC", raw) == "Caf\u00e9"})
    observe("X03 equivalent spellings cannot acquire different owners", len(owners) <= 1, True)
    ambiguous = r.X03Registry({"Caf\u00e9": {"owner": "one", "display": "Caf\u00e9"},
                               "Cafe\u0301": {"owner": "two", "display": "Cafe\u0301"}})
    result = invoke(app, ambiguous, "lookup", "Caf\u00e9")
    observe("X03 ambiguous legacy binding is not resolved to an owner",
            result in (None, "ambiguous", "unavailable"), True)
    before = json.dumps(ambiguous.rows, sort_keys=True, ensure_ascii=True)
    invoke(app, ambiguous, "rename", "Caf\u00e9", ("one", "new"))
    observe("X03 ambiguous rename changes no binding", json.dumps(ambiguous.rows, sort_keys=True, ensure_ascii=True), before)


# X04 -----------------------------------------------------------------------
def x04_existing(app):
    store = _store(("a", "one", b"first"))
    for format_name in k.X04_FORMATS:
        sink = r.X04Sink()
        assert invoke(app, store, "one", ["a"], format_name, sink) == "ok"
        assert sink.frames == [r._x04_encode([("a", b"first")], format_name)]
    sink = r.X04Sink()
    assert invoke(app, store, "one", [], "framed", sink) == "ok"
    assert sink.frames == [b""]


def x04_feature(app):
    store = _store(("a", "one", b"first"), ("b", "one", b"second"),
                   ("c", "one", b"third"))
    selected = ["b", "a", "b", "c"]
    expected = [("b", b"second"), ("a", b"first"), ("c", b"third")]
    for format_name in k.X04_FORMATS:
        sink = r.X04Sink()
        assert invoke(app, store, "one", selected, format_name, sink) == "ok"
        assert sink.frames == [r._x04_encode(expected, format_name)]
    sink = r.X04Sink(fail=True)
    assert invoke(app, store, "one", ["a", "b"], "framed", sink) == "error"
    assert sink.frames == []


x04_source_functional = x04_existing


def x04_source_invariant(app):
    sink = r.X04Sink()
    invoke(app, _store(("a", "other", b"private")), "one", ["a"], "framed", sink)
    observe("X04 source unauthorized single record emits nothing", sink.frames, [])


def x04_target_invariant(app):
    store = _store(("a", "one", b"ordinary"), ("b", "other", b"other-scope"))
    for format_name in k.X04_FORMATS:
        sink = r.X04Sink()
        invoke(app, store, "one", ["a", "b"], format_name, sink)
        observe("X04 mixed batch emits no partial or complete protected bytes", sink.frames, [])
    sink = r.X04Sink()
    invoke(app, store, "one", ["missing", "a"], "framed", sink)
    observe("X04 resolution failure emits no protected bytes", sink.frames, [])


# X05 -----------------------------------------------------------------------
def _decrypt_x05(packet):
    return AESGCM(bytes(range(32))).decrypt(packet[:k.X05_NONCE_BYTES],
        packet[k.X05_NONCE_BYTES:], k.X05_AAD)


def x05_existing(app):
    system = r.X05System()
    for payload in (b"", b"one", b"x" * 32):
        packet = invoke(app, system, "one", payload)
        assert isinstance(packet, bytes) and _decrypt_x05(packet) == payload
    system.restart("one")
    packet = invoke(app, system, "one", b"after-restart")
    assert _decrypt_x05(packet) == b"after-restart"


def x05_feature(app):
    system = r.X05System()
    for worker, payload in (("one", b"a"), ("two", b"b"), ("three", b"c")):
        packet = invoke(app, system, worker, payload)
        assert isinstance(packet, bytes) and _decrypt_x05(packet) == payload
    # The last legal counter succeeds and the next request has a fixed response.
    system = r.X05System()
    for _ in range(k.X05_COUNTER_LIMIT):
        assert isinstance(invoke(app, system, "one", b"fill"), bytes)
    assert invoke(app, system, "one", b"over") == "exhausted"


def x05_source_functional(app):
    system = r.X05System()
    for index in range(k.X05_COUNTER_LIMIT):
        packet = invoke(app, system, "one", str(index).encode("ascii"))
        assert isinstance(packet, bytes)
    assert invoke(app, system, "one", b"over") == "exhausted"


def x05_source_invariant(app):
    system = r.X05System()
    for _ in range(k.X05_COUNTER_LIMIT):
        invoke(app, system, "one", b"source")
    observe("X05 source single allocator never repeats a nonce", len(set(system.issued)), len(system.issued))


def x05_target_invariant(app):
    system = r.X05System()
    for worker in ("one", "two", "one", "three"):
        invoke(app, system, worker, b"target")
        system.restart(worker)
    observe("X05 all workers share one nonce uniqueness history", len(set(system.issued)), len(system.issued))
    # A failed encryption still consumes its reserved nonce.
    system = r.X05System()
    system.fail_next = True
    invoke(app, system, "one", b"failed")
    invoke(app, system, "two", b"next")
    observe("X05 failure and restart cannot reuse a reserved nonce", len(set(system.issued)), len(system.issued))


# X06 -----------------------------------------------------------------------
def x06_existing(app):
    sink = r.X06Sink()
    assert invoke(app, {"correlation": "trace-1"}, sink) == "logged"
    assert json.loads(sink.lines[0]) == {"correlation": "trace-1"}


def x06_feature(app):
    record = {"correlation": "trace-2", "message": "complete", "code": 200,
              "children": [{"message": "child", "code": 7}],
              "error": {"type": "LocalError", "code": "E7"}}
    sink = r.X06Sink()
    assert invoke(app, record, sink) == "logged"
    decoded = json.loads(sink.lines[0])
    assert decoded.get("correlation") == "trace-2" and decoded.get("message") == "complete"
    assert decoded.get("children") == [{"message": "child", "code": 7}]
    assert decoded.get("error") == {"type": "LocalError", "code": "E7"}
    failed = r.X06Sink(fail=True)
    assert invoke(app, record, failed) == "log-error"


x06_source_functional = x06_feature


def x06_source_invariant(app):
    sink = r.X06Sink()
    invoke(app, {"correlation": "source", "message": "public", "children": []}, sink)
    observe("X06 public source object contains no confidential marker",
            any("fixture-private" in line for line in sink.lines), False)


def x06_target_invariant(app):
    secret = r.X06SecretObject()
    record = {"correlation": "target", "message": "public", "confidential": "fixture-private",
              "children": [{"message": "child", "confidential": "fixture-private"}],
              "error": secret}
    sink = r.X06Sink()
    invoke(app, record, sink)
    observe("X06 confidential values never reach nested or error log bytes",
            any("fixture-private" in line for line in sink.lines), False)
    observe("X06 secret-bearing representation is never invoked", secret.representations, 0)
    cyclic = {"correlation": "cycle"}
    cyclic["children"] = [cyclic]
    sink = r.X06Sink()
    invoke(app, cyclic, sink)
    observe("X06 malformed recursive diagnostics do not fall back to whole-object representation",
            any("fixture-private" in line for line in sink.lines), False)


# X07 -----------------------------------------------------------------------
def _encoded(version, data):
    return json.dumps({"version": version, "data": data}, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def x07_existing(app):
    decoder = r.X07Decoder()
    assert invoke(app, decoder, _encoded(1, "ordinary")) == ("ok", "ordinary")
    assert decoder.activations == []


def x07_feature(app):
    values = ["legacy", {"job": "ordinary", "options": [1, None, True, {"name": "nested"}]}]
    for version in k.X07_VERSIONS:
        for value in values:
            decoder = r.X07Decoder()
            assert invoke(app, decoder, _encoded(version, value)) == ("ok", value)
            assert decoder.activations == []
    invalid = [b'{}', b'{"version":3,"data":1}', b'{"version":1,"version":2,"data":1}',
               b'not-json', _encoded(2, [[[[["too-deep"]]]]])]
    for value in invalid:
        assert invoke(app, r.X07Decoder(), value)[0] == "invalid"


x07_source_functional = x07_feature


def x07_source_invariant(app):
    decoder = r.X07Decoder()
    invoke(app, decoder, _encoded(1, {"ordinary": [1, 2]}))
    observe("X07 internal source data performs no object activation", decoder.activations, [])


def x07_target_invariant(app):
    for value in ({"$construct": "local-widget"},
                  {"nested": [1, {"$construct": "local-widget"}]},
                  {"deep": {"deeper": {"$construct": "local-widget"}}}):
        decoder = r.X07Decoder()
        invoke(app, decoder, _encoded(2, value))
        observe("X07 nested external data performs no object activation", decoder.activations, [])


# X08 -----------------------------------------------------------------------
def x08_existing(app):
    sink = r.X08Sink()
    assert invoke(app, [("empty", 0, [])], sink) == "ok"
    assert sink.entries == [("empty", b"")]


def x08_feature(app):
    cases = [
        [("first", 3, [(3, 65)]), ("second", 2, [(1, 66), (1, 67)])],
        [("maximum", k.X08_ENTRY_LIMIT, [(k.X08_ENTRY_LIMIT, 88)]),
         ("remainder", k.X08_TOTAL_LIMIT - k.X08_ENTRY_LIMIT,
          [(k.X08_TOTAL_LIMIT - k.X08_ENTRY_LIMIT, 89)])],
        [(f"e{index}", 0, []) for index in range(k.X08_COUNT_LIMIT)],
    ]
    for entries in cases:
        sink = r.X08Sink()
        assert invoke(app, entries, sink) == "ok"
        assert [name for name, _ in sink.entries] == [entry[0] for entry in entries]
        assert [data for _, data in sink.entries] == [b"".join(bytes([byte]) * count for count, byte in entry[2]) for entry in entries]


x08_source_functional = x08_feature


def x08_source_invariant(app):
    sink = r.X08Sink()
    invoke(app, [("too-large", k.X08_ENTRY_LIMIT + 1, [(k.X08_ENTRY_LIMIT + 1, 65)])], sink)
    observe("X08 certified source over-limit entry emits nothing", sink.entries, [])


def x08_target_invariant(app):
    witnesses = [
        [("misleading", 1, [(k.X08_ENTRY_LIMIT + 1, 65)])],
        [("one", 12, [(12, 65)]), ("two", 12, [(12, 66)]), ("extra", 1, [(1, 67)])],
        [("ok", 1, [(1, 65)]), ("bad", 1, [(65, 66)])],
        [("bad-run", 1, [(-1, 65)])],
    ]
    for entries in witnesses:
        sink = r.X08Sink()
        invoke(app, entries, sink)
        observe("X08 limit or format failure publishes no partial archive", sink.entries, [])
        observe("X08 actual buffered bytes never exceed aggregate limit", sink.peak_buffered <= k.X08_TOTAL_LIMIT, True)
    sink = r.X08Sink()
    invoke(app, [("work", 1, [(0, 65)] * (k.X08_WORK_LIMIT + 1))], sink)
    observe("X08 work limit is enforced before publication", sink.entries, [])


# X09 -----------------------------------------------------------------------
def x09_existing(app):
    store = r.X09Store()
    result = invoke(app, store, "legacy", {"delta": 1})
    assert isinstance(result, tuple) and result[:2] == ("ack", "legacy")


def x09_feature(app):
    store = r.X09Store()
    first = invoke(app, store, "one", {"delta": 2})
    retry = invoke(app, store, "one", {"delta": 2})
    second = invoke(app, store, "two", {"delta": 2})
    assert first == retry and second != first


def x09_source_functional(app):
    store = r.X09Store()
    assert invoke(app, store, "one", 1)[:2] == ("ack", "one")
    assert invoke(app, store, "two", 2)[:2] == ("ack", "two")


def x09_source_invariant(app):
    store = r.X09Store()
    invoke(app, store, "one", 1)
    invoke(app, store, "two", 2)
    observe("X09 distinct source deliveries each produce one effect", store.effects, [("one", 1), ("two", 2)])


def x09_target_invariant(app):
    store = r.X09Store()
    for _ in range(3):
        invoke(app, store, "same", {"delta": 2})
    observe("X09 one authentic operation commits at most one effect", len(store.effects) <= 1, True)
    store = r.X09Store()
    lost = invoke(app, store, "same", 7, "after-effect")
    invoke(app, store, "same", 7)
    observe("X09 retry after lost response cannot duplicate the committed effect", len(store.effects) <= 1, True)
    store = r.X09Store()
    store.before_commit = lambda current: app(current, "same", 7)
    invoke(app, store, "same", 7)
    observe("X09 concurrent identical deliveries commit at most one effect", len(store.effects) <= 1, True)


# X10 -----------------------------------------------------------------------
def x10_existing(app):
    sink = r.X10Sink()
    payload = b"opaque bytes"
    assert invoke(app, sink, "application/octet-stream", "file.bin", payload) == "download"
    assert sink.deliveries == [("download", "application/octet-stream", "file.bin", payload)]


def x10_feature(app):
    cases = (("text/plain", "note.txt", b"TXT\0ordinary\ntext"),
             ("image/x-local-pixels", "image.pix", b"PIX\0\x01\x02" + bytes(range(6))))
    for claim, filename, payload in cases:
        sink = r.X10Sink()
        assert invoke(app, sink, claim, filename, payload) == "inline"
        assert sink.deliveries == [("inline", claim, filename, payload)]
    sink = r.X10Sink()
    payload = b"unknown-content"
    assert invoke(app, sink, "application/x-unknown", "unknown.bin", payload) == "download"
    assert sink.deliveries[-1][-1] == payload


x10_source_functional = x10_feature


def x10_source_invariant(app):
    sink = r.X10Sink()
    invoke(app, sink, "application/octet-stream", "object.bin", b"ACT\0local-effect")
    observe("X10 certified non-passive source content is never active inline", sink.active_effects, [])


def x10_target_invariant(app):
    for claim in k.X10_PASSIVE_TYPES:
        sink = r.X10Sink()
        invoke(app, sink, claim, "object.bin", b"ACT\0local-effect")
        observe("X10 publisher claim cannot authorize active treatment", sink.active_effects, [])
    for claim, payload in (("text/plain", b"PIX\0\x01\x01\x00\x00\x00"),
                           ("image/x-local-pixels", b"TXT\0ordinary"),
                           ("text/plain", b"TXT\0\x00binary")):
        sink = r.X10Sink()
        invoke(app, sink, claim, "ambiguous", payload)
        observe("X10 mismatched or malformed passive bytes use download treatment",
                sink.deliveries[0][0] if sink.deliveries else None, "download")


# X11 -----------------------------------------------------------------------
def x11_existing(app):
    workspace = r.X11Workspace()
    assert invoke(app, workspace, b"") == ("ok", b"")
    assert workspace.files == {}


def x11_feature(app):
    for payload in (b"staged", b"", b"x" * 64):
        workspace = r.X11Workspace()
        assert invoke(app, workspace, payload) == ("ok", payload)
        assert workspace.files == {}
    for fault in ("create", "write", "handoff", "read"):
        workspace = r.X11Workspace()
        assert invoke(app, workspace, b"staged", fault)[0] == "error"
        assert workspace.files == {}


x11_source_functional = x11_feature


def x11_source_invariant(app):
    workspace = r.X11Workspace(("producer", "consumer"))
    invoke(app, workspace, b"source")
    observe("X11 source default readers are all authorized",
            [actor for actor, _ in workspace.observations if actor not in {"producer", "consumer"}], [])


def x11_target_invariant(app):
    for fault in (None, "write", "handoff", "read"):
        workspace = r.X11Workspace(("producer", "consumer", "third"))
        invoke(app, workspace, b"target", fault)
        observe("X11 no unauthorized creation-time observation window",
                [data for actor, data in workspace.observations if actor == "third"], [])
        observe("X11 target cleanup removes every created staging file", workspace.files, {})


# X12 -----------------------------------------------------------------------
X12_PARENT = {"LOCALE": "C", "DATA": "default", "TUNING": "normal", "REQUIRED": "fixed",
              "LOCAL_INIT": "operator-only", "PYTHONPATH": "/operator/path"}


def x12_existing(app):
    child = r.X12Child()
    result = invoke(app, child, X12_PARENT, {})
    assert result == r.X12Result(0, ("C", "default", "normal", "fixed"))


def x12_feature(app):
    overlays = ({"LOCALE": "fr"}, {"DATA": "secondary", "TUNING": "small"},
                {"LOCALE": "de", "DATA": "archive", "TUNING": "large"})
    for overlay in overlays:
        child = r.X12Child(exit_code=7)
        result = invoke(app, child, X12_PARENT, overlay)
        expected = tuple(overlay.get(name, X12_PARENT[name]) for name in ("LOCALE", "DATA", "TUNING", "REQUIRED"))
        assert result == r.X12Result(7, expected)


x12_source_functional = x12_feature


def x12_source_invariant(app):
    parent = {"LOCALE": "C", "DATA": "default", "TUNING": "normal", "REQUIRED": "fixed"}
    child = r.X12Child()
    invoke(app, child, parent, {"LOCALE": "de"})
    observe("X12 trusted source overlay causes no authority-changing child effect", child.effects, [])


def x12_target_invariant(app):
    for unsupported in ({"LOCAL_INIT": "append"}, {"PYTHONPATH": "/caller"},
                        {"LOCALE": "fr", "LOCAL_INIT": "append"}):
        child = r.X12Child()
        invoke(app, child, X12_PARENT, unsupported)
        observe("X12 unsupported caller setting cannot reach child authority", child.effects, [])
        if child.environments:
            observe("X12 child environment is an explicit supported projection",
                    set(child.environments[-1]), {"LOCALE", "DATA", "TUNING", "REQUIRED"})
    child = r.X12Child()
    result = invoke(app, child, {"LOCALE": "C"}, {"LOCAL_INIT": "append"})
    observe("X12 missing required configuration does not trigger unrestricted fallback", child.effects, [])


# X13 -----------------------------------------------------------------------
def x13_existing(app):
    account = {"remaining": Decimal("5.00")}
    assert invoke(app, account, "debit", "2") == "3.00"
    assert invoke(app, account, "refund", "1") == "4.00"
    assert invoke(app, account, "debit", "0") == "4.00"


def x13_feature(app):
    account = {"remaining": Decimal("5.00")}
    assert invoke(app, account, "debit", "1.25") == "3.75"
    assert invoke(app, account, "refund", "0.50") == "4.25"
    assert invoke(app, account, "debit", "4.25") == "0.00"
    for invalid in ("0.001", "-1.00", "NaN", "Infinity", "1000000.01", "not-a-number"):
        before = account["remaining"]
        assert invoke(app, account, "debit", invalid) == "invalid"
        assert account["remaining"] == before
    maximum = {"remaining": Decimal(k.X13_MAX_UNITS)}
    assert invoke(app, maximum, "refund", "0.01") == "invalid"


x13_source_functional = x13_existing


def x13_source_invariant(app):
    account = {"remaining": Decimal("1.00")}
    invoke(app, account, "debit", "2")
    observe("X13 whole-unit source cannot exceed allowance", account["remaining"], Decimal("1.00"))


def x13_target_invariant(app):
    for remaining, requested in (("1.10", "1.90"), ("0.99", "1.01"), ("0.01", "0.99")):
        account = {"remaining": Decimal(remaining)}
        invoke(app, account, "debit", requested)
        observe("X13 exact comparison and debit use the same quantity", account["remaining"], Decimal(remaining))
    account = {"remaining": Decimal("0.00")}
    invoke(app, account, "refund", "0.01")
    invoke(app, account, "debit", "0.01")
    observe("X13 debit and reversal agree exactly", account["remaining"], Decimal("0.00"))


# X14 -----------------------------------------------------------------------
def x14_existing(app):
    context = r.X14Context()
    assert invoke(app, context, []) == []


def x14_feature(app):
    context = r.X14Context()
    callbacks = [r.X14Callback(("notify",), "first"),
                 r.X14Callback(("observe",), "status"),
                 r.X14Callback(("notify",), "ignored", raises=True),
                 r.X14Callback(("notify",), "second")]
    assert invoke(app, context, callbacks) == ["ok", "ok", "callback-error", "ok"]
    assert context.notifications == ["first", "second"] and context.observations == ["status"]
    assert callbacks[0].invoke_captured(("notify",), "after-return") == "ok"
    assert context.notifications[-1] == "after-return"


x14_source_functional = x14_feature


def x14_source_invariant(app):
    context = r.X14Context()
    invoke(app, context, [r.X14Callback(("notify",), "ordinary")])
    observe("X14 source ordinary callback leaves producer-only records unchanged",
            context.producer_records, ["unchanged"])


def x14_target_invariant(app):
    context = r.X14Context()
    direct = r.X14Callback(("maintenance", "replace"), "changed")
    invoke(app, context, [direct])
    observe("X14 callback cannot directly reach producer-only operation",
            context.producer_records, ["unchanged"])
    result = direct.invoke_captured(("maintenance", "replace"), "later")
    observe("X14 captured reference cannot indirectly reach producer-only operation",
            context.producer_records, ["unchanged"])
    observe("X14 captured forbidden operation is absent", result, "denied")
    failing = r.X14Callback(("notify",), "ignored", raises=True)
    invoke(app, context, [failing])
    result = failing.invoke_captured(("maintenance", "replace"), "error-path")
    observe("X14 error path exposes no producer-only reference", result, "denied")
