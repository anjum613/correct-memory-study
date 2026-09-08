"""Complete closed reference states for X16--X18, X20--X21, X23--X24,
X26--X28.  X19 and X25 remain preserved, failed, and prospectively excluded.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib

from . import contracts as k


# ---------------------------------------------------------------------------
# X16: server-controlled authenticated session bindings and bounded transfer.

class X16Sessions:
    def __init__(self, now=100, lifetime=20):
        self.rows = {}
        self.now = now
        self.lifetime = lifetime
        self.serial = 0

    def fresh(self):
        self.serial += 1
        # A fixture-only opaque identity; never a deployable session credential.
        return ("server-session", self.serial, object())

    def advance(self, amount):
        self.now += amount

    def active(self, identity):
        row = self.rows.get(identity)
        if row is not None and row.get("expires_at", self.now + 1) <= self.now:
            self.rows.pop(identity, None)
            return None
        return row


def x16_source(store, operation, session, user=None):
    if operation == "login":
        row = store.rows.setdefault(session, {})
        row["user"] = user
        row["expires_at"] = store.now + store.lifetime
        return session
    if operation == "logout":
        store.rows.pop(session, None)
        return "signed-out"
    if operation == "query":
        row = store.active(session)
        return None if row is None else row.get("user")
    return None


def x16_base(store, operation, session, user=None):
    if operation == "login":
        return None
    return x16_source(store, operation, session, user)


def x16_repair(store, operation, session, user=None):
    if operation != "login":
        return x16_source(store, operation, session, user)
    previous = store.rows.pop(session, {})
    fresh = store.fresh()
    row = {"user": user, "expires_at": store.now + store.lifetime}
    for name in ("cart", "preferences"):
        if name in previous:
            row[name] = copy.deepcopy(previous[name])
    store.rows[fresh] = row
    return fresh


# ---------------------------------------------------------------------------
# X17: resumable bundle state machine with complete-before-active publication.

class X17Bundles:
    def __init__(self, atomic=False):
        self.atomic = atomic
        self.parts = {"old": {"left": b"old-L", "right": b"old-R"}}
        self.active = "old"
        self.observations = []
        self.events = []

    def read(self):
        value = copy.deepcopy(self.parts[self.active])
        self.observations.append((self.active, value))
        return value

    def stage(self, version, name, value):
        self.parts.setdefault(version, {})[name] = bytes(value)
        self.events.append(("stage", version, name))
        if not self.atomic:
            self.read()

    def publish(self, version):
        self.active = version
        self.events.append(("publish", version))
        if not self.atomic:
            self.read()

    def cleanup(self):
        for version in list(self.parts):
            if version != self.active:
                del self.parts[version]
        self.events.append(("cleanup", self.active))


def _x17_stopped(stop_after, point):
    return stop_after == point


def x17_source(store, version=None, left=None, right=None, stop_after=None):
    if version is None:
        return store.read()
    if not isinstance(version, str) or not isinstance(left, bytes) or not isinstance(right, bytes):
        return "invalid"
    store.parts.setdefault(version, {})
    store.publish(version)
    if _x17_stopped(stop_after, "published"):
        return "paused"
    if _x17_stopped(stop_after, "before-left"):
        return "paused"
    store.stage(version, "left", left)
    if _x17_stopped(stop_after, "left"):
        return "paused"
    store.stage(version, "right", right)
    if _x17_stopped(stop_after, "right"):
        return "paused"
    if _x17_stopped(stop_after, "before-publish"):
        return "paused"
    if store.atomic:
        store.read()
    return "complete"


def x17_base(store, version=None, left=None, right=None, stop_after=None):
    return store.read() if version is None else "unavailable"


def x17_repair(store, version=None, left=None, right=None, stop_after=None):
    if version is None:
        return store.read()
    if not isinstance(version, str) or not version or not isinstance(left, bytes) or not isinstance(right, bytes):
        return "invalid"
    if version == store.active:
        if store.parts[version] != {"left": left, "right": right}:
            return "conflict"
        store.cleanup()
        return "complete"
    staged = store.parts.setdefault(version, {})
    if staged and any(name in staged and staged[name] != value
                      for name, value in (("left", left), ("right", right))):
        return "conflict"
    if _x17_stopped(stop_after, "before-left"):
        return "paused"
    store.stage(version, "left", left)
    if _x17_stopped(stop_after, "left"):
        return "paused"
    store.stage(version, "right", right)
    if _x17_stopped(stop_after, "right"):
        return "paused"
    if set(store.parts[version]) != {"left", "right"}:
        return "invalid"
    if _x17_stopped(stop_after, "before-publish"):
        return "paused"
    store.publish(version)
    if _x17_stopped(stop_after, "published"):
        return "paused"
    store.cleanup()
    return "complete"


# ---------------------------------------------------------------------------
# X20: one parsed control interpretation shared by authorization and dispatch.

class X20Service:
    def __init__(self):
        self.dispatches = []
        self.writes = []

    def dispatch(self, parsed):
        self.dispatches.append(copy.deepcopy(parsed))
        if parsed["mode"] == "write":
            self.writes.append("local-write")
        return {"mode": parsed["mode"], "tags": list(parsed["tags"])}


def _x20_parse(fields, reject_repeated_control):
    if not isinstance(fields, (list, tuple)):
        return None
    controls, tags = [], []
    for pair in fields:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return None
        name, value = pair
        if not isinstance(name, str) or not isinstance(value, str):
            return None
        if name == "mode":
            controls.append(value)
        elif name == "tag":
            tags.append(value)
        else:
            return None
    if not controls:
        controls = ["read"]
    if any(value not in k.X20_MODES for value in controls):
        return None
    if reject_repeated_control and len(controls) != 1:
        return None
    return {"authorization_mode": controls[0], "mode": controls[-1], "tags": tags}


def _x20_execute(service, principal, fields, reject_repeated_control):
    parsed = _x20_parse(fields, reject_repeated_control)
    if parsed is None:
        return "invalid"
    if parsed["authorization_mode"] == "write" and principal != "writer":
        return "denied"
    return service.dispatch(parsed)


def x20_source(service, principal, fields):
    if not isinstance(fields, (list, tuple)):
        return "invalid"
    controls, tags = [], []
    for pair in fields:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return "invalid"
        name, value = pair
        if not isinstance(name, str) or not isinstance(value, str):
            return "invalid"
        if name == "mode":
            controls.append(value)
        elif name == "tag":
            tags.append(value)
        else:
            return "invalid"
    if not controls:
        controls = ["read"]
    if any(value not in k.X20_MODES for value in controls):
        return "invalid"
    if controls[0] == "write" and principal != "writer":
        return "denied"
    return service.dispatch({"authorization_mode": controls[0], "mode": controls[-1], "tags": tags})


def x20_base(service, principal, fields):
    names = [pair[0] for pair in fields] if isinstance(fields, (list, tuple)) and all(
        isinstance(pair, (list, tuple)) and len(pair) == 2 for pair in fields) else []
    if len(names) != len(set(names)):
        return "unavailable"
    return _x20_execute(service, principal, fields, True)


def x20_repair(service, principal, fields):
    parsed = _x20_parse(fields, True)
    if parsed is None:
        return "invalid"
    if parsed["mode"] == "write" and principal != "writer":
        return "denied"
    parsed["authorization_mode"] = parsed["mode"]
    return service.dispatch(parsed)


# ---------------------------------------------------------------------------
# X21: deny-overrides evaluation with stable, complete explanations.

@dataclass(frozen=True)
class X21Decision:
    effect: str
    matched: tuple
    reason: str


def _x21_match(selector, resource):
    return selector == "*" or selector == resource


def _x21_apply(effect, resource, effects):
    if effect == "allow":
        effects.append(resource)


def x21_source(rules, resource, effects):
    for rule_id, effect, selector in rules:
        if _x21_match(selector, resource):
            _x21_apply(effect, resource, effects)
            return X21Decision(effect, (rule_id,), "first-match")
    return X21Decision("deny", (), "default-deny")


def x21_base(rules, resource, effects):
    if len(rules) > 1:
        return X21Decision("unavailable", (), "overlap-unsupported")
    return x21_repair(rules, resource, effects)


def x21_repair(rules, resource, effects):
    if not isinstance(rules, (list, tuple)):
        return X21Decision("deny", (), "invalid-policy")
    matched = []
    for rule in rules:
        if not isinstance(rule, (list, tuple)) or len(rule) != 3:
            return X21Decision("deny", (), "invalid-policy")
        rule_id, effect, selector = rule
        if not all(isinstance(value, str) for value in rule) or effect not in ("allow", "deny"):
            return X21Decision("deny", (), "invalid-policy")
        if _x21_match(selector, resource):
            matched.append((rule_id, effect))
    decision = "deny" if any(effect == "deny" for _, effect in matched) else (
        "allow" if any(effect == "allow" for _, effect in matched) else "deny")
    if decision == "allow":
        effects.append(resource)
    reason = "deny-overrides" if matched else "default-deny"
    return X21Decision(decision, tuple(sorted(rule_id for rule_id, _ in matched)), reason)


# ---------------------------------------------------------------------------
# X23: complete identity transition in an in-memory kernel simulator.

class X23Kernel:
    def __init__(self, inherited=("readers",), intended=("readers",)):
        self.user = "launcher"
        self.primary = "launch"
        self.groups = set(inherited)
        self.intended = set(intended)
        self.failure = None
        self.events = []
        self.executions = []
        self.reads = []

    def set_groups(self, groups):
        self.events.append("groups")
        if self.failure == "groups" or self.user != "launcher":
            return False
        self.groups = set(groups)
        return True

    def set_primary(self, group):
        self.events.append("primary")
        if self.failure == "primary" or self.user != "launcher":
            return False
        self.primary = group
        return True

    def set_user(self, user):
        self.events.append("user")
        if self.failure == "user":
            return False
        self.user = user
        return True

    def run(self):
        self.events.append("run")
        self.executions.append((self.user, self.primary, frozenset(self.groups)))
        resources = {"ordinary": ("work", b"job"), "shared": ("readers", b"shared"),
                     "analysis": ("analysts", b"analysis"), "maintenance": ("ops", b"private")}
        for name, (group, data) in resources.items():
            if group == self.primary or group in self.groups:
                self.reads.append((name, data))
        return b"job"


def x23_source(kernel):
    if not kernel.set_primary("work") or not kernel.set_user("worker"):
        return None
    return kernel.run()


def x23_base(kernel):
    return None


def x23_repair(kernel):
    if not kernel.set_groups(kernel.intended):
        return None
    if not kernel.set_primary("work"):
        return None
    if not kernel.set_user("worker"):
        return None
    return kernel.run()


# ---------------------------------------------------------------------------
# X24: optimistic decisions scoped to the complete per-group invariant.

class X24Decisions:
    def __init__(self):
        self.rows = {
            "a": {"one": True, "two": True},
            "b": {"one": True, "two": True},
        }
        self.revisions = {"a": 0, "b": 0}
        self.events = []

    def valid(self):
        return all(any(row.values()) for row in self.rows.values())

    def commit(self, group, actor):
        self.rows[group][actor] = False
        self.revisions[group] += 1
        self.events.append(("commit", group, actor))


def _x24_read(store, group):
    return copy.deepcopy(store.rows[group])


def _x24_prepare(store, value):
    group, actor = value
    if group not in store.rows or actor not in store.rows[group] or not store.rows[group][actor]:
        return None
    if not any(active for other, active in store.rows[group].items() if other != actor):
        return None
    return (group, actor, store.revisions[group])


def x24_source(store, operation, value):
    if operation == "read":
        return _x24_read(store, value)
    if operation == "prepare":
        return _x24_prepare(store, value)
    if operation == "commit":
        group, actor, _revision = value
        store.commit(group, actor)
        return "committed"
    return "invalid"


def x24_base(store, operation, value):
    return _x24_read(store, value) if operation == "read" else "unavailable"


def x24_repair(store, operation, value):
    if operation != "commit":
        return x24_source(store, operation, value)
    group, actor, revision = value
    if group not in store.rows or actor not in store.rows[group]:
        return "invalid"
    if store.revisions[group] != revision:
        return "retry"
    # Recheck the complete invariant in the committed state, not only the snapshot.
    if not any(active for other, active in store.rows[group].items() if other != actor):
        return "conflict"
    store.commit(group, actor)
    return "committed"


# ---------------------------------------------------------------------------
# X26: every transmitted byte initialized for all payload and partial-send paths.

class X26Scratch:
    def __init__(self, previous=b"previous"):
        pattern = previous or b"\xff"
        self.previous = bytes((pattern * k.X26_RECORD_WIDTH)[:k.X26_RECORD_WIDTH])
        self.frames = []
        self.partial_frames = []

    def take(self):
        return bytearray(self.previous)

    def transmit(self, block, fail_after=None):
        value = bytes(block)
        if fail_after is not None:
            if not 0 <= fail_after <= len(value):
                raise ValueError("invalid partial boundary")
            self.partial_frames.append(value[:fail_after])
            return ("error", value[:fail_after])
        self.frames.append(value)
        return ("ok", value)


def _x26_build(pool, payload, fail_after, initialize):
    if not isinstance(payload, bytes) or len(payload) > k.X26_PAYLOAD_LIMIT:
        return ("invalid", None)
    block = pool.take()
    if initialize:
        block[:] = bytes(k.X26_RECORD_WIDTH)
    block[0] = len(payload)
    block[1] = 0
    block[2:2 + len(payload)] = payload
    try:
        return pool.transmit(block, fail_after)
    except ValueError:
        return ("invalid", None)


def x26_source(pool, payload, fail_after=None):
    if not isinstance(payload, bytes) or len(payload) > k.X26_PAYLOAD_LIMIT:
        return ("invalid", None)
    block = pool.take()
    block[0] = len(payload)
    block[1] = 0
    block[2:2 + len(payload)] = payload
    try:
        return pool.transmit(block, fail_after)
    except ValueError:
        return ("invalid", None)


def x26_base(pool, payload, fail_after=None):
    if not isinstance(payload, bytes) or len(payload) != k.X26_PAYLOAD_LIMIT:
        return ("unavailable", None)
    return _x26_build(pool, payload, fail_after, True)


def x26_repair(pool, payload, fail_after=None):
    return _x26_build(pool, payload, fail_after, True)


# ---------------------------------------------------------------------------
# X27: complete pagination before absence-based permission, fixed fail closed.

@dataclass(frozen=True)
class X27Decision:
    effect: str
    explanation: str
    pages: int


class X27Pages:
    ERROR = object()

    def __init__(self, pages):
        self.pages = dict(pages)
        self.calls = []
        self.grants = []

    def fetch(self, cursor):
        self.calls.append(cursor)
        return self.pages.get(cursor, self.ERROR)


def _x27_decide(service, resource, complete):
    cursor = 0
    seen = set()
    count = 0
    while cursor is not None:
        if cursor in seen:
            return X27Decision("deny", "incomplete-cycle", count)
        seen.add(cursor)
        page = service.fetch(cursor)
        count += 1
        if page is service.ERROR or not isinstance(page, tuple) or len(page) != 2:
            return X27Decision("deny", "service-error", count)
        restrictions, following = page
        if not isinstance(restrictions, (list, tuple)) or any(not isinstance(item, str) for item in restrictions):
            return X27Decision("deny", "malformed-page", count)
        if resource in restrictions:
            return X27Decision("deny", f"restricted-page-{count}", count)
        if not complete:
            cursor = None
        else:
            cursor = following
    service.grants.append(resource)
    return X27Decision("allow", "complete-no-restriction", count)


def x27_source(service, resource):
    page = service.fetch(0)
    if page is service.ERROR or not isinstance(page, tuple) or len(page) != 2:
        return X27Decision("deny", "service-error", 1)
    restrictions, _continuation = page
    if not isinstance(restrictions, (list, tuple)) or any(not isinstance(item, str) for item in restrictions):
        return X27Decision("deny", "malformed-page", 1)
    if resource in restrictions:
        return X27Decision("deny", "restricted-page-1", 1)
    service.grants.append(resource)
    return X27Decision("allow", "complete-no-restriction", 1)


def x27_base(service, resource):
    page = service.pages.get(0, service.ERROR)
    if page is service.ERROR or not isinstance(page, tuple) or len(page) != 2 or page[1] is not None:
        return X27Decision("unavailable", "pagination-unsupported", 0)
    return _x27_decide(service, resource, True)


def x27_repair(service, resource):
    return _x27_decide(service, resource, True)


# ---------------------------------------------------------------------------
# X28: approximate positives are confirmed by the authoritative local store.

class X28Membership:
    def __init__(self, members=(), approximate=False):
        self.members = set(members)
        self.approximate = approximate
        self.grants = []
        self.exact_reads = 0
        self.fail_exact = False

    @staticmethod
    def bucket(item):
        return hashlib.sha256(item.encode("ascii")).digest()[0] % 16

    def preliminary(self, item):
        if not self.approximate:
            return item in self.members
        bits = 0
        for member in self.members:
            bits |= 1 << self.bucket(member)
        return bool(bits & (1 << self.bucket(item)))

    def exact(self, item):
        self.exact_reads += 1
        if self.fail_exact:
            raise OSError("controlled authoritative-store failure")
        return item in self.members


def _x28_update(store, operation, item):
    if operation == "add":
        store.members.add(item)
        return True
    if operation == "remove":
        store.members.discard(item)
        return True
    return None


def x28_source(store, operation, item):
    update = _x28_update(store, operation, item)
    if update is not None:
        return update
    if operation != "check":
        return False
    if store.preliminary(item):
        store.grants.append(item)
        return True
    return False


def x28_base(store, operation, item):
    update = _x28_update(store, operation, item)
    if update is not None:
        return update
    if operation != "check":
        return False
    try:
        if store.exact(item):
            store.grants.append(item)
            return True
    except OSError:
        return False
    return False


def x28_repair(store, operation, item):
    update = _x28_update(store, operation, item)
    if update is not None:
        return update
    if operation != "check" or not store.preliminary(item):
        return False
    try:
        if store.exact(item):
            store.grants.append(item)
            return True
    except OSError:
        return False
    return False
