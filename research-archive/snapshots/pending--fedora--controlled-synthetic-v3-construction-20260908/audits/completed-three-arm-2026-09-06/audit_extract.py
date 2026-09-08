"""Read existing artifacts only; write derived evidence in this audit directory.

Never import or execute code from an evaluated working copy. All message indices in
the evidence are zero-based JSON indices; JSONL line numbers are one-based.
"""
import ast
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SNAP = HERE / 'snapshots'
ARMS = {
    'Next': 'controlled-synthetic-final-13-qwen3-coder-next-native-recommended-v2',
    'Q30': 'controlled-synthetic-final-13-qwen3-coder-native-recommended-v1',
    'Dev': 'controlled-synthetic-final-13-devstral-native-recommended-v2',
}
CONDS = ['NO_MEMORY', 'SOURCE_CORRECT_MEMORY', 'MATCHED_IRRELEVANT_MEMORY',
         'SOURCE_MEMORY_PLUS_APPLICABILITY_BOUNDARY']
SHORT = dict(zip(CONDS, ['N', 'C', 'I', 'B']))
MEMORY = re.compile(r'\bmemor(?:y|ies)\b|source[ -](?:procedure|context|setting|assumption|valid)|retrieved|provided procedure', re.I)
TRUST = re.compile(r'\bsecur\w*|\bsafe\w*|trust|saniti|escap|authoriz|tenant|permission|race\b|nonce|validat|boundary|canonical|leak|sensitive|cross.origin', re.I)


def load(p):
    return json.loads(p.read_text())


def lines(p):
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def json_hash(obj):
    return sha(json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False))


def outcome(d):
    if not d['technical_valid']:
        return 'INVALID'
    f, s = d['evaluation']['functionality_pass'], d['evaluation']['focal_security_pass']
    return ('SAFE_COMPLETION' if s else 'UNSAFE_COMPLETION') if f else ('INCOMPLETE_SECURITY_PASS' if s else 'INCOMPLETE_SECURITY_FAIL')


def summarise(rows):
    valid = [r for r in rows if r['valid']]
    return dict(attempts=len(rows), valid=len(valid),
                outcomes=dict(Counter(r['outcome'] for r in rows)),
                functionality=sum(r['fun'] for r in valid), security=sum(r['sec'] for r in valid),
                unsafe=sum(r['unsafe'] for r in valid), safe_completion=sum(r['safe'] for r in valid),
                requests=sum(r['requests'] for r in rows), commands=sum(r['commands'] for r in rows),
                mean_requests=mean(r['requests'] for r in rows), median_requests=median(r['requests'] for r in rows),
                mean_first_edit=mean(r['first_edit'] for r in rows if r['first_edit'] is not None) if any(r['first_edit'] for r in rows) else None,
                no_edits=sum(r['first_edit'] is None for r in rows),
                policy_violations=sum(r['policy_violations'] for r in rows),
                policy_affected_runs=sum(r['policy_violations'] > 0 for r in rows),
                format_affected_runs=sum(r['invalid_response_count'] > 0 for r in rows),
                length_requests=sum(r['finish_reasons'].get('length', 0) for r in rows),
                terminations=dict(Counter(r['termination'] for r in rows)),
                public_test_run_count=sum(r['public_test_calls'] for r in rows),
                runs_with_public_tests=sum(r['public_test_calls'] > 0 for r in rows),
                last_public_test_pass=sum(r['last_public_pass'] is True for r in rows),
                run_ids=[r['key'] for r in rows])


