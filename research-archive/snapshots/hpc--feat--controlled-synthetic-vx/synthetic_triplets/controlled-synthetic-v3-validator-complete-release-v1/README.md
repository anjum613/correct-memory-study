# Validator-complete release request: blocked by frozen canonical tests

Release ID: `controlled-synthetic-v3-validator-complete-release-v1`.

Status: **BLOCKED_NONBEHAVIORAL_CANONICAL_TESTS**. This directory records the
requested version and reproducible readiness evidence. It is not a completed or
construction-ready validator release. No constructor attempts were consumed.

The base corrected-input release at commit
`1dbd33cec574a8acfd15f05077469655aa894f47` is preserved unchanged. Its actual manifest
SHA-256 is `59cfd1575f5922ff2f2a4aaf4b3b50f84addd4ee605e17f86ab8e1076a511e66`;
the different hash printed in the previous assistant's final message was incorrect.

All 28 frozen `public_tests.py` files check only the presence of three payload
files. Each `sealed_tests.py` checks the length and nonempty strings of a literal
list of security descriptions. Neither test calls or inspects candidate behavior.
The source functions return a generic family/value dictionary, and target stubs
raise `NotImplementedError`. These inputs do not implement the 28 domain-specific
procedures or their focal witnesses.

The preflight runs the exact frozen public/sealed test functions for every family
against four inert validator fixtures: an empty implementation, invalid syntax,
an import-failure sentinel, and a missing implementation. Candidate fixture code is
never imported or executed. The first three pass both tests; the missing file
fails only the file-presence test. All four pass the purported security test.
These are 112 fixture observations, not constructor attempts or candidate reviews.

Consequently, a faithful validator cannot establish the required U focal-security
FAIL from these tests, nor B-feature FAIL versus U/R-feature PASS. Inventing a new
behavioral oracle inside the validator would change the scientific test contract
that this request explicitly requires to remain byte-identical. The earlier
forbidden-word meta-tests did not establish these properties: they checked labels
in candidate text and ordinary byte inequality after file edits, not the requested
behavioral counterexamples. This release does not reuse those success claims.

The required S/B/U/R matrix is recorded in `preflight_results.json`. Unestablished
properties remain `NOT_ESTABLISHED`; no crash, assertion, timeout, import failure
or missing implementation is labeled an intended focal-security failure. There
are no automated decisions on procedural plausibility, second mismatches, answer
leakage or family distinctness, and no replacement human-review records.

Run from the repository root:

```sh
/opt/miniconda3/bin/python -B scripts/check_v3_validator_complete_readiness.py --check
/opt/miniconda3/bin/python -B -m pytest -q tests/test_v3_validator_complete_readiness.py
```

The preflight deliberately returns **2** when it reproduces the blocker and **1**
for input corruption or unexpected test shape. It never reports construction
ready. Passing regression tests mean the blocker and preservation checks were
reproduced; they do not mean any family passed machine admission.

`scientific_input_inventory.json` pins the 168 canonical scientific files without
copying or editing them. The source corrected-release manifest additionally binds
its full inventory. Existing specifications, order, four-attempt limits, full-pool
retention amendment, human admission procedure and six retained V2 families remain
unchanged. These are input-release defects, not specification failures or family
rejections; X01 remains unattempted.

A separate authorization to repair the canonical source/feature/security test
inputs is required before a validator can establish the requested matrix. The
previous placeholder release and invalid generated owner attestations remain
preserved with their existing correction/supersession notices. A committed audit
record is not evidence that the requested validator-complete release succeeded.
