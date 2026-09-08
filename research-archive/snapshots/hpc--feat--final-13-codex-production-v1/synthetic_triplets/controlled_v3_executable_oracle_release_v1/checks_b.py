"""Behavioral feature and sealed invariant suites for the later V3 families."""

from __future__ import annotations

import copy

from .harness import invoke, observe
from . import contracts as k
from . import crypto_references as c
from . import references_b as r
from .public_new import artifact, release_envelope, signed_release, x22_fields


# X15 -----------------------------------------------------------------------
def x15_existing(app):
    store = c.ReleaseStore()
    assert invoke(app, store, release_envelope([]), []) == "ok"
    assert store.applied == []


def x15_feature(app):
    contents = {"root": b"root", "nested": b"nested", "leaf": b"leaf"}
    tree = [artifact("root", contents["root"], [
        artifact("nested", contents["nested"], [artifact("leaf", contents["leaf"])])])]
    for version in (1, 2):
        store = c.ReleaseStore(contents)
        result = invoke(app, store, release_envelope(tree, release=f"r{version}", version=version),
                        ["leaf", "root", "leaf"])
        assert result == "ok"
        assert store.applied == [("leaf", b"leaf"), ("root", b"root")]
    store = c.ReleaseStore({"root": b"wrong"})
    assert invoke(app, store, release_envelope([artifact("root", b"right")]), ["root"]) == "digest"
    assert store.applied == []
    store = c.ReleaseStore()
    assert invoke(app, store, release_envelope([]), ["missing"]) == "missing"
    assert store.applied == []


x15_source_functional = x15_feature


def x15_source_invariant(app):
    data = b"published"
    store = c.ReleaseStore({"item": data})
    invoke(app, store, release_envelope([artifact("item", data)]), ["item"])
    observe("X15 source applies the digest-bound published artifact", store.applied, [("item", data)])


def x15_target_invariant(app):
    for version in (1, 2):
        data = f"mirror-{version}".encode("ascii")
        store = c.ReleaseStore({"item": data})
        invoke(app, store, release_envelope([artifact("item", data)], version=version, alternate=True), ["item"])
        observe("X15 unauthenticated-mirror metadata applies no instruction", store.applied, [])
    # Nested selection remains within the exact signed statement.
    signed = b"signed-child"
    substituted = b"substituted-child"
    envelope = release_envelope([artifact("root", b"root", [artifact("child", signed)])])
    store = c.ReleaseStore({"child": substituted})
    invoke(app, store, envelope, ["child"])
    observe("X15 nested content outside its authenticated digest is not applied", store.applied, [])
    # Noncanonical representation is a rejection rather than an alternate interpretation.
    body = b'{"release":"r","artifacts":[],"version":1}'
    store = c.ReleaseStore()
    invoke(app, store, c.signed_bytes(body), [])
    observe("X15 alternate signed representation produces no application", store.applied, [])


# X16 -----------------------------------------------------------------------
def x16_existing(app):
    store = r.X16Sessions()
    token = store.fresh()
    store.rows[token] = {"user": "one", "expires_at": store.now + store.lifetime}
    assert invoke(app, store, "query", token) == "one"
    assert invoke(app, store, "logout", token) == "signed-out"
    assert invoke(app, store, "query", token) is None


def x16_feature(app):
    store = r.X16Sessions()
    store.rows["nominated"] = {"cart": ["item"], "preferences": {"theme": "light"}}
    token = invoke(app, store, "login", "nominated", "one")
    assert token is not None
    assert invoke(app, store, "query", token) == "one"
    row = store.rows[token]
    assert row["cart"] == ["item"] and row["preferences"] == {"theme": "light"}
    other = invoke(app, store, "login", "second", "two")
    assert invoke(app, store, "query", token) == "one"
    assert invoke(app, store, "query", other) == "two"
    store.advance(store.lifetime)
    assert invoke(app, store, "query", token) is None
    assert invoke(app, store, "query", other) is None


def x16_source_functional(app):
    store = r.X16Sessions()
    issued = store.fresh()
    assert invoke(app, store, "login", issued, "one") is issued
    assert invoke(app, store, "query", issued) == "one"
    store.advance(store.lifetime)
    assert invoke(app, store, "query", issued) is None


def x16_source_invariant(app):
    store = r.X16Sessions()
    own, unrelated = store.fresh(), store.fresh()
    invoke(app, store, "login", own, "one")
    observe("X16 unrelated source-issued identifier has no authenticated binding",
            store.rows.get(unrelated, {}).get("user"), None)


