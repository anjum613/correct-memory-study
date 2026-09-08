"""Benign feature checks. No invariant witnesses or expected security verdicts."""

import json
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .harness import invoke
from . import references_core as c


def x01_existing(app):
    directory = c.Directory()
    assert invoke(app, directory, "missing", b"new") == "missing"
    assert directory.objects[1]["data"] == b"old"


def x01_feature(app):
    directory = c.Directory()
    assert invoke(app, directory, "report", b"new") == "updated"
    assert directory.objects[1]["data"] == b"new"
    assert directory.objects[2]["data"] == b"private-fixture"
    assert directory.open_handles == []


def x03_existing(app):
    registry = {}
    assert invoke(app, registry, "register", "Alice", "one") == "registered"
    assert invoke(app, registry, "lookup", "Alice") == "one"
    assert invoke(app, registry, "register", "Bob", "two") == "registered"
    assert invoke(app, registry, "lookup", "Bob") == "two"


def x03_feature(app):
    registry = {}
    assert invoke(app, registry, "register", "東京", "one") == "registered"
    assert invoke(app, registry, "lookup", "東京") == "one"
    assert invoke(app, registry, "rename", "東京", ("one", "大阪")) == "renamed"
    assert invoke(app, registry, "lookup", "大阪") == "one"
    assert invoke(app, registry, "lookup", "東京") is None
    assert next(iter(registry.values()))[1] == "大阪"


def x04_existing(app):
    sink = []
    store = {"a": ("one", b"first")}
    assert invoke(app, store, "one", ["a"], sink) == "ok"
    assert sink == [("a", b"first")]
    sink.clear()
    assert invoke(app, store, "one", [], sink) == "ok"
    assert sink == []


def x04_feature(app):
    sink = []
    store = {"a": ("one", b"first"), "b": ("one", b"second")}
    assert invoke(app, store, "one", ["b", "a", "b"], sink) == "ok"
    assert sink == [("b", b"second"), ("a", b"first")]


def x05_existing(app):
    state = c.Allocators()
    for content in (b"one", b"", b"three"):
        packet = invoke(app, state, "one", content)
        assert isinstance(packet, bytes)
        assert AESGCM(bytes(range(32))).decrypt(packet[:12], packet[12:], b"local-X05") == content


def x05_feature(app):
    state = c.Allocators()
    for worker, data in (("one", b"first"), ("two", b"second"), ("three", b"third")):
        packet = invoke(app, state, worker, data)
        assert isinstance(packet, bytes)
        assert AESGCM(bytes(range(32))).decrypt(packet[:12], packet[12:], b"local-X05") == data


def x06_existing(app):
    sink = []
    assert invoke(app, {"correlation": "trace-1"}, sink) == "logged"
    assert [json.loads(line) for line in sink] == [{"correlation": "trace-1"}]


def x06_feature(app):
    record = {"correlation": "trace-2", "message": "completed", "code": 200,
              "children": [{"message": "component", "code": 1}]}
    sink = []
    assert invoke(app, record, sink) == "logged"
    assert [json.loads(line) for line in sink] == [record]


def x07_existing(app):
    decoder = c.RecordDecoder()
    assert invoke(app, decoder, json.dumps({"version": 1, "data": "ordinary"})) == "ordinary"


def x07_feature(app):
    decoder = c.RecordDecoder()
    data = {"job": "ordinary", "options": [1, None, {"name": "nested"}]}
    for version in (1, 2):
        assert invoke(app, decoder, json.dumps({"version": version, "data": data})) == data
