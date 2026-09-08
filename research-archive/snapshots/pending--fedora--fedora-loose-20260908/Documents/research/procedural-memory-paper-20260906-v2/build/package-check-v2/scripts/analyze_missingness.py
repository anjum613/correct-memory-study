"""Sharp finite-cohort bounds and treatment-specific measurement coverage."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
E=pd.read_csv(ROOT/'data/measurement_components.csv')
D=pd.read_csv(ROOT/'data/outcomes.csv')
MODELS=['GPT55','Luna','Terra','QwenNext','Qwen30','Devstral']
LABELS={'GPT55':'GPT-5.5 Low','Luna':'Luna Medium','Terra':'Terra Medium','QwenNext':'Qwen Next','Qwen30':'Qwen 30B','Devstral':'Devstral'}
CATS=['external_interruption','session_budget_timeout','candidate_execution_exception','evaluator_lowering_incompatibility']
CONDS=['N','C','I','B']
assert len(E)==624 and E.record.is_unique
assert E.set_index('record').original_technical_validity.equals(D.set_index('record').revised_valid)
rows=[]
for m in MODELS:
    for c in CONDS:
        q=E[(E.model==m)&(E.condition==c)]
        rows.append({'model':m,'condition':c,**{k:int(q.event_category.eq(k).sum()) for k in CATS},
                     'recorded':len(q),'valid':int(q.original_technical_validity.sum()),
                     'known_F':int(q.observed_F.notna().sum()),'known_S':int(q.observed_S.notna().sum()),
                     'unresolved_U':int(q.U_lower.ne(q.U_upper).sum())})
J=pd.DataFrame(rows);J.to_csv(ROOT/'generated/measurement_coverage.csv',index=False)
bounds=[]
for m in MODELS:
    q=E[E.model==m].copy()
    for a,b in [('C','N'),('I','N'),('B','C')]:
        for mode in ['all_invalid_unresolved','preserve_observed_components']:
            z=q.copy()
            if mode=='all_invalid_unresolved':
                z.loc[~z.original_technical_validity,'U_lower']=0
                z.loc[~z.original_technical_validity,'U_upper']=1
            cells=z.groupby(['family','condition'])[['U_lower','U_upper']].mean()
            # All 13 fixed families and both recorded repetitions are retained.
            lower=cells.xs(a,level='condition').U_lower-cells.xs(b,level='condition').U_upper
            upper=cells.xs(a,level='condition').U_upper-cells.xs(b,level='condition').U_lower
            assert len(lower)==13 and (lower<=upper).all()
            bounds.append({'model':m,'contrast':a+'-'+b,'mode':mode,'families':13,
                           'lower':float(lower.mean()*100),'upper':float(upper.mean()*100),
                           'unresolved_A':int(z[z.condition==a].U_lower.ne(z[z.condition==a].U_upper).sum()),
                           'unresolved_B':int(z[z.condition==b].U_lower.ne(z[z.condition==b].U_upper).sum())})
B=pd.DataFrame(bounds);B.to_csv(ROOT/'generated/missingness_bounds.csv',index=False)
def fmt(x):return f'{x:+.1f}' if abs(x)>1e-8 else '0.0'
def interval(row):return '['+fmt(row.lower)+', '+fmt(row.upper)+']'
text=[r'\begin{tabular}{llll}',r'\toprule',r'Configuration & C$-$N & I$-$N & B$-$C\\',r'\midrule']
for m in MODELS:
    g=B[(B.model==m)&(B['mode']=='preserve_observed_components')].set_index('contrast')
    text.append(LABELS[m]+' & '+' & '.join(interval(g.loc[c]) for c in ['C-N','I-N','B-C'])+r'\\')
text.extend([r'\bottomrule',r'\end{tabular}'])
(ROOT/'generated/missingness_bounds.tex').write_text('\n'.join(text)+'\n')
text=[r'\begin{tabular}{llrrrrrr}',r'\toprule',r'Configuration & Arm & Interrupt & Time cap & Exception & Lowering & Known $F$ & Known $S$\\',r'\midrule']
for m in MODELS:
    for i,(_,r) in enumerate(J[J.model==m].iterrows()):
        text.append((LABELS[m] if i==0 else '')+' & '+r.condition+' & '+' & '.join(str(r[k]) for k in CATS+['known_F','known_S'])+r'\\')
    text.append(r'\addlinespace')
text.extend([r'\bottomrule',r'\end{tabular}'])
(ROOT/'generated/measurement_coverage.tex').write_text('\n'.join(text)+'\n')
text=[r'\begin{tabular}{llll}',r'\toprule',r'Configuration & Contrast & All invalids unresolved & Components retained\\',r'\midrule']
for m in MODELS:
    for i,c in enumerate(['C-N','I-N','B-C']):
        q=B[(B.model==m)&(B.contrast==c)].set_index('mode')
        text.append((LABELS[m] if i==0 else '')+' & '+c.replace('-','$-$')+' & '+interval(q.loc['all_invalid_unresolved'])+' & '+interval(q.loc['preserve_observed_components'])+r'\\')
    text.append(r'\addlinespace')
text.extend([r'\bottomrule',r'\end{tabular}'])
(ROOT/'generated/bounds_information_comparison.tex').write_text('\n'.join(text)+'\n')
summary={'recorded':624,'historically_valid':595,'invalid':29,'invalid_known_F':int(E.loc[~E.original_technical_validity,'observed_F'].notna().sum()),'invalid_known_S':int(E.loc[~E.original_technical_validity,'observed_S'].notna().sum()),'invalid_known_U':int(E.loc[~E.original_technical_validity,'U_lower'].eq(E.loc[~E.original_technical_validity,'U_upper']).sum()),
         'unresolved_U':int(E.U_lower.ne(E.U_upper).sum()),'meaning':'identification bounds for fixed recorded submissions; not confidence intervals or estimates for interrupted counterfactual continuations'}
(ROOT/'generated/missingness_summary.json').write_text(json.dumps(summary,indent=2))
print(B[B['mode']=='preserve_observed_components'][['model','contrast','lower','upper']].to_string(index=False))
