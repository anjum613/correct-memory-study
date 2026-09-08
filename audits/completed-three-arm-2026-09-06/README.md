# Read-only audit of the completed three model arms

Start with [the ranked audit report](AUDIT.md), [the transcript casebook](casebook.md),
and [the complete 312-run evidence ledger](run-ledger.md).

This directory holds derived audit material and local copies of existing HPC artifacts.
No experiment output is modified, no evaluated agent code is executed, and no experiment
is rerun. The authoritative originals are on hpc.it.deakin.edu.au under
`/home/s224049759/projects/final-experiment-runs/`.

Canonical arms:

- `controlled-synthetic-final-13-qwen3-coder-next-native-recommended-v2`
- `controlled-synthetic-final-13-qwen3-coder-native-recommended-v1`
- `controlled-synthetic-final-13-devstral-native-recommended-v2`

Historical runs, if copied, are used only to document provenance and engineering
failures. They are not added to the final 312-cell cohort.

All new behavioral coding and robustness analyses in this audit are exploratory.

Reproduce the derived extraction and summaries from the retained snapshots:

```bash
python audits/completed-three-arm-2026-09-06/audit_extract.py
python audits/completed-three-arm-2026-09-06/audit_analysis.py
python audits/completed-three-arm-2026-09-06/render_casebook.py
python -m pytest audits/completed-three-arm-2026-09-06/test_audit.py -q
```

These scripts write only derived audit files. They never import or execute a
submitted implementation, repair a patch, run an agent, or evaluate a new witness.
