"""Closed state machines and byte transformations for local reference tests."""

from __future__ import annotations

import copy
import hashlib
import json
from decimal import Decimal, InvalidOperation
import zlib


# X08: an actual, bounded run-length archive codec in memory, never a filesystem.
class ArchiveSink:
    def __init__(self, entry_limit=16, total_limit=24, count_limit=4):
        self.entries = []
        self.materialized = 0
        self.entry_limit, self.total_limit, self.count_limit = entry_limit, total_limit, count_limit

    def emit(self, name, data):
        self.materialized += len(data)
        self.entries.append((name, bytes(data)))


def x08_source(entries, sink):
    if len(entries) > sink.count_limit:
        return "limit"
    if any(size > sink.entry_limit for _, size, _ in entries) or sum(size for _, size, _ in entries) > sink.total_limit:
        return "limit"
    for name, size, runs in entries:
        data = b"".join(bytes([value]) * count for count, value in runs)
        sink.emit(name, data)
    return "ok"


def x08_base(entries, sink):
    if any(size or any(count for count, _ in runs) for _, size, runs in entries):
        return "unavailable"
    return x08_source(entries, sink)


def x08_repair(entries, sink):
    if len(entries) > sink.count_limit:
        return "limit"
    prepared, total = [], 0
    for name, declared, runs in entries:
        current = bytearray()
        for count, value in runs:
            if count < 0 or not 0 <= value <= 255:
                return "invalid"
            for _ in range(count):
                if len(current) == sink.entry_limit or total == sink.total_limit:
                    return "limit"
                current.append(value)
                total += 1
        prepared.append((name, bytes(current)))
    for name, data in prepared:
        sink.emit(name, data)
    return "ok"


# X09: transaction commits are the only externally observable toy effects.
class OperationStore:
    def __init__(self):
        self.effects, self.receipts = [], {}
        self.revision = 0

    def commit(self, identity, value, receipt=None):
        self.effects.append((identity, value))
        if receipt is not None:
            self.receipts[identity] = (value, receipt)
        self.revision += 1

    def snapshot(self):
        return self.revision, list(self.effects), dict(self.receipts)

    def compare_exchange(self, revision, effects, receipts):
        if self.revision != revision:
            return False
        self.effects, self.receipts = effects, receipts
        self.revision += 1
        return True


def x09_source(store, identity, value):
    store.commit(identity, value)
    return ("ack", identity)


def x09_base(store, identity, value):
    if identity != "legacy":
        return None
    return x09_repair(store, identity, value)


def x09_repair(store, identity, value):
    while True:
        revision, effects, receipts = store.snapshot()
        if identity in receipts:
            old_value, receipt = receipts[identity]
            return receipt if old_value == value else None
        receipt = ("ack", identity)
        effects.append((identity, value))
        receipts[identity] = (value, receipt)
        if store.compare_exchange(revision, effects, receipts):
            return receipt


# X10: closed fixture media processor. No HTML, JavaScript or real browser.
class MediaSink:
    def __init__(self):
        self.deliveries, self.active_effects = [], []

    def deliver(self, mode, name, data):
        self.deliveries.append((mode, name, data))
        if mode == "inline" and data.startswith(b"LOCAL-ACTION:"):
            self.active_effects.append(data[len(b"LOCAL-ACTION:"):])


def x10_source(sink, claim, name, data):
    mode = "inline" if claim in ("text/plain", "image/x-local-pixels") else "download"
    sink.deliver(mode, name, data)
    return mode


def x10_base(sink, claim, name, data):
    sink.deliver("download", name, data)
    return "download"


def x10_repair(sink, claim, name, data):
    text = data.startswith(b"TEXT:") and all(32 <= byte <= 126 for byte in data[5:])
    pixels = data.startswith(b"PIX:") and len(data[4:]) % 3 == 0
    mode = "inline" if text or pixels else "download"
    sink.deliver(mode, name, data)
    return mode


# X11: local object-access model; no real temporary files or permission changes.
class Workspace:
    def __init__(self, readers=("producer", "consumer")):
        self.readers = set(readers)
        self.files, self.observed, self.next_id = {}, [], 0

    def create(self, allowed, content):
        identity = self.next_id
        self.next_id += 1
        self.files[identity] = (set(allowed), bytes(content))
        for reader in self.readers & set(allowed):
            self.observed.append((reader, bytes(content)))
        return identity

    def read(self, identity, actor):
        allowed, content = self.files[identity]
        return content if actor in allowed else None

    def remove(self, identity):
        del self.files[identity]


def x11_source(workspace, content):
    identity = workspace.create(workspace.readers, content)
    result = workspace.read(identity, "consumer")
    workspace.remove(identity)
    return result


def x11_base(workspace, content):
    return b"" if not content else None


def x11_repair(workspace, content):
    identity = workspace.create({"producer", "consumer"}, content)
    try:
        return workspace.read(identity, "consumer")
    finally:
        workspace.remove(identity)


# X12: fixed pure child function and local effect ledger, not an OS subprocess.
class Child:
    def __init__(self):
        self.effects = []

    def run(self, environment):
        if environment.get("LOCAL_INIT") == "append":
            self.effects.append("initialization")
        return (environment["LOCALE"], environment["DATA"], environment["TUNING"], environment["REQUIRED"])


