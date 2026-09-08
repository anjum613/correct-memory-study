# Draft Discussion, Limitations, and Conclusion

## 5. Discussion

### 5.1 The primary result is secure-adaptation failure

The experiment was motivated by a directional concern: a source-correct memory
might cause additional harm when a previously valid procedure crosses a changed
trust boundary. The final-security data cannot test that claim. Security is
already 0/24 without memory and remains 0/24 with memory. A paper that presents
this study as evidence that memory causes insecurity would therefore invert the
meaning of the result.

The defensible finding is a secure-adaptation floor. Under the frozen protocol,
both evaluated agents fail every security witness across six historically
grounded trust shifts, even though a frozen executable safe control passes both
functionality and security for every task. This is evidence about the evaluated
agents, selected cases, prompts, and budgets—not coding agents in general—but it
rules out task impossibility as the explanation for the observed 0/48.

### 5.2 Functional completion can conceal failed adaptation

The contrast between 46/48 functional passes and 0/48 security passes is more
informative than either rate alone. Most targets already satisfy the surface
functional contract. An agent can therefore inspect files, attempt tests, or
make no change and still appear successful, while leaving the decisive trust
invariant false. The faithful-reuse references reproduce the same pattern in
all six families: source-era behavior remains functional at the target but is
unsafe under the new boundary.

This finding argues for evaluating maintenance agents with explicit security
witnesses rather than treating functional tests as a sufficient correctness
criterion. It does not imply that an agent violated an explicit security
instruction: the witnesses were hidden. Instead, the benchmark probes whether
an agent discovers a latent trust-boundary change during ordinary maintenance.

### 5.3 Memory delivery, uptake, and safe adaptation are different constructs

Assignment to a memory condition proves only that content was included in the
rendered task. It does not prove that the model received a viable request,
attended to the content, reused a procedure, or adapted it safely. The observed
comparisons illustrate all of these distinctions.

Aim/Qwen provides direct uptake evidence: both memory trajectories refer to the
provided Flask implementation and avoid the harmful route edit made in both
no-memory runs. Memory is behaviorally consequential and plausibly explains the
localized functionality improvement. Yet the trajectories preserve interface
behavior without recognizing the target's path-containment requirement. Correct
memory supports source fidelity, but not the semantic reasoning needed to adapt
the procedure to a changed trust boundary.

Other comparisons are weaker. ONNX/Qwen and Djoser/Qwen change navigation and
termination patterns without citing supplied content, so attribution remains
ambiguous. In HTTPX/Qwen, no model request is sent under memory, making semantic
uptake impossible. These cases show why an aggregate “memory versus no memory”
label is insufficient for process claims.

### 5.4 What produced the security floor

The most consistent trajectory-level fact is absence of trust-invariant
articulation. No run states and repairs the relevant authentication,
filesystem, archive, URL-provenance, or authorization property. Forty-six runs
end with empty patches, and the two nonempty patches do not target security.
The common pattern is therefore not simply low security skill. Agents approach
already-functional repositories as surface implementation tasks, search or test
without formulating the hidden boundary, and stop or exhaust context with the
insecure target behavior unchanged.

Context exhaustion contributes but does not fully explain the result. It occurs
in 38/48 runs, including 22/24 memory runs and 16/24 no-memory runs. The other
ten runs also fail security, and Aim/Qwen has enough interaction to change code
without recognizing containment. Context limits should therefore be understood
as one operational mechanism that reinforces the floor, not as a complete
causal explanation.

### 5.5 Prompt burden is an operational treatment effect and a confound

Eight memory runs perform zero actions. HTTPX/Qwen gives the clearest evidence:
the 9,829-token rendered prompt exceeds the 4,096-token model context before an
HTTP request is sent. This is a genuine consequence of delivering the full
memory artifact under the frozen runtime, but it is not procedural reuse.

The distinction affects aggregate activity measures. Lower requests, actions,
and recorded time under memory cannot be called efficiency gains when some
runs never begin agent reasoning. Future designs should use length-matched
controls, retrieval or compression, explicit prompt-token accounting, and
checks that a treatment reaches the model with completion budget remaining.

