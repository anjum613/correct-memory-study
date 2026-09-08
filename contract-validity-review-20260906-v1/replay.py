"""Bounded offline reference validation and exhaustive saved-submission replay."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parent
DEPENDENCY = Path('/home/anjum/.local/lib/python3.14/site-packages/cryptography')
VERSIONS = ('evaluator-original', 'evaluator-correction-v1')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify_freeze():
    frozen = read(ROOT / 'FREEZE_RECEIPT.json')
    assert digest(ROOT / 'REVIEW_RULE_v1.md') == frozen['rule_sha256']
    assert digest(ROOT / 'review_census.json') == frozen['census_sha256']
    return frozen


def call(version, mode, family, workspace, log):
    assert not log.exists(), 'Logs are append-only: ' + str(log)
    command = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session',
        '--cap-drop', 'ALL', '--ro-bind', '/usr', '/usr',
        '--symlink', 'usr/lib64', '/lib64', '--symlink', 'usr/lib', '/lib',
        '--ro-bind', str(DEPENDENCY), '/deps/cryptography',
        '--ro-bind', str(ROOT / version), '/oracle',
        '--ro-bind', str(ROOT / 'review_worker.py'), '/review/review_worker.py',
        '--ro-bind', str(workspace), '/workspace', '--proc', '/proc', '--dev', '/dev',
        '--tmpfs', '/tmp', '--chdir', '/workspace', '--clearenv',
        '--setenv', 'PATH', '/usr/bin', '--setenv', 'PYTHONPATH', '/workspace:/oracle:/deps',
        '--setenv', 'PYTHONDONTWRITEBYTECODE', '1', '--setenv', 'PYTHONHASHSEED', '0',
        '/usr/bin/python3', '-B', '/review/review_worker.py', mode, family]
    start = datetime.now(timezone.utc).isoformat()
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=25)
        payloads = [line[len('REVIEW_RESULT='):] for line in proc.stdout.splitlines()
                    if line.startswith('REVIEW_RESULT=')]
        value = json.loads(payloads[0]) if len(payloads) == 1 else {
            'worker_status': 'UNRESOLVED', 'error': 'missing_or_multiple_worker_results'}
        log_value = {'started_at_utc': start, 'ended_at_utc': datetime.now(timezone.utc).isoformat(),
            'command': command, 'returncode': proc.returncode, 'stdout': proc.stdout,
            'stderr': proc.stderr, 'result': value}
    except subprocess.TimeoutExpired as error:
        value = {'worker_status': 'UNRESOLVED', 'error': 'offline_timeout'}
        log_value = {'started_at_utc': start, 'command': command, 'result': value}
    save(log, log_value)
    iso = value.get('isolation', {})
    if value.get('worker_status') == 'COMPLETE':
        assert iso['interfaces'] == [[1, 'lo']] and len(iso['routes']) == 1 and not iso['home_visible']
    return value


def validate():
    verify_freeze()
    records = []
    for version in VERSIONS:
        for family in ('X05', 'X06', 'X28'):
            home = ROOT / 'frozen-families' / family
            value = call(version, 'matrix', family, home / 'baseline',
                ROOT / 'validation' / version / f'{family}-canonical-matrix.json')
            records.append({'version': version, 'family': family, 'kind': 'canonical-S-B-U-R',
                'passed': value.get('reference_matrix_pass') is True, 'result': value})
            for state in ('B', 'U', 'R'):
                expected = {'existing': 'PASS', 'feature': 'FAIL' if state == 'B' else 'PASS',
                            'invariant': 'FAIL' if state == 'U' else 'PASS'}
                value = call(version, 'candidate', family, home / 'reference' / state,
                    ROOT / 'validation' / version / f'{family}-admitted-{state}.json')
                records.append({'version': version, 'family': family, 'kind': 'admitted-' + state,
                    'passed': all(value.get(k, {}).get('status') == v for k, v in expected.items()),
                    'expected': expected, 'result': value})
    value = call(VERSIONS[1], 'observer', 'X05', ROOT / 'frozen-families/X05/baseline',
        ROOT / 'validation/observer-unit-checks.json')
    records.append({'kind': 'observer-unit-checks', 'passed': value.get('observer_unit_checks') == 'PASS', 'result': value})
    save(ROOT / 'validation_summary.json', {'passed': all(r['passed'] for r in records), 'checks': records})
    print(json.dumps([{'kind': r['kind'], 'family': r.get('family'), 'version': r.get('version'),
                       'passed': r['passed']} for r in records], indent=2), flush=True)
    assert all(r['passed'] for r in records), 'Reference validation failed; no candidate replay authorized by this driver'
    save(ROOT / 'CORRECTION_FREEZE.json', {'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
        'rule_sha256': digest(ROOT / 'REVIEW_RULE_v1.md'),
        'worker_sha256': digest(ROOT / 'review_worker.py'), 'replay_driver_sha256': digest(Path(__file__)),
        'corrected_suite_sha256': digest(ROOT / VERSIONS[1] / 'synthetic_triplets/controlled_v3_executable_oracle_release_v1/researcher_tests/shared/sealed_suite.py'),
        'validation_summary_sha256': digest(ROOT / 'validation_summary.json')})


def replay():
    verify_freeze()
    validation = read(ROOT / 'validation_summary.json')
    assert validation['passed']
    frozen = read(ROOT / 'CORRECTION_FREEZE.json')
    assert frozen['worker_sha256'] == digest(ROOT / 'review_worker.py')
    assert frozen['replay_driver_sha256'] == digest(Path(__file__))
    suite = ROOT / VERSIONS[1] / 'synthetic_triplets/controlled_v3_executable_oracle_release_v1/researcher_tests/shared/sealed_suite.py'
    assert frozen['corrected_suite_sha256'] == digest(suite)
    census = read(ROOT / 'review_census.json')

    def one(row):
        workspace = Path(row['copied_workspace'])
        assert digest(workspace / 'app/service.py') == row['service_sha256']
        values = {}
        for version in VERSIONS:
            values[version] = call(version, 'candidate', row['family'], workspace,
                ROOT / 'replays' / row['run_id'] / (version + '.json'))
        return {'run_id': row['run_id'], 'family': row['family'], 'model': row['model'],
                'condition': row['condition'], 'rep': row['rep'], 'results': values}

    # Independent local test processes, no agent/model work.
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = []
        for value in pool.map(one, census):
            results.append(value)
            if len(results) % 20 == 0:
                print(f'Replayed {len(results)}/{len(census)} saved submissions', flush=True)
    save(ROOT / 'replay_results.json', results)
    print(f'Completed {len(results)} saved submissions under both evaluator versions', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['validate', 'replay'])
    args = parser.parse_args()
    (validate if args.mode == 'validate' else replay)()
