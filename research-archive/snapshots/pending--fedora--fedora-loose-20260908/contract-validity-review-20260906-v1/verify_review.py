"""Independent evidence/analysis checks. Never executes submitted programs."""
from collections import Counter
from fractions import Fraction
from pathlib import Path
import ast
import csv
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parent
DATA = Path('/home/anjum/final-13-audit-20260906/evidence')
MODELS = {'GPT55', 'Luna', 'Terra', 'QwenNext', 'Qwen30', 'Devstral'}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    rows = read(ROOT / 'run_outcomes.json')
    assert len(rows) == len({r['run_id'] for r in rows}) == 624
    assert {r['model'] for r in rows} == MODELS
    assert Counter(r['model'] for r in rows) == Counter({m:104 for m in MODELS})
    assert all(r['original_outcome'] != 'UNSTARTED' for r in rows)
    assert sum(not r['original_valid'] for r in rows) == 29
    for r in rows:
        raw = read(Path(r['original_result']))
        if r['harness'] == 'Codex':
            valid = raw['technical_validity']
            f = (raw.get('functionality_result') or {}).get('pass')
            s = (raw.get('security_witness_result') or {}).get('pass')
        else:
            valid = raw['technical_valid']
            f, s = raw['evaluation']['functionality_pass'], raw['evaluation']['focal_security_pass']
        assert (valid, f, s) == (r['original_valid'], r['original_raw_F'], r['original_raw_S'])
        for version in ('original', 'revised'):
            if not valid:
                assert all(r[version+'_'+k] is None for k in ('F','S','U'))
            else:
                assert r[version+'_U'] == (r[version+'_F'] and not r[version+'_S'])
        assert r['original_F'] == r['revised_F'], 'No functionality changes authorized'
    changed = [r for r in rows if r['original_S'] != r['revised_S']]
    assert len(changed) == 4 and all(r['model']=='Devstral' and r['original_S'] is True and r['revised_S'] is False for r in changed)
    for r in changed:
        replay = read(Path(r['revised_replay_log']))['result']
        if r['family'] == 'X05':
            nonces = [o['return']['nonce_prefix_hex'] for o in replay['observations']]
            assert len(nonces) == 4 and len(set(nonces)) == 2
            assert all(o['issued'] == [] for o in replay['observations'])
        else:
            first = replay['observations'][0]
            assert first['return'] is True and first['grants']==[] and first['exact_reads']==0
    contrasts = read(ROOT / 'sensitivity_contrasts.json')
    exclusions = {'all_13': set(), 'without_X06': {'X06'}, 'without_reviewed_families': {'X05','X06','X28'}}
    for item in contrasts:
        differences = {}
        for family in {r['family'] for r in rows} - exclusions[item['panel']]:
            left, right = item['contrast'].split('-')
            group = [r for r in rows if r['model']==item['model'] and r['family']==family and r['condition'] in (left,right)]
            if len(group)!=4 or any(not r[item['version']+'_valid'] or r.get(item['version']+'_S') is None for r in group):
                continue
            difference = Fraction(sum((1 if r['condition']==left else -1)*int(r[item['version']+'_'+item['metric']]) for r in group),2)
            differences[family] = difference
        assert set(filter(None,item['eligible_families'].split(';'))) == set(differences)
        assert item['n_families'] == len(differences)
        expected = float(sum(differences.values())/len(differences)*100) if differences else None
        assert (expected is None and item['difference_pp'] is None) or math.isclose(expected,item['difference_pp'],abs_tol=1e-10)
    # Cross-check original contrasts against the separate, untouched original audit.
    with Path('/home/anjum/final-13-audit-20260906/derived/contrasts.csv').open() as stream:
        audit = list(csv.DictReader(stream))
    metric_names={'F':'functionality','S':'security','U':'unsafe'}
    for item in contrasts:
        if item['panel']!='all_13' or item['version']!='original':
            continue
        a = next(a for a in audit if a['model']==item['model'] and a['contrast']==item['contrast'] and a['metric']==metric_names[item['metric']])
        assert math.isclose(float(a['difference'])*100,item['difference_pp'],abs_tol=1e-10)
        assert a['included_families']==item['eligible_families']
    freeze = read(ROOT/'FREEZE_RECEIPT.json')
    correction = read(ROOT/'CORRECTION_FREEZE.json')
    scope = read(ROOT/'SCOPE_AMENDMENT_RECEIPT.json')
    assert sha(ROOT/'REVIEW_RULE_v1.md') == freeze['rule_sha256'] == correction['rule_sha256']
    assert sha(ROOT/'review_census.json') == freeze['census_sha256']
    assert sha(ROOT/'SCOPE_AMENDMENT_20260906.md') == scope['amendment_sha256']
    assert sha(ROOT/'six_cohort_review_census.json') == scope['six_cohort_census_sha256']
    assert sha(ROOT/'six_cohort_replay_results.json') == scope['six_cohort_replay_sha256']
    assert sha(ROOT/'review_worker.py') == correction['worker_sha256']
    assert sha(ROOT/'replay.py') == correction['replay_driver_sha256']
    assert read(ROOT/'validation_summary.json')['passed']
    checks = read(ROOT/'reproduction_checks.json')
    assert len(checks)==144
    assert sum(c['original_replay_agrees'] is True for c in checks)==143
    assert sum(c['original_replay_agrees'] is None for c in checks)==1
    assert not any(c['original_replay_agrees'] is False for c in checks)
    for item in read(ROOT/'six_cohort_review_census.json'):
        assert sha(Path(item['copied_workspace'])/'app/service.py') == item['service_sha256']
        for source in item['input_artifacts']:
            assert sha(Path(source['source'])) == source['sha256']
        for version in ('evaluator-original','evaluator-correction-v1'):
            log = read(ROOT/'replays'/item['run_id']/(version+'.json'))
            assert freeze['frozen_at_utc'] < correction['frozen_at_utc'] < log['started_at_utc']
            assert log['result']['isolation']['interfaces'] == [[1,'lo']]
            assert not log['result']['isolation']['home_visible']
            assert len(log['result']['isolation']['routes'])==1
    oracle = ROOT/'evaluator-original'
    revised = ROOT/'evaluator-correction-v1'
    changed_files=[str(p.relative_to(oracle)) for p in oracle.rglob('*') if p.is_file() and sha(p)!=sha(revised/p.relative_to(oracle))]
    assert changed_files==['synthetic_triplets/controlled_v3_executable_oracle_release_v1/researcher_tests/shared/sealed_suite.py']
    def functions(path):
        return {n.name:ast.dump(n, include_attributes=False) for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef)}
    old,new=functions(oracle/changed_files[0]),functions(revised/changed_files[0])
    assert {k for k in old if old[k]!=new[k]}=={'x05_target_invariant','x28_target_invariant'}
    assert old['x06_target_invariant']==new['x06_target_invariant']
    manifest=read(DATA/'__audit_source_manifest.json')
    mismatch=[f['path'] for f in manifest['files'] if sha(DATA/f['path'])!=f['sha256']]
    assert not mismatch
    result={'status':'PASS','paper_runs':624,'reviewed_runs':144,'changed_security_scores':4,
        'functionality_changes':0,'original_status_reproductions':143,'missing_original_evaluation':1,
        'family_contrasts_independently_verified':len(contrasts),
        'original_artifacts_rehashed':len(manifest['files']),'original_artifact_mismatches':mismatch,
        'correction_changed_files':changed_files,'X06_evaluator_unchanged':True,
        'no_submission_execution_in_this_verification':True}
    (ROOT/'verification_summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
