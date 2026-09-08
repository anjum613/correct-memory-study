"""Local policy/state/buffer reference procedures; no OS or network authority."""

import hashlib
import zlib


# X19: response bytes stay inside the fixture; only encoded length is observed.
def x19_source(secret, public):
    data = len(secret).to_bytes(2, "big") + secret + public
    return b"J" + zlib.compress(data)


def x19_base(secret, public):
    return x19_repair(secret, b"")


def x19_repair(secret, public):
    encoded = zlib.compress(secret)
    # The fixture secret length class is eight bytes. Both streams still compress.
    if len(secret) != 8 or len(encoded) > 64:
        return None
    return b"P" + len(encoded).to_bytes(2, "big") + encoded.ljust(64, b"\0") + zlib.compress(public)


# X20: a closed field protocol with an actual local dispatch effect.
class FieldService:
    def __init__(self):
        self.writes = []

    def dispatch(self, fields):
        modes = [value for name, value in fields if name == "mode"]
        mode = modes[-1] if modes else "read"
        if mode == "write":
            self.writes.append("local-write")
        return {"mode": mode, "tags": [value for name, value in fields if name == "tag"]}


def x20_source(service, fields):
    modes = [value for name, value in fields if name == "mode"]
    if modes and modes[0] != "read":
        return None
    return service.dispatch(fields)


def x20_base(service, fields):
    if len({name for name, _ in fields}) != len(fields):
        return None
    return x20_source(service, fields)


def x20_repair(service, fields):
    modes = [value for name, value in fields if name == "mode"]
    if any(mode != "read" for mode in modes):
        return None
    canonical = [("mode", "read")] + [(name, value) for name, value in fields if name != "mode"]
    return service.dispatch(canonical)


# X21: denied decisions cannot append a protected local operation.
def x21_source(rules, resource, effects):
    for effect, selector in rules:
        if selector in (resource, "*"):
            if effect == "allow":
                effects.append(resource)
            return effect
    return "deny"


def x21_base(rules, resource, effects):
    if len(rules) > 1:
        return "unavailable"
    return x21_source(rules, resource, effects)


def x21_repair(rules, resource, effects):
    matched = [effect for effect, selector in rules if selector in (resource, "*")]
    if "deny" in matched or "allow" not in matched:
        return "deny"
    effects.append(resource)
    return "allow"


# X23: model kernel identity/access checks, never setuid/setgid or real files.
class IdentityKernel:
    def __init__(self, supplementary=("readers",)):
        self.user, self.primary, self.groups = "launcher", "launch", set(supplementary)
        self.executions, self.reads, self.fail = [], [], None
        self.intended_groups = {"readers"}

    def set_groups(self, groups):
        if self.fail == "groups" or self.user != "launcher":
            return False
        self.groups = set(groups)
        return True

    def set_primary(self, group):
        if self.fail == "primary" or self.user != "launcher":
            return False
        self.primary = group
        return True

    def set_user(self, user):
        if self.fail == "user":
            return False
        self.user = user
        return True

    def run(self):
        self.executions.append((self.user, self.primary, sorted(self.groups)))
        files = {"ordinary": ("work", b"job-data"), "shared": ("readers", b"shared-data"),
                 "maintenance": ("ops", b"ops-data")}
        for name, (group, data) in files.items():
            if group == self.primary or group in self.groups:
                self.reads.append((name, data))
        return next((data for name, data in self.reads if name == "ordinary"), None)


def x23_source(kernel):
    if not kernel.set_primary("work") or not kernel.set_user("worker"):
        return None
    return kernel.run()


def x23_base(kernel):
    return None


def x23_repair(kernel):
    if not kernel.set_groups(kernel.intended_groups):
        return None
    if not kernel.set_primary("work") or not kernel.set_user("worker"):
        return None
    return kernel.run()


# X24: optimistic transaction snapshots and per-invariant compare/exchange.
class Decisions:
    def __init__(self):
        self.rows = {"a": {"one": True, "two": True}, "b": {"one": True, "two": True}}
        self.revisions = {"a": 0, "b": 0}

    def commit(self, group, actor):
        self.rows[group][actor] = False
        self.revisions[group] += 1


def x24_source(store, operation, value):
    if operation == "read":
        return dict(store.rows[value])
    if operation == "prepare":
        group, actor = value
        if not any(active for who, active in store.rows[group].items() if who != actor):
            return None
        return group, actor, store.revisions[group]
    group, actor, revision = value
    store.commit(group, actor)
    return "committed"


def x24_base(store, operation, value):
    return x24_source(store, operation, value) if operation == "read" else None


def x24_repair(store, operation, value):
    if operation != "commit":
        return x24_source(store, operation, value)
    group, actor, revision = value
    if store.revisions[group] != revision:
        return "retry"
    store.commit(group, actor)
    return "committed"


