# Controlled synthetic V3 construction V2 runtime amendment

Release ID: `controlled-v3-construction-v2-runtime-amendment-v1`.

This separately versioned, pre-construction amendment corrects only the constructor
runtime implementation binding. It does not alter any scientific specification,
the `controlled-synthetic-v3-difficulty-amendment-v1` release, evaluator envelope, validator, canonical
test, family order, X19/X25 exclusion, four-attempt cap, ceiling-risk metadata,
machine admission criterion, or human-review protocol.

Construction V1 remains byte-for-byte preserved as historical provenance. Its
X01 attempt-001 is classified `ABORTED_PRE_SEMANTIC_CONSTRUCTION_MODEL_UNAVAILABLE`:
the exact raw failed invocation remains present and is neither deleted nor
reinterpreted. It produced zero candidate artifacts, zero tool calls, no semantic
constructor output, no machine-admissible candidate, no evaluated-agent outcome,
and no human review. It does not consume any of V2's four attempts for X01.

The V2 constructor runtime is Codex CLI 0.153.3 authenticated through ChatGPT,
model `gpt-5.6-sol`, reasoning effort `max`, Fast Mode disabled,
and explicit standard service tier. The exact noninteractive command controls,
binary digest, sandbox, authentication probe, model-catalog projection, and
relevant configuration are recorded in `constructor_runtime_amendment.json`.

One empty-workspace, non-benchmark accessibility invocation was completed and its
raw JSONL events and stderr are preserved under `runtime_accessibility_check/`.
It is not an X-family constructor attempt. No X-family input was mounted.

At this freeze, every V2 in-scope family has zero attempts, evaluated-agent
outcomes are zero, and actual V3 human reviews are zero. Construction must stop
until this amendment is committed and its commit is recorded externally.

The preserved dummy stream contains one nonfatal diagnostic: its historical
isolation mounted the main CLI executable but not the installed code-mode-host
companion. The dummy prompt prohibited tools, made zero tool calls, and still
completed the exact semantic acknowledgment. Before X01, V2 freezes a separate
launcher that binds the matching companion executable by exact SHA-256. A
non-model `--help` probe of that companion is preserved. In accordance with the
one-dummy requirement, no second Codex dummy or end-to-end tool-call probe was
performed; the original raw stream is unchanged and the diagnostic disposition
is explicit.
