"""Additional read-only calculations on the captured evidence; no code under study is run."""
from pathlib import Path
from collections import Counter, defaultdict
import ast, csv, hashlib, json, re, shlex, statistics

HERE=Path(__file__).resolve().parent
DATA=HERE/'evidence'; OUT=HERE/'derived'
R=json.loads((OUT/'records.json').read_text())
COMPLETE=('GPT55','Luna','Terra')

def write(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')

def csvwrite(name,rows):
    if not rows:return
    with (OUT/name).open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader();w.writerows(rows)

# Compare the capture hashes against the independently recorded per-attempt manifests.
source=json.loads((DATA/'__audit_source_manifest.json').read_text())
hashes={r['path']:r['sha256'] for r in source['files']}
manifest_rows=[]
for r in R:
    if r['harness']!='Codex':continue
    p=DATA/r['record_path']/'sha256-manifest.txt'
    checked=omitted=0;mismatches=[]
    if p.exists():
        for line in p.read_text().splitlines():
            expected,relative=line.split('  ',1)
            relative_path=str((p.parent.parent/relative).relative_to(DATA))
            actual=hashes.get(relative_path)
            if actual is None:omitted+=1;continue
            checked+=1
            if actual!=expected:mismatches.append({'path':relative_path,'recorded_sha256':expected,'captured_sha256':actual})
    manifest_rows.append({'run_id':r['run_id'],'checked_files':checked,'omitted_files':omitted,
                          'mismatches':mismatches,'manifest_exists':p.exists()})
write('record_manifest_integrity.json',manifest_rows)

# All completed shell-command events, with source line references. These are actual logged
# shell executions, including commands nested within Codex code-mode tools.
commands=[];tool_summary=[];patches=[]
for r in R:
    if r['harness']!='Codex':continue
    p=DATA/r['record_path']/'events.jsonl'
    rc=[]
    for n,line in enumerate(p.read_text().splitlines() if p.exists() else [],1):
        e=json.loads(line);i=e.get('item',{})
        if e.get('type')!='item.completed' or i.get('type')!='command_execution':continue
        c=i['command'];out=i.get('aggregated_output','')
        try:
            parts=shlex.split(c);inner=parts[-1] if parts and parts[0].endswith(('bash','sh')) else c
        except ValueError:inner=c
        row={'run_id':r['run_id'],'model':r['model'],'family':r['family'],'condition':r['condition'],
             'event_path':str(p.relative_to(DATA)),'line':n,'command':c,'inner_command':inner,
             'exit_code':i.get('exit_code'),'output':out,
             'direct_public_module_no_output':bool(re.fullmatch(r'(?:python3|/usr/bin/python3)\s+(?:\./)?public_tests\.py',inner.strip()) and i.get('exit_code')==0 and not out.strip()),
             'zero_unittest_count':bool(re.search(r'\bRan 0 tests\b',out)),
             'python_missing':bool(re.search(r'python: command not found',out)),
             'pytest_missing':bool(re.search(r'(?:pytest: command not found|No module named pytest)',out))}
        rc.append(row);commands.append(row)
    for n,c in enumerate(rc):
        if c['direct_public_module_no_output']:
            c['later_commands']=[{'line':x['line'],'command':x['command']} for x in rc[n+1:]]
    patch=DATA/r['record_path']/'final.patch'
    patches.append({**{k:r[k] for k in ('run_id','model','family','condition','valid','functionality','security','termination')},
                    'patch_exists':patch.exists(),'patch_bytes':patch.stat().st_size if patch.exists() else None})
    tool_summary.append({**{k:r[k] for k in ('run_id','model','family','condition','valid','functionality','security')},
        'command_events':len(rc),'direct_public_module_no_output':any(c['direct_public_module_no_output'] for c in rc),
        'zero_unittest_count':any(c['zero_unittest_count'] for c in rc),
        'python_missing':any(c['python_missing'] for c in rc),'pytest_missing':any(c['pytest_missing'] for c in rc)})
with (OUT/'commands.jsonl').open('w') as f:
    for c in commands:f.write(json.dumps(c,ensure_ascii=False)+'\n')
write('no_op_candidates.json',[c for c in commands if c['direct_public_module_no_output']])
csvwrite('tool_summary.csv',tool_summary);csvwrite('patch_summary.csv',patches)

# Complete-case common panels and family-stratum contrasts; all post hoc/descriptive.
common=[]
families=sorted({r['family'] for r in R})
panel=[f for f in families if all(len(a:=[r for r in R if r['model']==m and r['family']==f])==8 and all(r['valid'] for r in a) for m in COMPLETE)]
for m in COMPLETE:
    for cohort,fs in [('common_all_conditions_all_models',panel),('legacy_F',[f for f in families if f.startswith('F')]),('extension_X',[f for f in families if f.startswith('X')])]:
        for l,right in [('C','N'),('I','N'),('B','C'),('B','N')]:
            ds=[];kept=[]
            for f in fs:
                a=[r for r in R if r['model']==m and r['family']==f and r['condition']==l]
                b=[r for r in R if r['model']==m and r['family']==f and r['condition']==right]
                if len(a)==len(b)==2 and all(r['valid'] for r in a+b):
                    ds.append((sum(r['unsafe'] for r in a)-sum(r['unsafe'] for r in b))/2);kept.append(f)
            common.append({'model':m,'panel':cohort,'contrast':l+'-'+right,'family_count':len(ds),'difference':statistics.mean(ds) if ds else None,'families':';'.join(kept)})
csvwrite('robustness_panels.csv',common)

# Bounds on U as a hypothetical outcome for invalid attempts. This is a sensitivity
# calculation ONLY; stored validity and outcomes are never changed or imputed.
bounds=[]
for m in COMPLETE:
    for l,right in [('C','N'),('I','N'),('B','C')]:
        a=[r for r in R if r['model']==m and r['condition']==l]
        b=[r for r in R if r['model']==m and r['condition']==right]
        ua=sum(r['valid'] and r['unsafe'] for r in a);ub=sum(r['valid'] and r['unsafe'] for r in b)
        ia=sum(not r['valid'] for r in a);ib=sum(not r['valid'] for r in b)
        bounds.append({'model':m,'contrast':l+'-'+right,'left_invalid':ia,'right_invalid':ib,
                       'lower':ua/26-(ub+ib)/26,'upper':(ua+ia)/26-ub/26,
                       'note':'Hypothetical binary completion of invalids; not measured outcomes or frozen estimand.'})
csvwrite('invalid_sensitivity_bounds.csv',bounds)

# Traceable four-way outcomes and failure causes for every harness.
native_check=[];failures=[]
for r in R:
    if r['harness']=='MiniSWE':
        raw=json.loads((DATA/r['result_path']).read_text());ev=raw['evaluation']
        native_check.append({'run_id':r['run_id'],'computed_unsafe_consistent':r['unsafe']==(bool(r['functionality'] and not r['security']) if r['valid'] else None)})
    if not r['valid'] or not r['functionality']:
        failures.append(r)
write('native_integrity.json',native_check);write('all_failures.json',failures)

print(json.dumps({'manifest_files_checked':sum(r['checked_files'] for r in manifest_rows),
                  'manifest_files_mismatched':sum(len(r['mismatches']) for r in manifest_rows),
                  'complete_common_panel':panel,
                  'tool_summary':{m:{k:sum(r[k] for r in tool_summary if r['model']==m) for k in ['direct_public_module_no_output','zero_unittest_count','python_missing','pytest_missing']} for m in (*COMPLETE,'Spark')},
                  'empty_patches':dict(Counter(r['model'] for r in patches if r['patch_bytes']==0))},indent=2))
