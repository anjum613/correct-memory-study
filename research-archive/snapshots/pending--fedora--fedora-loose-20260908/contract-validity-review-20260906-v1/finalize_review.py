"""Validate artifact links and package only the six completed cohorts."""
from datetime import datetime, timezone
from pathlib import Path
import ast
import hashlib
import json
import re
import tarfile

ROOT = Path(__file__).resolve().parent
CORE = ('README.md', 'VALIDITY_REPORT.md', 'RUN_TABLE.md', 'SENSITIVITY.md',
        'EVIDENCE_CARDS.md', 'REVIEW_RULE_v1.md', 'FREEZE_RECEIPT.json',
        'CORRECTION_FREEZE.json', 'SCOPE_AMENDMENT_20260906.md', 'SCOPE_AMENDMENT_RECEIPT.json',
        'six_cohort_all_original_records.json', 'six_cohort_review_census.json',
        'six_cohort_replay_results.json', 'run_outcomes.json', 'run_outcomes.csv',
        'reviewed_run_outcomes.csv', 'reviewed_run_details.json', 'X06_mechanisms.csv',
        'model_outcomes.csv', 'family_condition_means.csv', 'changed_runs.json',
        'sensitivity_contrasts.csv', 'sensitivity_contrasts.json', 'sensitivity_family_units.csv',
        'reproduction_checks.json', 'verification_summary.json', 'validation_summary.json',
        'upstream_evaluator_binding.json', 'source_integrity_before.json',
        'evaluator-correction-v1.patch', 'prepare.py', 'replay.py', 'review_worker.py',
        'replay_six_cohorts.py', 'analyze_review.py', 'verify_review.py',
        'apply_scope_amendment.py', 'finalize_review.py')


def main():
    errors = []
    count = 0
    for name in ('VALIDITY_REPORT.md', 'README.md', 'RUN_TABLE.md', 'SENSITIVITY.md', 'EVIDENCE_CARDS.md'):
        for target in re.findall(r'\]\(([^)]+)\)', (ROOT / name).read_text()):
            target = target.split('#')[0]
            parts = target.rsplit(':', 1)
            line = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else None
            path = Path(parts[0] if line else target)
            if not path.is_absolute():
                path = ROOT / path
            count += 1
            if not path.exists():
                errors.append((name, target, 'missing'))
            elif line and len(path.read_text().splitlines()) < line:
                errors.append((name, target, 'line out of bounds'))
    assert not errors, errors
    for name in CORE:
        if name.endswith('.py'):
            ast.parse((ROOT / name).read_text())
    verified = json.loads((ROOT / 'verification_summary.json').read_text())
    assert verified['status'] == 'PASS'
    census = json.loads((ROOT / 'six_cohort_review_census.json').read_text())
    assert len(census) == 144 and all(r['model'] != 'Spark' for r in census)
    paths = [ROOT / name for name in CORE]
    for folder in ('evaluator-original', 'evaluator-correction-v1', 'frozen-families',
                   'frozen-protocol', 'synthetic_triplets', 'protocols', 'validation'):
        paths.extend(p for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    for row in census:
        for folder in (ROOT / 'submissions' / row['run_id'], ROOT / 'replays' / row['run_id']):
            paths.extend(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    paths = sorted(set(paths))
    manifest = {'completed_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'six completed cohorts only', 'link_targets_checked': count,
        'paper_runs': 624, 'rescored_saved_submissions': 144, 'agent_executions': 0,
        'excluded_from_package': 'All Spark submissions, replays, results, examples and pre-clarification tables; original full source capture remains preserved separately.',
        'files': [{'path': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size,
                   'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]}
    manifest_path = ROOT / 'FINAL_ARTIFACT_MANIFEST.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    archive_path = ROOT.parent / 'contract-validity-review-six-completed-cohorts-20260906-v1.tar.gz'
    with tarfile.open(archive_path, 'x:gz') as archive:
        for path in paths + [manifest_path]:
            archive.add(path, arcname='contract-validity-review-six-cohorts/' + str(path.relative_to(ROOT)))
    with tarfile.open(archive_path) as archive:
        names = archive.getnames()
        assert len(names) == len(paths) + 1
        for row in json.loads((ROOT/'review_census.json').read_text()):
            if row['model'] == 'Spark':
                assert not any('/submissions/'+row['run_id']+'/' in n or '/replays/'+row['run_id']+'/' in n for n in names)
    print(json.dumps({'archive': str(archive_path), 'bytes': archive_path.stat().st_size,
                     'packaged_files': len(paths)+1, 'verified_links': count,
                     'archive_sha256': hashlib.sha256(archive_path.read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    main()
