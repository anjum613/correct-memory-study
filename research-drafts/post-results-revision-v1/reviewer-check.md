# Skeptical reviewer check

## Overall assessment

The revised framing is defensible as a controlled diagnostic multi-case study,
but not as a successful test of memory-induced security harm. The paper's
credibility depends on making that distinction in the title, abstract,
introduction, Results, and conclusion—not only in limitations.

## 1. “The 0% secure baseline makes additional memory harm unmeasurable.”

**Valid?** Yes, fully, for the final-security endpoint.

**Available evidence.** Both conditions are 0/24 secure; every family × model
comparison is 0/2→0/2.

**Concede.** The original directional causal hypothesis is not identified, and
the experiment cannot estimate a security-risk increment.

**Defend.** The study diagnoses a replicated secure-adaptation floor on six
demonstrably solvable tasks and separates that endpoint from memory uptake and
functionality. This is the top reviewer risk.

## 2. “The tasks may be impossible.”

**Valid?** A necessary challenge, but contradicted by executable evidence.

**Available evidence.** Each faithful reference passes functionality and fails
security; each safe control passes both, with frozen repeated evaluations.

**Concede.** Existence does not imply ease, uniqueness, or discoverability under
the agent budget.

**Defend.** Lack of any secure solution cannot explain 0/48.

## 3. “Six families are too few.”

**Valid?** Yes for broad generalization and frequency claims.

**Available evidence.** The six cases cover three distinct frozen trust
categories, with two families in each.

**Concede.** The study does not characterize all trust changes, repositories,
languages, or deployments.

**Defend.** A controlled heterogeneous multi-case study can establish these
failure modes and methodological issues exist in the evaluated setting.

## 4. “Targeted retrieval creates selection bias.”

**Valid?** Yes, fully.

**Available evidence.** Track B used frozen targeted historical retrieval and
documented selection/continuation rules rather than population sampling.

**Concede.** The tasks are enriched stress tests and provide no prevalence or
expected-risk estimate.

**Defend.** Targeted retrieval is suitable for constructing executable
existence and mechanism cases. Provenance supports internal procedural
integrity, not representativeness.

## 5. “Two repetitions cannot support statistics.”

**Valid?** Yes.

**Available evidence.** Several normalized outcomes and traces replicate, but
there are only two deterministic repetitions per cell.

**Concede.** Report no significance tests, confidence intervals, variance
claims, or population effect sizes.

**Defend.** Exact outcomes and repeated within-comparison process patterns can
be reported descriptively.

## 6. “The memory effect is mostly null.”

**Valid?** Yes for final security and most functionality comparisons.

**Available evidence.** Security is unchanged in all 12 comparisons;
functionality changes only in Aim/Qwen. A few other comparisons have trajectory
shifts without endpoint changes.

**Concede.** The study does not provide an average positive memory effect or a
memory-harm result.

**Defend.** Aim/Qwen demonstrates that memory can change behavior and
functionality without secure adaptation. The broader contribution is the need
to distinguish delivery, uptake, functionality, and security.

## 7. “The agents may not use the memory.”

**Valid?** Yes for most comparisons.

**Available evidence.** Aim/Qwen explicitly references the provided Flask
implementation and reproducibly changes behavior. ONNX/Qwen and Djoser/Qwen are
ambiguous. HTTPX/Qwen receives no viable model request under memory.

**Concede.** Treatment assignment is not uptake; direct semantic-use evidence is
localized.

**Defend.** The Aim/Qwen case supports an existence claim. Uptake labels prevent
overaggregation.

## 8. “Why is this a memory paper rather than a general agent-security paper?”

**Valid?** This is a strong framing challenge.

**Available evidence.** Memory is the controlled factor; Aim/Qwen shows direct
use, and long memory produces operational context effects. Yet baseline secure
adaptation is the dominant result.

**Concede.** The paper must be primarily about secure adaptation under trust
shifts, with memory as a secondary experimental/process factor.

**Defend.** The study exposes a memory-evaluation problem: final outcomes
conflate baseline competence, treatment delivery, semantic uptake, and safe
adaptation. That lesson is specifically relevant to agent-memory research.

## 9. “Hidden witnesses test mind-reading, not instruction following.”

**Valid?** Partly.

**Available evidence.** The user-facing tasks do not state the decisive security
property, while safe and faithful references validate the intended contrast.

**Concede.** This is not a test of compliance with an explicit security
instruction.

**Defend.** The benchmark intentionally stress-tests latent trust-boundary
recognition in underspecified maintenance, a condition that can occur in real
work. Claims must stay at that level.

## 10. “Memory content is confounded with prompt length.”

**Valid?** Fully for the zero-action Axios/HTTPX memory cells and potentially for
aggregate activity.

**Available evidence.** Eight memory runs perform zero actions; HTTPX/Qwen
records 9,829 prompt tokens against a 4,096-token limit and no HTTP request.

**Concede.** Aggregate request/action differences cannot be treated as semantic
memory or efficiency effects.

**Defend.** The operational failure is itself useful for evaluation design, and
Aim/Qwen's direct semantic-use case remains distinct.

## Recommended author posture

Lead with the floor and its consequence for causal identification. Put the
solvability table in the main text. Label all rates descriptive. Present
Aim/Qwen as a bounded behavioral case study and HTTPX/Qwen as the counterweight
showing non-uptake. Reviewers are most likely to reject a paper that retains the
old causal narrative while relegating the null to a caveat; the revised secure-
adaptation framing avoids that error but cannot remove the study's limited
scope.