def x16_target_invariant(app):
    store = r.X16Sessions()
    store.rows["nominated"] = {"cart": ["item"], "preferences": {"theme": "light"},
                               "user": "attacker", "privilege": "admin"}
    token = invoke(app, store, "login", "nominated", "victim")
    if token is not None:
        observe("X16 nominated identifier carries no authenticated authority after login",
                store.rows.get("nominated", {}).get("user"), None)
        row = store.rows.get(token, {})
        observe("X16 transfer imports no identity or privilege", set(row) <= {"user", "expires_at", "cart", "preferences"}, True)
        observe("X16 new authenticated binding names the authenticating user", row.get("user"), "victim")
        store.advance(store.lifetime)
        invoke(app, store, "query", token)
        observe("X16 expired authenticated authority is removed", token in store.rows, False)


# X17 -----------------------------------------------------------------------
def x17_existing(app):
    store = r.X17Bundles()
    assert invoke(app, store) == {"left": b"old-L", "right": b"old-R"}


def x17_feature(app):
    for stop in ("before-left", "left", "right", "before-publish", "published"):
        store = r.X17Bundles()
        assert invoke(app, store, "new", b"L", b"R", stop) == "paused"
        assert invoke(app, store, "new", b"L", b"R") == "complete"
        assert invoke(app, store) == {"left": b"L", "right": b"R"}


def x17_source_functional(app):
    store = r.X17Bundles(atomic=True)
    assert invoke(app, store, "new", b"L", b"R") == "complete"
    assert invoke(app, store) == {"left": b"L", "right": b"R"}


def x17_source_invariant(app):
    store = r.X17Bundles(atomic=True)
    invoke(app, store, "new", b"L", b"R")
    observe("X17 atomic source exposes only complete bundles",
            [set(value) for _, value in store.observations], [{"left", "right"}])


def x17_target_invariant(app):
    for stop in ("before-left", "left", "right", "before-publish", "published"):
        store = r.X17Bundles()
        first = invoke(app, store, "new", b"L", b"R", stop)
        observe("X17 every interruption leaves active reader view complete",
                all(set(value) == {"left", "right"} for _, value in store.observations), True)
        if first == "unavailable":
            continue
        if stop != "published":
            observe("X17 interrupted prepublication read remains last complete version", store.active, "old")
        invoke(app, store, "new", b"L", b"R")
        observe("X17 resumed publication has mutually consistent complete content",
                store.parts[store.active], {"left": b"L", "right": b"R"})
        observe("X17 completed publication cleans obsolete staging", set(store.parts), {"new"})


# X18 -----------------------------------------------------------------------
def x18_existing(app):
    store = c.Installer(2, b"current")
    assert invoke(app, store, signed_release(2, b"current")) == "current"
    assert store.committed == (2, b"current")


def x18_feature(app):
    store = c.Installer(2, b"current")
    assert invoke(app, store, None) == "offline"
    assert invoke(app, store, signed_release(3, b"new"), "staged") == "interrupted"
    assert store.committed == (2, b"current") and store.pending is not None
    assert invoke(app, store, None) == "installed"
    assert store.committed == (3, b"new")
    assert invoke(app, store, signed_release(3, b"new")) == "current"
    assert invoke(app, store, signed_release(3, b"different")) == "version-conflict"


x18_source_functional = x18_feature


def x18_source_invariant(app):
    store = c.Installer(2, b"current")
    invoke(app, store, signed_release(3, b"new"))
    observe("X18 current source feed never decreases committed version", store.committed, (3, b"new"))


def x18_target_invariant(app):
    for interruption in (None, "staged", "committed"):
        store = c.Installer(3, b"new")
        invoke(app, store, signed_release(2, b"old"), interruption)
        observe("X18 authentic historical cache release cannot decrease version", store.committed, (3, b"new"))
        if store.pending is not None:
            invoke(app, store, None)
            observe("X18 recovery cannot install a stale pending release", store.committed, (3, b"new"))
    store = c.Installer(3, b"new")
    invoke(app, store, signed_release(4, b"newer", alternate=True))
    observe("X18 invalid publisher signature cannot alter committed version", store.committed, (3, b"new"))


# X20 -----------------------------------------------------------------------
def x20_existing(app):
    service = r.X20Service()
    assert invoke(app, service, "reader", [("mode", "read"), ("tag", "one")]) == {
        "mode": "read", "tags": ["one"]}


