"""Index all visible conversation/tool records; encrypted reasoning is not interpreted."""
import json
from pathlib import Path
from collections import Counter
import re

HERE=Path(__file__).resolve().parent
DATA=HERE/'evidence';OUT=HERE/'derived'
TRACE=OUT/'visible-traces';TRACE.mkdir(exist_ok=True)
records=json.loads((OUT/'records.json').read_text())
summary=[];messages=[];errors=[]

def stringify(v):
    if isinstance(v,str):return v
    if isinstance(v,list):return '\n'.join(stringify(x.get('text',x)) if isinstance(x,dict) else stringify(x) for x in v)
    return json.dumps(v,ensure_ascii=False)

for r in records:
    items=[];encrypted=0;event_counts=Counter();parse_errors=0
    if r['harness']=='Codex' and r['native_paths']:
        for file in r['native_paths']:
            p=DATA/file
            for line_number,line in enumerate(p.read_text().splitlines(),1):
                try:d=json.loads(line)
                except ValueError:
                    parse_errors+=1;continue
                a=d.get('payload',{});event_counts[d.get('type')]+=1
                if d.get('type')!='response_item':continue
                kind=a.get('type');role=a.get('role')
                if kind=='reasoning':
                    encrypted+=int(bool(a.get('encrypted_content')))
                    # Only plaintext summaries, if any, are available as evidence.
                    text=stringify(a.get('summary',[]))
                    if not text:continue
                    role='reasoning_summary'
                elif kind=='message':
                    text=stringify(a.get('content',[]))
                elif kind in ('custom_tool_call','function_call'):
                    role='tool_call';text=a.get('name','')+'\n'+stringify(a.get('input',a.get('arguments','')))
                elif kind in ('custom_tool_call_output','function_call_output'):
                    role='tool_output';text=stringify(a.get('output',''))
                else:continue
                items.append({'role':role,'text':text,'file':file,'line':line_number,
                              'kind':kind,'call_id':a.get('call_id')})
    elif r['harness']=='Codex':
        file=r['record_path']+'/events.jsonl';p=DATA/file
        for line_number,line in enumerate(p.read_text().splitlines() if p.exists() else [],1):
            try:d=json.loads(line)
            except ValueError:parse_errors+=1;continue
            event_counts[d.get('type')]+=1;a=d.get('item',{})
            if d.get('type')=='item.completed':
                items.append({'role':'assistant' if a.get('type')=='agent_message' else 'tool_output',
                              'text':a.get('text',stringify(a)),'file':file,'line':line_number,'kind':a.get('type')})
    else:
        file=r['transcript_path'];p=DATA/file;d=json.loads(p.read_text())
        for n,a in enumerate(d['messages']):
            event_counts[a.get('role')]+=1
            text=stringify(a.get('content') or '')
            if text:items.append({'role':a.get('role'),'text':text,'file':file,'json_pointer':f'/messages/{n}/content','kind':'message'})
            for k,t in enumerate(a.get('tool_calls') or []):
                f=t.get('function',{})
                items.append({'role':'tool_call','text':f.get('name','')+'\n'+stringify(f.get('arguments','')),
                              'file':file,'json_pointer':f'/messages/{n}/tool_calls/{k}','kind':'function_call'})
    head=f"# {r['model']} {r['family']} {r['condition']} repetition {r['rep']} — {r['run_id']}\n\n"
    head+=f"valid={r['valid']} functionality={r['functionality']} security={r['security']} unsafe={r['unsafe']}\n\n"
    fragments=[head]
    for n,it in enumerate(items):
        location=f"line {it['line']}" if 'line' in it else it['json_pointer']
        fragments.append(f"## {n}: {it['role']} ({it['kind']})\n\nSource: {it['file']} {location}\n\n{it['text']}\n\n")
        if it['role'] in ('assistant','reasoning_summary'):
            messages.append({**{k:r[k] for k in ('run_id','model','family','condition','rep','valid','unsafe')},**it})
    (TRACE/(r['run_id']+'.md')).write_text(''.join(fragments))
    summary.append({'run_id':r['run_id'],'model':r['model'],'visible_items':len(items),
                    'role_counts':dict(Counter(x['role'] for x in items)),
                    'native_event_counts':dict(event_counts),'encrypted_reasoning_records':encrypted,
                    'parse_errors':parse_errors})
(OUT/'trace_coverage.json').write_text(json.dumps(summary,indent=2)+'\n')
with (OUT/'agent_messages.jsonl').open('w') as f:
    for msg in messages:f.write(json.dumps(msg,ensure_ascii=False)+'\n')
hits=[m for m in messages if re.search(r'\bmemor(?:y|ies)\b|source.valid|reus(?:e|ing)|assumptions?|trust.bound|untrusted|irrelevant|precondition',m['text'],re.I)]
(OUT/'memory_rationale_candidates.json').write_text(json.dumps(hits,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'runs_indexed':len(summary),'visible_items':sum(x['visible_items'] for x in summary),
                  'assistant_or_summary_messages':len(messages),'candidate_passages':len(hits),
                  'encrypted_reasoning_records':sum(x['encrypted_reasoning_records'] for x in summary),
                  'parse_errors':sum(x['parse_errors'] for x in summary)},indent=2))
