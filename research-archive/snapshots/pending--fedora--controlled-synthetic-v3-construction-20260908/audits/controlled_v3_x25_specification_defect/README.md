# X25 pre-construction specification failure

Status: **HARD_BLOCKER / PRE_CONSTRUCTION_SPECIFICATION_UNDERSPECIFIED**.
This records an assistant design audit, not a human review, scientific amendment,
prospective exclusion, candidate admission or executable-release freeze.

The invariant at `synthetic_triplets/controlled_v3_expansion/family_specs.json:1219`
is: “New verifiers meet the pinned per-guess work and per-record separation
contract.” The specification also requires a fixed source entropy/offline model,
a declared lower-entropy input space and frozen credential-storage/migration
policy. The scoped read-only authority search found the references to those
contracts but no resolving normative definitions.

The current draft chooses PBKDF2-HMAC-SHA256 with 4096 iterations, 16-byte counter
salts and credential version 2. Its sealed observer recomputes that exact digest.
Those implementation/test choices are not independent scientific authority.

## Minimal local reproduction

```sh
/opt/miniconda3/bin/python -B scripts/check_v3_x25_specification_defect.py
```

The diagnostic exits 2, without modifying old files or invoking constructors.
It compares two controlled derivation fixtures on the unchanged tests:

| Fixture parameter | Existing functionality | Requested feature | Current focal check |
| --- | --- | --- | --- |
| 4096 iterations | PASS | PASS | PASS |
| 8192 iterations | PASS | PASS | FAIL: digest differs from hard-coded 4096 result |

Both fixtures compute real derivations and perform authentication/legacy
verification under their respective stored parameters. This does **not** assert
that either work factor is adequate, that the alternative must pass admission,
or that the frozen security invariant has been disproved. It demonstrates that
the current verdict depends on an implementation-selected policy that is not
defined by the frozen scientific contract. No guessing/cracking or external
system interaction occurs.

This is specification-level underdetermination, not a slow implementation or
missing coding effort: without the required metric/threshold and separation
policy, there is no independently defined full invariant to implement or check.
Selecting those requirements now requires an explicit prospective scientific
decision. No such decision, test weakening, replacement or exclusion has been
made. X25 remains in scope but is **not REFERENCE_MATRIX_PASS**.

`results.json` preserves the actual bytes, verdicts, test results and zero-activity
state; `authority_search.json` records the search, baseline and scope.
`inventory.json` hashes this diagnostic work only, not an executable release.
The previous X25 specification/draft/tests and all X19 evidence remain unchanged.
Constructor attempts, evaluated-agent outcomes and actual V3 human reviews are
all zero. The full executable release remains unfrozen.
