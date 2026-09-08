# Current-draft audit

## Draft-location result

No current paper or manuscript was found. The audit searched the current
worktree for TeX files and paths containing `paper`, `manuscript`, or `draft`,
then searched all Git refs and path history. The repository contains experiment
infrastructure, family packages, protocol records, and engineering reports, but
not a manuscript. Consequently, there is no existing title, abstract, or paper
sentence that can be quoted or edited in place.

This matters for traceability: the section-by-section statuses below are
`NOT_PRESENT`, not endorsements of unseen prose.

| Requested component | Audit status | Revision action |
|---|---|---|
| Title | `NOT_PRESENT` | Supply five options and one recommendation. |
| Abstract | `NOT_PRESENT` | Draft from frozen outcomes; lead with the security floor. |
| Introduction | `NOT_PRESENT` | Reframe around secure adaptation, with memory as a factor. |
| Research questions | `NOT_PRESENT` | Replace the directional harm question with diagnostic RQs. |
| Contributions | `NOT_PRESENT` | Center executable solvability and endpoint/process separation. |
| Methodology | `NOT_PRESENT_AS_MANUSCRIPT` | Convert frozen protocol records into a concise study-design section. |
| Results | `NOT_PRESENT` | Report exact descriptive counts without significance tests. |
| Discussion | `NOT_PRESENT` | Interpret the floor, uptake evidence, and context effects. |
| Limitations | `NOT_PRESENT` | State all sampling, repetition, floor, and context limitations. |
| Conclusion | `NOT_PRESENT` | Conclude secure-adaptation failure, not memory-caused harm. |

## Sentence-level overclaim audit

Because no manuscript exists in the repository or its Git history, there are
zero available manuscript sentences to classify as overclaims. This is not a
claim that an external or uncommitted draft is sound; it could not be audited.

The tracked framing-bearing documents were also searched. None states an
observed causal memory-harm result:

- `README.md` describes engineering infrastructure only.
- `docs/qualification/qwen32b-no-memory-v1-result.md:5` and
  `docs/qualification/qwen36-no-memory-v1-result.md:5` explicitly say that
  qualification does not test or support the memory-security hypothesis.
- `docs/methodology/deadline-bounded-family-count-amendment-v1.json:7-10`
  explicitly prohibits prevalence and representativeness claims for the
  deadline-bounded phase.
- `configs/experiments/conditions/source-correct-memory-v1.json:3` describes
  treatment delivery only; it is not evidence of treatment uptake or effect.
- `docs/methodology/source-procedural-memory-generation-v1.json:21` defines a
  source-only memory-selection rule and forbids selecting content based on an
  expected vulnerability.

## Statements that must be removed if they occur in an external draft

The following formulations conflict with the frozen results and should be
treated as overclaims wherever they appear:

1. “Source-correct memory causes agents to produce insecure code.”
2. “Memory increases the probability or rate of security failure.”
3. “The treatment makes otherwise secure agents insecure.”
4. “The study demonstrates a general memory-induced security hazard.”
5. “Coding agents systematically fail under trust shifts,” without restricting
   the statement to the two evaluated agents, six selected families, and frozen
   protocol.
6. “The benchmark measures how prevalent these failures are in software
   development.”
7. “Memory improves efficiency,” based on lower request/action totals; eight
   memory runs performed no action and context exhaustion confounds that total.
8. “Agents used the supplied memory” as a blanket treatment-level claim.
   Direct semantic-use evidence exists for Aim/Qwen, not for all comparisons.
9. “Devstral outperforms Qwen,” or the reverse. Both were 0/24 secure; the two
   functionality failures were localized to Aim/Qwen without memory.
10. Any significance, confidence, or population-effect statement based on two
    repetitions per cell.

## Methodology material worth preserving

The eventual manuscript should preserve the exact historical selection and
continuation chronology, frozen model revisions and budgets, two repetitions,
hidden-witness design, and distinction between targeted retrieval and sampling.
It should also report that safe controls demonstrate evaluator-relative
solvability, not ease or likely discoverability by an agent.

One historical protocol document needs careful contextualization:
`docs/methodology/deadline-bounded-family-count-amendment-v1.json` records an
earlier deadline-bounded partial phase with one to three admitted families and
an original target of six families across four categories. It must not be cited
as though it describes the final completed design, which contains six families
across three categories. The paper should narrate the later family expansion
and its timing, including which outcomes were already known, rather than
silently collapsing the stages into a single preregistered six-family sample.

## Integration note

If a manuscript exists outside this repository, it should be supplied before a
literal redline. Until then, this packet is a clean replacement draft rather
than a revision against known prose.
