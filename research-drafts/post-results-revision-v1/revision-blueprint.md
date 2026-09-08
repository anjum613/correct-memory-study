# Revision blueprint

## Recommended title

**When Correct Memory Is Not Enough: Coding Agents Under Historical Trust
Shifts**

Alternative titles:

1. **Functionally Right, Securely Wrong: Coding Agents Under Historical Trust
   Shifts**
2. **Source-Correct Memory Without Secure Adaptation**
3. **Beyond Final Outcomes: Memory Uptake and Security Floors in Coding Agents**
4. **A Security Floor in Coding-Agent Maintenance Under Changed Trust
   Assumptions**

The recommended title retains memory without implying that memory caused the
security failures.

## Revised central claim

Across six executable historical trust shifts, two coding agents achieved
functionality in 46/48 runs but security in 0/48 despite a verified secure
solution for every task; source-correct memory changed behavior—and improved
Aim/Qwen functionality—without producing secure adaptation.

## Revised research questions

**RQ1 — Secure adaptation.** Can the evaluated coding agents produce secure
adaptations on functionally solvable tasks whose trust assumptions changed
historically?

**RQ2 — Behavioral memory effects.** Does source-correct procedural memory
change agents' search, reasoning, editing, completion, or functionality even
when final security is unchanged?

**RQ3 — Semantic adaptation.** When behavior changes under memory, do agents
adapt the source procedure to the target trust boundary, or do they preserve
only source-era surface structure?

**RQ4 — Failure mechanisms.** Which observed process failures create the final
security floor, and how can they be distinguished from benchmark impossibility?

**RQ5 — Evaluation design.** What controls are needed to identify incremental
memory harm separately from baseline insecurity, treatment non-uptake, and
prompt-budget effects?

The original directional question—whether source-correct memory increases
security failures—should remain in the paper as the motivating hypothesis and
be explicitly reported as unanswerable on the final-security endpoint because
the no-memory baseline is 0/24 secure.

## Revised contributions

- An executable six-family benchmark of historically grounded trust shifts,
  with a functional-but-insecure faithful reference and a functional-and-secure
  safe control for every family.
- A complete 48-cell study across two coding agents, two memory conditions, and
  two repetitions, revealing 46/48 functional passes but 0/48 security passes
  on demonstrably solvable tasks.
- An analysis that separates memory assignment, observable memory uptake,
  functionality, and final security; Aim/Qwen directly uses the source material
  and improves from 0/2 to 2/2 functional passes without a security repair.
- A cross-family trajectory taxonomy centered on absent trust-invariant
  articulation, lack of durable security repair, surface functionality success,
  and context exhaustion.
- Evaluation lessons for memory-security studies: calibrate a nonzero secure
  baseline, measure uptake, and control memory length and context burden before
  estimating incremental harm.

## Proposed paper structure

1. **Introduction**
   - Motivating risk: historically correct procedures can cross a changed trust
     boundary.
   - Original memory-harm hypothesis and why final outcomes do not support it.
   - Central secure-adaptation finding and contributions.
2. **Related Work**
   - Coding agents and software maintenance.
   - Retrieval/procedural memory for agents.
   - Secure code generation and trust-boundary reasoning.
   - Historical bug and vulnerability benchmarks.
3. **Study Design**
   - Historical trust-shift construction and three trust categories.
   - Targeted Track B retrieval and selection chronology.
   - Six family packages, functional evaluators, hidden witnesses.
   - Faithful-reuse and safe-control executable validation.
   - Models, memory conditions, repetitions, fixed budgets, and integrity.
   - Outcomes and trajectory-evidence classification.
4. **Results**
   - Complete cell accounting and solvability.
   - Security floor and functionality/security separation.
   - Family-by-model comparison.
   - Aim/Qwen direct-use case study.
   - Mixed effects and HTTPX/Qwen semantic-use null.
   - Failure taxonomy and model-level description.
5. **Discussion**
   - Secure adaptation rather than incremental memory harm.
   - Functionality is not evidence of security.
   - Delivery, uptake, semantic adaptation, and endpoints are distinct.
   - Context length as an operational treatment effect and confound.
   - Benchmark and agent-design implications.
6. **Limitations**
   - Sampling, model, repetition, floor, context, hidden-witness, and
     evaluator-relative limitations.
7. **Conclusion**
   - Solvable tasks, pervasive secure-adaptation failure in this protocol, and
     the need for calibrated baselines and uptake-aware memory evaluation.

## Introduction logic

The introduction should avoid presenting memory harm as an established fact.
It can motivate the concern, explain the controlled manipulation, and then
state early that the observed no-memory floor prevented the intended causal
contrast. This concession should precede secondary trajectory results. The
positive scientific value is the conjunction of executable solvability,
functionality/security separation, and direct evidence that memory can affect
behavior without producing trust-aware adaptation.
