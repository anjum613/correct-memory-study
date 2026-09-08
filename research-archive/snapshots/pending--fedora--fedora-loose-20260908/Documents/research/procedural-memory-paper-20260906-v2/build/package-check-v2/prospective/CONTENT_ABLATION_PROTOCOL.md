# Prospective memory content ablation

Status: planning specification, version 1, 6 September 2026. No agent runs have been performed for this protocol. It is separate from the original cohort and requires its own configuration and evaluator freeze before execution.

## Objective and intervention

Test whether an explicit source assumption contributes information beyond the supplied implementation procedure. For every selected family, hold the target task and its shifted context fixed and cross procedure present/absent with explicit source assumption present/absent:

| Condition | Procedure | Explicit source assumption |
| --- | --- | --- |
| N | absent | absent |
| P | present | absent |
| A | absent | present |
| PA | present | present |

`memory_components.json` provides draft components extracted from the frozen original C memories. The procedure string is identical in P and PA; the assumption string is identical in A and PA. The assumption is the original source justification, not a sentence explaining how to repair the target. Source task labels and neutral padding are omitted. Some procedures inherently reveal aspects of their preconditions. This ablation therefore isolates the addition of the explicit justification section, not every possible semantic cue about applicability.

Before freezing, review all thirteen component pairs against their source artifacts and reject any accidental target repair or changed procedure. Preserve headers and separator rules exactly. Record UTF-8 bytes and tokenizer counts for every final condition using the selected endpoint's tokenizer; token counts are currently unverified. Do not add outcome informed padding or claim equal information content. Keep any length control as a separately specified condition, not a silent modification.

## Configuration and execution qualification

Choose one or two configurations before observing new outcomes, using interface availability and reliability on an unrelated disposable task. Record exact endpoint ID, revision where available, sampling parameters, native agent version, tool schemas, instruction envelope, wall time, action/step cap, context cap and output cap. Do not infer backend identity from an alias.

The disposable task must require reading a provided file, making a small benign edit, and invoking a documented public check. Its result qualifies the interface, not the benchmark outcome. Freeze all instructions and budgets after qualification. If the interface changes, assign a new cohort version rather than selectively retrying failed treatment runs.

For every selected family and repetition, randomize the four conditions' execution order with a recorded seed. Balance condition position across the schedule and interleave families. Execute all selected conditions; do not sample only previously unsuccessful runs. Log outages and retries under a frozen rule that retains the original attempt. No paid endpoint is invoked by the planning artifact.

## Evaluation and analysis

Freeze a separately versioned evaluator before new runs, including explicit X06 confidentiality and public output requirements and an observer acceptance suite across all thirteen families. Keep historical labels unchanged. If saved implementations are later reevaluated, report that cohort separately and preserve the original observations.

Retain F, the focal security observation, and their joint outcomes. Define the new utility requirement explicitly where it differs from the historical F test. Select a primary endpoint before execution; a reasonable continuation is functional completion with focal security failure, accompanied by the full joint table and the extra X06 public output component.

Within each configuration, average repetitions within family, then equally weight selected families. The two component main effects are half the sum of their effects at the other component's two levels. The interaction is PA minus P minus A plus N. Report its uncertainty and the paired contrasts PA minus P and A minus N. An interaction in this design concerns supplied content, not causal mediation through a transcript code. Preserve invalidity reasons and component informed missingness bounds.

## Precision planning

`precision_grid.csv` is a conservative within-cohort Monte Carlo planning calculation for independent binary outcomes, using variance at most 1/4 per recorded repetition. With K=13 fixed families and r repetitions per condition, a two-arm difference has variance at most 1/(2Kr), and the four-arm interaction at most 1/(Kr). The table reports 1.96 times the corresponding standard errors. These are normal-approximation planning widths, not guaranteed confidence intervals and not precision for a population of software tasks.

For an illustrative 10 percentage point half-width, the bound calls for at least 15 repetitions per condition for a paired contrast, or 30 for the interaction. Choose the interaction only if its precision is the scientific priority and the budget supports it. Final repetition counts, selected configurations, tokenizer counts and execution dates remain to be frozen. More repetitions improve conditional precision; they do not make thirteen selected families representative of repository work.
