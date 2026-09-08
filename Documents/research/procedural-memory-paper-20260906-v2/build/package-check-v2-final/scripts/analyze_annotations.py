"""Describe two completed, isolated LLM annotation passes without score-based adjudication."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DIM={'A':'Explicit assumption recognition before editing','P':'Source procedure without the target check',
     'T':'Target protection present','Z':'No meaningful implementation'}
LABELS=['Y','N','U','NA']
coders=[]
for coder in ['a','b']:
    rows=[json.loads(x) for x in (ROOT/f'annotation/annotator_{coder}.jsonl').read_text().splitlines() if x.strip()]
    t=pd.DataFrame(rows).set_index('packet').sort_index()
    assert len(t)==52 and t.index.is_unique and set(t.index)=={f'P{i:03d}' for i in range(1,53)}
    for dim in DIM:
        assert set(t[dim])<=set(LABELS)
        assert t[f'{dim}_evidence'].map(lambda x:isinstance(x,str) and bool(x.strip())).all()
    coders.append(t)
a,b=coders
sample=pd.read_csv(ROOT/'data/behavior_sample.csv').set_index('packet')
assert set(sample.index)==set(a.index)
summaries=[];long=[];disagreements=[]
for dim in DIM:
    x,y=a[dim],b[dim]
    agree=float(x.eq(y).mean())
    expected=sum(float(x.eq(label).mean()*y.eq(label).mean()) for label in LABELS)
    kappa=(agree-expected)/(1-expected) if expected<1 else None
    resolved=x.isin(['Y','N'])&y.isin(['Y','N'])
    summaries.append({'dimension':dim,'description':DIM[dim],'n':52,'a_yes':int(x.eq('Y').sum()),'b_yes':int(y.eq('Y').sum()),
                      'both_yes':int((x.eq('Y')&y.eq('Y')).sum()),'agree':int(x.eq(y).sum()),'agreement':agree,
                      'kappa_four_categories':kappa,'both_resolved':int(resolved.sum()),
                      'resolved_agree':int((x.eq(y)&resolved).sum()),
                      **{f'{c}_{label}':int(z[dim].eq(label).sum()) for c,z in [('a',a),('b',b)] for label in LABELS}})
    for packet in a.index:
        row=sample.loc[packet]
        long.append({'packet':packet,'record':row.record,'model':row.model,'family':row.family,'condition':row.condition,
                     'dimension':dim,'a':x[packet],'b':y[packet],'both_yes':x[packet]=='Y' and y[packet]=='Y',
                     'a_evidence':a.loc[packet,dim+'_evidence'],'b_evidence':b.loc[packet,dim+'_evidence']})
        if x[packet]!=y[packet]:disagreements.append(long[-1])
S=pd.DataFrame(summaries);S.to_csv(ROOT/'generated/annotation_agreement.csv',index=False)
L=pd.DataFrame(long);L.to_csv(ROOT/'generated/behavior_codes.csv',index=False)
pd.DataFrame(disagreements).to_csv(ROOT/'generated/annotation_disagreements.csv',index=False)
counts=L.groupby(['dimension','condition']).agg(sampled=('packet','size'),both_yes=('both_yes','sum')).reset_index()
counts.to_csv(ROOT/'generated/annotation_by_condition.csv',index=False)
text=[r'\begin{tabular}{p{6.1cm}rrrr}',r'\toprule',r'Observable dimension & Pass A: Y & Pass B: Y & Both Y & Agreement\\',r'\midrule']
for _,r in S.iterrows():text.append(f'{r.dimension}: {r.description} & {r.a_yes} & {r.b_yes} & {r.both_yes} & {r.agree}/52'+r'\\')
text +=[r'\bottomrule',r'\end{tabular}'];(ROOT/'generated/annotation_agreement.tex').write_text('\n'.join(text)+'\n')
text=[r'\begin{tabular}{llrrrrrr}',r'\toprule',r'Dimension & Annotator & Y & N & Uncertain & Unavailable & Paired resolved & $\kappa$\\',r'\midrule']
for _,r in S.iterrows():
    for c in ['a','b']:
        text.append(f'{r.dimension} & {c.upper()} & '+ ' & '.join(str(r[f'{c}_{label}']) for label in LABELS)+f' & {r.both_resolved if c=="a" else ""} & '+(f'{r.kappa_four_categories:.2f}' if c=='a' and pd.notna(r.kappa_four_categories) else '')+r'\\')
text +=[r'\bottomrule',r'\end{tabular}'];(ROOT/'generated/annotation_full_counts.tex').write_text('\n'.join(text)+'\n')
macros={}
for _,r in S.iterrows():
    macros['Code'+r.dimension+'BothYes']=int(r.both_yes)
    macros['Code'+r.dimension+'Agreement']=int(r.agree)
    macros['Code'+r.dimension+'Disagree']=52-int(r.agree)
common={d:(a[d].eq('Y')&b[d].eq('Y')) for d in DIM}
macros['RecognitionAndProtection']=int((common['A']&common['T']).sum())
macros['ProtectionWithoutExplicitRecognition']=int((common['T']&~common['A']).sum())
macros['ProcedureAndProtection']=int((common['P']&common['T']).sum())
(ROOT/'generated/annotation_numbers.tex').write_text('\n'.join('\\newcommand{\\'+k+'}{'+str(v)+'}' for k,v in macros.items())+'\n')
(ROOT/'generated/annotation_summary.json').write_text(json.dumps({'sampled':52,'overlap':52,'label_decisions':208,
                                                              'disagreements':len(disagreements),'annotators':'two isolated LLM sessions; no human annotation',
                                                              'macros':macros},indent=2))
print(S[['dimension','a_yes','b_yes','both_yes','agree','both_resolved','kappa_four_categories']].to_string(index=False))
print(macros)
