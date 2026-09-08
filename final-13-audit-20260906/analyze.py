"""Descriptive reanalysis of copied artifacts only. Does not execute agents or evaluators."""
from collections import Counter, defaultdict
from pathlib import Path
from itertools import product
import csv
import hashlib
import json
import statistics

HERE = Path(__file__).resolve().parent
DATA = HERE / 'evidence'
OUT = HERE / 'derived'
OUT.mkdir(exist_ok=True)
COND = {'NO_MEMORY':'N', 'SOURCE_CORRECT_MEMORY':'C', 'MATCHED_IRRELEVANT_MEMORY':'I',
        'SOURCE_MEMORY_PLUS_APPLICABILITY_BOUNDARY':'B'}
MODELS = {'gpt-5.5-low':'GPT55', 'gpt-5.6-luna-medium':'Luna',
          'gpt-5.6-terra-medium':'Terra', 'gpt-5.3-codex-spark-medium':'Spark'}
NATIVE = {'controlled-synthetic-final-13-qwen3-coder-native-recommended-v1':'Qwen30',
          'controlled-synthetic-final-13-qwen3-coder-next-native-recommended-v2':'QwenNext',
          'controlled-synthetic-final-13-devstral-native-recommended-v2':'Devstral'}

def j(path): return json.loads(path.read_text())
def rel(path): return str(path.relative_to(DATA))
def write(name, value): (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')
def csv_write(name, rows):
    if not rows: return
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/name).open('w') as f:
        w = csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

records=[]; integrity=[]; invalid=[]; missing=[]; coverage=[]
for root in sorted(DATA.glob('*codex-*')):
    if not (root/'results.json').exists(): continue
    results=j(root/'results.json'); matrix=j(root/'frozen/protocol/run_matrix.json')['cells']
    by_id={r['run_id']:r for r in results}
    lines=[json.loads(x) for x in (root/'results.jsonl').read_text().splitlines()]
    integrity.append({'root':root.name,'results_json_equals_jsonl':results==lines,
                      'matrix_cells':len(matrix),'recorded':len(results)})
    for c in matrix:
        rid=c['run_id'];r=by_id.get(rid)
        if r is None:
            missing.append({'model':MODELS[c['model_profile']], 'family':c['family_id'],
                            'condition':COND[c['condition']], 'rep':c['repetition'], 'run_id':rid})
            continue
        rec=root/'runs'/rid/'attempts/attempt-001/record'
        rfile=j(rec/'result.json');cl=j(rec/'classification.json')
        ag=j(rec/'agent-execution.json') if (rec/'agent-execution.json').exists() else {}
        fun=r.get('functionality_result') or {};sec=r.get('security_witness_result') or {}
        v=r['technical_validity'];f=fun.get('pass');s=sec.get('pass');u=r['unsafe_completion']
        native=list((rec/'native-codex-home/sessions').glob('**/*.jsonl'))
        events_path=rec/'events.jsonl';events=[];bad_lines=[]
        for n,line in enumerate(events_path.read_text().splitlines() if events_path.exists() else [],1):
            try:events.append(json.loads(line))
            except ValueError:bad_lines.append(n)
        errors=[e for e in events if e.get('type') in ('error','turn.failed')]
        term=r['termination_reason']
        if v: reason=None
        elif term in ('INTERRUPTED','TIMEOUT','MODEL_SERVER_FAILURE','COMMAND_LIMIT'): reason=term
        elif sec.get('focal',{}).get('status')=='HARNESS_ERROR':reason='FOCAL_'+str(sec['focal'].get('error'))
        elif fun.get('worker_output_valid') is False:reason='CANDIDATE_WORKER_ERROR'
        else:reason='OTHER'
        row={'model':MODELS[r['model_profile']],'model_profile':r['model_profile'], 'harness':'Codex',
             'family':r['family_id'],'condition':COND[r['condition']],'rep':r['repetition'],
             'run_id':rid,'order':c['execution_order'],'valid':v,'functionality':f,
             'security':s,'unsafe':u,'classification':r['final_classification'],
             'termination':term,'invalid_reason':reason,'elapsed':r['elapsed_seconds'],
             'action_count':r['action_count'],'command_count':ag.get('command_count'),
             'tokens':(r.get('token_usage') or {}).get('total_tokens'),
             'result_path':rel(rec/'result.json'),'record_path':rel(rec),
             'transcript_path':rel(rec/'transcript.md'),'native_paths':[rel(p) for p in native],
             'started':j(rec/'started.json').get('at'),'finished':j(rec/'finished.json').get('at')}
        records.append(row)
        if not v: invalid.append({**row,'agent_execution_valid':ag.get('technical_validity'),
                                  'functionality_result':fun,'security_result':sec,'errors':errors})
        coverage.append({'run_id':rid,'model':row['model'],'event_count':len(events),
                         'events_invalid_lines':bad_lines,'native_files':len(native),
                         'transcript_exists':(rec/'transcript.md').exists(),
                         'report_equals_record':r==rfile,'classification_equals_result':cl['label']==r['final_classification'],
                         'recomputed_unsafe_consistent':u==(bool(f and not s) if v else None),
                         'forbidden_changes':r['forbidden_changes'],
                         'behavioral_status':j(rec/'behavioral-coding.json').get('status') if (rec/'behavioral-coding.json').exists() else None})

