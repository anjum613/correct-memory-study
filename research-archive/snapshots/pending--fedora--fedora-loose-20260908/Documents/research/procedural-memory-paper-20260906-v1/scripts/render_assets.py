from pathlib import Path
import json,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
D=pd.read_csv(ROOT/'data/outcomes.csv');C=pd.read_csv(ROOT/'generated/contrasts.csv')
models=['GPT55','Luna','Terra','QwenNext','Qwen30','Devstral']
labels={'GPT55':'GPT-5.5 Low','Luna':'Luna Medium','Terra':'Terra Medium','QwenNext':'Qwen-Next','Qwen30':'Qwen-30B','Devstral':'Devstral'}
def wr(name,lines):(ROOT/'generated'/name).write_text('\n'.join(lines)+'\n')
def esc(t):
 for a,b in [('&',r'\&'),('_',r'\_'),('%',r'\%'),('#',r'\#')]:t=t.replace(a,b)
 return t.replace('`label`',r'\texttt{label}')
cfg={x['model']:x for x in json.loads((ROOT/'data/configurations.json').read_text())}
s=[r'\begin{tabular}{lllr}',r'\toprule',r'Configuration & Agent / tools & Sampling selection & Recorded / valid\\',r'\midrule']
for m in models:
 q=D[D.model==m];v=cfg[m]['config_variants'][0]['spec']
 if m in models[:3]:agent='Codex / shell, patch';sampling=v['reasoning_effort']+' reasoning'
 else:agent='MiniSWE / bash';sampling=f"$T={v['temperature']:g}$"
 s.append(f'{labels[m]} & {agent} & {sampling} & {len(q)} / {int(q.revised_valid.sum())}'+r'\\')
s += [r'\bottomrule',r'\end{tabular}'];wr('design.tex',s)
s=[]
for m in models:
 v=cfg[m]['config_variants'][0]['spec'];mid=v.get('actual_model_id',v.get('model'));rev=v.get('actual_model_revision')
 s.append(r'\paragraph{'+labels[m]+r'.} Requested model: \nolinkurl{'+mid+'}.')
 if rev:s.append(r'Revision: {\footnotesize\texttt{'+rev+'}}.')
 else:s.append('Model revision, sampling temperature, generation seed, and provider request count were not exposed by the executed interface. No underlying identity is inferred from the alias.')
 if m not in models[:3]:
  params=[f"temperature {v['temperature']:g}"]
  for k in ['top_p','top_k','repetition_penalty']:
   if v[k] is not None:params.append(k.replace('_',' ')+f" {v[k]:g}")
  s.append('Recorded sampling settings: '+', '.join(params)+'. Other sampling overrides were not supplied in the saved configuration. Served name: '+r'\nolinkurl{'+v['actual_served_model_name']+'}.')
wr('config_details.tex',s)
fams=json.loads((ROOT/'data/families.json').read_text())
s=[r'\begin{longtable}{p{.7cm}>{\raggedright\arraybackslash}p{3.8cm}>{\raggedright\arraybackslash}p{3.6cm}>{\raggedright\arraybackslash}p{4.1cm}}',r'\caption{Source assumptions, target changes, and focal witness scopes.}\label{tab:familydefs}\\',r'\toprule',r'ID & Source assumption & Target change & Bounded witness\\',r'\midrule\endhead']
for f in fams:s.append(' & '.join(esc(f[k]) for k in ['family','source','shift','witness'])+r'\\\addlinespace[3pt]')
s += [r'\bottomrule',r'\end{longtable}'];wr('family_definitions.tex',s)
cs=json.loads((ROOT/'data/cases.json').read_text())
s=[r'\begin{tabularx}{\linewidth}{>{\raggedright\arraybackslash}p{1.25cm}>{\raggedright\arraybackslash}X>{\raggedright\arraybackslash}X>{\raggedright\arraybackslash}p{1.1cm}}',r'\toprule',r'Arm / record & Visible transcript excerpt & Saved implementation change & $F/S$\\']
for panel,title in [('A','F01: two repetitions of the same correct-memory treatment'),('B','X11: correct memory versus applicability boundary'),('C','F08: no memory versus correct memory')]:
 s += [r'\midrule',r'\multicolumn{4}{l}{\textbf{'+panel+'. '+title+r'}}\\\addlinespace[2pt]']
 for c in cs:
  if c['panel']!=panel:continue
  s.append(f"{c['condition']}/r{c['rep']} \\newline {c['record']} & ``{esc(c['quote'])}'' & {esc(c['implementation'])} & {'Pass' if c['F'] else 'Fail'}/ {'Pass' if c['S'] else 'Fail'}"+r'\\\addlinespace[3pt]')
