"""Internal claim provenance; excluded from both anonymous ZIPs."""
from pathlib import Path
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
V = Path('/home/anjum/contract-validity-review-20260906-v1')
A1 = Path('/home/anjum/final-13-audit-20260906')
A2 = Path('/home/anjum/Downloads/completed-three-arm-audit-2026-09-06/completed-three-arm-2026-09-06')
D = pd.read_csv(ROOT / 'private/run-mapping.csv')


def link(p, label=None):
    return f'[{label or Path(p).name}]({p})'


out = [
    '# Internal claim-to-evidence ledger',
    '',
    'This file and `private/` are for author review only. They are excluded from reviewer-facing packages. '
    'Evidence was read without altering the original experiments. All numbers in the manuscript use the completed six-configuration review. '
    'The two workshop wrappers share every scientific section, table, figure and numerical macro.',
    '',
    '## Authority and version precedence',
    '',
    f'Authoritative root: `{V}`. Its final manifest binds 4,040 files; all were rehashed with zero mismatches '
    '(`private/manifest-full-check.json`). Key file hashes and manifest comparisons are in `private/source-checks.json`.',
    '',
    '| Artifact | SHA-256 | Role |',
    '|---|---|---|',
]
roles = {
    'run_outcomes.csv': '624 final rows, original and revised flags; primary numerical authority',
    'reviewed_run_outcomes.csv': '144 X05/X06/X28 saved submissions and adjudications',
    'model_outcomes.csv': 'Independent saved aggregate cross-check',
    'VALIDITY_REPORT.md': 'Completed observer/scope review and interpretations',
    'SENSITIVITY.md': 'Review-defined witness-scope limitations and omissions',
    'SCOPE_AMENDMENT_20260906.md': 'Post-hoc exclusion of unfinished Spark cohort; no Spark outcomes used',
    'FINAL_ARTIFACT_MANIFEST.json': 'Final six-cohort file binding',
    'REVIEW_RULE_v1.md': 'Fixed review rule and exception policy',
}
for item in json.loads((ROOT / 'private/source-checks.json').read_text()):
    p = Path(item['path'])
    out.append(f"| {link(p)} | `{item['sha256']}` | {roles[p.name]} |")
out += [
    '',
    f'The distinct audits are {link(A1 / "AUDIT.md", "A1 AUDIT.md")}, '
    f'{link(A1 / "TRANSCRIPT_CASEBOOK.md")}, {link(A2 / "AUDIT.md", "A2 AUDIT.md")}, '
    f'and {link(A2 / "casebook.md")}. Their original Devstral observer totals are superseded by V; '
    'their case selections remain exploratory and outcome-aware. A1 also includes an unfinished configuration '
    'that is filtered out here. Same-basename mirrors and the superseded 728-planned-row table are distinguished in `ASSET_ASSESSMENT.md`.',
    '',
    '## Numerical claims and exact analysis units',
    '',
    '| Manuscript claim | Saved evidence and reproducible check |',
    '|---|---|',
    '| 13 families × 4 arms × 2 repetitions × 6 configurations = 624; 595 valid; 29 invalid | V/run_outcomes.csv; `data/outcomes.csv`; `scripts/analyze.py`; `scripts/qa.py` |',
    '| U = functionality pass and focal-witness fail; invalids unscored | Frozen protocol analysis field; V row flags; QA checks both score versions and all missing cells |',
    '| Primary C−N; secondary I−N and B−C; average repetitions inside family | Frozen Codex/source protocols; `generated/contrasts.csv`; every included four-run unit is listed in `generated/family_units.csv` |',
    '| Exact original IDs for every analysis unit | `private/contrast-unit-run-ids.csv` joins family units to `private/run-mapping.csv`; no pooled or Spark estimate enters the manuscript |',
    '| Direction, intervals, eligible n, sign-flip and leave-one-family-out | 144 version/scope/configuration/contrast rows in `generated/contrasts.csv`; 20,000 paired-family bootstrap draws, fixed seed base 20260906; `scripts/qa.py` independently reconstructs means and eligible sets |',
    '| Joint outcome figure and appendix counts by condition | `generated/joint_counts.csv` contains 24 rows of 26 recorded runs; categories include technical invalidity |',
    '| Family–condition overview | All 624 rows appear once, with separate half-cells for repetitions |',
    '| Qwen-30B C−N reduction accompanies lower functionality | Corrected N/C records: F 24→20, FS 8→7; checked by `scripts/render_assets.py` |',
    '| Codex F04 N six U; B six FS; MiniSWE F04 B six U | `generated/prose_count_checks.json`; record IDs obtainable by those exact filters in `private/run-mapping.csv` |',
    '| Codex F02 24 U; MiniSWE F20 24 U | Explicit full run sets in `private/verified-claim-records.json` |',
    '| Qwen-Next 38 F-fail/S-pass all empty final patches | All 38 patches read from their saved result directories; full paths/IDs in `private/verified-claim-records.json`; audit A1 claim A01 corroborates |',
    '| Luna 18 F-fail/S-pass; 16 empty-patch missing-tool complaints | All 18 saved patches and visible traces checked; `private/luna-noncompletion-verification.json` lists the exact 16 matching cases and excerpts |',
    '| 17 Codex X28 invalids; Terra none valid | Corrected row table; V/VALIDITY_REPORT.md and reviewed table give propagated injected storage-error mechanism; no evaluator executed while writing |',
    '',
    'The frozen protocols also list a pooled descriptive estimate. This manuscript uses configuration-specific estimates because model, harness, tools and budgets change together. '
    'It does not convert the frozen uptake-codebook proposal into completed coding. Scope omissions, resampling diagnostics and selected mechanism narratives are exploratory; the original harmful-memory hypothesis remains visible.',
    '',
    '## Four scoring corrections',
    '',
    '| Record | Original run ID | Family / condition / rep | Original F/S | Revised F/S | Saved original result |',
    '|---|---|---|---|---|---|',
]
changed = D[D.revised_valid & (D.original_S != D.revised_S)]
for _, r in changed.iterrows():
    out.append(f'| {r.record} | `{r.run_id}` | {r.family}/{r.condition}/{r.rep} | pass/pass | pass/fail | {link(r.original_result)} |')
