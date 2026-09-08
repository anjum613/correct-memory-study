"""Preserve pre-clarification outputs and freeze the user-directed six-cohort set."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parent
DEST = ROOT / 'superseded-before-spark-exclusion'
NAMES = ('EVIDENCE_CARDS.md', 'RUN_TABLE.md', 'SENSITIVITY.md', 'X06_mechanisms.csv',
         'changed_runs.json', 'family_condition_means.csv', 'model_outcomes.csv',
         'reproduction_checks.json', 'reviewed_run_details.json', 'reviewed_run_outcomes.csv',
         'run_outcomes.csv', 'run_outcomes.json', 'sensitivity_contrasts.csv',
         'sensitivity_contrasts.json', 'sensitivity_family_units.csv', 'analyze_review.py')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def main():
    DEST.mkdir()
    preserved = []
    for name in NAMES:
        source = ROOT / name
        shutil.copy2(source, DEST / name)
        preserved.append({'file': name, 'sha256': digest(source)})
    for name in ('all_original_records', 'review_census', 'replay_results'):
        rows = json.loads((ROOT / (name + '.json')).read_text())
        selected = [r for r in rows if r['model'] != 'Spark']
        save(ROOT / ('six_cohort_' + name + '.json'), selected)
    assert len(json.loads((ROOT/'six_cohort_all_original_records.json').read_text())) == 624
    assert len(json.loads((ROOT/'six_cohort_review_census.json').read_text())) == 144
    receipt = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'decision_date_melbourne': '2026-09-06', 'post_hoc': True,
        'reason': 'User-directed exclusion of unfinished Spark cohort after usage quota exhaustion',
        'amendment_sha256': digest(ROOT / 'SCOPE_AMENDMENT_20260906.md'),
        'unchanged_review_rule_sha256': digest(ROOT / 'REVIEW_RULE_v1.md'),
        'six_cohort_record_sha256': digest(ROOT / 'six_cohort_all_original_records.json'),
        'six_cohort_census_sha256': digest(ROOT / 'six_cohort_review_census.json'),
        'six_cohort_replay_sha256': digest(ROOT / 'six_cohort_replay_results.json'),
        'preserved_preclarification_outputs': preserved,
        'additional_evaluator_or_agent_executions': 0}
    save(ROOT / 'SCOPE_AMENDMENT_RECEIPT.json', receipt)
    (ROOT / 'SCOPE_AMENDMENT_20260906.md').chmod(0o444)
    (ROOT / 'SCOPE_AMENDMENT_RECEIPT.json').chmod(0o444)
    print(json.dumps({k:v for k,v in receipt.items() if k!='preserved_preclarification_outputs'}, indent=2))


if __name__ == '__main__':
    main()
