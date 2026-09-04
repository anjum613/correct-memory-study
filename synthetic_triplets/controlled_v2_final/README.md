# Controlled synthetic v2: assembled machine cohort

This directory contains the exact 20-family machine-accepted cohort assembled
after the original construction pass, a uniform continuation, and the frozen
reserve queue.

Current state:

- 20/20 selected families reproduce `COMPLETE_ACCEPT` on all 21 deterministic
  checks;
- all selected B implementations, feature patches, security patches, and full
  candidate trees have unique SHA-256 hashes;
- 20 distinct mechanism labels and 20 distinct mismatch axes are represented;
- F10 and F13 were retired after eight unsuccessful attempts each;
- pre-frozen reserves R01 and R02 occupy those two slots;
- R03, R04, and R05 were never run after the cohort reached 20;
- the primary AI semantic audit passes every selected family as strong and clean;
- blinded human semantic review remains mandatory before confirmatory evaluation.

`cohort_manifest.json` is the machine-verifiable provenance record. `accepted/`
contains stable copies of the constructor-owned B, `feature.patch`, and
`security.patch` artifacts, plus the frozen specification and provenance row for
each family. Complete accepted and rejected constructor traces remain under the
two acquisition roots referenced by the manifest.

Do not expose accepted patches, sealed tests, constructor traces, validation
decisions, or this researcher-side directory to evaluated agents.
