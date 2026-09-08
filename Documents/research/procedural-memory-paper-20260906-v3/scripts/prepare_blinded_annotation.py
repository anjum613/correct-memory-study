"""Freeze an outcome-independent sample and prepare visible, model-masked packets.

This private preparation script reads saved artifacts only. It never executes
candidate code or an evaluator. The public selection rule uses design labels,
not F/S/U, termination, or earlier case selection.
"""
from pathlib import Path
import hashlib,json,re
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
D=pd.read_csv(ROOT/'private/run-mapping.csv')
FAMS=sorted(D.family.unique())
MODELS=['GPT55','Luna','Terra','QwenNext','Qwen30','Devstral']
CONDS=['N','C','I','B']
SEED=2026090602
out=ROOT/'annotation/blinded'
assert not out.exists(), 'Frozen packets must not be overwritten.'
out.mkdir()
rng=np.random.default_rng(SEED)
cells=[(f,c) for f in FAMS for c in CONDS]
# Balanced configuration assignments: four configurations appear nine times,
# two eight times. Randomize both the model list and the cell assignment.
models=list(rng.permutation(MODELS))*9
models=models[:len(cells)]
rng.shuffle(models)
reps=rng.integers(1,3,len(cells))
order=rng.permutation(len(cells))
family_notes={x['family']:x for x in json.loads((ROOT/'data/families.json').read_text())}

def mask(t):
    t=re.sub(r'/(?:home|Users|mnt/data)/[^\s\"\'<>]+','[LOCAL_PATH]',t)
    t=re.sub(r'\b(?:gpt-[\w.\-]+|GPT-?[\w.\-]+|Qwen/[\w./\-]+|mistralai/[\w./\-]+)\b','[MODEL]',t,flags=re.I)
    t=re.sub(r'\b(?:Codex|MiniSWE|mini-SWE-agent|Devstral|Terra|Luna|QwenNext|Qwen30|GPT55|Qwen)\b','[CONFIGURATION]',t,flags=re.I)
    t=re.sub(r'\b(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b','[ADDRESS]',t)
    t=re.sub(r'\b[0-9a-f]{24,64}\b','[IDENTIFIER]',t)
    t=re.sub(r'\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b','[IDENTIFIER]',t)
    t=re.sub(r'(?:s\d{8,}|anjum)@[\w.\-]+','[ACCOUNT]',t)
    t=re.sub(r'\b(?:hpc\.it\.deakin\.edu\.au|Workstation-Pro-E800-G4-WS950T)\b','[HOST]',t,flags=re.I)
    return t

def lines(t,prefix):
    return '\n'.join(f'{prefix}{i:04d} {line}' for i,line in enumerate(mask(t).splitlines(),1))

def visible(p,harness):
    events=[]
    native=list((p/'native-codex-home/sessions').rglob('*.jsonl')) if (p/'native-codex-home/sessions').exists() else []
    if harness=='Codex' and native:
        for i,line in enumerate(native[0].read_text().splitlines(),1):
            obj=json.loads(line)
            if obj.get('type')!='response_item':continue
            x=obj.get('payload',{});kind=x.get('type')
            if kind=='message' and x.get('role')=='assistant':
                content='\n'.join(c.get('text','') for c in x.get('content',[]) if c.get('text'))
                events.append((f'E{i:04d}','agent statement',content))
            elif kind in ['function_call','custom_tool_call']:
                events.append((f'E{i:04d}','tool request',x.get('name','')+'\n'+str(x.get('arguments',x.get('input','')))))
            elif kind in ['function_call_output','custom_tool_call_output']:
                events.append((f'E{i:04d}','tool response',str(x.get('output',''))))
        return events,'native visible response items; encrypted reasoning omitted'
    f=p/'trajectory.json'
    if harness=='MiniSWE' and f.exists():
        x=json.loads(f.read_text())
        for i,m in enumerate(x.get('messages',[]),1):
            if m.get('role') not in ['assistant','tool']:continue
            content=m.get('content','')
            if not isinstance(content,str):content=json.dumps(content,ensure_ascii=False)
            calls=m.get('tool_calls',[])
            if calls:
                content+='\nTOOL REQUESTS\n'+'\n'.join(str(c.get('function',{}).get('arguments','')) for c in calls)
            events.append((f'E{i:04d}','agent statement/tool request' if m['role']=='assistant' else 'tool response',content))
        return events,'saved visible messages and tool calls'
    return [],'required native trace unavailable; no replacement sample'

