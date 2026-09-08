# Figure and table plan

## Main paper

### Figure 1 — Endpoint separation by condition

A compact paired bar or dot plot with exact counts:

- No memory: functionality 22/24, security 0/24.
- Source-correct memory: functionality 24/24, security 0/24.

Annotate that the two additional functionality passes are both Aim/Qwen. Do not
add confidence intervals, p-values, or visual cues implying inferential
precision.

### Table 1 — Family × model outcomes

Use the 12-row table in `main-result-table.md`. It should be the central results
table because it shows that the aggregate is not hiding a family/model security
contrast and identifies the one functionality transition.

### Table 2 — Executable solvability

Show all six faithful-reference and safe-control outcomes. This table directly
answers the “tasks may be impossible” objection and should remain in the main
paper even under tight space.

### Figure 2 — Aim/Qwen trajectory divergence

A four-lane, two-condition schematic:

`inspect views.py → second action → final patch → functionality/security`

- No-memory repetitions: generic catch-all route edit → nonempty harmful patch
  → functionality FAIL, security FAIL.
- Memory repetitions: explicit comparison with provided Flask implementation
  → no durable edit → functionality PASS, security FAIL.

Label this `DIRECT_MEMORY_USE` and explicitly show the unaddressed containment
invariant. The figure is a process case study, not an average treatment-effect
plot.

### Table 3 — Overlapping failure taxonomy

Report at least:

| Failure mode | Runs | NM | M |
|---|---:|---:|---:|
| Trust shift not articulated | 48 | 24 | 24 |
| No durable security repair | 48 | 24 | 24 |
| Empty final patch | 46 | 22 | 24 |
| Functional pass/security fail | 46 | 22 | 24 |
| Context exhaustion | 38 | 16 | 22 |
| Zero-action context floor | 8 | 0 | 8 |

State that modes overlap and counts are descriptive.

## Optional main-paper or appendix figure

### Figure 3 — Treatment delivery versus semantic uptake

Use a flow diagram:

`memory assigned → viable model request → observable uptake → behavioral change
→ functional outcome → secure adaptation`

Place Aim/Qwen at observable uptake/behavior/functionality but not security;
HTTPX/Qwen stops before a viable model request. This visual communicates the
paper's methodological contribution without pretending all cells share one
mechanism.

## Appendix

- Complete 48-cell table with selected run IDs, attempts, outcomes, requests,
  actions, termination modes, and artifact paths.
- Full behavioral-effects table for all 12 comparisons.
- Detailed four-cell trajectory tables for Aim/Qwen, ONNX/Qwen, Djoser/Qwen,
  and HTTPX/Qwen.
- Complete failure-taxonomy definitions, overlapping coding rules, and evidence
  paths.
- Model request/action/termination summaries, including elapsed times with
  runtime-confounding caveats.
- Memory lengths, rendered prompt sizes, context limits, and transport records.
- Reference-validation records, evaluator hashes, safe-control patch hashes,
  and repetition evidence.
- Historical retrieval, candidate ranking, family selection, and post-outcome
  continuation chronology.
- Frozen prompts, seeds, model revisions, agent/runtime versions, tool policies,
  dependency fingerprints, and integrity hashes.
- Supported/unsupported claim checklist and reviewer-response matrix.

## Displays to avoid

- A memory “security effect” plot that visually implies an estimable difference
  despite both conditions being 0/24.
- Significance stars, confidence intervals, or fitted models with two
  repetitions per cell and targeted family selection.
- An aggregate activity plot labeled “efficiency” without exposing the eight
  zero-action memory runs.
- A family-frequency or prevalence chart.
