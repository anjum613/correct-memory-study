# Stage-1 static screening v0.1

Status: `COMPLETED_STATIC_FACT_CAPTURE`

The frozen inspector at commit
`a706f3271b68e6f75326bfe77a733bd09a453289` processed all eight records from
`github-python-2024-medium-001` in source-list order. The input source-list
SHA-256 is
`64d4e57420060938e45d1446a93c73b81538b536b211e9e709e465f7b41ddd68`.
The batch ran from `2026-08-12T17:42:46Z` through
`2026-08-12T17:42:53Z`.

The operation used fresh bare depth-1 repositories and exact commit fetches.
It created no checkout and executed no candidate code, installation, test,
service, model, treatment, or experiment. Temporary bare repositories were
removed after the atomic result directory was written.

## Gate outcome

- `immutable_commit`: eight `PASS`, zero `FAIL`, zero `NEEDS_REVIEW`;
- `usable_licence`: six `PASS`, zero `FAIL`, two `NEEDS_REVIEW`;
- `reproducible_setup`: eight `NEEDS_REVIEW`;
- `deterministic_baseline_tests`: eight `NEEDS_REVIEW`;
- `manageable_task_size`: eight `NEEDS_REVIEW`; and
- `no_proprietary_credentials_or_uncontrolled_service`: eight
  `NEEDS_REVIEW`.

No candidate was excluded or advanced. All eight remain `DISCOVERED`, and no
status-history event was appended. Mechanism gates remain `NOT_ASSESSED`;
trust families, decisive conditions, triplets, scores, ranks, and benchmark
selection remain unset.

`results/github-python-2024-medium-001/` contains one hashed result per
candidate, a derived summary, and the batch manifest. Re-run `verify` to check
the frozen inputs, complete artifact inventory, method commit, candidate
order, hashes, execution boundary, gate/state consistency, summary, and ledger
links:

```bash
python scripts/stage1_screen_candidates.py verify
```

Static signal absence is not evidence that a service, GPU, database, network,
or proprietary dependency is unnecessary. Setup-command and baseline-command
entries are candidates inferred from files; none was executed.
