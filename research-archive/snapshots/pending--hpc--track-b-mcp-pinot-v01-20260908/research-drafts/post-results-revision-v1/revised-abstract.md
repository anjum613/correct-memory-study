# Revised abstract

Procedures that are correct in one software revision can become unsafe after a
trust boundary changes, raising the concern that coding agents may inappropriately
reuse source-correct procedural memory. We study this concern using six targeted,
historically grounded task families spanning authentication/identity,
filesystem/path/archive, and validation/use/provenance shifts. For each family,
an executable faithful-reuse reference passes functionality but fails a hidden
security witness, whereas a safe-control implementation passes both, establishing
that a secure solution exists. We evaluate two coding agents with and without
source-correct memory, using two repetitions per family, model, and condition
(48 technically valid runs). The agents pass functionality in 46/48 runs but
security in 0/48: 0/24 without memory and 0/24 with memory. The complete baseline
floor means that these data do not identify whether memory causes or increases
insecurity. Trajectories nevertheless separate treatment delivery from uptake.
In Aim/Qwen, both memory runs explicitly consult the supplied source
implementation, avoid a functionality-damaging edit made in both no-memory runs,
and improve functionality from 0/2 to 2/2, while remaining 0/2 secure. In
HTTPX/Qwen, by contrast, the memory prompt exceeds the context limit before a
model request, providing no evidence of semantic memory use. Across all runs,
no trajectory articulates and repairs the changed trust invariant, 46 final
patches are empty, and 38 runs end through context exhaustion. We therefore
frame the result as a controlled diagnosis of secure-adaptation failure on
solvable trust shifts, not as evidence that memory causes insecurity. The study
shows why memory delivery, memory uptake, functionality, and security must be
measured separately, and why future causal evaluations require secure-capable
baselines and context-controlled memory treatments.
