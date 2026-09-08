# Source-Pairing Development V2 Report

## Decision

**Development V2 succeeds.** The successor design produces a reproducible
50-entry real-source corpus, a threshold-free B-only top-one matcher, one
all-YES development pair, a timestamp-valid matched irrelevant memory, and a
complete four-condition DESIGN_C deterministic mock. The prospective
confirmatory V2 candidate is ready for independent review and freeze.

This decision does not authorize unseen screening, GPU qualification, an
evaluated model, or a study run.

## Integrity and chronology

- The successor worktree was based exactly on authoritative V1 commit
  `120cb7f6c166e81e85752f493b8bfb316abe8135`.
- `SOURCE_PAIRING_DEVELOPMENT_SUCCESSOR_V2` was frozen alone at commit
  `9bf08a16241eac92e79a36c2bc3421adfa1623de` before new candidate-specific
  evidence.
- V1 protocol, evidence, and the five diagnostic decisions were not modified.
- The three unchanged V1 source-target decisions were carried byte-for-byte;
  only the two genuinely new V2 top-source pairs received new fail-closed
  review.
- No unseen task row, U/R patch, security artifact, or evaluated-model outcome
  was used by source mining or matching. No GPU or model command was run.

V2 is methodologically admissible because no unseen confirmatory target was
screened, no evaluated model was run, V1 exposed a construct/calibration
limitation, and the new method was frozen prospectively before confirmatory
screening.

## Source-only partition decision

A metadata-only SHA-256 partition was assessed before source-only internals
could be opened. A one-fifth illustrative rule would have permanently removed
42 of 181 unseen tasks and left 139 future targets. It was not used. The
target-independent S1/S2 source strategy reached the frozen corpus and breadth
requirements without sacrificing targets and avoided opening 42 task-specific
environments for source mining.

## Corpus size and construction

The first ten new attempts formed the frozen cost pilot. Eight qualified. The
pilot estimated 26.35 seconds per qualified source including discovery
overhead. New materialization occupied 0.137 GiB. The fixed five-minute human
audit allowance projected:

| Total corpus | Machine hours | Reviewer hours | Feasible |
|---:|---:|---:|:---:|
| 50 | 0.28 | 3.17 | YES |
| 100 | 0.64 | 7.33 | NO |
| 200 | 1.38 | 15.67 | NO |

The prospective rule therefore selected 50. Automated AST extraction used
only exact top-level production definitions and exact assertion-bearing
upstream test nodes. It generated no natural-language task summaries. The
final run attempted 45 new candidates, retained seven objective attritions,
and qualified 38 new sources in addition to the 12 immutable V1 sources.

Final corpus evidence:

- entries: 50;
- `SOURCE_BUILD=PASS`: 50;
- `SOURCE_TASK_TEST=PASS`: 50;
- focal source safety PASS at A/B/C: 50 (A=6, B=6, C=38);
- repositories: 7 (minimum 6);
- S2 repositories: 2 (minimum 2);
- primary operation classes: 13 (minimum 8); and
- canonical corpus hash:
  `1b4f9584c88317d1a523ce24bc4ef27aa4a1f8317cbf804e41de4816f9b3df2c`.

The execution ledger retains the infrastructure-calibration failures: a wrong
packet-audit key, an S2 working-directory error, pytest 7/Python 3.12
collection incompatibility, and an unavailable Python 3.10 `ensurepip` path.
The final adjustment was a narrow recorded collection-warning filter; source
code, tests, source commits, queue order, eligibility rules, and outcomes were
not changed.

## Matcher V2

The matcher implements:

`B-only hard gates -> deterministic lexicographic ranking -> top source -> immutable lock -> independent all-YES review`.

Hard gates cover frozen corpus identity, Python language, coarse timestamp,
real executable/correct/focal-safe source evidence, controlled operation-class
compatibility, and required API compatibility when explicitly demanded by the
public task. Ranking uses operation class, library/API, ordered API sequence,
type/data role, AST, normalized tokens, semantic vector, source tier, and hash
tie-break in that order.

There is no global similarity threshold, combined weighted score, or arbitrary
scalar ambiguity margin. All five top sources were unambiguous under the
scientifically meaningful dimensions (one had a single eligible source).
Every exact timestamp check passed. Source IDs and complete rankings are bound
into immutable locks. Rank-2 and manual fallback paths are absent and tested.

## Pair review

Five V2 top-source pairs were reviewed. Aiohttp-session, Wagtail, and Requests
selected the same source as V1, so their immutable V1 answers were carried
without reinterpretation. Buildbot and Django selected new sources and were
reviewed only after their locks existed; neither passed material relevance and
alignment requirements. No alternative source was reviewed.

