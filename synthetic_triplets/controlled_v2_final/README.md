# Controlled synthetic v2: machine cohort and human-review resolution

This directory contains the exact 20-family machine-accepted cohort assembled
after the original construction pass, a uniform continuation, and the frozen
reserve queue.

The machine-stage artifacts remain historical and unchanged. The downstream
human decision is frozen in `human_review_resolution.json`; it supersedes the
machine manifest's pending-review status without rewriting that manifest.

Current disposition:

- F01, F02, F04, F08, F17, and F20 are permanently retained;
- the other 14 machine-accepted family versions are permanently rejected, with
  the review stage, failed criteria, and reasons recorded in the resolution;
- rejected artifacts remain in `accepted/` because that directory records
  machine acceptance, not final human admission;
- neither the original 20-family cohort nor the intermediate 12-family cohort
  may be tagged as a final cohort;
- confirmatory evaluation remains blocked pending a separately frozen protocol
  for the retained six-family pool.

Historical machine-stage state:

- 20/20 selected families reproduce `COMPLETE_ACCEPT` on all 21 deterministic
  checks;
- all selected B implementations, feature patches, security patches, and full
  candidate trees have unique SHA-256 hashes;
- 20 distinct mechanism labels and 20 distinct mismatch axes are represented;
- F10 and F13 were retired after eight unsuccessful attempts each;
- pre-frozen reserves R01 and R02 occupy those two slots;
- R03, R04, and R05 were never run after the cohort reached 20;
- the primary AI semantic audit passed every selected family as strong and clean;
- subsequent human semantic review overruled final admission for 14 families.

`cohort_manifest.json` is the machine-verifiable provenance record. `accepted/`
contains stable copies of the constructor-owned B, `feature.patch`, and
`security.patch` artifacts, plus the frozen specification and provenance row for
each family. Complete accepted and rejected constructor traces remain under the
two acquisition roots referenced by the manifest.

Run `python scripts/verify_synthetic_human_resolution.py --check` to verify the
frozen resolution, its exact retained/rejected sets, and its binding to the
machine-cohort manifest.

Do not expose accepted patches, sealed tests, constructor traces, validation
decisions, or this researcher-side directory to evaluated agents.