s += [r'\bottomrule',r'\end{tabularx}'];wr('cases.tex',s)
s=[r'\begin{tabular}{llrrr}',r'\toprule',r'Contrast & Version & $\Delta F$ & $\Delta S$ & $\Delta U$\\',r'\midrule']
for co in ['C-N','I-N','B-C']:
 for ver in ['original','revised']:
  r=C[(C.model=='Devstral')&(C.scope=='all13')&(C.contrast==co)&(C.version==ver)].iloc[0]
  s.append(f"{co.replace('-','$-$')} & {ver} & {r.F:+.2f} & {r.S:+.2f} & {r.U:+.2f}"+r'\\')
s += [r'\bottomrule',r'\end{tabular}'];wr('correction_contrasts.tex',s)
s=[r'\begin{tabular}{llrrr}',r'\toprule',r'Configuration & Family & Recorded & Valid & Invalid\\',r'\midrule']
for (m,f),g in D.groupby(['model','family']):
 if (~g.revised_valid).sum():s.append(f'{labels[m]} & {f} & {len(g)} & {g.revised_valid.sum()} & {(~g.revised_valid).sum()}'+r'\\')
s += [r'\bottomrule',r'\end{tabular}'];wr('missingness.tex',s)
s=[r'\begin{tabular}{lrrrrl}',r'\toprule',r'Configuration & $n$ & $\Delta F$ & $\Delta S$ & $\Delta U$ & 95\% interval for $\Delta U$\\',r'\midrule']
for m in models:
 r=C[(C.model==m)&(C.scope=='all13')&(C.contrast=='C-I')&(C.version=='revised')].iloc[0]
 s.append(f'{labels[m]} & {r.n} & {r.F:+.1f} & {r.S:+.1f} & {r.U:+.1f} & [{r.U_lo:+.1f}, {r.U_hi:+.1f}]'+r'\\')
s += [r'\bottomrule',r'\end{tabular}'];wr('c_minus_i.tex',s)
# Verify all prose count assertions against complete saved rows.
assertions=[]
def check(label,query,expected):
 got=int(query);assert got==expected,(label,got,expected);assertions.append({'claim':label,'value':got})
q=D[(D.model=='Qwen30')&D.revised_valid]
for arm,nf,nfs in [('N',24,8),('C',20,7)]:
 g=q[q.condition==arm];check('Qwen30 '+arm+' functional',g.revised_F.sum(),nf);check('Qwen30 '+arm+' joint',((g.revised_F==True)&(g.revised_S==True)).sum(),nfs)
check('Codex invalids',((D.harness=='Codex')&~D.revised_valid).sum(),25)
check('Codex X28 invalids',((D.harness=='Codex')&(D.family=='X28')&~D.revised_valid).sum(),17)
for harness,arm,want in [('Codex','B',0),('Codex','N',6),('MiniSWE','B',6)]:
 g=D[(D.harness==harness)&(D.family=='F04')&(D.condition==arm)];check(harness+' F04 '+arm+' U',g.revised_U.sum(),want);check(harness+' F04 '+arm+' F',g.revised_F.sum(),6)
(ROOT/'generated/prose_count_checks.json').write_text(json.dumps(assertions,indent=2))
print('Generated configuration, case, family, correction, missingness and sensitivity tables; checked prose counts.')