manifest=[]
for k,idx in enumerate(order,1):
    f,c=cells[idx];m=models[idx];rep=int(reps[idx]);r=D[(D.family==f)&(D.condition==c)&(D.model==m)&(D.rep==rep)].iloc[0]
    p=Path(r.original_result).parent; packet=f'P{k:03d}'
    final=Path(r.submitted_service) if 'submitted_service' in r and pd.notna(r.submitted_service) else None
    if final is None or not final.exists():
        options=list(p.glob('working-copy/app/service.*'))
        if r.harness=='Codex':options+=list((p.parent/'workspace/app').glob('service.*'))
        final=next((x for x in options if x.suffix in ['.py','.csirpy']),None)
    initial_base=Path('/home/anjum/contract-validity-review-20260906-v1/frozen-families')/f/'baseline/app'
    initial=initial_base/('service.csirpy' if f=='X02' else 'service.py')
    # Use the frozen source-memory text from a C run in the same family.
    source_row=D[(D.family==f)&(D.condition=='C')&(D.harness=='MiniSWE')].iloc[0]
    source_p=Path(source_row.original_result).parent
    source_messages=json.loads((source_p/'frozen-messages.json').read_text())
    source_task=next(x['content'] for x in source_messages if x['role']=='user')
    memory=source_task.split('[BEGIN_MEMORY_CONTEXT]',1)[1].split('[END_MEMORY_CONTEXT]',1)[0] if '[BEGIN_MEMORY_CONTEXT]' in source_task else source_task
    if r.harness=='MiniSWE':
        msgs=json.loads((p/'frozen-messages.json').read_text());prompt=next(x['content'] for x in msgs if x['role']=='user')
    else:prompt=(p/'prompt.txt').read_text() if (p/'prompt.txt').exists() else 'Task prompt unavailable.'
    # Omit padding only; preserve all non-padding task/memory text.
    memory=re.sub(r'(?m)^.*(?:neutral padding|NEUTRAL_PADDING).*$','[PADDING LINE OMITTED]',memory)
    events,availability=visible(p,r.harness)
    notes=family_notes[f]
    text=[f'# Packet {packet}', '', '## Target task and delivered context',lines(prompt,'Q'),'',
          '## Source procedure supplied to annotators for comparison',lines(memory.strip(),'M'),'',
          '## Contract summary',f"Source assumption: {notes['source']}\nTarget change: {notes['shift']}\nFocal property: {notes['witness']}",'',
          '## Initial implementation',lines(initial.read_text(),'I') if initial.exists() else 'Unavailable','',
          '## Visible chronological trace',availability,'']
    for event,kind,content in events:text.extend([f'### {event}: {kind}',lines(content,event+'L'),''])
    text+=['## Saved final implementation',lines(final.read_text(),'F') if final and final.exists() else 'Unavailable','']
    text+=['## Saved patch',lines((p/'final.patch').read_text(),'D') if (p/'final.patch').exists() else 'Unavailable','']
    payload=mask('\n'.join(text))
    dest=out/(packet+'.md');dest.write_text(payload)
    manifest.append({'packet':packet,'record':r.record,'run_id':r.run_id,'model':m,'family':f,'condition':c,'rep':rep,
                     'packet_sha256':hashlib.sha256(payload.encode()).hexdigest(),'bytes':len(payload.encode()),
                     'visible_events':len(events),'availability':availability,'original_result':str(p/'result.json'),
                     'saved_implementation':str(final) if final else None})
pd.DataFrame(manifest).to_csv(ROOT/'private/annotation-sample-mapping.csv',index=False)
public=[{k:v for k,v in x.items() if k in ['packet','packet_sha256','bytes','visible_events','availability']} for x in manifest]
(ROOT/'annotation/sample-receipt.json').write_text(json.dumps({'version':'behavior-sample-v1','seed':SEED,'selected':52,'selection':'one run per family-condition cell; balanced shuffled configuration labels; random repetition; no outcomes or availability used; no replacement','overlap':'both annotators code all 52 packets','packets':public},indent=2))
(out/'CODEBOOK.md').write_text((ROOT/'annotation/CODEBOOK.md').read_text())
print('Frozen 52 packets; bytes',sum(x['bytes'] for x in manifest),'events',sum(x['visible_events'] for x in manifest))
print(pd.DataFrame(manifest).groupby('model').size().to_dict())
