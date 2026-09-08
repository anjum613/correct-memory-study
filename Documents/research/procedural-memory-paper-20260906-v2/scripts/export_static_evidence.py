"""Private, read-only extraction of saved evidence into anonymous static JSON.

No imported candidate module, test, security witness, or agent is executed.
Original files are never changed. Only visible messages are exported.
"""
from pathlib import Path
import ast,hashlib,json,re
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
D=pd.read_csv(ROOT/'private/run-mapping.csv')
# Reuse exactly the packet masking and visible-item selection functions without
# executing the sample preparation script's top-level sampling/mutation code.
source=ast.parse((ROOT/'scripts/prepare_blinded_annotation.py').read_text())
functions=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in ['mask','visible']]
exec(compile(ast.Module(body=functions,type_ignores=[]),'saved_extraction_functions','exec'))
base_mask=mask
def mask(t):
    # Stop at a backslash as well, preserving escaped JSON after a local path.
    t=re.sub(r"""/(?:home|Users|mnt/data)/[^\s\\"'<>]+""",'[LOCAL_PATH]',t)
    t=base_mask(t)
    t=re.sub(r'\b(?:anjum|s224049759)\b','[AUTHOR]',t,flags=re.I)
    t=re.sub(r'\b[\w.\-]+\.deakin\.edu\.au\b','[HOST]',t,flags=re.I)
    t=re.sub(r'(?i)(?:sk-[a-zA-Z0-9_\-]{20,}|gh[pousr]_[a-zA-Z0-9]{20,})','[CREDENTIAL REMOVED]',t)
    return t
out=ROOT/'evidence';out.mkdir(exist_ok=True)
(out/'records').mkdir(exist_ok=True);(out/'families').mkdir(exist_ok=True)
freeze=Path('/home/anjum/contract-validity-review-20260906-v1/frozen-families')
receipt=[];private=[]
def h(b):return hashlib.sha256(b).hexdigest()
def read(p):return p.read_text() if p and p.exists() else None
def store(rel,obj):
    def redact(x):
        if isinstance(x,str):return x if re.fullmatch(r'[0-9a-f]{64}',x) else mask(x)
        if isinstance(x,list):return [redact(v) for v in x]
        if isinstance(x,dict):return {k:redact(v) for k,v in x.items()}
        return x
    text=json.dumps(redact(obj),indent=2,ensure_ascii=False)+'\n'
    # JSON masking never inserts literal quoting characters.
    json.loads(text)
    p=out/rel;p.write_text(text)
    return {'file':p.relative_to(ROOT).as_posix(),'bytes':len(text.encode()),'sha256':h(text.encode())}
for _,r in D.iterrows():
    p=Path(r.original_result).parent
    final=Path(r.submitted_service) if pd.notna(r.submitted_service) else None
    if final is None or not final.exists():
        options=list(p.glob('working-copy/app/service.*'))
        if r.harness=='Codex':options+=list((p.parent/'workspace/app').glob('service.*'))
        final=next((x for x in options if x.suffix in ['.py','.csirpy']),None)
    patch=Path(r.saved_patch) if pd.notna(r.saved_patch) else p/'final.patch'
    if r.harness=='MiniSWE':
        messages=json.loads((p/'frozen-messages.json').read_text())
        prompt=next(x['content'] for x in messages if x['role']=='user')
    else:prompt=read(p/'prompt.txt')
    events,availability=visible(p,r.harness)
    result=json.loads(Path(r.original_result).read_text())
    if r.harness=='Codex':
        keys=['functionality_result','security_witness_result','technical_validity','termination_reason','final_classification','unsafe_completion','action_count','elapsed_seconds','token_usage']
    else:keys=['evaluation','technical_valid','status','trajectory_metrics','protected_paths_intact']
    obj={'record':r.record,'task_and_delivered_context':prompt,'trace_availability':availability,
         'visible_events':[{'event':a,'kind':b,'text':c} for a,b,c in events],
         'saved_implementation_text':read(final),'saved_patch_text':read(patch),
         'original_observations':{k:result[k] for k in keys if k in result},
         'outcome_join':'data/outcomes.csv; revised labels remain separate from original observations',
         'measurement_join':'data/measurement_components.csv; only explicitly completed components are retained'}
    file=store(Path('records')/(r.record+'.json'),obj)
    receipt.append({**file,'record':r.record,'visible_events':len(events),'trace_available':bool(events),
                    'implementation_available':bool(final and final.exists()),'patch_available':patch.exists(),
                    'task_available':prompt is not None})
    private.append({'record':r.record,'original_result':str(p/'result.json'),'final':str(final),'patch':str(patch),
                    'original_implementation_sha256':h(final.read_bytes()) if final and final.exists() else None})
for f in sorted(D.family.unique()):
    p=freeze/f;aux={}
    for folder in ['app','fixture_api']:
        for q in sorted((p/'baseline'/folder).glob('*.py')):
            if q.name not in ['service.py','__init__.py','public_harness.py']:
                aux[q.relative_to(p/'baseline').as_posix()]=q.read_text()
    name='service.csirpy' if f=='X02' else 'service.py'
    refs={state:read(p/'reference'/state/'app'/name) for state in ['B','U','R']}
    contexts={}
    for c in ['N','C','I','B']:
        row=D[(D.family==f)&(D.condition==c)&(D.harness=='MiniSWE')].iloc[0]
        messages=json.loads((Path(row.original_result).parent/'frozen-messages.json').read_text())
        prompt=next(x['content'] for x in messages if x['role']=='user')
        memory=prompt.split('[BEGIN_MEMORY_CONTEXT]',1)[1].split('[END_MEMORY_CONTEXT]',1)[0] if '[BEGIN_MEMORY_CONTEXT]' in prompt else ''
        contexts[c]={'task_and_context':prompt,'memory_between_delimiters':memory,'memory_sha256':h(memory.encode()),'memory_bytes_between_delimiters':len(memory.encode()),'memory_trimmed_bytes':len(memory.strip('\n').encode())}
    store(Path('families')/(f+'.json'),{'family':f,'workspace_instructions':read(p/'baseline/AGENTS.md'),
          'baseline_implementation_text':read(p/'baseline/app'/name),'reference_implementation_text':refs,
          'supporting_api_text':aux,'frozen_task_and_memory_records':contexts,
          'reference_observations':'data/reference_controls.json',
          'observer_version_and_scope':'data/observer_contract_review.csv; executable sealed witnesses omitted'})
summary={'version':'static-evidence-v2','records':len(receipt),'traces_available':sum(x['trace_available'] for x in receipt),
         'implementations_available':sum(x['implementation_available'] for x in receipt),'patches_available':sum(x['patch_available'] for x in receipt),
         'task_prompts_available':sum(x['task_available'] for x in receipt),'candidate_execution':False,
         'transformations':['personal paths, account and host names masked','session identifiers masked','model labels in content masked; declared configurations remain in outcome data','encrypted reasoning and system/provider metadata excluded','only visible assistant/tool records exported','saved implementations and fixture APIs are static text; sealed executable witnesses omitted'],
         'records_manifest':receipt}
(out/'COVERAGE.json').write_text(json.dumps(summary,indent=2)+'\n')
(ROOT/'private/static-evidence-mapping.json').write_text(json.dumps(private,indent=2)+'\n')
print({k:v for k,v in summary.items() if k!='records_manifest'})
