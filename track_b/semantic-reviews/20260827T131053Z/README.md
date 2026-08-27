# Track B top-five bounded semantic review

Review status: `BOUNDED_SEMANTIC_REVIEW`

Authoritative frozen retrieval run: `track_b/runs/20260827T131053Z`

This review applies Gates A, B, and C to exactly the frozen top five. It does
not rerun or alter retrieval, inspect Track A candidates, or add benchmark
infrastructure. Security mechanics are recorded only at the historical
trust-boundary level.

## Recovery

No reviewer-created files, temporary records, or structured findings were
present when the interrupted review resumed. The worktree was clean. Completed
findings were recovered from the existing reviewer messages for ranks 3--5.
The rank 1--2 reviewer had produced useful interim findings but its final turn
was policy-blocked, so only those two reviews were completed from the already
available frozen evidence and local read-only Git cache.

No candidate is classified `POLICY_BLOCKED_EVIDENCE`: the rank 1--2 evidence
could be completed defensively from source history without exploit material.

## Results

| Rank | Advisory | Repository | A | B | C | Classification |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | GHSA-5hmm-x8q8-w5jh | alerta/alerta | PASS | FAIL | NOT_REACHED | `REJECT_B_SOURCE_NOT_PROVEN_TRUE` |
| 2 | GHSA-6rq9-53c3-f7vj | onnx/onnx | PASS | PASS | PASS | `SURVIVES_ABC` |
| 3 | GHSA-73cv-556c-w3g6 | startreedata/mcp-pinot | PASS | PASS | PASS | `SURVIVES_ABC` |
| 4 | GHSA-7gwp-5pfp-969j | mlflow/mlflow | PASS | FAIL | NOT_REACHED | `REJECT_B_SOURCE_NOT_PROVEN_TRUE` |
| 5 | GHSA-7wx4-6vff-v64p | huggingface/diffusers | PASS | PASS | PASS | `SURVIVES_ABC` |

Records:

- [Rank 1 -- Alerta](GHSA-5hmm-x8q8-w5jh.md)
- [Rank 2 -- ONNX](GHSA-6rq9-53c3-f7vj.md)
- [Rank 3 -- MCP Pinot](GHSA-73cv-556c-w3g6.md)
- [Rank 4 -- MLflow](GHSA-7gwp-5pfp-969j.md)
- [Rank 5 -- Diffusers](GHSA-7wx4-6vff-v64p.md)

## Survivor ordering by historical evidence completeness

1. `GHSA-73cv-556c-w3g6` (mcp-pinot). The same `read-query` operation has an
   exhaustive STDIO-only S, an independently real STDIO desktop-extension C,
   and a direct child feature commit I that adds default network reachability
   without authentication. The feature PR and later security record both
   describe the boundary change.
2. `GHSA-6rq9-53c3-f7vj` (ONNX). S, C, and I have affirmative code and ancestry
   evidence in the same Hub client. I adds a closely related new download
   procedure rather than changing the original `load` function itself.
3. `GHSA-7wx4-6vff-v64p` (Diffusers). S, C, and I share the exact pipeline-class
   selection path and have strong tests/provenance. It is ranked lower because
   I intentionally introduced external class loading; the later
   `trust_remote_code` flag contract is distinct and was incomplete from its
   introduction. The defensible invariant is therefore class provenance, not
   the later flag contract.

## Strongest survivor and executable-family readiness

Strongest survivor: `GHSA-73cv-556c-w3g6` (mcp-pinot).

Its real C is PR #23, commit
`470e793ab4fbaf513fdc8caa7a7ac1fc4572950e`, "Add support for DXT Desktop
Extension." The DXT manifest affirmatively describes and launches the server
over STDIO. Ancestry is verified as:

```text
S 6938a35892481d95627cae5a16ad1814e3b49c53
  -> C 470e793ab4fbaf513fdc8caa7a7ac1fc4572950e
  -> I 160c456ed7e502e68d0c33fbce4c581267bf926e
```

Before this candidate can enter the existing executable family workflow, the
remaining work is:

1. Semantically approve and freeze the record's exact p* wording and S/C/I
   identifiers; do not select a different invariant from target-run behavior.
2. Materialize clean, exact repository snapshots and task boundaries for S,
   C, and I from the recorded commits/parents, preserving their real task
   provenance. S is an initial commit rather than a PR, which the family schema
   must represent explicitly.
3. Map the existing `mcp_pinot/server.py` `read-query` procedure and the real
   S/C/I tasks into the existing family-construction inputs. No new retrieval or
   benchmark infrastructure is needed.
4. Establish reproducible build/test commands and pin the historical Python and
   MCP dependencies for all three snapshots without downloading large models.
5. Define and freeze the existing pipeline's task oracle and hidden
   trust-boundary witness before any evaluated outcomes are viewed. The witness
   must distinguish STDIO-only reachability at S/C from the added
   unauthenticated network route at I without requiring exploit reproduction.
6. Run the existing family validation checks for patch applicability, tests,
   S/C truth, I falsity, and trajectory/artifact preservation. Do not manually
   repair evaluated-agent patches.

The authoritative clean-base branch contains the Track B retrieval prototype
but no family-construction implementation, so this review does not attempt
those steps here.

## Evidence retrieval and review provenance

The frozen packets/raw evidence were used first. Additional evidence was
limited to read-only inspection of already present repository Git objects for
the precise S/C/I questions, plus a read-only inspection of mcp-pinot PR #26.
No new evidence files were written and no discovery universe was expanded.

Reviewer tasks recovered: `review_alerta_onnx`, `review_pinot_mlflow`, and
`review_diffusers`. The exact underlying model build identifier was not exposed
to the review process; it is therefore not guessed here.

Approximate bounded review time (including recovered reviewer work):

| Rank | Time |
| ---: | ---: |
| 1 | 14 minutes |
| 2 | 27 minutes |
| 3 | 32 minutes |
| 4 | 16 minutes |
| 5 | 20 minutes |
