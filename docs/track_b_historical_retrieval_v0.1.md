# Historical trust-transition retrieval v0.1

This is a minimal, provenance-independent Track B retrieval prototype. It does
not consume Track A candidates, make semantic `p*`/S/C/I decisions, or build
benchmark families.

The pipeline reads reviewed OSV JSON from a pinned GitHub Advisory Database
checkout. It rejects withdrawn advisories, package ecosystems outside the
existing Python/JavaScript/TypeScript support boundary, advisories outside the
versioned CWE/keyword map, and advisories without a GitHub repository reference.
It deterministically deduplicates `(repository, fix commit)` and orders records
by descending fact-only score and then advisory ID.

The v0.1 score is:

```text
8 * has exact 40-character GitHub fix commit
+ 4 * has explicit GitHub pull-request reference
+ 2 * has explicit GitHub issue reference
+ 1 * min(other explicit GitHub references, 3)
```

For only the configured top seeds, the runner caches GitHub REST evidence,
retrieves associated pull requests and two bounded relationship hops, clones a
partial repository history, and records at most 20 earlier commits for each of
at most three changed supported-language source files. Packets remain evidence
for later human semantic review and explicitly state `NOT_REVIEWED_AS_S_C_OR_I`.

Run from the repository root:

```bash
python -m cmpilot.track_b.runner \
  --advisory-repository .track-b-cache/github-advisory-database \
  --run-root track_b/runs/<UTC-RUN-ID>
```
