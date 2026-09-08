"""Freeze evidence and copy inputs. Does not import submitted code or evaluators."""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
AUDIT = Path('/home/anjum/final-13-audit-20260906')
DATA = AUDIT / 'evidence'
FROZEN = DATA / 'controlled-synthetic-final-13-codex-v3/frozen'
FAMILIES = ('X05', 'X06', 'X28')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def copy_tree(source, destination):
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(
        '.git', '__pycache__', '*.pyc', '.pytest_cache'))


def integrity():
    manifest = read(DATA / '__audit_source_manifest.json')
    mismatch = []
    for item in manifest['files']:
        path = DATA / item['path']
        if not path.is_file() or digest(path) != item['sha256']:
            mismatch.append(item['path'])
    return {'checked': len(manifest['files']), 'mismatches': mismatch,
            'manifest_sha256': digest(DATA / '__audit_source_manifest.json')}


def main():
    assert not (ROOT / 'FREEZE_RECEIPT.json').exists(), 'Already frozen'
    check = integrity()
    assert not check['mismatches'], check
    rows = read(AUDIT / 'derived/records.json')
    missing = read(AUDIT / 'derived/missing.json')
    assert len(rows) == 705 and len(missing) == 23
    assert len({r['run_id'] for r in rows}) == 705
    for row in rows:
        raw = read(DATA / row['result_path'])
        if row['harness'] == 'Codex':
            observed = (raw['technical_validity'],
                        (raw.get('functionality_result') or {}).get('pass'),
                        (raw.get('security_witness_result') or {}).get('pass'))
            assert raw['run_id'] == row['run_id']
        else:
            ev = raw['evaluation']
            observed = (raw['technical_valid'], ev['functionality_pass'], ev['focal_security_pass'])
            assert raw['cell']['actual_run_id'] == row['run_id']
        assert observed == (row['valid'], row['functionality'], row['security']), row['run_id']
    save(ROOT / 'all_original_records.json', rows)
    save(ROOT / 'all_missing_cells.json', missing)
    save(ROOT / 'source_integrity_before.json', check)

    for label, original in [('oracle', 'v3_oracle'), ('adapter', 'v3_difficulty_oracle')]:
        destination = ROOT / 'evaluator-original/synthetic_triplets' / (
            'controlled_v3_executable_oracle_release_v1' if label == 'oracle'
            else 'controlled_v3_difficulty_amendment_v1')
        copy_tree(FROZEN / 'snapshot' / original, destination)
    copy_tree(ROOT / 'evaluator-original', ROOT / 'evaluator-correction-v1')
    copy_tree(FROZEN / 'snapshot/families', ROOT / 'frozen-families')
    copy_tree(FROZEN / 'protocol', ROOT / 'frozen-protocol')
    copied = []
    for row in sorted((r for r in rows if r['family'] in FAMILIES), key=lambda r: r['run_id']):
        rec = DATA / row['record_path']
        workspace = rec / 'working-copy' if row['harness'] == 'MiniSWE' else rec.parent / 'workspace'
        base = rec / 'initial-repository' if row['harness'] == 'MiniSWE' else FROZEN / 'snapshot/families' / row['family'] / 'baseline'
        dest = ROOT / 'submissions' / row['run_id']
        dest.mkdir(parents=True)
        copy_tree(workspace, dest / 'workspace')
        shutil.copy2(rec / 'final.patch', dest / 'final.patch')
        shutil.copy2(rec / 'result.json', dest / 'original-result.json')
        copy_tree(base, dest / 'patch-reconstruction')
        patch = dest / 'final.patch'
        target_paths = [line[6:] for line in patch.read_text().splitlines() if line.startswith('+++ b/')]
        assert all(p == 'app/service.py' for p in target_paths), (row['run_id'], target_paths)
        applied = subprocess.run(['git', 'apply', '--no-index', '--whitespace=nowarn', str(patch)],
            cwd=dest / 'patch-reconstruction', capture_output=True, text=True) if patch.stat().st_size else None
        patch_ok = (applied is None or applied.returncode == 0)
        service = workspace / 'app/service.py'
        reconstructed = dest / 'patch-reconstruction/app/service.py'
        byte_match = patch_ok and digest(reconstructed) == digest(service)
        eval_service = rec.parent / 'evaluation/workspace/app/service.py'
        eval_match = digest(eval_service) == digest(service) if eval_service.exists() else None
        copied.append({**row, 'service_path': str(service), 'patch_path': str(rec / 'final.patch'),
            'copied_workspace': str(dest / 'workspace'), 'service_sha256': digest(service),
            'patch_sha256': digest(patch), 'patch_reconstruction_ok': byte_match,
            'patch_error': applied.stderr if applied is not None and not patch_ok else None,
            'evaluation_copy_agrees': eval_match,
            'input_artifacts': [{'source': str(p), 'sha256': digest(p)} for p in
                [service, rec / 'final.patch', DATA / row['result_path'], base / 'app/service.py']]})
    save(ROOT / 'review_census.json', copied)
    assert len(copied) == 163
    assert all(r['patch_reconstruction_ok'] and r['evaluation_copy_agrees'] is not False for r in copied), 'Reconstruction mismatch'
    upstream_comparison = {}
    for rel in ['controlled_v3_executable_oracle_release_v1/researcher_tests/shared/sealed_suite.py',
                'controlled_v3_difficulty_amendment_v1/worker.py',
                'controlled_v3_difficulty_amendment_v1/interface_adapter.py']:
        a = ROOT / 'synthetic_triplets' / rel
        b = ROOT / 'evaluator-original/synthetic_triplets' / rel
        upstream_comparison[rel] = {'original_commit_sha256': digest(a), 'snapshot_sha256': digest(b),
                                    'equal': digest(a) == digest(b)}
    assert all(x['equal'] for x in upstream_comparison.values())
    save(ROOT / 'upstream_evaluator_binding.json', upstream_comparison)
    receipt = {'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
        'stage': 'BEFORE_REFERENCE_OR_CANDIDATE_EXECUTION', 'post_hoc': True,
        'rule_sha256': digest(ROOT / 'REVIEW_RULE_v1.md'),
        'census_sha256': digest(ROOT / 'review_census.json'),
        'all_records_sha256': digest(ROOT / 'all_original_records.json'),
        'all_missing_sha256': digest(ROOT / 'all_missing_cells.json'),
        'source_manifest_sha256': check['manifest_sha256'],
        'recorded_review_runs': len(copied), 'planned_review_cells': 168,
        'counts': {str(k): v for k, v in Counter((r['harness'], r['model'], r['family']) for r in copied).items()},
        'git_source_commit': 'c03215d43faec963affae284db08b12743cd9fb6',
        'upstream_evaluator_binding_sha256': digest(ROOT / 'upstream_evaluator_binding.json')}
    save(ROOT / 'FREEZE_RECEIPT.json', receipt)
    (ROOT / 'REVIEW_RULE_v1.md').chmod(0o444)
    (ROOT / 'review_census.json').chmod(0o444)
    (ROOT / 'FREEZE_RECEIPT.json').chmod(0o444)
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
