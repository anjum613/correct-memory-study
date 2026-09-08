# Candidate discovery v0.1

This directory separates three operations:

1. `capture` makes a frozen, metadata-only forge API request and preserves the
   exact response bodies and selected response headers.
2. `materialize` operates offline, verifies every raw SHA-256, normalizes every
   returned item in source order, writes the immutable source list and
   self-excluding discovery manifest, and appends raw `DISCOVERED` records.
3. `verify` operates offline and reconstructs the expected normalized bytes,
   hashes, and ledger/source-list relationships.

The v0.1 query is frozen before its first capture. Its inclusion policy is
`ALL_RETURNED_ITEMS_IN_API_ORDER`: no observed repository may be omitted,
reordered, substituted, or added manually. Query restrictions define only the
source universe; they are not hard-gate decisions.

Discovery does not clone repositories or download archives. An immutable head
commit and Git tree identity are captured from the Git-reference and Git
commit-object metadata endpoints; the general commit endpoint, which may carry
changed-file patches, is not used.
`tree_sha256` is the SHA-256 of the canonical tree-identity envelope containing
the forge Git-tree SHA and URL; it is not a content archive digest and does not
pass the `immutable_commit` gate. Every hard gate remains `NOT_ASSESSED`.

The query uses GitHub's versioned public REST API without credentials. The
capture is deliberately sequential and small. A failed or rate-limited request
aborts without creating a completed snapshot; it is never silently retried
with a changed query.

The derived pagination audit in `audits/` records that the preserved response
reported 2,420 matches and returned eight page-1 items. The imported eight are
therefore the complete frozen page, not the complete search universe. The raw
response and all original capture artifacts remain byte-for-byte unchanged.

`../prospective-v0.1/` contains separately frozen, unexecuted specifications
for repository-repair tasks, advisory-linked repairs, and trust-boundary
issue/PR searches. Their source revisions, complete-import rules, ID ranges,
deduplication, and source-priority policy must be committed before any of those
sources is fetched or displayed.

Commands use only the standard library:

```bash
python scripts/discover_candidates.py capture
python scripts/discover_candidates.py materialize
python scripts/discover_candidates.py verify
```

The source list and discovery manifest are immutable once written. The ledger
is a status register and is cross-checked against them, but is intentionally
not hashed into the immutable discovery manifest because later append-only
status-history additions change its bytes.