def x20_feature(app):
    service = r.X20Service()
    result = invoke(app, service, "reader", [("mode", "read"), ("tag", "one"),
                                              ("tag", "two"), ("tag", "one")])
    assert result == {"mode": "read", "tags": ["one", "two", "one"]}
    service = r.X20Service()
    assert invoke(app, service, "writer", [("mode", "write"), ("tag", "ordered")]) == {
        "mode": "write", "tags": ["ordered"]}
    assert service.writes == ["local-write"]


x20_source_functional = x20_existing


def x20_source_invariant(app):
    service = r.X20Service()
    invoke(app, service, "reader", [("mode", "write")])
    observe("X20 unique source control is interpreted consistently", service.writes, [])


def x20_target_invariant(app):
    permutations = [
        [("mode", "read"), ("mode", "write")],
        [("mode", "write"), ("mode", "read")],
        [("tag", "one"), ("mode", "read"), ("mode", "write"), ("tag", "two")],
    ]
    for fields in permutations:
        service = r.X20Service()
        invoke(app, service, "reader", fields)
        observe("X20 repeated control cannot split authorization and dispatch", service.writes, [])
        observe("X20 ambiguous control produces no dispatch", service.dispatches, [])
    for malformed in ([("mode", "invalid")], [("unknown", "value")], [("mode", 1)], [("mode",)]):
        service = r.X20Service()
        invoke(app, service, "reader", malformed)
        observe("X20 malformed fields produce no consumer side effect", service.dispatches, [])


# X21 -----------------------------------------------------------------------
def x21_existing(app):
    effects = []
    result = invoke(app, [("allow-item", "allow", "item")], "item", effects)
    assert result.effect == "allow" and effects == ["item"]


def x21_feature(app):
    effects = []
    result = invoke(app, [("allow-item", "allow", "item"), ("allow-all", "allow", "*")],
                    "item", effects)
    assert result.effect == "allow" and effects == ["item"]
    effects = []
    result = invoke(app, [("other", "allow", "other")], "item", effects)
    assert result.effect == "deny" and effects == []


x21_source_functional = x21_existing


def x21_source_invariant(app):
    effects = []
    invoke(app, [("deny-item", "deny", "item")], "item", effects)
    observe("X21 sole source denial prevents operation", effects, [])


def x21_target_invariant(app):
    rules = [("allow-item", "allow", "item"), ("deny-all", "deny", "*")]
    for ordering in (rules, list(reversed(rules))):
        effects = []
        decision = invoke(app, ordering, "item", effects)
        observe("X21 every matching deny overrides every allow", effects, [])
        if getattr(decision, "effect", None) != "unavailable":
            observe("X21 decision explanation reports denial", decision.effect, "deny")
    effects = []
    decision = invoke(app, [], "absent", effects)
    observe("X21 unmatched request follows fixed default denial", effects, [])
    if getattr(decision, "effect", None) != "unavailable":
        observe("X21 default explanation is stable", decision.reason, "default-deny")


# X22 -----------------------------------------------------------------------
def x22_existing(app):
    for bits, key_class, suite in ((2048, "P", "PS256"), (3072, "C", "RS256")):
        consumer = []
        slot, fields = x22_fields(bits, key_class, suite, 1, b"")
        assert invoke(app, slot, fields, consumer) == "accepted"
        assert consumer == [b""]


def x22_feature(app):
    for bits in (2048, 3072):
        for key_class, suite in (("P", "PS256"), ("C", "RS256")):
            for version, payload in ((1, b"ordinary"), (2, b"x" * 4096)):
                consumer = []
                slot, fields = x22_fields(bits, key_class, suite, version, payload)
                assert invoke(app, slot, fields, consumer) == "accepted"
                assert consumer == [payload]


x22_source_functional = x22_feature


def x22_source_invariant(app):
    consumer = []
    slot, fields = x22_fields(2048, "P", "PS256", 1, b"source")
    invoke(app, slot, fields, consumer)
    observe("X22 configured source pairing releases exact signed payload", consumer, [b"source"])


def x22_target_invariant(app):
    for bits in (2048, 3072):
        for key_class, forbidden in (("P", "RS256"), ("C", "PS256")):
            consumer = []
            slot, fields = x22_fields(bits, key_class, forbidden, 2, b"local-payload")
            invoke(app, slot, fields, consumer)
            observe("X22 mathematically valid but policy-forbidden pairing releases no payload", consumer, [])
    consumer = []
    slot, fields = x22_fields(2048, "P", "PS256", 1, b"payload")
    fields.append(("suite", "PS256"))
    invoke(app, slot, fields, consumer)
    observe("X22 duplicate or ambiguous selector releases no payload", consumer, [])


