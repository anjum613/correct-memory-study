"""Recompute family-weighted contrasts and figures from the anonymized saved table."""
from pathlib import Path
import csv,json,itertools
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch,Rectangle
ROOT=Path(__file__).resolve().parents[1]
D=pd.read_csv(ROOT/'data/outcomes.csv')
MODELS=['GPT55','Luna','Terra','QwenNext','Qwen30','Devstral']
LABELS={'GPT55':'GPT-5.5 Low','Luna':'Luna Medium','Terra':'Terra Medium','QwenNext':'Qwen Next','Qwen30':'Qwen 30B','Devstral':'Devstral'}
FAMS=['F01','F02','F04','F08','F17','F20','X02','X05','X06','X11','X20','X24','X28']
CONDS=['N','C','I','B']
assert len(D)==624 and D.revised_valid.sum()==595
assert not D.duplicated(['model','family','condition','rep']).any()
assert D.groupby('model').size().eq(104).all()
assert D[D.revised_valid].apply(lambda r:bool(r.revised_U)==(bool(r.revised_F) and not bool(r.revised_S)),axis=1).all()
for version in ['original','revised']:
 for v in 'FSU':D[f'{version}_{v}']=pd.to_numeric(D[f'{version}_{v}'],errors='raise')

def texfile(name,s): (ROOT/'generated'/name).write_text(s+'\n')
def fmt(x):return f'{x:+.1f}' if abs(x)>1e-9 else '0.0'

def units(m,a,b,version,omit=()):
 q=D[(D.model==m)&(~D.family.isin(omit))&D.condition.isin([a,b])]
 out=[]
 for f,g in q.groupby('family',sort=True):
  if len(g)!=4 or not g[f'{version}_valid'].all() or g[[f'{version}_{v}' for v in 'FSU']].isna().any().any():continue
  x=g.groupby('condition')[[f'{version}_{v}' for v in 'FSU']].mean()
  out.append({'family':f,**{v:float(x.loc[a,f'{version}_{v}']-x.loc[b,f'{version}_{v}']) for v in 'FSU'},'records':';'.join(sorted(g.record))})
 return out

allc=[]; allu=[]
for vi,version in enumerate(['original','revised']):
 for si,(scope,omit) in enumerate([('all13',()),('omitX06',('X06',)),('omitReviewed',('X05','X06','X28'))]):
  for mi,m in enumerate(MODELS):
   for ci,(a,b) in enumerate([('C','N'),('I','N'),('B','C'),('C','I')]):
    us=units(m,a,b,version,omit);n=len(us);arr=np.array([[u[v] for v in 'FSU'] for u in us]);mean=arr.mean(axis=0)*100
    rng=np.random.default_rng(20260906+mi*10+ci+si*100)
    samples=arr[rng.integers(0,n,size=(20000,n))].mean(axis=1)*100
    lo,hi=np.quantile(samples,[.025,.975],axis=0)
    u=arr[:,2]; signs=np.array(list(itertools.product([-1,1],repeat=n)));p=float((np.abs((signs*u).mean(axis=1))>=abs(u.mean())-1e-12).mean())
    loo=np.array([np.delete(u,j).mean()*100 for j in range(n)])
    row={'version':version,'scope':scope,'model':m,'contrast':a+'-'+b,'n':n,'families':';'.join(x['family'] for x in us),'p_signflip_U':p,'loo_min_U':loo.min(),'loo_max_U':loo.max()}
    for j,v in enumerate('FSU'):row.update({v:mean[j],v+'_lo':lo[j],v+'_hi':hi[j]})
    allc.append(row)
    allu += [{'version':version,'scope':scope,'model':m,'contrast':a+'-'+b,**x} for x in us]
C=pd.DataFrame(allc);C.to_csv(ROOT/'generated/contrasts.csv',index=False)
pd.DataFrame(allu).to_csv(ROOT/'generated/family_units.csv',index=False)
main=C[(C.version=='revised')&(C.scope=='all13')&(C.contrast!='C-I')]
rows=[r'\begin{tabular}{llrrrrl}',r'\toprule',r'Configuration & Contrast & $n$ & $\Delta F$ & $\Delta S$ & $\Delta U$ & 95\% interval for $\Delta U$\\',r'\midrule']
for m in MODELS:
 for j,(_,r) in enumerate(main[main.model==m].iterrows()):
  rows.append(f"{LABELS[m] if j==0 else ''} & {r.contrast.replace('-', '$-$')} & {r.n} & {fmt(r.F)} & {fmt(r.S)} & {fmt(r.U)} & [{fmt(r.U_lo)}, {fmt(r.U_hi)}]"+r'\\')
 if m!='Devstral':rows.append(r'\addlinespace[2pt]')
