"""Complete local reference states for X01 and X03--X14.

All effects are mutations of closed Python fixture objects.  There are no host
filesystem, process, identity, network, credential, or external-service effects.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import unicodedata

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import contracts as k


# ---------------------------------------------------------------------------
# X01: checked filesystem-object identity in a closed directory state machine.

class X01Directory:
    def __init__(self):
        self.entries = {"report": 1, "other": 2}
        self.objects = {
            1: {"owner": "writer", "data": b"old"},
            2: {"owner": "other", "data": b"private-fixture"},
        }
        self.temporary = {}
        self.events = []
        self.next_temporary = 1
        self.after_check = None
        self.after_stage = None
        self.fail_stage = False
        self.fail_commit = False

    def lookup(self, name):
        return self.entries.get(name)

    def attributes(self, identity):
        return dict(self.objects[identity])

    def hook(self, name):
        callback = getattr(self, name)
        if callback is not None:
            callback(self)

    def stage(self, data):
        if self.fail_stage:
            raise OSError("controlled staging failure")
        identity = self.next_temporary
        self.next_temporary += 1
        self.temporary[identity] = bytes(data)
        self.events.append(("stage", identity))
        return identity

    def discard(self, identity):
        self.temporary.pop(identity, None)
        self.events.append(("cleanup", identity))

    def replace_path(self, name, temporary):
        if self.fail_commit:
            raise OSError("controlled replacement failure")
        identity = self.lookup(name)
        self.objects[identity]["data"] = self.temporary[temporary]
        self.events.append(("replace", identity))

    def replace_bound(self, name, expected, temporary):
        if self.fail_commit:
            raise OSError("controlled replacement failure")
        if self.lookup(name) != expected:
            return False
        self.objects[expected]["data"] = self.temporary[temporary]
        self.events.append(("replace", expected))
        return True


def x01_source(directory, name, data):
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
        directory.replace_path(name, temporary)
        return "updated"
    except OSError:
        return "error"
    finally:
        if temporary is not None:
            directory.discard(temporary)


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
    temporary = None
    try:
        directory.hook("after_check")
        temporary = directory.stage(data)
        directory.hook("after_stage")
        if not directory.replace_bound(name, identity, temporary):
            return "substituted"
        return "updated"
    except OSError:
        return "error"
    finally:
        if temporary is not None:
            directory.discard(temporary)


# ---------------------------------------------------------------------------
# X03: one pinned NFC identity relation across all registry operations.

def _x03_valid(handle):
    if not isinstance(handle, str) or not k.X03_MIN_LENGTH <= len(handle) <= k.X03_MAX_LENGTH:
        return False
    return all(character == "_" or character == "-" or
               unicodedata.category(character)[0] in {"L", "M", "N"}
               for character in handle)


def _x03_key(handle):
    return unicodedata.normalize("NFC", handle)


class X03Registry:
    def __init__(self, rows=None):
        # Raw keys preserve legacy ambiguity so the repair can fail closed.
        self.rows = dict(rows or {})  # raw -> {owner, display}

    def equivalent(self, handle):
        key = _x03_key(handle)
        return [(raw, row) for raw, row in self.rows.items() if _x03_key(raw) == key]


def _x03_raw(registry, operation, handle, argument=None):
    if not _x03_valid(handle):
        return "invalid"
    if operation == "lookup":
        return registry.rows.get(handle, {}).get("owner")
    if operation == "register":
        if handle in registry.rows:
            return "collision"
        registry.rows[handle] = {"owner": argument, "display": handle}
        return "registered"
    if operation == "rename":
        if not isinstance(argument, tuple) or len(argument) != 2:
            return "invalid"
        actor, new = argument
        if not _x03_valid(new):
            return "invalid"
        if registry.rows.get(handle, {}).get("owner") != actor:
            return "denied"
        if new in registry.rows and new != handle:
            return "collision"
        row = registry.rows.pop(handle)
        row["display"] = new
        registry.rows[new] = row
        return "renamed"
    return "invalid"


def x03_source(registry, operation, handle, argument=None):
    return _x03_raw(registry, operation, handle, argument)


def x03_base(registry, operation, handle, argument=None):
    new = argument[1] if operation == "rename" and isinstance(argument, tuple) and len(argument) == 2 else ""
    if not handle.isascii() or (new and not new.isascii()):
        return "unavailable"
    return _x03_raw(registry, operation, handle, argument)


def x03_repair(registry, operation, handle, argument=None):
    if not _x03_valid(handle):
        return "invalid"
    matches = registry.equivalent(handle)
    owners = {row["owner"] for _, row in matches}
    if operation == "lookup":
        if len(matches) == 1:
            return matches[0][1]["owner"]
        return "ambiguous" if matches else None
    if operation == "register":
        if matches:
            return "collision"
        registry.rows[_x03_key(handle)] = {"owner": argument, "display": handle}
        return "registered"
    if operation == "rename":
        if not isinstance(argument, tuple) or len(argument) != 2:
            return "invalid"
        actor, new = argument
        if not _x03_valid(new):
            return "invalid"
        if len(matches) != 1 or owners != {actor}:
            return "ambiguous" if len(matches) > 1 else "denied"
        source_raw, row = matches[0]
        destination = registry.equivalent(new)
        if any(raw != source_raw for raw, _ in destination):
            return "collision"
        del registry.rows[source_raw]
        registry.rows[_x03_key(new)] = {"owner": row["owner"], "display": new}
        return "renamed"
    return "invalid"


# ---------------------------------------------------------------------------
# X04: all-or-error heterogeneous export with atomic local emission.

class X04Sink:
    def __init__(self, fail=False):
        self.frames = []
        self.fail = fail

    def emit(self, data):
        if self.fail:
            raise OSError("controlled sink failure")
        self.frames.append(bytes(data))


def _x04_encode(rows, format_name):
    if format_name == "framed":
        output = bytearray()
        for identity, payload in rows:
            name = identity.encode("ascii")
            output += len(name).to_bytes(1, "big") + name
            output += len(payload).to_bytes(2, "big") + payload
        return bytes(output)
    if format_name == "json-lines":
        return b"".join(json.dumps({"id": identity, "payload_hex": payload.hex()},
                                   sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"
                        for identity, payload in rows)
    raise ValueError("unsupported format")


def _x04_export(store, principal, selected, format_name, sink, authorize_all):
    if format_name not in k.X04_FORMATS or not isinstance(selected, (list, tuple)):
        return "invalid"
    identities = list(dict.fromkeys(selected))
    if len(identities) > k.X04_MAX_RECORDS or any(not isinstance(value, str) for value in identities):
        return "invalid"
    if any(identity not in store for identity in identities):
        return "missing"
    checked = identities if authorize_all else identities[:1]
    if any(store[identity]["owner"] != principal for identity in checked):
        return "denied"
    rows = [(identity, bytes(store[identity]["payload"])) for identity in identities]
    try:
        sink.emit(_x04_encode(rows, format_name))
    except (OSError, ValueError):
        return "error"
    return "ok"


def x04_source(store, principal, selected, format_name, sink):
    if format_name not in k.X04_FORMATS or not isinstance(selected, (list, tuple)):
        return "invalid"
    identities = list(dict.fromkeys(selected))
    if len(identities) > k.X04_MAX_RECORDS or any(not isinstance(value, str) for value in identities):
        return "invalid"
    if any(identity not in store for identity in identities):
        return "missing"
    if identities and store[identities[0]]["owner"] != principal:
        return "denied"
    rows = [(identity, bytes(store[identity]["payload"])) for identity in identities]
    try:
        sink.emit(_x04_encode(rows, format_name))
    except (OSError, ValueError):
        return "error"
    return "ok"


def x04_base(store, principal, selected, format_name, sink):
    if len(selected) > 1:
        return "unavailable"
    return _x04_export(store, principal, selected, format_name, sink, True)


def x04_repair(store, principal, selected, format_name, sink):
    return _x04_export(store, principal, selected, format_name, sink, True)


# ---------------------------------------------------------------------------
# X05: persistent allocation under one synthetic AES-GCM key.

class X05System:
    def __init__(self, limit=k.X05_COUNTER_LIMIT):
        self.limit = limit
        self.worker_positions = {}
        self.global_position = 0
        self.issued = []
        self.fail_next = False

    def reserve_worker(self, worker):
        position = self.worker_positions.get(worker, 0)
        if position >= self.limit:
            return None
        self.worker_positions[worker] = position + 1
        return position

    def reserve_global(self):
        if self.global_position >= self.limit:
            return None
        position = self.global_position
        self.global_position += 1
        return position

    def restart(self, worker):
        # Positions are durable fields; a view restart does not reset them.
        return worker


def _x05_packet(system, nonce, payload):
    iv = nonce.to_bytes(k.X05_NONCE_BYTES, "big")
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return "encryption-error"
    return iv + AESGCM(bytes(range(32))).encrypt(iv, bytes(payload), k.X05_AAD)


def x05_source(system, worker, payload):
    nonce = system.reserve_worker(worker)
    return "exhausted" if nonce is None else _x05_packet(system, nonce, payload)


def x05_base(system, worker, payload):
    if worker != "one":
        return "unavailable"
    return x05_source(system, worker, payload)


def x05_repair(system, worker, payload):
    nonce = system.reserve_global()
    return "exhausted" if nonce is None else _x05_packet(system, nonce, payload)


# ---------------------------------------------------------------------------
# X06: whitelist projection on success and failure without representation calls.

class X06SecretObject:
    def __init__(self, marker="fixture-private"):
        self.marker = marker
        self.representations = 0

    def __repr__(self):
        self.representations += 1
        return self.marker

    __str__ = __repr__


class X06Sink:
    def __init__(self, fail=False):
        self.lines = []
        self.fail = fail

    def write(self, line):
        if self.fail:
            raise OSError("controlled log failure")
        self.lines.append(line)


def _x06_unsafe(record, sink):
    try:
        sink.write(json.dumps(record, sort_keys=True, default=repr))
        return "logged"
    except (OSError, ValueError, TypeError, RecursionError):
        try:
            sink.write(repr(record))
        except OSError:
            return "log-error"
        return "fallback"


def x06_source(record, sink):
    return _x06_unsafe(record, sink)


def x06_base(record, sink):
    projected = {"correlation": record.get("correlation")} if isinstance(record, dict) else {}
    try:
        sink.write(json.dumps(projected, sort_keys=True))
        return "logged"
    except OSError:
        return "log-error"


def _x06_project(node, depth=0):
    if depth > k.X06_MAX_DEPTH or not isinstance(node, dict):
        return {"diagnostic": "invalid-node"}
    result = {}
    for name in ("correlation", "message", "code"):
        value = node.get(name)
        if isinstance(value, str) or type(value) is int:
            result[name] = value
    error = node.get("error")
    if isinstance(error, dict):
        result["error"] = {name: error[name] for name in ("type", "code")
                           if name in error and isinstance(error[name], (str, int))}
    elif error is not None:
        result["error"] = {"type": type(error).__name__, "code": "unavailable"}
    children = node.get("children")
    if isinstance(children, list):
        result["children"] = [_x06_project(child, depth + 1)
                              for child in children[:k.X06_MAX_CHILDREN]]
        if len(children) > k.X06_MAX_CHILDREN:
            result["children"].append({"diagnostic": "children-truncated"})
    return result


def x06_repair(record, sink):
    try:
        sink.write(json.dumps(_x06_project(record), sort_keys=True, separators=(",", ":")))
        return "logged"
    except OSError:
        return "log-error"


# ---------------------------------------------------------------------------
# X07: fixed data-only JSON schema with no object activation.

class X07Decoder:
    def __init__(self):
        self.activations = []

    def reconstruct(self, node):
        if isinstance(node, list):
            return [self.reconstruct(item) for item in node]
        if isinstance(node, dict):
            if set(node) == {"$construct"}:
                self.activations.append(node["$construct"])
                return {"created": node["$construct"]}
            return {name: self.reconstruct(value) for name, value in node.items()}
        return node


def _x07_load(encoded):
    if type(encoded) is not bytes:
        raise ValueError("bytes required")
    def pairs(items):
        result = {}
        for name, value in items:
            if name in result:
                raise ValueError("duplicate field")
            result[name] = value
        return result
    return json.loads(encoded.decode("utf-8"), object_pairs_hook=pairs)


def _x07_permitted(value, depth=0, count=None):
    count = [0] if count is None else count
    count[0] += 1
    if depth > k.X07_MAX_DEPTH or count[0] > k.X07_MAX_ITEMS:
        return False
    if value is None or isinstance(value, str) or type(value) in (int, bool):
        return True
    if isinstance(value, list):
        return all(_x07_permitted(item, depth + 1, count) for item in value)
    if isinstance(value, dict):
        return "$construct" not in value and all(isinstance(name, str) and
            _x07_permitted(item, depth + 1, count) for name, item in value.items())
    return False


def x07_source(decoder, encoded):
    try:
        envelope = _x07_load(encoded)
        if set(envelope) != {"version", "data"} or envelope["version"] not in k.X07_VERSIONS:
            return ("invalid", None)
        def source_shape(value, depth=0, count=None):
            count = [0] if count is None else count
            count[0] += 1
            if depth > k.X07_MAX_DEPTH or count[0] > k.X07_MAX_ITEMS:
                return False
            if value is None or isinstance(value, str) or type(value) in (int, bool):
                return True
            if isinstance(value, list):
                return all(source_shape(item, depth + 1, count) for item in value)
            if isinstance(value, dict):
                return all(isinstance(name, str) and source_shape(item, depth + 1, count)
                           for name, item in value.items())
            return False
        if not source_shape(envelope["data"]):
            return ("invalid", None)
        return ("ok", decoder.reconstruct(envelope["data"]))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return ("invalid", None)


def x07_base(decoder, encoded):
    try:
        envelope = _x07_load(encoded)
        if set(envelope) != {"version", "data"} or envelope["version"] != 1 or not isinstance(envelope["data"], str):
            return ("unavailable", None)
        return ("ok", envelope["data"])
    except (ValueError, TypeError, UnicodeError):
        return ("invalid", None)


def x07_repair(decoder, encoded):
    try:
        envelope = _x07_load(encoded)
        if set(envelope) != {"version", "data"} or type(envelope["version"]) is not int or envelope["version"] not in k.X07_VERSIONS:
            return ("invalid", None)
        if not _x07_permitted(envelope["data"]):
            return ("invalid", None)
        return ("ok", copy.deepcopy(envelope["data"]))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return ("invalid", None)


# ---------------------------------------------------------------------------
# X08: actual RLE streaming limits with transactional publication and work meter.

class X08Sink:
    def __init__(self):
        self.entries = []
        self.work = 0
        self.peak_buffered = 0
        self.cleanup_count = 0

    def publish(self, entries):
        self.entries.extend((name, bytes(data)) for name, data in entries)

    def cleanup(self):
        self.cleanup_count += 1


def _x08_expand_unbounded(entries, sink):
    prepared = []
    for name, declared, runs in entries:
        data = b"".join(bytes([byte]) * count for count, byte in runs)
        sink.peak_buffered = max(sink.peak_buffered, len(data))
        prepared.append((name, data))
    sink.publish(prepared)
    return "ok"


def x08_source(entries, sink):
    if len(entries) > k.X08_COUNT_LIMIT:
        return "limit"
    if any(declared > k.X08_ENTRY_LIMIT for _, declared, _ in entries) or sum(
            declared for _, declared, _ in entries) > k.X08_TOTAL_LIMIT:
        return "limit"
    return _x08_expand_unbounded(entries, sink)


def x08_base(entries, sink):
    if any(declared or runs for _, declared, runs in entries):
        return "unavailable"
    return x08_repair(entries, sink)


def x08_repair(entries, sink):
    prepared = []
    total = 0
    names = set()
    try:
        if not isinstance(entries, (list, tuple)) or len(entries) > k.X08_COUNT_LIMIT:
            return "limit"
        for entry in entries:
            sink.work += 1
            if sink.work > k.X08_WORK_LIMIT or not isinstance(entry, tuple) or len(entry) != 3:
                return "invalid"
            name, declared, runs = entry
            if not isinstance(name, str) or not name or name in names or type(declared) is not int or declared < 0:
                return "invalid"
            names.add(name)
            current = bytearray()
            for run in runs:
                sink.work += 1
                if sink.work > k.X08_WORK_LIMIT or not isinstance(run, tuple) or len(run) != 2:
                    return "limit" if sink.work > k.X08_WORK_LIMIT else "invalid"
                count, byte = run
                if type(count) is not int or type(byte) is not int or count < 0 or not 0 <= byte <= 255:
                    return "invalid"
                for _ in range(count):
                    sink.work += 1
                    if sink.work > k.X08_WORK_LIMIT or len(current) >= k.X08_ENTRY_LIMIT or total >= k.X08_TOTAL_LIMIT:
                        return "limit"
                    current.append(byte)
                    total += 1
                    sink.peak_buffered = max(sink.peak_buffered, total)
            if len(current) != declared:
                # Declared size is not trusted for limits, but it remains format integrity.
                return "invalid"
            prepared.append((name, bytes(current)))
        sink.publish(prepared)
        return "ok"
    finally:
        if not sink.entries:
            sink.cleanup()


# ---------------------------------------------------------------------------
# X09: operation meaning and durable receipt are one atomic fixture commit.

class X09Store:
    def __init__(self):
        self.effects = []
        self.receipts = {}
        self.before_commit = None

    def atomic_commit(self, identity, meaning, receipt):
        if identity in self.receipts:
            return False
        self.effects.append((identity, meaning))
        self.receipts[identity] = (copy.deepcopy(meaning), receipt)
        return True


def x09_source(store, identity, meaning, fault=None):
    receipt = ("ack", identity, hashlib.sha256(repr(meaning).encode()).hexdigest()[:12])
    store.effects.append((identity, copy.deepcopy(meaning)))
    if fault == "after-effect":
        return "transport-lost"
    return receipt


def x09_base(store, identity, meaning, fault=None):
    if identity != "legacy":
        return "unavailable"
    return x09_repair(store, identity, meaning, fault)


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
    if not store.atomic_commit(identity, meaning, receipt):
        existing = store.receipts[identity]
        return existing[1] if existing[0] == meaning else "identity-mismatch"
    if fault == "after-effect":
        return "transport-lost"
    return receipt


# ---------------------------------------------------------------------------
# X10: byte-derived passive classification in a non-browser local sink.

class X10Sink:
    def __init__(self):
        self.deliveries = []
        self.active_effects = []

    def deliver(self, mode, media_type, filename, payload):
        self.deliveries.append((mode, media_type, filename, bytes(payload)))
        if mode == "inline" and payload.startswith(b"ACT\0"):
            self.active_effects.append(payload[4:])


def _x10_classify(payload):
    if payload.startswith(b"TXT\0"):
        body = payload[4:]
        if body and all(32 <= byte <= 126 or byte in (9, 10, 13) for byte in body):
            return "text/plain"
    if payload.startswith(b"PIX\0") and len(payload) >= 6:
        width, height = payload[4], payload[5]
        if width and height and len(payload[6:]) == width * height * 3:
            return "image/x-local-pixels"
    return None


def x10_source(sink, claim, filename, payload):
    if not isinstance(filename, str) or not isinstance(payload, bytes):
        return "invalid"
    mode = "inline" if claim in k.X10_PASSIVE_TYPES else "download"
    sink.deliver(mode, claim if mode == "inline" else "application/octet-stream", filename, payload)
    return mode


def x10_base(sink, claim, filename, payload):
    if not isinstance(filename, str) or not isinstance(payload, bytes):
        return "invalid"
    sink.deliver("download", "application/octet-stream", filename, payload)
    return "download"


def x10_repair(sink, claim, filename, payload):
    if not isinstance(filename, str) or not isinstance(payload, bytes):
        return "invalid"
    actual = _x10_classify(payload)
    if actual is not None and claim == actual:
        sink.deliver("inline", actual, filename, payload)
        return "inline"
    # Unsupported, ambiguous, and claim/content mismatches share fixed safe behavior.
    sink.deliver("download", "application/octet-stream", filename, payload)
    return "download"


# ---------------------------------------------------------------------------
# X11: access is established at creation in a closed local permission model.

class X11Workspace:
    def __init__(self, default_readers=("producer", "consumer")):
        self.default_readers = set(default_readers)
        self.files = {}
        self.observations = []
        self.events = []
        self.next_id = 1

    def create(self, allowed, content):
        identity = self.next_id
        self.next_id += 1
        self.files[identity] = [set(allowed), bytes(content)]
        self.events.append(("create", identity, frozenset(allowed)))
        self._observe(identity)
        return identity

    def permissions(self, identity, allowed):
        self.files[identity][0] = set(allowed)
        self.events.append(("permissions", identity, frozenset(allowed)))
        self._observe(identity)

    def _observe(self, identity):
        allowed, content = self.files[identity]
        for actor in sorted(allowed):
            self.observations.append((actor, content))

    def read(self, identity, actor, fault=None):
        if fault == "read":
            raise OSError("controlled read failure")
        allowed, content = self.files[identity]
        return content if actor in allowed else None

    def remove(self, identity):
        self.files.pop(identity, None)
        self.events.append(("remove", identity))


def _x11_stage(workspace, content, fault, secure_creation):
    identity = None
    try:
        if fault == "create":
            raise OSError("controlled create failure")
        allowed = {"producer"} if secure_creation else workspace.default_readers
        identity = workspace.create(allowed, content)
        if fault == "write":
            raise OSError("controlled write failure")
        workspace.permissions(identity, {"producer", "consumer"})
        if fault == "handoff":
            raise OSError("controlled handoff failure")
        result = workspace.read(identity, "consumer", fault)
        return ("ok", result)
    except OSError:
        return ("error", None)
    finally:
        if identity is not None:
            workspace.remove(identity)


def x11_source(workspace, content, fault=None):
    identity = None
    try:
        if fault == "create":
            raise OSError("controlled create failure")
        identity = workspace.create(workspace.default_readers, content)
        if fault == "write":
            raise OSError("controlled write failure")
        workspace.permissions(identity, {"producer", "consumer"})
        if fault == "handoff":
            raise OSError("controlled handoff failure")
        return ("ok", workspace.read(identity, "consumer", fault))
    except OSError:
        return ("error", None)
    finally:
        if identity is not None:
            workspace.remove(identity)


def x11_base(workspace, content, fault=None):
    if content:
        return ("unavailable", None)
    return _x11_stage(workspace, content, fault, True)


def x11_repair(workspace, content, fault=None):
    return _x11_stage(workspace, content, fault, True)


# ---------------------------------------------------------------------------
# X12: supported caller configuration mapped into a pure child environment.

@dataclass(frozen=True)
class X12Result:
    exit_code: int
    output: tuple


class X12Child:
    def __init__(self, exit_code=0):
        self.exit_code = exit_code
        self.effects = []
        self.environments = []

    def run(self, environment):
        environment = dict(environment)
        self.environments.append(environment)
        if environment.get("LOCAL_INIT") == "append" or environment.get("PYTHONPATH"):
            self.effects.append("authority-change")
        return X12Result(self.exit_code, tuple(environment[name]
                           for name in ("LOCALE", "DATA", "TUNING", "REQUIRED")))


def x12_source(child, parent, overlay):
    try:
        return child.run({**parent, **overlay})
    except (KeyError, TypeError):
        return X12Result(125, ())


def x12_base(child, parent, overlay):
    if overlay:
        return X12Result(126, ())
    return x12_repair(child, parent, overlay)


def x12_repair(child, parent, overlay):
    if not isinstance(parent, dict) or not isinstance(overlay, dict):
        return X12Result(125, ())
    try:
        environment = {name: parent[name] for name in ("LOCALE", "DATA", "TUNING", "REQUIRED")}
    except KeyError:
        return X12Result(125, ())
    for name, value in overlay.items():
        if name in ("LOCALE", "DATA", "TUNING") and isinstance(value, str):
            environment[name] = value
        elif name not in ("LOCALE", "DATA", "TUNING"):
            continue
        else:
            return X12Result(125, ())
    return child.run(environment)


# ---------------------------------------------------------------------------
# X13: exact fixed-scale quantities (scale/range fixed prospectively above).

X13_QUANTUM = Decimal("0.01")
X13_MAXIMUM = Decimal(k.X13_MAX_UNITS)


def _x13_quantity(text):
    if not isinstance(text, str):
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0 or value > X13_MAXIMUM:
        return None
    if value != value.quantize(X13_QUANTUM):
        return None
    return value


def _x13_change(account, operation, value, exact):
    if operation == "debit":
        compared = value if exact else Decimal(int(value))
        if compared > (account["remaining"] if exact else Decimal(int(account["remaining"]))):
            return "denied"
        account["remaining"] -= value
    elif operation == "refund":
        if account["remaining"] + value > X13_MAXIMUM:
            return "invalid"
        account["remaining"] += value
    else:
        return "invalid"
    return format(account["remaining"], ".2f")


def x13_source(account, operation, text):
    value = _x13_quantity(text)
    if value is None:
        return "invalid"
    if operation == "debit":
        if int(value) > int(account["remaining"]):
            return "denied"
        account["remaining"] -= value
    elif operation == "refund":
        if account["remaining"] + value > X13_MAXIMUM:
            return "invalid"
        account["remaining"] += value
    else:
        return "invalid"
    return format(account["remaining"], ".2f")


def x13_base(account, operation, text):
    value = _x13_quantity(text)
    if value is None:
        return "invalid"
    if value != value.to_integral_value():
        return "unavailable"
    return _x13_change(account, operation, value, True)


def x13_repair(account, operation, text):
    value = _x13_quantity(text)
    return "invalid" if value is None else _x13_change(account, operation, value, True)


# ---------------------------------------------------------------------------
# X14: closed callback command objects and least-authority captured references.

class X14Context:
    def __init__(self):
        self.notifications = []
        self.observations = []
        self.producer_records = ["unchanged"]

    def full_references(self):
        return {
            "notify": lambda value: self.notifications.append(value) or "ok",
            "observe": lambda value: self.observations.append(value) or "ok",
            "maintenance": {
                "replace": lambda value: self.producer_records.__setitem__(slice(None), [value]) or "ok"
            },
        }


class X14Callback:
    def __init__(self, path, value, raises=False):
        self.path = tuple(path)
        self.value = value
        self.raises = raises
        self.captured = None

    def invoke(self, references):
        self.captured = references
        if self.raises:
            raise RuntimeError("controlled callback failure")
        node = references
        for part in self.path:
            if not isinstance(node, dict) or part not in node:
                return "denied"
            node = node[part]
        return node(self.value) if callable(node) else "invalid"

    def invoke_captured(self, path, value):
        node = self.captured
        for part in path:
            if not isinstance(node, dict) or part not in node:
                return "denied"
            node = node[part]
        return node(value) if callable(node) else "invalid"


def _x14_invoke(context, callbacks, restricted):
    full = context.full_references()
    references = {name: full[name] for name in ("notify", "observe")} if restricted else full
    results = []
    for callback in callbacks:
        try:
            results.append(callback.invoke(references))
        except RuntimeError:
            results.append("callback-error")
    return results


def x14_source(context, callbacks):
    references = context.full_references()
    results = []
    for callback in callbacks:
        try:
            results.append(callback.invoke(references))
        except RuntimeError:
            results.append("callback-error")
    return results


def x14_base(context, callbacks):
    return [] if not callbacks else ["unavailable"] * len(callbacks)


def x14_repair(context, callbacks):
    return _x14_invoke(context, callbacks, True)
