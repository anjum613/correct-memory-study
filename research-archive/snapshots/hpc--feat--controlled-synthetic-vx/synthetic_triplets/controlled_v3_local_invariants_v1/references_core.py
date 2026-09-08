"""Local reference procedures. No filesystem, processes, sockets or live identities."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# X01: a closed directory/object model. Operations alter actual byte strings.
class Directory:
    def __init__(self):
        self.entries = {"report": 1, "other": 2}
        self.objects = {1: {"owner": "writer", "data": b"old"},
                        2: {"owner": "other", "data": b"private-fixture"}}
        self.open_handles = []

    def lookup(self, name):
        return self.entries.get(name)

    def attributes(self, identity):
        return dict(self.objects[identity])

    def write(self, identity, data):
        self.objects[identity]["data"] = bytes(data)

    def compare_exchange(self, name, expected, data):
        if self.entries.get(name) != expected:
            return False
        self.objects[expected]["data"] = bytes(data)
        return True


def x01_source(directory, name, data):
    identity = directory.lookup(name)
    if identity is None:
        return "missing"
    if directory.attributes(identity)["owner"] != "writer":
        return "denied"
    directory.write(directory.lookup(name), data)
    return "updated"


def x01_base(directory, name, data):
    if directory.lookup(name) is None:
        return "missing"
    return "unavailable"


def x01_repair(directory, name, data):
    identity = directory.lookup(name)
    if identity is None:
        return "missing"
    if directory.attributes(identity)["owner"] != "writer":
        return "denied"
    if not directory.compare_exchange(name, identity, data):
        return "substituted"
    return "updated"


# X03: NFC equivalence is applied to real registry keys and returned owners.
def x03_source(registry, operation, handle, owner=None):
    if operation == "lookup":
        return registry.get(handle, (None, None))[0]
    if operation == "register":
        if handle in registry:
            return "collision"
        registry[handle] = (owner, handle)
        return "registered"
    if operation == "rename":
        actor, new = owner
        if registry.get(handle, (None,))[0] != actor:
            return "denied"
        if new in registry:
            return "collision"
        del registry[handle]
        registry[new] = (actor, new)
        return "renamed"
    raise ValueError("unsupported operation")


def x03_base(registry, operation, handle, owner=None):
    if not handle.isascii() or (operation == "rename" and not owner[1].isascii()):
        return "unavailable"
    return x03_source(registry, operation, handle, owner)


def x03_repair(registry, operation, handle, owner=None):
    key = unicodedata.normalize("NFC", handle)
    matches = [item for raw, item in registry.items()
               if unicodedata.normalize("NFC", raw) == key]
    if operation == "lookup":
        owners = {item[0] for item in matches}
        return next(iter(owners)) if len(owners) == 1 else None
    if operation == "register":
        if matches:
            return "collision"
        registry[key] = (owner, handle)
        return "registered"
    if operation == "rename":
        actor, new = owner
        owners = {item[0] for item in matches}
        if owners != {actor}:
            return "denied"
        new_key = unicodedata.normalize("NFC", new)
        if any(unicodedata.normalize("NFC", raw) == new_key for raw in registry):
            return "collision"
        for raw in list(registry):
            if unicodedata.normalize("NFC", raw) == key:
                del registry[raw]
        registry[new_key] = (actor, new)
        return "renamed"
    raise ValueError("unsupported operation")


# X04: emission is a mutable fixture sink, not a claimed authorization result.
def x04_source(store, principal, selected, sink):
    ids = list(dict.fromkeys(selected))
    if not ids:
        return "ok"
    if any(key not in store for key in ids):
        return "missing"
    if store[ids[0]][0] != principal:
        return "denied"
    sink.extend((key, store[key][1]) for key in ids)
    return "ok"


def x04_base(store, principal, selected, sink):
    if len(selected) > 1:
        return "unavailable"
    return x04_source(store, principal, selected, sink)


def x04_repair(store, principal, selected, sink):
    ids = list(dict.fromkeys(selected))
    if any(key not in store for key in ids):
        return "missing"
    if any(store[key][0] != principal for key in ids):
        return "denied"
    sink.extend((key, store[key][1]) for key in ids)
    return "ok"


# X05: synthetic-only AES-GCM messages; no production key or external service.
class Allocators:
    def __init__(self, limit=16):
        self.local, self.global_position, self.issued = {}, 0, []
        self.limit = limit

    def reserve(self, scope):
        value = self.local.get(scope, 0)
        if value >= self.limit:
            return None
        self.local[scope] = value + 1
        return value


def _x05_encode(nonce, data):
    # Public, fixed test material; never an authentication/deployment credential.
    iv = nonce.to_bytes(12, "big")
    return iv + AESGCM(bytes(range(32))).encrypt(iv, bytes(data), b"local-X05")


def x05_source(state, worker, data):
    nonce = state.reserve(worker)
    if nonce is None:
        return None
    state.issued.append(nonce)
    return _x05_encode(nonce, data)


def x05_base(state, worker, data):
    if worker != "one":
        return None
    return x05_source(state, worker, data)


def x05_repair(state, worker, data):
    nonce = state.reserve("global-key-scope")
    if nonce is None:
        return None
    state.issued.append(nonce)
    return _x05_encode(nonce, data)


# X06: project a schema; never call arbitrary object repr or exception text.
def x06_source(record, sink):
    sink.append(json.dumps(record, sort_keys=True))
    return "logged"


def x06_base(record, sink):
    sink.append(json.dumps({"correlation": record["correlation"]}, sort_keys=True))
    return "logged"


def x06_repair(record, sink):
    def project(node):
        if not isinstance(node, dict):
            return {"diagnostic": "invalid-node"}
        result = {key: node[key] for key in ("correlation", "message", "code")
                  if key in node and isinstance(node[key], (str, int))}
        if "children" in node:
            result["children"] = [project(child) for child in node["children"]]
        return result
    sink.append(json.dumps(project(record), sort_keys=True))
    return "logged"


# X07: a closed data/object codec; activation only changes the fixture's list.
class RecordDecoder:
    def __init__(self):
        self.activations = []

    def reconstruct(self, node):
        if isinstance(node, list):
            return [self.reconstruct(item) for item in node]
        if isinstance(node, dict):
            if set(node) == {"record-constructor"}:
                self.activations.append(node["record-constructor"])
                return {"created": node["record-constructor"]}
            return {key: self.reconstruct(value) for key, value in node.items()}
        return node


def x07_source(decoder, encoded):
    node = json.loads(encoded)
    if node.get("version") not in (1, 2):
        return None
    return decoder.reconstruct(node["data"])


def x07_base(decoder, encoded):
    node = json.loads(encoded)
    if node.get("version") != 1 or not isinstance(node.get("data"), str):
        return None
    return node["data"]


def x07_repair(decoder, encoded):
    node = json.loads(encoded)
    if set(node) != {"version", "data"} or node["version"] not in (1, 2):
        return None
    def permitted(value):
        if value is None or isinstance(value, (str, int, bool)):
            return True
        if isinstance(value, list):
            return all(permitted(item) for item in value)
        if isinstance(value, dict):
            return "record-constructor" not in value and all(
                isinstance(key, str) and permitted(item) for key, item in value.items())
        return False
    return node["data"] if permitted(node["data"]) else None