rows += [r'\bottomrule',r'\end{tabular}'];texfile('contrasts.tex','\n'.join(rows))
counts=[]
for m in MODELS:
 for c in CONDS:
  q=D[(D.model==m)&(D.condition==c)];v=q[q.revised_valid]
  counts.append({'model':m,'condition':c,'recorded':len(q),'valid':len(v),'invalid':len(q)-len(v),'FS':int(((v.revised_F==1)&(v.revised_S==1)).sum()),'U':int(v.revised_U.sum()),'notF_S':int(((v.revised_F==0)&(v.revised_S==1)).sum()),'notF_notS':int(((v.revised_F==0)&(v.revised_S==0)).sum())})
J=pd.DataFrame(counts);J.to_csv(ROOT/'generated/joint_counts.csv',index=False)
colors={'FS':'#287b8e','U':'#cc5a41','notF_S':'#e3bd62','notF_notS':'#bd93c2','invalid':'#b5b5b5'}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42,'ps.fonttype':42,'axes.spines.top':False,'axes.spines.right':False})
fig,axs=plt.subplots(2,3,figsize=(5.5,3.7),sharex=True,sharey=True)
for ax,m in zip(axs.flat,MODELS):
 q=J[J.model==m].set_index('condition').loc[CONDS];left=np.zeros(4)
 for k,col in colors.items():
  ax.barh(np.arange(4),q[k],left=left,color=col,height=.7,label=k)
  for y,(l,w) in enumerate(zip(left,q[k])):
   if w>=2:ax.text(l+w/2,y,str(w),ha='center',va='center',fontsize=8,color='white' if k in ['FS','U'] else 'black')
  left+=q[k].values
 ax.set_yticks(range(4),CONDS);ax.set_ylim(3.6,-.6);ax.set_xlim(0,26);ax.set_xticks([0,13,26]);ax.set_title(LABELS[m]+(' / Codex' if m in MODELS[:3] else ' / MiniSWE'),fontsize=9)
for ax in axs[-1]:ax.set_xlabel('Recorded runs', fontsize=8)
legend=['F pass, S pass','F pass, S fail (U)','F fail, S pass','F fail, S fail','Invalid']
fig.legend([Patch(color=c) for c in colors.values()],legend,loc='lower center',ncol=3,frameon=False,fontsize=8)
fig.tight_layout(rect=(0,.11,1,1));fig.savefig(ROOT/'figures/joint_outcomes.pdf',bbox_inches='tight');plt.close(fig)
fig,axs=plt.subplots(1,6,figsize=(5.5,3.5),sharey=True)
for ax,m in zip(axs,MODELS):
 for yi,f in enumerate(FAMS):
  for xi,c in enumerate(CONDS):
   for ri in range(2):
    r=D[(D.model==m)&(D.family==f)&(D.condition==c)&(D.rep==ri+1)].iloc[0]
    k='invalid' if not r.revised_valid else ('FS' if r.revised_F and r.revised_S else 'U' if r.revised_F else 'notF_S' if r.revised_S else 'notF_notS')
    ax.add_patch(Rectangle((xi+ri*.5,yi),.5,1,facecolor=colors[k],edgecolor='white',linewidth=.4))
 ax.set_xlim(0,4);ax.set_ylim(13,0);ax.set_xticks(np.arange(4)+.5,CONDS);ax.xaxis.tick_top();ax.set_yticks(np.arange(13)+.5,FAMS);ax.tick_params(length=0);ax.set_title({'GPT55':'GPT-5.5','Luna':'Luna','Terra':'Terra','QwenNext':'Qwen Next','Qwen30':'Qwen 30B','Devstral':'Devstral'}[m],fontsize=8,pad=22)
 for s in ax.spines.values():s.set_visible(False)
fig.legend([Patch(color=c) for c in colors.values()],legend,loc='lower center',ncol=3,frameon=False,fontsize=8)
fig.tight_layout(rect=(0,.12,1,1),w_pad=.5);fig.savefig(ROOT/'figures/family_overview.pdf',bbox_inches='tight');plt.close(fig)
# Compact joint-count appendix table.
s=[r'\begin{tabular}{llrrrrrr}',r'\toprule',r'Configuration & Arm & Valid & $F S$ & $U$ & $\neg F,S$ & $\neg F,\neg S$ & Invalid\\',r'\midrule']
for m in MODELS:
 for j,(_,r) in enumerate(J[J.model==m].iterrows()):s.append(f"{LABELS[m] if j==0 else ''} & {r.condition} & {r.valid} & {r.FS} & {r.U} & {r.notF_S} & {r.notF_notS} & {r.invalid}"+r'\\')
 s.append(r'\addlinespace')