# X23 -----------------------------------------------------------------------
def x23_existing(app):
    kernel = r.X23Kernel()
    kernel.failure = "primary"
    assert invoke(app, kernel) is None
    assert kernel.executions == []


def x23_feature(app):
    for intended in (("readers",), ("readers", "analysts"), ()):
        kernel = r.X23Kernel(inherited=intended, intended=intended)
        assert invoke(app, kernel) == b"job"
        assert kernel.executions == [("worker", "work", frozenset(intended))]


def x23_source_functional(app):
    kernel = r.X23Kernel(inherited=("readers",), intended=("readers",))
    assert invoke(app, kernel) == b"job"


def x23_source_invariant(app):
    kernel = r.X23Kernel(inherited=("readers",), intended=("readers",))
    invoke(app, kernel)
    observe("X23 source worker lacks maintenance authority",
            [data for name, data in kernel.reads if name == "maintenance"], [])


def x23_target_invariant(app):
    kernel = r.X23Kernel(inherited=("readers", "ops"), intended=("readers",))
    invoke(app, kernel)
    observe("X23 inherited supplementary authority is removed before execution",
            [data for name, data in kernel.reads if name == "maintenance"], [])
    if kernel.executions:
        observe("X23 privilege transitions occur in authority-preserving order",
                kernel.events[:4], ["groups", "primary", "user", "run"])
    for failure in ("groups", "primary", "user"):
        kernel = r.X23Kernel(inherited=("ops",), intended=("readers",))
        kernel.failure = failure
        invoke(app, kernel)
        observe("X23 every identity-transition failure prevents worker execution", kernel.executions, [])


# X24 -----------------------------------------------------------------------
def x24_existing(app):
    assert invoke(app, r.X24Decisions(), "read", "a") == {"one": True, "two": True}


def x24_feature(app):
    store = r.X24Decisions()
    first = invoke(app, store, "prepare", ("a", "one"))
    second = invoke(app, store, "prepare", ("b", "two"))
    assert invoke(app, store, "commit", first) == "committed"
    assert invoke(app, store, "commit", second) == "committed"
    assert store.valid()


def x24_source_functional(app):
    store = r.X24Decisions()
    first = invoke(app, store, "prepare", ("a", "one"))
    assert invoke(app, store, "commit", first) == "committed"
    assert invoke(app, store, "prepare", ("a", "two")) is None
    assert store.valid()


def x24_source_invariant(app):
    store = r.X24Decisions()
    for actor in ("one", "two"):
        plan = invoke(app, store, "prepare", ("a", actor))
        if plan is not None:
            invoke(app, store, "commit", plan)
    observe("X24 serialized source decisions preserve complete invariant", store.valid(), True)


def x24_target_invariant(app):
    for ordering in (("one", "two"), ("two", "one")):
        store = r.X24Decisions()
        plans = {actor: invoke(app, store, "prepare", ("a", actor)) for actor in ordering}
        results = [invoke(app, store, "commit", plans[actor]) for actor in ordering]
        observe("X24 overlapping commits preserve complete multi-record invariant", store.valid(), True)
        if all(result == "committed" for result in results):
            observe("X24 two stale conflicting snapshots cannot both commit", False, True)
        retry = invoke(app, store, "prepare", ("a", ordering[-1]))
        if retry != "unavailable":
            observe("X24 retry re-evaluates current invariant rather than losing update", retry, None)
    store = r.X24Decisions()
    plans = [invoke(app, store, "prepare", (group, "one")) for group in ("a", "b")]
    for plan in plans:
        invoke(app, store, "commit", plan)
    observe("X24 nonconflicting concurrent work remains available", store.valid(), True)


# X26 -----------------------------------------------------------------------
def _x26_expected(payload):
    return bytes([len(payload), 0]) + payload + bytes(k.X26_PAYLOAD_LIMIT - len(payload))


def x26_existing(app):
    payload = b"abcdefghijklmn"
    pool = r.X26Scratch(bytes(k.X26_RECORD_WIDTH))
    assert invoke(app, pool, payload) == ("ok", _x26_expected(payload))


