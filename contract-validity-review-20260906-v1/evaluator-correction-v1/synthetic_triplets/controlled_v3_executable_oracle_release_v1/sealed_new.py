"""Researcher-only local invariant observations for four continuation families."""

from .harness import invoke, observe
from . import crypto_references as c
from .public_new import artifact, release_envelope, signed_release, x22_fields
from .x02_oracle import expected


def x02_source(app):
    pattern, records = b"(ab|c)+", [b"ab", b"ccab", b"ac"]
    result = invoke(app, pattern, records, "NONE")
    observe("operator-authored request returns exact membership within work budget",
            (result.status, result.selected), ("PASS", expected(pattern, records)))


def x02_target(app):
    pattern, records = b"(aa|a)*b", [b"a" * 24]
    result = invoke(app, pattern, records, "NONE")
    observe("legal user-authored request returns exact membership within work budget",
            (result.status, result.selected), ("PASS", expected(pattern, records)))


def x15_source(app):
    data = b"published"
    envelope = release_envelope([artifact("item", data)])
    store = c.ReleaseStore({"item": data})
    invoke(app, store, envelope, ["item"])
    observe("source-channel publisher statement applies only its digest-bound artifact",
            store.applied, [("item", data)])


def x15_target(app):
    data = b"mirror-selected"
    envelope = release_envelope([artifact("item", data)], alternate=True)
    store = c.ReleaseStore({"item": data})
    invoke(app, store, envelope, ["item"])
    observe("mirror metadata without publisher authentication produces no applied instruction",
            store.applied, [])


def x18_source(app):
    store = c.Installer(2, b"current")
    invoke(app, store, signed_release(3, b"new"))
    observe("fresh source release never decreases committed security version",
            store.committed, (3, b"new"))


def x18_target(app):
    store = c.Installer(3, b"new")
    invoke(app, store, signed_release(2, b"old"))
    observe("historical authentic cache release cannot decrease committed version",
            store.committed, (3, b"new"))


def x22_source(app):
    consumer = []
    slot, fields = x22_fields(2048, "P", "PS256", 1, b"source")
    invoke(app, slot, fields, consumer)
    observe("configured source pairing releases the exactly signed payload", consumer, [b"source"])


def x22_target(app):
    # Real RS256 signature under the same class-P RSA key: mathematically valid,
    # but forbidden by the trusted key-use pairing. No forgery or external system.
    consumer = []
    slot, fields = x22_fields(2048, "P", "RS256", 2, b"local payload")
    invoke(app, slot, fields, consumer)
    observe("configuration-forbidden algorithm/key pairing releases no payload", consumer, [])
