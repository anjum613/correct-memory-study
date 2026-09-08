# Local V3 reference work — HARD_BLOCKER, NOT FROZEN

This directory continues the existing implementation work. It is not a new
scientific protocol version, an executable release freeze, a candidate-admission
API, or authorization to construct X01. All fixtures are researcher-only; none
has been exported to a constructor or evaluated-agent envelope.

The current checks pass for 23 families. X19 fails its source invariant.
X02, X15, X18 and X22 remain unimplemented. Passing these checks does not establish
full feature/invariant coverage against the frozen specification. The broader
coverage and candidate-integrity gates remain incomplete.

## Specific specification blocker: X19

The frozen specification at
`synthetic_triplets/controlled_v3_expansion/family_specs.json`, lines 891–934,
says that source security rests on neighboring text being fixed. It keeps the
secret length class and encoded-length observation fixed across source/target,
and requires indistinguishability of equal-length permitted confidential
alternatives. It refers to a frozen observation model, but does not define that
model or the permitted alternative domain. The X02/X22 clarification explicitly
leaves X19 unchanged.

The current local source is functional, but its response lengths for two inert
eight-byte secrets differ even with the neighboring text fixed to empty:

| Local secret | Fixed neighbor | Encoded bytes | Authorized decode |
| --- | --- | --- | --- |
| `AAAAAAAA` | empty | 13 | PASS |
| `ABCDEFGH` | empty | 19 | PASS |

This is an actual length difference, not a crash, missing function, malformed
record, timeout, caller label, or external interaction. In this draft, the
purported target failure therefore already exists under the source condition.

Classification: **PRE_CONSTRUCTION_SPECIFICATION_UNDERSPECIFIED**. This is not a
proof that every possible compressor/domain is impossible. The draft's zlib and
eight-byte domain are implementation choices, not authority. Silently choosing
only equal-baseline-compressibility secrets, replacing raw length observation
with an incremental-leakage metric, or adding source padding would require
scientific justification and may change the source procedure or focal property.
No such reinterpretation or amendment has been made.

The appropriate stopping condition is the user's HARD_BLOCKER endpoint. No
further construction or scientific design changes are authorized by these files.

## Reproduction

From the repository root on the recorded Python 3.12.8 / zlib 1.2.13 environment:

```sh
/opt/miniconda3/bin/python -B scripts/check_v3_local_invariant_preflight.py
/opt/miniconda3/bin/python -B -m pytest -q -p no:cacheprovider tests/test_v3_local_invariants.py tests/test_x19_preconstruction_defect.py
```

The diagnostic exits 2. The original matrix test for X19 remains a failing test;
it is not skipped, rewritten to expect success, or marked xfail. The additional
diagnostic tests establish the failure's cause, not X19's validity.

`preconstruction_report.json` records every current matrix, the four unrun
families, the source evidence, integrity-check scope and zero-activity state.
`authority_search.json` records the read-only search and its scope.
`work_inventory.json` hashes this incomplete work; it is not a release manifest.

All prior releases, scientific specifications, admission rules, six retained V2
families and historical invalid attestations remain unchanged. Constructor
attempts, evaluated-agent outcomes and actual new human-review files remain zero.
The harness checks trusted local references; it is not a sandbox for arbitrary
candidate Python. Its raised-TimeoutError test is not deadline enforcement.