# X25: test-only enrollment material; verification never targets an account.
class Verifiers:
    def __init__(self):
        self.rows, self.next_salt = {}, 0

    def salt(self):
        self.next_salt += 1
        return self.next_salt.to_bytes(16, "big")


def x25_source(store, operation, name, value):
    if operation == "enroll":
        store.rows[name] = {"version": 1, "digest": hashlib.sha256(value).digest()}
        return "enrolled"
    record = store.rows.get(name)
    return record is not None and record["digest"] == hashlib.sha256(value).digest()


def x25_base(store, operation, name, value):
    return None if operation == "enroll" else x25_source(store, operation, name, value)


def x25_repair(store, operation, name, value):
    if operation == "enroll":
        salt = store.salt()
        store.rows[name] = {"version": 2, "salt": salt, "iterations": 4096,
                            "digest": hashlib.pbkdf2_hmac("sha256", value, salt, 4096)}
        return "enrolled"
    record = store.rows.get(name)
    if record is None:
        return False
    if record["version"] == 1:
        good = record["digest"] == hashlib.sha256(value).digest()
        if good:
            x25_repair(store, "enroll", name, value)
        return good
    if record["version"] != 2 or record.get("iterations") != 4096 or len(record.get("salt", b"")) != 16:
        return False
    return record["digest"] == hashlib.pbkdf2_hmac("sha256", value, record["salt"], 4096)


# X26: actual transmitted byte arrays, with a closed in-memory scratch allocator.
class Scratch:
    def __init__(self, previous=b"\0"):
        self.previous, self.frames = previous, []

    def take(self):
        return bytearray((self.previous * 16)[:16])

    def transmit(self, data):
        self.frames.append(bytes(data))
        return bytes(data)


def x26_source(pool, payload):
    if not isinstance(payload, bytes) or len(payload) > 14:
        return None
    block = pool.take()
    block[0], block[1] = len(payload), 0
    block[2:2 + len(payload)] = payload
    return pool.transmit(block)


def x26_base(pool, payload):
    return x26_source(pool, payload) if len(payload) == 14 else None


def x26_repair(pool, payload):
    if not isinstance(payload, bytes) or len(payload) > 14:
        return None
    block = pool.take()
    block[:] = bytes(16)
    block[0] = len(payload)
    block[2:2 + len(payload)] = payload
    return pool.transmit(block)


# X27: policy pages are local immutable fixture records, never HTTP responses.
class Pages:
    def __init__(self, pages):
        self.pages, self.calls, self.grants = pages, [], []

    def fetch(self, cursor):
        self.calls.append(cursor)
        return self.pages.get(cursor)


def x27_source(service, resource):
    page = service.fetch(0)
    if page is None:
        return "unavailable"
    restrictions, continuation = page
    if resource in restrictions:
        return "deny"
    service.grants.append(resource)
    return "allow"


def x27_base(service, resource):
    page = service.fetch(0)
    if page is None or page[1] is not None:
        return "unavailable"
    return x27_source(service, resource)


def x27_repair(service, resource):
    cursor, seen = 0, set()
    while cursor is not None:
        if cursor in seen:
            return "unavailable"
        seen.add(cursor)
        page = service.fetch(cursor)
        if page is None:
            return "unavailable"
        restrictions, cursor = page
        if resource in restrictions:
            return "deny"
    service.grants.append(resource)
    return "allow"


# X28: a real finite bitset prefilter, not a supplied false-positive flag.
class Membership:
    def __init__(self, members=()):
        self.members, self.grants, self.exact_reads = set(members), [], 0

    def preliminary(self, item):
        return item in self.members

    def exact(self, item):
        self.exact_reads += 1
        return item in self.members


class ApproximateMembership(Membership):
    @staticmethod
    def bucket(item):
        return hashlib.sha256(item.encode("ascii")).digest()[0] % 16

    def preliminary(self, item):
        bits = 0
        for member in self.members:
            bits |= 1 << self.bucket(member)
        return bool(bits & (1 << self.bucket(item)))


def x28_source(store, operation, item):
    if operation == "add":
        store.members.add(item)
        return True
    if operation == "remove":
        store.members.discard(item)
        return True
    if store.preliminary(item):
        store.grants.append(item)
        return True
    return False


def x28_base(store, operation, item):
    if operation != "check":
        return x28_source(store, operation, item)
    if store.exact(item):
        store.grants.append(item)
        return True
    return False


def x28_repair(store, operation, item):
    if operation != "check":
        return x28_source(store, operation, item)
    if store.preliminary(item) and store.exact(item):
        store.grants.append(item)
        return True
    return False
