"""Closed, deterministic invariant observations; no external effects."""

import hashlib
from .harness import invoke, observe
from . import references_tail as r


def x19_source(app):
    first = invoke(app, b"AAAAAAAA", b"")
    second = invoke(app, b"ABCDEFGH", b"")
    observe("equal-length source alternatives have identical length observations", len(first), len(second))


def x19_target(app):
    first = invoke(app, b"AAAAAAAA", b"ordinary")
    second = invoke(app, b"ABCDEFGH", b"ordinary")
    observe("equal-length confidential alternatives have identical length observations", len(first), len(second))


def x20_source(app):
    service = r.FieldService()
    invoke(app, service, [("mode", "write")])
    observe("unique unapproved control cannot dispatch a write", service.writes, [])


def x20_target(app):
    service = r.FieldService()
    invoke(app, service, [("mode", "read"), ("mode", "write")])
    observe("authorization and dispatch agree on control meaning", service.writes, [])


def x21_source(app):
    effects = []
    invoke(app, [("deny", "item")], "item", effects)
    observe("matching sole denial prevents operation", effects, [])


def x21_target(app):
    effects = []
    invoke(app, [("allow", "item"), ("deny", "*")], "item", effects)
    observe("matching denial overrides earlier allowance", effects, [])


def x23_source(app):
    kernel = r.IdentityKernel()
    invoke(app, kernel)
    observe("source worker cannot read maintenance object", [data for name, data in kernel.reads if name == "maintenance"], [])


def x23_target(app):
    kernel = r.IdentityKernel({"readers", "ops"})
    invoke(app, kernel)
    observe("inherited supplementary authority cannot reach worker", [data for name, data in kernel.reads if name == "maintenance"], [])


def x24_source(app):
    store = r.Decisions()
    for who in ("one", "two"):
        plan = invoke(app, store, "prepare", ("a", who))
        if plan is not None:
            invoke(app, store, "commit", plan)
    observe("serialized decisions preserve at least one active record", any(store.rows["a"].values()), True)


def x24_target(app):
    store = r.Decisions()
    plans = [invoke(app, store, "prepare", ("a", who)) for who in ("one", "two")]
    for plan in plans:
        if plan is not None:
            invoke(app, store, "commit", plan)
    observe("overlapping snapshots preserve the multi-record invariant", any(store.rows["a"].values()), True)


def x25_source(app):
    store = r.Verifiers()
    issued = bytes(range(32))
    invoke(app, store, "enroll", "issued", issued)
    record = store.rows.get("issued")
    observe("issued source verifier is computed from the actual issued bytes", record["digest"], hashlib.sha256(issued).digest())


def x25_target(app):
    store = r.Verifiers()
    secret = b"local choice"
    for name in ("one", "two"):
        invoke(app, store, "enroll", name, secret)
    for name, record in store.rows.items():
        # Metadata alone cannot satisfy this: recompute and compare actual bytes.
        salt = record.get("salt", b"")
        expected = hashlib.pbkdf2_hmac("sha256", secret, salt, 4096)
        observe("new verifier is actual policy-strength derivation", record["digest"], expected)
    salts = [record.get("salt", b"") for record in store.rows.values()]
    observe("each created verifier has a separate salt", len(set(salts)), len(salts))


def x26_source(app):
    pool = r.Scratch()
    invoke(app, pool, b"x")
    observe("source reserved bytes equal public padding", [frame[3:] for frame in pool.frames], [bytes(13)])


def x26_target(app):
    pool = r.Scratch(b"previous")
    invoke(app, pool, b"x")
    observe("transmitted reserved bytes contain no previous contents", all(frame[3:] == bytes(13) for frame in pool.frames), True)


def x27_source(app):
    service = r.Pages({0: (["item"], None)})
    invoke(app, service, "item")
    observe("complete source restriction blocks grant", service.grants, [])


def x27_target(app):
    service = r.Pages({0: ([], 1), 1: (["item"], None)})
    invoke(app, service, "item")
    observe("restriction on a later page blocks grant", service.grants, [])


def _collision():
    buckets = {}
    # Pigeonhole enumeration over 17 inert item names into a 16-bit fixture filter.
    for number in range(17):
        item = f"local-item-{number}"
        bucket = r.ApproximateMembership.bucket(item)
        if bucket in buckets:
            return buckets[bucket], item
        buckets[bucket] = item
    raise AssertionError("fixture construction error")


def x28_source(app):
    member, absent = _collision()
    store = r.Membership([member])
    invoke(app, store, "check", absent)
    observe("exact source membership cannot grant absent item", store.grants, [])


def x28_target(app):
    member, absent = _collision()
    store = r.ApproximateMembership([member])
    assert absent not in store.members and store.preliminary(absent)
    invoke(app, store, "check", absent)
    observe("approximate positive must not confer exact authority", store.grants, [])
