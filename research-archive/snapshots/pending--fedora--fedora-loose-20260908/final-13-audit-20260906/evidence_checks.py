"""Supporting provenance, missing implementation and transport analyses, all from existing files."""
from pathlib import Path
from collections import Counter, defaultdict
from itertools import product
import csv, json, hashlib, statistics

P=Path(__file__).resolve().parent;D=P/'evidence';O=P/'derived'
R=json.loads((O/'records.json').read_text())
CONDS={'N':'NO_MEMORY','C':'SOURCE_CORRECT_MEMORY','I':'MATCHED_IRRELEVANT_MEMORY','B':'SOURCE_MEMORY_PLUS_APPLICABILITY_BOUNDARY'}
SNAP=D/'controlled-synthetic-final-13-codex-v3/frozen/snapshot'
def out(name,rows):
    if name.endswith('.json'):(O/name).write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n');return
    with (O/name).open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)

checks=[];implementation=[];transport=[];length_events=[];configurations=[]
for r in R:
    rec=D/r['record_path'];treatment=SNAP/'treatments'/r['family']/CONDS[r['condition']]
    target=(treatment/'user-content.txt').read_bytes()
    actual=(rec/('prompt.txt' if r['harness']=='Codex' else 'rendered-task.md')).read_bytes()
    checks.append({'run_id':r['run_id'],'model':r['model'],'task_treatment_bytes_equal':actual==target,
                   'prompt_sha256':hashlib.sha256(actual).hexdigest()})
    patch=rec/'final.patch'
    final=(rec/'final-message.txt').read_text() if (rec/'final-message.txt').exists() else None
    missing_tools=bool(final and all(k in final for k in ['list_files','read_file','edit_service','run_public_tests']))
    implementation.append({**{k:r[k] for k in ['run_id','model','family','condition','rep','valid','functionality','security','unsafe','termination','record_path']},
                           'empty_patch':patch.exists() and patch.stat().st_size==0,
                           'reports_required_tools_missing':missing_tools,'final_message':final})
    if r['harness']=='MiniSWE':
        config=json.loads((rec/'agent-config.json').read_text())
        configurations.append({'run_id':r['run_id'],'model':r['model'],
             **{k:config['model'].get(k) for k in ['max_tokens','context_limit','temperature','top_p','top_k','native_tool_calls']},
             **{k:config['agent'].get(k) for k in ['step_limit','wall_time_limit_seconds']}})
        counts=Counter();requests=0;max_prompt=0;ceiling=Counter()
        p=rec/'model-transport.jsonl'
        for n,l in enumerate(p.read_text().splitlines(),1):
            a=json.loads(l);requests+=1;response=a.get('response') or {}
            budget=a.get('token_budget') or {};max_prompt=max(max_prompt,budget.get('prompt_tokens') or 0)
            ceiling[a.get('request',{}).get('max_tokens')]+=1
            for c in response.get('choices',[]):
                reason=c.get('finish_reason');counts[str(reason)]+=1
                if reason=='length':length_events.append({'run_id':r['run_id'],'model':r['model'],'family':r['family'],'condition':r['condition'],
                   'file':str(p.relative_to(D)),'line':n,'attempt':a.get('attempt'),
                   'finish_reason':reason,'completion_tokens':response.get('usage',{}).get('completion_tokens')})
        transport.append({'run_id':r['run_id'],'model':r['model'],'family':r['family'],'condition':r['condition'],
             'requests':requests,'length_finishes':counts['length'],'finish_reasons':dict(counts),
             'max_prompt_tokens':max_prompt,'request_max_tokens_counts':dict(ceiling)})
out('treatment_integrity.json',checks);out('implementation_status.csv',implementation)
out('native_transport.json',transport);out('length_limited_responses.csv',length_events);out('native_configurations.csv',configurations)

contrasts=[]
for model in sorted({r['model'] for r in R}):
    ds=[];families=[];support=[]
    for family in sorted({r['family'] for r in R}):
        a=[r for r in R if r['model']==model and r['family']==family and r['condition']=='C']
        b=[r for r in R if r['model']==model and r['family']==family and r['condition']=='I']
        if len(a)==len(b)==2 and all(r['valid'] for r in a+b):
            ds.append((sum(r['unsafe'] for r in a)-sum(r['unsafe'] for r in b))/2)
            families.append(family);support.extend(r['run_id'] for r in a+b)
    exact=sum(abs(sum(x*s for x,s in zip(ds,signs)))>=abs(sum(ds))-1e-12 for signs in product([-1,1],repeat=len(ds)))/2**len(ds) if ds else None
    contrasts.append({'model':model,'contrast':'C-I','metric':'unsafe','families':len(ds),'difference':statistics.mean(ds) if ds else None,
                      'p_exact':exact,'included_families':';'.join(families),'run_ids':';'.join(support),'status':'Exploratory matched-memory-envelope control contrast'})
out('additional_contrasts.csv',contrasts)
summary={'prompt_matches':sum(x['task_treatment_bytes_equal'] for x in checks),'prompt_total':len(checks),
         'implementation':{m:{'empty':sum(x['empty_patch'] for x in implementation if x['model']==m),
              'valid_Ffail_empty':sum(x['valid'] and not x['functionality'] and x['empty_patch'] for x in implementation if x['model']==m),
              'valid_Ffail_Spass_empty':sum(x['valid'] and not x['functionality'] and x['security'] and x['empty_patch'] for x in implementation if x['model']==m),
              'missing_tool_statements':sum(x['reports_required_tools_missing'] for x in implementation if x['model']==m)} for m in sorted({r['model'] for r in R})},
         'transport':{m:{'requests':sum(x['requests'] for x in transport if x['model']==m),
                         'length_finishes':sum(x['length_finishes'] for x in transport if x['model']==m),
                         'runs_with_length':sum(x['length_finishes']>0 for x in transport if x['model']==m),
                         'max_prompt_tokens':max(x['max_prompt_tokens'] for x in transport if x['model']==m)} for m in ['Qwen30','QwenNext','Devstral']}}
out('evidence_checks_summary.json',summary);print(json.dumps(summary,indent=2))