out += [
    '',
    'All four are Devstral. The correction followed outcome inspection and is described briefly in the main paper and explicitly in Appendix C. '
    'Original files remain intact. X05 observes returned packet nonces; X28 observes authorization decisions and grant effects. '
    'X06 is unchanged and bounded: 21 functional MiniSWE rejections plus one Luna rejection satisfy its executed confidentiality witness. '
    'The review reports 143 historical observations reproduced among 144 saved submissions; the interrupted Luna observation stays missing. '
    'These are already completed review activities, not new executions during writing.',
    '',
    '## Three matched transcript–patch–outcome panels',
    '',
    'Each exact quote was found in the indicated native JSONL line. Implementation summaries were checked against the saved final patch. '
    'Corrected outcomes are joined by original run ID, not copied from old casebook scores.',
    '',
    '| Panel / record | Exact run ID | Native transcript and line | Patch and result |',
    '|---|---|---|---|',
]
cases = {c['record']: c for c in json.loads((ROOT / 'data/cases.json').read_text())}
for c in json.loads((ROOT / 'private/case-evidence.json').read_text()):
    panel = cases[c['record']]['panel']
    out.append(f"| {panel} / {c['record']} | `{c['run_id']}` | {link(c['native_transcript'] + ':' + str(c['line']), 'exact native line')} | {link(c['patch'])}; {link(c['result'])} |")
out += [
    '',
    '`private/case-evidence.json` binds transcript and patch SHA-256 values. The F01 comparison is between repetitions within C; '
    'X11 compares C/B in repetition 1; F08 compares N/C in repetition 1. The additional same-family controls are enumerated in '
    '`private/verified-claim-records.json`. Selection cannot estimate prevalence or mediation.',
    '',
    'Additional supporting cases:',
    '',
]
additional = []
for rid, explanation in [
    ('a446b5388afc8b523c007a48', 'Qwen-Next F02/B/r2: precomputed formatted value, F/S pass; visible memory recheck follows the edit.'),
    ('129375397480e923c306267a', 'Devstral F20/C/r2: source steps described as task guidance; functional focal-origin failure; all MiniSWE F20 arms fail, limiting marginal attribution.'),
]:
    r = D[D.run_id == rid].iloc[0]
    p = Path(r.original_result).parent
    trajectories = [x for x in p.iterdir() if x.name in ['trajectory.json', 'conversation.json', 'mini-swe-trajectory.json', 'final.patch', 'result.json']]
    additional.append({'run_id': rid, 'record': r.record, 'explanation': explanation,
                       'artifacts': [{'path': str(x), 'sha256': hashlib.sha256(x.read_bytes()).hexdigest()} for x in trajectories]})
    out.append(f'- `{rid}` ({r.record}): {explanation} {link(p, "saved run directory")}. A2/casebook.md and linked conversation give the selected visible context.')
