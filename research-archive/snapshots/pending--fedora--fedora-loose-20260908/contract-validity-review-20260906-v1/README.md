# Contract validity review v1

This separate post-hoc review preserves both original audits, every captured
submission and every original score. The source capture is
`/home/anjum/final-13-audit-20260906/evidence`.

Start with [VALIDITY_REPORT.md](VALIDITY_REPORT.md), [RUN_TABLE.md](RUN_TABLE.md)
and [SENSITIVITY.md](SENSITIVITY.md). Machine-readable tables are
[run_outcomes.csv](run_outcomes.csv) (624 runs) and
[reviewed_run_outcomes.csv](reviewed_run_outcomes.csv) (144 re-evaluated saved
submissions in X05/X06/X28).

The paper scope is six completed cohorts. The [dated scope amendment](SCOPE_AMENDMENT_20260906.md) excludes the unfinished quota-limited Spark cohort
post-hoc. Its original evidence and the already-completed pre-clarification review
remain solely as audit history. Earlier derived outputs are in
`superseded-before-spark-exclusion/`; use no estimates or examples from that folder.

The [contract review rule](REVIEW_RULE_v1.md) and [freeze receipt](FREEZE_RECEIPT.json)
predate all replay. [CORRECTION_FREEZE.json](CORRECTION_FREEZE.json)
records successful control validation before candidate
rescoring. [The correction patch](evaluator-correction-v1.patch) changes only
X05/X28 observer logic; X06 is unchanged. `review_worker.py` and `replay.py`
are the exact first-pass execution code retained under that freeze. `replay.py`
is historical and must not be used for a new seven-profile pass.

Recompute the six-cohort analyses without executing any submission:

```sh
python3 analyze_review.py
python3 verify_review.py
```

For an optional fresh offline reproduction of saved submissions, use
`python3 replay_six_cohorts.py --output /absolute/new/replay-directory`.
It enforces the six-cohort scope, writes only new logs, and never launches agents.
The necessary Python runtime, cryptography dependency and namespace tool are
recorded in the execution logs; the original study runtime is not asserted to be
identical to this review environment.

Full source excerpts, exact source links and observed effects for all reviewed
submissions are in [EVIDENCE_CARDS.md](EVIDENCE_CARDS.md). Individual offline
execution logs are under `replays/<run-id>/`. The final dataset is explicitly
`six_cohort_replay_results.json`, not the superseded all-profile replay index.

Outputs are generated only within this directory. No submission is repaired.
