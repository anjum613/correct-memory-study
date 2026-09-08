"""Private extraction of planning components from saved source memories only."""
from pathlib import Path
import pandas as pd
import json,re,hashlib,math
ROOT=Path(__file__).resolve().parents[1]
d=pd.read_csv(ROOT/'private/run-mapping.csv');rows=[]
for f in sorted(d.family.unique()):
 r=d[(d.family==f)&(d.condition=='C')&(d.harness=='MiniSWE')].iloc[0]
 messages=json.loads((Path(r.original_result).parent/'frozen-messages.json').read_text())
 p=next(x['content'] for x in messages if x['role']=='user')
 memory=p.split('[BEGIN_MEMORY_CONTEXT]',1)[1].split('[END_MEMORY_CONTEXT]',1)[0]
 clean=memory.split('[NEUTRAL_PADDING]',1)[0].strip()
 if 'Reusable procedure\n' in clean:
  proc=clean.split('Reusable procedure\n',1)[1].split('\n\nWhy it was correct in the source',1)[0]
  assumption=clean.split('Why it was correct in the source\n',1)[1].split('\n\nImplementation steps',1)[0]
  proc+='\n\nImplementation steps\n'+clean.split('Implementation steps\n',1)[1]
 else:
  proc=clean.split('Source procedure\n',1)[1].split('\n\nWhy it was correct in its source setting',1)[0]
  assumption=clean.split('Why it was correct in its source setting\n',1)[1]
 conditions={'N':'','P':'Procedure\n'+proc,'A':'Source assumption\n'+assumption,'PA':'Procedure\n'+proc+'\n\nSource assumption\n'+assumption}
 rows.append({'family':f,'status':'draft extracted components; not executed or final frozen','source_memory_sha256':hashlib.sha256(memory.encode()).hexdigest(),
              'procedure':proc,'source_assumption':assumption,'conditions':conditions,'utf8_bytes':{k:len(v.encode()) for k,v in conditions.items()},'token_counts':None})
(ROOT/'prospective/memory_components.json').write_text(json.dumps(rows,indent=2)+'\n')
pd.DataFrame([{'fixed_families':13,'repetitions_per_arm':r,'runs_per_configuration':13*4*r,'two_arm_half_width_pp':100*1.96*math.sqrt(1/(2*13*r)),'interaction_half_width_pp':100*1.96*math.sqrt(1/(13*r))} for r in [2,4,8,15,16,30,32,64]]).to_csv(ROOT/'prospective/precision_grid.csv',index=False)
print('Prepared 13 draft component pairs; no execution.')