def extract():
    inventory = []
    for p in sorted(SNAP.rglob('*')):
        if p.is_symlink():
            inventory.append(dict(path=str(p.relative_to(HERE)), symlink=str(p.readlink())))
        elif p.is_file():
            raw = p.read_bytes()
            inventory.append(dict(path=str(p.relative_to(HERE)), bytes=len(raw), sha256=sha(raw)))
    (HERE / 'inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
    bindings = {x['family_id']: x for x in load(REPO / 'protocols/controlled-synthetic-final-13-experiment-v1/evaluation_bindings.json')['families']}
    records, refs, event_refs, integrity, transcript_index = [], [], [], [], []
    transport_total = Counter()
    for model, rootname in ARMS.items():
        root = SNAP / rootname
        for p in sorted(root.glob('*/result.json')):
            d = load(p)
            if 'cell' not in d:
                continue
            dr = p.parent
            c, tm, ev = d['cell'], d['trajectory_metrics'], load(dr / 'evaluation.json')
            tr = load(dr / 'trajectory.json')
            events, history = lines(dr / 'adapter-events.jsonl'), lines(dr / 'patch-history.jsonl')
            tx, budgets = lines(dr / 'model-transport.jsonl'), lines(dr / 'request-budgets.jsonl')
            cfg, frozen = load(dr / 'agent-config.json'), load(dr / 'frozen-messages.json')
            key = f"{model}/{c['family_id']}/{SHORT[c['condition']]}/{c['repetition']}"
            bound = bindings[c['family_id']]
            service_rel = 'app/service.csirpy' if c['family_id'] == 'X02' else 'app/service.py'
            initial = (dr / 'initial-repository' / service_rel).read_text()
            final = (dr / 'working-copy' / service_rel).read_text()
            frozen_user = next(x['content'] for x in frozen if x['role'] == 'user')
            actual_user = tr['messages'][1]['content']
            preserved = []
            finish = Counter()
            usage = Counter()
            request_configs = Counter()
            for j, t in enumerate(tx, 1):
                request = t.get('request') or {}
                response = t.get('response') or {}
                transport_total[str(t.get('status_code'))] += 1
                user = [x.get('content', '') for x in request.get('messages', []) if x.get('role') == 'user']
                preserved.append(any(frozen_user in x for x in user if isinstance(x, str)))
                for ch in response.get('choices', []):
                    finish[str(ch.get('finish_reason'))] += 1
                for k, v in (response.get('usage') or {}).items():
                    if isinstance(v, (float, int)):
                        usage[k] += v
                request_configs[json.dumps({k: request[k] for k in ['temperature', 'top_p', 'top_k', 'max_tokens', 'seed', 'repetition_penalty', 'model'] if k in request}, sort_keys=True)] += 1
            changed = []
            prev = ''
            for j, h in enumerate(history, 1):
                if h['patch'] != prev:
                    changed.append(j)
                prev = h['patch']
            # An exit status can be masked by `|| true`, and `which`/`cat` are not
            # test executions. Require the recorded diagnostic summary itself.
            tests = []
            for j, h in enumerate(history, 1):
                summary = re.findall(r'Public (?:test files|checks): (\d+); failed: (\d+)', h.get('stdout_stderr', ''))
                if 'run_public_tests' in h['command'] and summary:
                    tests.append((j, h, int(summary[-1][1])))
            public_pass = tests[-1][2] == 0 if tests else None
            ast_sha = None
            try:
                ast_sha = sha(ast.dump(ast.parse(final), include_attributes=False))
            except SyntaxError:
                pass
            row = dict(key=key, model=model, family=c['family_id'], condition=SHORT[c['condition']], rep=c['repetition'], seed=c['seed'], run_id=dr.name,
                       local_dir=str(dr), hpc_dir='/home/s224049759/projects/final-experiment-runs/' + rootname + '/' + dr.name,
                       valid=d['technical_valid'], fun=ev['functionality_pass'] if d['technical_valid'] else None,
                       sec=ev['focal_security_pass'] if d['technical_valid'] else None,
                       unsafe=ev['unsafe_completion'] if d['technical_valid'] else None,
                       safe=bool(ev['functionality_pass'] and ev['focal_security_pass']) if d['technical_valid'] else None,
                       outcome=outcome(d), termination=tm['termination_reason'], requests=tm['model_request_count'], commands=len(history),
                       trajectory_messages=len(tr['messages']), first_edit=changed[0] if changed else None, edit_events=changed,
                       no_final_change=initial == final, final_sha256=sha(final), final_ast_sha256=ast_sha,
                       final_bytes=len(final.encode()), patch_bytes=(dr / 'final.patch').stat().st_size,
                       policy_violations=tm['policy_violation_count'], invalid_response_count=tm['invalid_response_count'],
                       failure_dimension=tm['failure_dimension'], functional_outcome_metric=tm['functional_outcome'],
                       inspected_files=tm['files_inspected'], finish_reasons=dict(finish), usage=dict(usage), request_configs=dict(request_configs),
                       max_prompt_tokens=max(t['token_budget']['prompt_tokens'] for t in budgets),
                       min_completion_limit=min(t['token_budget']['effective_completion_limit'] for t in budgets),
                       initial_prompt_tokens=budgets[0]['token_budget']['prompt_tokens'],
                       treatment_in_every_request=all(preserved), request_count_in_transport=len(tx),
                       memory_envelope_bytes=len(frozen_user.split('[BEGIN_MEMORY_CONTEXT]')[1].split('[END_MEMORY_CONTEXT]')[0].encode()) if '[BEGIN_MEMORY_CONTEXT]' in frozen_user else 0,
                       public_test_calls=len(tests), public_test_lines=[j for j, _, _ in tests], last_public_pass=public_pass,
                       masked_public_failures=sum(h.get('returncode') == 0 and failures > 0 for _, h, failures in tests),
                       last_public_output=tests[-1][1].get('stdout_stderr') if tests else None,
                       last_public_patch_matches_final=tests[-1][1].get('patch') == history[-1].get('patch') if tests and history else None,
                       protected_intact=d['protected_paths_intact'], evaluator=ev,
                       event_counts=dict(Counter(e['event'] for e in events)))
            records.append(row)
            integ = dict(key=key, frozen_hash_matches_binding=d['frozen_message_sha256'] == bound['messages_sha256'][c['condition']],
                         baseline_hash_matches=sha(initial) == bound['baseline_B']['sha256'],
                         frozen_user_in_trajectory=frozen_user in actual_user,
                         treatment_in_every_request=all(preserved), outcome_consistent=all(d['evaluation'][k] == ev[k] for k in ['functionality_pass', 'focal_security_pass', 'unsafe_completion']))
            integrity.append(integ)
            for j, e in enumerate(events, 1):
                if e['event'] in ['ACTION_POLICY_VIOLATION', 'PROTECTED_PATH_WRITE_ATTEMPT', 'INVALID_ACTION_FORMAT', 'INVALID_ACTION_CONTENT', 'protocol_terminated']:
                    event_refs.append(dict(key=key, line=j, file=str(dr/'adapter-events.jsonl'), event=e))
            # Keep only unique role/content/actions. Full raw responses stay in the original JSON.
            readable = []
            for j, msg in enumerate(tr['messages']):
                content = msg.get('content') or ''
                actions = (msg.get('extra') or {}).get('actions', [])
                readable.append(dict(index=j, role=msg['role'], content=content, tool_calls=msg.get('tool_calls'), actions=actions))
                if msg['role'] == 'assistant':
                    for kind, pat in [('memory_lexical_candidate', MEMORY), ('trust_lexical_candidate', TRUST)]:
                        if pat.search(content):
                            refs.append(dict(key=key, kind=kind, index=j, file=str(dr/'trajectory.json'), text=content))
            transcript_index.append(dict(key=key, run_id=dr.name, file=str(dr/'trajectory.json'), messages=readable))
    groups = {}
    for model in ARMS:
        groups[model] = summarise([r for r in records if r['model'] == model])
        for cond in SHORT.values():
            groups[f'{model}/{cond}'] = summarise([r for r in records if r['model'] == model and r['condition'] == cond])
    for family in sorted(bindings):
        groups[family] = summarise([r for r in records if r['family'] == family])
        for model in ARMS:
            groups[f'{model}/{family}'] = summarise([r for r in records if r['model'] == model and r['family'] == family])
        for cond in SHORT.values():
            groups[f'{family}/{cond}'] = summarise([r for r in records if r['family'] == family and r['condition'] == cond])
    assert len(records) == 312
    assert len({r['key'] for r in records}) == 312
    assert all(Counter(r['family'] for r in records if r['model'] == m).values() for m in ARMS)
    for fn, data in [('runs.json',records),('aggregates.json',groups),('integrity.json',integrity),('lexical-candidates.json',refs),('events.json',event_refs),('transcripts.json',transcript_index)]:
        (HERE/fn).write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps(dict(files=len(inventory), runs=len(records), transport_statuses=dict(transport_total),
                         messages=sum(r['trajectory_messages'] for r in records), requests=sum(r['requests'] for r in records),
                         commands=sum(r['commands'] for r in records),
                         integrity_failures=[x for x in integrity if not all(v for k,v in x.items() if k != 'key')]),indent=2))
    for model in ARMS:
        print(model,json.dumps({k:v for k,v in groups[model].items() if k != 'run_ids'}))
    print('FAMILY n valid functionality security unsafe safe-completion no-edits')
    for f in sorted(bindings):
        g=groups[f]
        print(f,g['attempts'],g['valid'],g['functionality'],g['security'],g['unsafe'],g['safe_completion'],g['no_edits'])


if __name__ == '__main__':
    extract()
