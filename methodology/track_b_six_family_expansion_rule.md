# Frozen Track B six-family expansion rule

Status: **FROZEN BEFORE RANK-8+ CONTENT REVIEW**

This expansion is being undertaken after the MCP Pinot result is known. Its
sole purpose is to restore, or approach as closely as the frozen retrieval
universe permits, the study's original breadth target of six real historical
families. Candidate selection remains outcome-blind.

The authoritative inputs are the frozen Track B retrieval universe and its
provenance at `refs/remotes/track-b-provenance/cleanbase`, the semantic-review
freeze `1f5a3ee910c03ce32da7eab674d5da94aea52752`, the authoritative retrieval
run `20260827T131053Z`, and that run's exact seed records. Unopened Track A
candidates are outside scope.

Selection resumes at frozen Track B rank 8. Candidates are processed in their
original deterministic order. Parallel review is permitted for speed, but the
frozen ordering remains authoritative: a lower-ranked passing candidate cannot
supersede an unresolved higher-ranked candidate.

The expansion uses, without alteration:

- the same Gate A, Gate B, and Gate C definitions;
- the same executable-family admission criteria;
- the frozen `source-procedural-memory-generation-v1` protocol and its single
  deterministic rendering behavior;
- the same functional-oracle, security-witness, faithful-reuse-reference, and
  safe-control-reference contrast.

Model outcomes from MCP Pinot, ONNX, Axios, or any other prior family are
forbidden selection inputs. In particular, no current or future prior-family
outcome may be used to choose candidates, define or tune a proposition, edit a
memory, weaken an oracle or witness, or decide a reference implementation.

The first three candidates in frozen order that satisfy Gates A/B/C, have a
real compatible historical state C with `p*(C)=TRUE`, and pass all executable
admission criteria become Families 4, 5, and 6. Only after those three primary
selections are determined may review continue to construct one additional
survivor, designated `BACKUP_FAMILY_7`. The backup is optional and is not
model-run by default.

Every inspected candidate, including every rejection and its pre-outcome
reason, must be preserved. Every admitted family must retain the final semantic
structure `p*(S)=TRUE`, `p*(C)=TRUE`, and `p*(I)=FALSE`, and must demonstrate
before model execution:

- faithful reuse: functional PASS, security FAIL;
- safe control: functional PASS, security PASS.

This rule is immutable for the present expansion.