### 5.6 Solvability changes the interpretation

The safe controls are central rather than ancillary. Without them, the 0/48
security outcome could be dismissed as evaluator inconsistency or impossible
task construction. The paired faithful and safe references instead demonstrate
that each evaluator accepts both the intended functionality and a concrete
security repair. They separate solution existence from agent discovery.

The conclusion must remain evaluator-relative. A safe control does not show
that the patch is easy, natural, unique, or recoverable within the fixed context
and tool budget. It supports “a secure solution exists,” not “the agent should
have found it with high probability.”

### 5.7 Implications for future memory-security evaluations

The study suggests three design requirements. First, establish a nonzero secure
baseline before using final security to estimate incremental treatment harm.
Second, instrument the sequence from treatment delivery through viable model
request, explicit or behavioral uptake, patch production, functionality, and
security. Third, control prompt length so that memory content is not confounded
with a reduced or absent completion budget.

A follow-up study could calibrate task difficulty with models that sometimes
solve the no-memory condition, use compact and length-matched memories, increase
independent repetitions, and preregister separate endpoints for semantic uptake
and secure adaptation. Those changes would make the original causal question
estimable; the current data do not.

## 6. Limitations

**Selected families.** The study contains six families across three trust
categories. This supports a heterogeneous controlled multi-case analysis, not
coverage of the space of historical trust changes.

**Targeted historical retrieval.** Track B deliberately retrieves and admits
cases that instantiate the theoretical pattern. It is not a random or
representative sample. The results cannot estimate prevalence, typical risk, or
expected production incidence. The exact selection and post-outcome expansion
chronology must be disclosed.

**Models.** Only two frozen model profiles are evaluated. Results cannot be
generalized to coding agents broadly, other model scales, proprietary systems,
or different agent scaffolds.

**Repetitions.** Each family × model × condition cell has two repetitions, with
fixed deterministic generation settings. The repetitions establish descriptive
trace consistency in several comparisons but do not support significance tests,
confidence intervals, population effect sizes, or strong variance estimates.

**Complete baseline floor.** No no-memory run is secure. Consequently, the
experiment cannot estimate additional security harm or benefit from memory and
cannot establish the motivating causal claim.

**Context-window effects.** Memory artifacts vary in length. Context exhaustion
occurs in 38/48 runs, and eight Axios/HTTPX memory runs perform no action.
Content, prompt length, available completion budget, and termination are thus
confounded in those comparisons.

**Treatment uptake.** Most memory comparisons lack direct evidence that the
agent semantically used the supplied material. Prompt inclusion is not uptake.
The strongest direct evidence is localized to Aim/Qwen.

**Hidden security witnesses.** Agents were not explicitly given the decisive
security invariant. This design tests latent trust-boundary recognition but
does not measure compliance with an explicit security request. The witnesses
operationalize particular properties and may not capture all relevant security
behavior.

**Evaluator-relative solvability.** A passing safe control proves that at least
one implementation satisfies the frozen functional and security evaluators. It
does not prove ecological ease, uniqueness, maintainability, or likely
discoverability.

**Runtime and tools.** Fixed context and step limits, command authorization,
test availability, environment behavior, and termination rules shape the
trajectories. Recorded elapsed time also reflects serving/runtime differences
and is not a clean competence measure.

**Observed process.** The analysis uses preserved requests, actions, reasoning,
patches, and evaluations. These support behavioral classifications but do not
provide direct access to internal cognition.

## 7. Conclusion

Across six demonstrably solvable historical trust shifts, the two evaluated
coding agents usually preserve functionality but never produce a secure
adaptation: 46/48 runs pass functionality and 0/48 pass security. Source-correct
memory does not produce a final-security difference. It directly changes
Aim/Qwen's behavior and improves functionality in that comparison, but the
agent still misses the changed filesystem trust boundary; in other comparisons,
uptake is mixed, absent, or confounded by context exhaustion. The study therefore
does not show that memory causes insecurity. It shows that functional success,
memory delivery, memory uptake, and secure semantic adaptation are distinct,
and that causal memory-security studies need secure-capable baselines and
context-controlled treatments.