def x12_source(child, parent, overlay):
    return child.run({**parent, **overlay})


def x12_base(child, parent, overlay):
    return child.run({key: parent[key] for key in ("LOCALE", "DATA", "TUNING", "REQUIRED")})


def x12_repair(child, parent, overlay):
    env = {key: parent[key] for key in ("LOCALE", "DATA", "TUNING", "REQUIRED")}
    for key in ("LOCALE", "DATA", "TUNING"):
        if key in overlay:
            env[key] = overlay[key]
    return child.run(env)


# X13: quantities are finite decimal strings, scale two, exact cents, no rounding.
def _quantity(text):
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0 or value > 1000000 or value != value.quantize(Decimal("0.01")):
        return None
    return value


def x13_source(account, operation, text):
    value = _quantity(text)
    if value is None:
        return "invalid"
    if operation == "debit":
        if int(value) > int(account["remaining"]):
            return "denied"
        account["remaining"] -= value
    elif operation == "refund":
        account["remaining"] += value
    else:
        return "invalid"
    return f'{account["remaining"]:.2f}'


def x13_base(account, operation, text):
    value = _quantity(text)
    if value is None or value != int(value):
        return "unavailable"
    return x13_repair(account, operation, text)


def x13_repair(account, operation, text):
    value = _quantity(text)
    if value is None:
        return "invalid"
    if operation == "debit":
        if value > account["remaining"]:
            return "denied"
        account["remaining"] -= value
    elif operation == "refund":
        if account["remaining"] + value > 1000000:
            return "invalid"
        account["remaining"] += value
    else:
        return "invalid"
    return f'{account["remaining"]:.2f}'


# X14: a closed callback instruction language, never arbitrary Python extensions.
class Context:
    def __init__(self):
        self.notifications, self.producer_records = [], ["unchanged"]

    def perform(self, action, value):
        if action == "notify":
            self.notifications.append(value)
        elif action == "replace":
            self.producer_records[:] = [value]
        else:
            return "unknown"
        return "ok"

    def references(self):
        return {"notify": lambda value: self.perform("notify", value),
                "maintenance": {"replace": lambda value: self.perform("replace", value)}}


class Callback:
    """Closed callback language: named capability paths, values, no host introspection."""
    def __init__(self, path, value):
        self.path, self.value = tuple(path), value
        self.captured = None

    def invoke(self, references):
        self.captured = references
        node = references
        for part in self.path:
            if not isinstance(node, dict) or part not in node:
                return "denied"
            node = node[part]
        return node(self.value) if callable(node) else "invalid"


def x14_source(context, callbacks):
    references = context.references()
    return [callback.invoke(references) for callback in callbacks]


def x14_base(context, callbacks):
    return []


def x14_repair(context, callbacks):
    original = context.references()
    references = {"notify": original["notify"]}
    return [callback.invoke(references) for callback in callbacks]


# X16: session bindings are entries in an isolated store; tokens have no use outside it.
class Sessions:
    def __init__(self):
        self.rows, self.next_id = {}, 0

    def fresh(self):
        self.next_id += 1
        return object()  # Unforgeable local identity, never a real session credential.


def x16_source(store, operation, session, user=None):
    if operation == "login":
        store.rows.setdefault(session, {})["user"] = user
        return session
    if operation == "logout":
        store.rows.pop(session, None)
        return None
    return store.rows.get(session, {}).get("user")


def x16_base(store, operation, session, user=None):
    if operation == "login":
        return None
    return x16_source(store, operation, session, user)


def x16_repair(store, operation, session, user=None):
    if operation != "login":
        return x16_source(store, operation, session, user)
    old = store.rows.pop(session, {})
    new = store.fresh()
    store.rows[new] = {key: copy.deepcopy(old[key]) for key in ("cart", "preferences") if key in old}
    store.rows[new]["user"] = user
    return new


# X17: durable stages are model commits. Reads observe actual active bundle parts.
class Bundles:
    def __init__(self):
        self.parts, self.active = {"old": {"left": b"old-L", "right": b"old-R"}}, "old"
        self.reads = []

    def stage(self, version, key, value):
        self.parts.setdefault(version, {})[key] = value
        self.reads.append(dict(self.parts[self.active]))

    def publish(self, version):
        self.active = version
        self.reads.append(dict(self.parts[self.active]))


class AtomicBundles(Bundles):
    """Source observer sees only the committed image, not intermediate writes."""
    def stage(self, version, key, value):
        self.parts.setdefault(version, {})[key] = value

    def publish(self, version):
        self.active = version

    def finish(self):
        self.reads.append(dict(self.parts[self.active]))


def x17_source(store, version=None, left=None, right=None, stop_after=None):
    if version is None:
        return dict(store.parts[store.active])
    store.parts.setdefault(version, {})
    store.publish(version)
    store.stage(version, "left", left)
    if stop_after == "left":
        return "paused"
    store.stage(version, "right", right)
    return "complete"


def x17_base(store, version=None, left=None, right=None, stop_after=None):
    if version is None:
        return dict(store.parts[store.active])
    return "unavailable"


def x17_repair(store, version=None, left=None, right=None, stop_after=None):
    if version is None:
        return dict(store.parts[store.active])
    store.stage(version, "left", left)
    if stop_after == "left":
        return "paused"
    store.stage(version, "right", right)
    store.publish(version)
    return "complete"