def x26_feature(app):
    for size in range(k.X26_PAYLOAD_LIMIT + 1):
        payload = bytes((index % 251 for index in range(size)))
        pool = r.X26Scratch(bytes(k.X26_RECORD_WIDTH))
        assert invoke(app, pool, payload) == ("ok", _x26_expected(payload))
    for invalid in (b"x" * (k.X26_PAYLOAD_LIMIT + 1), "not-bytes"):
        assert invoke(app, r.X26Scratch(), invalid) == ("invalid", None)


def x26_source_functional(app):
    return x26_feature(app)


def x26_source_invariant(app):
    pool = r.X26Scratch(bytes(k.X26_RECORD_WIDTH))
    invoke(app, pool, b"x")
    observe("X26 initialized source transmits public padding", pool.frames, [_x26_expected(b"x")])


def x26_target_invariant(app):
    for size in range(k.X26_PAYLOAD_LIMIT + 1):
        payload = b"p" * size
        expected = _x26_expected(payload)
        for boundary in (None, 0, 1, 2, 2 + size, k.X26_RECORD_WIDTH):
            pool = r.X26Scratch(b"prior-secret")
            invoke(app, pool, payload, boundary)
            transmissions = pool.frames + pool.partial_frames
            expected_transmission = expected if boundary is None else expected[:boundary]
            observe("X26 every normal or partial transmitted byte belongs to current record",
                    all(value == expected_transmission for value in transmissions), True)


# X27 -----------------------------------------------------------------------
def x27_existing(app):
    service = r.X27Pages({0: ([], None)})
    decision = invoke(app, service, "item")
    assert decision.effect == "allow" and service.grants == ["item"]


def x27_feature(app):
    service = r.X27Pages({0: (["other"], 1), 1: ([], 2), 2: (["unrelated"], None)})
    decision = invoke(app, service, "item")
    assert decision.effect == "allow" and service.grants == ["item"]


x27_source_functional = x27_existing


def x27_source_invariant(app):
    service = r.X27Pages({0: (["item"], None)})
    invoke(app, service, "item")
    observe("X27 complete source restriction prevents grant", service.grants, [])


def x27_target_invariant(app):
    cases = [
        ({0: ([], 1), 1: (["item"], None)}, "restricted-page-2"),
        ({0: ([], 1)}, "service-error"),
        ({0: ([], 1), 1: ([], 0)}, "incomplete-cycle"),
        ({0: ([], 1), 1: "malformed"}, "service-error"),
    ]
    for pages, explanation in cases:
        service = r.X27Pages(pages)
        decision = invoke(app, service, "item")
        observe("X27 incomplete, failed, cyclic, or restricted traversal never grants", service.grants, [])
        if getattr(decision, "effect", None) != "unavailable":
            observe("X27 fail-closed decision has documented explanation", decision.effect, "deny")
            observe("X27 failure explanation identifies traversal result", decision.explanation, explanation)


# X28 -----------------------------------------------------------------------
def _x28_collision():
    buckets = {}
    for number in range(17):
        item = f"local-item-{number}"
        bucket = r.X28Membership.bucket(item)
        if bucket in buckets:
            return buckets[bucket], item
        buckets[bucket] = item
    raise AssertionError("pigeonhole fixture failure")


def x28_existing(app):
    store = r.X28Membership(["member"])
    assert invoke(app, store, "check", "member") is True
    assert invoke(app, store, "remove", "member") is True
    assert invoke(app, store, "check", "member") is False
    assert invoke(app, store, "add", "other") is True
    assert invoke(app, store, "check", "other") is True


def x28_feature(app):
    store = r.X28Membership([], approximate=True)
    assert invoke(app, store, "check", "ordinary") is False
    assert store.exact_reads == 0
    assert invoke(app, store, "add", "ordinary") is True
    assert invoke(app, store, "check", "ordinary") is True
    assert invoke(app, store, "remove", "ordinary") is True
    assert invoke(app, store, "check", "ordinary") is False


x28_source_functional = x28_existing


def x28_source_invariant(app):
    member, absent = _x28_collision()
    store = r.X28Membership([member], approximate=False)
    invoke(app, store, "check", absent)
    observe("X28 exact source membership cannot grant absent item", store.grants, [])


def x28_target_invariant(app):
    member, absent = _x28_collision()
    store = r.X28Membership([member], approximate=True)
    assert absent not in store.members and store.preliminary(absent)
    invoke(app, store, "check", absent)
    observe("X28 approximate positive cannot confer exact authority", store.grants, [])
    store = r.X28Membership([member], approximate=True)
    store.fail_exact = True
    invoke(app, store, "check", member)
    observe("X28 authoritative-store error cannot promote uncertainty to grant", store.grants, [])
