# Prospectively amended candidate-source protocol v0.2

Status: `FROZEN_NOT_EXECUTED`

This directory resolves only the structural defects recorded by
`../audits/source-specification-v0.1-failed.json`. The four files in
`../prospective-v0.1/` remain the immutable failed specification; v0.2 does
not rewrite them.

The amendment separates a raw source object from a repository repair
candidate. Every source object encountered during a future authorized capture
must receive a content-addressed source record and exactly one final
disposition:

- `MATERIALIZED`: all required repository, snapshot, and repair identity is
  present, and the record links to at least one canonical candidate;
- `SOURCE_REJECTED`: no candidate-ledger entry is created, and one or more
  deterministic rejection codes explain why.

A candidate identity is assigned only after normalization. For GitHub, the
numeric repository ID and exact repair commit SHA are the canonical identity;
owner, name, and URL remain capture-time metadata. Missing values never match
as wildcards. Source priority orders provenance presentation only and cannot
rank, select, exclude, or replace candidates.

The source-specific documents freeze safe BugsInPy parsing, explicit OSV
advisory repair resolution, and public merged-PR search resolution. The
offline validator checks these documents without contacting any source:

```bash
python scripts/validate_candidate_source_v02.py
```

This commit does not authorize discovery execution. No BugsInPy object,
advisory, GitHub search result, candidate identity, experiment artifact, or
treatment outcome was fetched or inspected while preparing v0.2.
