"""Read saved evidence only; never imports or executes experimental code."""
from pathlib import Path
import csv,json,hashlib,shutil
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('/home/anjum/contract-validity-review-20260906-v1')
FILES=['VALIDITY_REPORT.md','run_outcomes.csv','reviewed_run_outcomes.csv','model_outcomes.csv','SENSITIVITY.md','SCOPE_AMENDMENT_20260906.md','FINAL_ARTIFACT_MANIFEST.json','REVIEW_RULE_v1.md']
manifest=json.loads((SOURCE/'FINAL_ARTIFACT_MANIFEST.json').read_text())
bind={x['path']:x for x in manifest['files']}
checks=[]
for fn in FILES:
 p=SOURCE/fn; h=hashlib.sha256(p.read_bytes()).hexdigest()
 if fn in bind: assert h==bind[fn]['sha256'],fn
 checks.append({'path':str(p),'sha256':h,'manifest_match':h==bind.get(fn,{}).get('sha256') if fn in bind else None})
 (ROOT/'private/authoritative').mkdir(exist_ok=True)
 shutil.copy2(p,ROOT/'private/authoritative'/fn)
rows=list(csv.DictReader((SOURCE/'run_outcomes.csv').open()))
review={r['run_id']:r for r in csv.DictReader((SOURCE/'reviewed_run_outcomes.csv').open())}
assert len(rows)==624 and len(review)==144
keys=['harness','model','family','condition','rep','original_valid','original_F','original_S','original_U','original_outcome','termination','revised_valid','revised_F','revised_S','revised_U','revised_outcome','review_status','full_contract_adjudication','X06_mixed_fixture_mechanism']
public=[]; mappings=[]
for i,r in enumerate(sorted(rows,key=lambda x:(x['harness'],x['model'],x['family'],x['condition'],int(x['rep']))),1):
 if r['run_id'] in review:
  for k in ['revised_valid','revised_F','revised_S','revised_U']:
   assert r[k]==review[r['run_id']][k],(r['run_id'],k)
 if r['revised_valid']=='False':assert all(r[k]=='' for k in ['revised_F','revised_S','revised_U'])
 pid=f'R{i:04d}'
 public.append({'record':pid,**{k:r[k] for k in keys}})
 mappings.append({'record':pid,**r})
for dest,rs in [('data/outcomes.csv',public),('private/run-mapping.csv',mappings)]:
 with (ROOT/dest).open('w') as f:w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
(ROOT/'private/source-checks.json').write_text(json.dumps(checks,indent=2))
print('Imported 624 rows; 144 reviewed rows agree; all bound authoritative hashes match.')