s += [r'\bottomrule',r'\end{tabular}'];texfile('joint_counts.tex','\n'.join(s))
# Eligibility and scope/leave-one-family-out sensitivities.
s=[r'\begin{tabular}{llrrrrrr}',r'\toprule',r'& & \multicolumn{2}{c}{All families} & \multicolumn{2}{c}{Omit X06} & \multicolumn{2}{c}{Omit X05/X06/X28}\\',r'Configuration & Contrast & $n$ & $\Delta U$ & $n$ & $\Delta U$ & $n$ & $\Delta U$\\',r'\midrule']
for m in MODELS:
 for j,co in enumerate(['C-N','I-N','B-C']):
  qs=[C[(C.version=='revised')&(C.model==m)&(C.contrast==co)&(C.scope==sc)].iloc[0] for sc in ['all13','omitX06','omitReviewed']]
  s.append(f"{LABELS[m] if j==0 else ''} & {co.replace('-','$-$')} & "+' & '.join(f'{r.n} & {fmt(r.U)}' for r in qs)+r'\\')
s += [r'\bottomrule',r'\end{tabular}'];texfile('sensitivity.tex','\n'.join(s))
s=[r'\begin{tabular}{lllr}',r'\toprule',r'Configuration & Contrast & Leave-one-family-out range ($\Delta U$) & Sign-flip $p$\\',r'\midrule']
for _,r in main.iterrows():s.append(f'{LABELS[r.model]} & {r.contrast.replace("-","$-$")} & [{fmt(r.loo_min_U)}, {fmt(r.loo_max_U)}] & {r.p_signflip_U:.3f}'+r'\\')
s += [r'\bottomrule',r'\end{tabular}'];texfile('diagnostics.tex','\n'.join(s))
s=[r'\begin{tabular}{llp{9cm}}',r'\toprule',r'Configuration & Contrast & Eligible families\\',r'\midrule']
for _,r in main.iterrows():s.append(f'{LABELS[r.model]} & {r.contrast.replace("-","$-$")} & {r.families.replace(";",", ")}'+r'\\')
s += [r'\bottomrule',r'\end{tabular}'];texfile('eligibility.tex','\n'.join(s))
# Versioned correction comparison.
changed=D[(D.original_S!=D.revised_S)&D.revised_valid]
assert len(changed)==4 and set(changed.model)=={'Devstral'}
s=[r'\begin{tabular}{llllcc}',r'\toprule',r'Record & Configuration & Family & Arm / rep. & Original $F/S$ & Corrected $F/S$\\',r'\midrule']
for _,r in changed.iterrows():s.append(f'{r.record} & Devstral / MiniSWE & {r.family} & {r.condition} / {r.rep} & Pass/Pass & Pass/Fail'+r'\\')
s += [r'\bottomrule',r'\end{tabular}'];texfile('corrections.tex','\n'.join(s))
macros={'RecordedRuns':len(D),'ValidRuns':int(D.revised_valid.sum()),'InvalidRuns':int((~D.revised_valid).sum())}
primary=main[main.contrast=='C-N']
macros.update({'PrimaryURangeLow':fmt(primary.U.min()),'PrimaryURangeHigh':fmt(primary.U.max())})
for _,r in main.iterrows():
 co=r.contrast.replace('-','minus');key=r.model.replace('55','FiveFive').replace('30','Thirty')
 for v in 'FSU':macros[key+co+v]=fmt(r[v])
 macros[key+co+'N']=int(r.n)
for m in MODELS:
 key=m.replace('55','FiveFive').replace('30','Thirty');q=J[J.model==m]
 for k in ['valid','invalid','FS','U','notF_S','notF_notS']:macros[key+k.replace("_", "")]=int(q[k].sum())
texfile('numbers.tex','\n'.join('\\newcommand{\\'+k+'}{'+str(v)+'}' for k,v in macros.items()))
summary={'recorded':len(D),'valid':int(D.revised_valid.sum()),'invalid':int((~D.revised_valid).sum()),'corrections':len(changed),'bootstrap_draws':20000,'bootstrap_seed_base':20260906,'analysis':'complete pairs; average repetitions within family; equal family weights; exploratory percentile intervals'}
(ROOT/'generated/analysis_summary.json').write_text(json.dumps(summary,indent=2))
print(main[['model','contrast','n','F','S','U','U_lo','U_hi']].to_string(index=False))
print(J.groupby('model').sum(numeric_only=True).to_string())