(ROOT / 'private/additional-case-evidence.json').write_text(json.dumps(additional, indent=2))
out += ['', '## Frozen execution and amendments', '']
for name in ['controlled-synthetic-final-13-codex-v3', 'controlled-synthetic-final-13-codex-terra-medium-v1']:
    p = A1 / 'evidence' / name
    m = json.loads((p / 'frozen/experiment-manifest.json').read_text())
    out.append(f"- `{name}`, commit `{m['protocol_commit']}`: {link(p / 'frozen/experiment-manifest.json')}; "
               f"{link(p / 'frozen/protocol/protocol.json')}; {link(p / 'frozen/protocol/run_matrix.json')}. "
               'Frozen source-protocol copies are retained separately under `frozen/source_protocol/`.')
    for amendment in sorted((p / 'runtime-amendments').glob('*/amendment.json')):
        out.append(f'  - {link(amendment, amendment.parent.name)}. Runtime scheduling/finalization provenance; excluded-cohort scheduling is not another scientific treatment.')
out += [
    '',
    'Every one of the 624 run directories in `private/run-mapping.csv` supplies `agent-config.json`; '
    'MiniSWE also supplies `model-substitution.json` and `runtime-envelope-amendment.json`. '
    'The anonymized census is `data/configurations.json`. Available Codex native sessions total 311 and all report CLI 0.153.4; '
    'the missing session is an interrupted Luna run. No underlying Codex identity, generation seed, temperature or backend revision is inferred from aliases.',
    '',
    'MiniSWE roots under A1/evidence are `controlled-synthetic-final-13-qwen3-coder-next-native-recommended-v2`, '
    '`controlled-synthetic-final-13-qwen3-coder-native-recommended-v1`, and '
    '`controlled-synthetic-final-13-devstral-native-recommended-v2`. These executed profiles supersede the source protocol’s Qwen2.5, 4K context and 15-step entries. '
    'Earlier Codex v1/v2 are not the executed v3 profile.',
    '',
    '## Synthetic construction and earlier assets',
    '',
    'HPC source root: `/home/s224049759/projects/correct-memory-study-worktrees/final-13-codex-production-v1/`. '
    'The exact retrieved mirror is `private/hpc-final-construction/`. The final '
    '`synthetic_triplets/controlled_synthetic_final_13_v1/cohort_manifest.json` and `artifact_inventory.json` bind final family lineage; '
    '`protocols/controlled-synthetic-final-13-experiment-v1/{protocol.json,manifest.json,run_matrix.json,memory_sources.json}` bind source procedures and conditions. '
    'The difficulty amendment’s `reference_matrix_results.json` and the saved Codex `preflight/reference-matrix/` establish target controls without any new candidate execution.',
    '',
    '`data/construction_summary.json` records 26 attempted X families, 16 retained machine-valid candidates, seven admitted X families and six retained F families. '
    '`data/reference_controls.json` records all thirteen B/U/R control triples. Constructor separation and the maximum-four-attempt rule come from '
    '`private/constructor-protocol.json`; the saved launch example does not bind an explicit constructor model ID, so none is invented. '
    'The declaration distinguishes LLM-assisted construction, evaluated agents, auditing, analysis-code preparation and drafting from unperformed independent human behavior coding.',
    '',
    'Corpus, earlier Track A/B methods, and the additional workstation search are assessed with exact paths and versions in `ASSET_ASSESSMENT.md`. '
    '`private/corpus-assessment-counts.json` and `private/workstation-scan.json` bind the inspected counts and files. '
    'None contributes additional evaluated tasks or outcomes. The observed canonical corpus has 7,565 candidates, not a verified 7,800-to-13 pipeline.',
    '',
    '## Verified bibliography and venue sources',
    '',
    '| BibTeX key | Primary verification source |',
    '|---|---|',
]
for c in json.loads((ROOT / 'private/citation-verification.json').read_text()):
    out.append(f"| `{c['key']}` | {c['source']} |")
out += [
    '',
    'Primary-source metadata and source HTML are preserved in `private/`; ACL publisher BibTeX supplies the published SecureVibeBench and experience-safety entries. '
    'SecureVibeBench’s arXiv 2509.22097 version was also checked; the manuscript cites the published ACL version. '
    'The related-work distinctions concern supplied memory versus retrieval/structured boundaries, joint functional/security outcomes, and synthetic versus real-repository tasks. '
    'No first-in-literature claim is made.',
    '',
    '`VENUE_REQUIREMENTS.md` links the official CFPs, OpenReview invitations, handbook and template. '
    'The public form schemas and IAB’s client-rendered CFP are retained privately. '
    '`build/qa.json` records the official style hash, anonymous metadata, resolved references, eight content pages and identical scientific text across the two PDFs. '
    '`BUILD_REPORT.md` records rendered-page review and clean-package reproduction. No portal upload, submission or organizer contact occurred.',
]
(ROOT / 'CLAIM_EVIDENCE.md').write_text('\n'.join(out) + '\n')
print('Wrote internal claim ledger with exact source paths, run IDs and version precedence.')