The Wagtail pair again passed all 16 questions. Development V2 therefore has
1/5 all-YES pairs. This is an infrastructure/identification check, not a
confirmatory yield estimate.

## Irrelevant control and prompt length

For the accepted Wagtail pair, the deterministic selector chose
`src-aio-fernet-save-session`. It is real, executable, source-correct,
focal-safe, Python, uses the same packet template, is operation-class
disjoint, leaks no target API/symbol, and predates target B. The sealed exact
timestamp check passes. No model outcome informed selection.

The relevant packet has 260 lexical tokens and the irrelevant packet 342, an
absolute difference of 82 and a relevant-denominator difference of 31.54%.
This is the nearest eligible source under the frozen rule; both sensitivity
rankings select the same control. No padding, truncation, or fixed ±10% window
is used. The attention-length difference must be reported in the paper.

Resource balance is distinct from prompt-length matching. Every condition has
16,384 tokens of usable post-ingestion trajectory capacity, so the packet
difference cannot mechanically reduce the trajectory budget.

## Lifecycle, fidelity, revalidation, and DESIGN_C

All 50 packets pass exact implementation/task identity, forbidden-material,
and p* non-disclosure checks. The existing source-session, validation,
persistent-store, session-separation, B-only retrieval, exact delivery, and
logging lifecycle passes unchanged.

The four deterministic stub arms all execute:

1. `NO_MEMORY`;
2. `IRRELEVANT_CORRECT_MEMORY`;
3. `SOURCE_CORRECT_INAPPLICABLE`; and
4. `SOURCE_CORRECT_INAPPLICABLE_REVALIDATE`.

NO_MEMORY receives no junk. All arms keep physical context 32,768,
post-ingestion budget 16,384, reserve 256, per-turn generation maximum 4,096,
and model-decision maximum 32. The revalidation wording and SHA-256 are
unchanged from V1. The complete DESIGN_C mock passes without a model or GPU.

An applicable control remains `NOT_AVAILABLE` and was not manufactured.
Consequently, generic procedural anchoring remains an alternative explanation
to the p*-specific mechanism. The revalidation interaction and observable
p*-responsive behavior can strengthen mechanism evidence but cannot fully
replace an applicable control.

## Confirmatory candidate and N recommendation

The confirmatory V2 candidate freezes the SusVibes revision, permanent
development exclusions, 181-target universe identity, task-cue rule, B/U/R
eligibility, 50-source universe, timestamp rule, A-C source safety, p*
ontology, B-only matcher, exact gates/ranking/ambiguity, top-one lock,
firewall, all-YES review, exact memory, nearest irrelevant selector, DESIGN_C,
revalidation, resource budgets, deterministic target/condition order, N,
stopping, technical-invalid handling, and full attrition ledger.

Recommend minimum N=8, target N=12, and maximum practical N=16. The observed
1/5 diagnostic fraction is not a population estimate; it is used only for
rough workload planning. At that fraction, N=8/12/16 would require about
40/60/80 screens. Existing substrate measurements imply about 0.218 machine
hours plus 0.5-1.5 reviewer hours per screened target. Screening all 181 would
therefore require about 39.5 machine hours and 90.5-271.5 reviewer hours.

Interpret 8-11 as a controlled mechanism pilot, 12 or more as a controlled
workshop causal study, and 3-7 as a case series/methods study. Do not launch a
causal model study below N=8, and never use model outcomes to stop screening.

## Limitations

- Fifty sources are substantially better than 12 but remain a bounded Python
  corpus dominated by seven repositories.
- Mechanically validated level C accounts for 38/50 sources and remains focal,
  not global, safety evidence.
- Only one heterogeneous development pair is all-YES; confirmatory yield is
  unknown.
- The irrelevant packet is 31.54% longer, although it is the deterministic
  nearest eligible packet and resource capacity is equal.
- No applicable control exists, so the strongest p*-specific mechanistic claim
  remains underidentified.
- No evaluated-model behavior, effect size, power, GPU compatibility, or model
  runtime has been measured.

## Final readiness

All ten Development V2 success criteria pass. The next action is to
independently review and freeze the confirmatory V2 candidate before any
unseen screening.

Verification retained all 181 historical relevant tests and adds 45 V2 tests:
226 passed. Python compilation, JSON parsing, protocol-copy identity, and
`git diff --check` pass. Repository-wide pytest stops at the same pre-existing
frozen Aim `compatible_repository` hash mismatch recorded by V1 (48 tests pass
before that failure); no historical test or witness was weakened to hide it.

- `confirmatory_screening_authorized = FALSE`
- `gpu_qualification_ready = FALSE`
- `study_run_authorized = FALSE`