for rootname,model in NATIVE.items():
    root=DATA/rootname
    if not root.exists(): continue
    for p in sorted(root.glob('*/result.json')):
        r=j(p);c=r['cell'];ev=r['evaluation'];tm=r['trajectory_metrics'];rec=p.parent
        records.append({'model':model,'model_profile':r['model']['id'],'harness':'MiniSWE',
                        'family':c['family_id'],'condition':COND[c['condition']], 'rep':c['repetition'],
                        'run_id':c['actual_run_id'],'order':c['qwen_execution_index']+1,
                        'valid':r['technical_valid'],'functionality':ev['functionality_pass'],
                        'security':ev['focal_security_pass'],
                        'unsafe':ev['unsafe_completion'] if r['technical_valid'] else None,
                        'raw_unsafe':ev['unsafe_completion'],
                        'classification':r['status'],'termination':tm['termination_reason'],
                        'invalid_reason':None if r['technical_valid'] else ('EVALUATOR_HARNESS_ERROR' if 'HARNESS_ERROR' in ev.get('statuses',{}).values() else tm['termination_reason']),
                        'result_path':rel(p),'record_path':rel(rec),'transcript_path':rel(rec/'trajectory.json'),
                        'native_paths':[],'started':r['started_at_utc'],'finished':r['finished_at_utc'],
                        'action_count':tm.get('agent_steps'),'command_count':tm.get('command_count')})

def summarize(rs):
    v=[r for r in rs if r['valid']]
    return {'attempts':len(rs),'valid':len(v),'invalid':len(rs)-len(v),
            'F':sum(r['functionality'] is True for r in v),'S':sum(r['security'] is True for r in v),
            'U':sum(r['unsafe'] is True for r in v),
            'FandS':sum(r['functionality'] is True and r['security'] is True for r in v),
            'Ffail':sum(r['functionality'] is False for r in v),
            'FfailSpass':sum(r['functionality'] is False and r['security'] is True for r in v)}

groups=defaultdict(list)
for r in records:groups[r['model']].append(r)
model_summary=[{'model':m,**summarize(rs)} for m,rs in groups.items()]
cells=[]; family=[]; condition=[]
for m,rs in groups.items():
    for f in sorted({r['family'] for r in rs}):
        family.append({'model':m,'family':f,**summarize([r for r in rs if r['family']==f])})
        for c in COND.values():
            rows=[r for r in rs if r['family']==f and r['condition']==c]
            cells.append({'model':m,'family':f,'condition':c,**summarize(rows),
                          'run_ids':';'.join(r['run_id'] for r in rows)})
    for c in COND.values():
        condition.append({'model':m,'condition':c,**summarize([r for r in rs if r['condition']==c])})
contrasts=[]; pairs=[]
for m,rs in groups.items():
    for l,rgt in [('C','N'),('I','N'),('B','C'),('B','N')]:
        for metric in ('unsafe','functionality','security'):
            ds=[]; units=[]
            for f in sorted({r['family'] for r in rs}):
                ls=[r for r in rs if r['family']==f and r['condition']==l]
                rr=[r for r in rs if r['family']==f and r['condition']==rgt]
                if len(ls)==len(rr)==2 and all(x['valid'] for x in ls+rr):
                    d=(sum(x[metric] for x in ls)-sum(x[metric] for x in rr))/2
                    ds.append(d);units.append(f)
                    pairs.append({'model':m,'family':f,'contrast':l+'-'+rgt,'metric':metric,'difference':d,
                                  'left_runs':';'.join(x['run_id'] for x in ls),'right_runs':';'.join(x['run_id'] for x in rr)})
            pval=(sum(abs(sum(s*x for s,x in zip(signs,ds)))>=abs(sum(ds))-1e-12
                      for signs in product([-1,1],repeat=len(ds)))/2**len(ds)) if ds else None
            loo=[sum(ds[:i]+ds[i+1:])/(len(ds)-1) for i in range(len(ds))] if len(ds)>1 else []
            contrasts.append({'model':m,'contrast':l+'-'+rgt,'metric':metric,'families':len(ds),
                              'difference':statistics.mean(ds) if ds else None,'p_exact':pval,
                              'loo_min':min(loo) if loo else None,'loo_max':max(loo) if loo else None,
                              'positive':sum(d>0 for d in ds),'negative':sum(d<0 for d in ds),
                              'zero':sum(d==0 for d in ds),'included_families':';'.join(units)})

repeat=[]
for m,rs in groups.items():
    for f in sorted({r['family'] for r in rs}):
        for c in COND.values():
            a=[r for r in rs if r['family']==f and r['condition']==c]
            if len(a)==2 and all(r['valid'] for r in a):
                repeat.append({'model':m,'family':f,'condition':c,'run_ids':';'.join(r['run_id'] for r in a),
                               'same_U':a[0]['unsafe']==a[1]['unsafe'],'same_F':a[0]['functionality']==a[1]['functionality'],
                               'same_S':a[0]['security']==a[1]['security']})

write('records.json',records);write('invalids.json',invalid);write('integrity.json',integrity)
write('coverage.json',coverage);write('missing.json',missing)
for name,rows in [('models',model_summary),('cells',cells),('family',family),('condition',condition),
                  ('contrasts',contrasts),('family_contrasts',pairs),('repetition',repeat),('records',records),('missing',missing)]:
    csv_write(name+'.csv',rows)
print(json.dumps({'models':model_summary,'invalid_reasons':dict(Counter((r['invalid_reason'] or '') for r in invalid)),
                  'codex_coverage':len(coverage),'missing':len(missing)},indent=2))
