"""Render the saved static contract-review inventory; do not execute observers."""
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
d=pd.read_csv(ROOT/'data/observer_contract_review.csv')
def escape(s):
    for a,b in [('&',r'\&'),('_',r'\_'),('%',r'\%')]:s=str(s).replace(a,b)
    return s
lines=[r'\begin{longtable}{p{.65cm}>{\raggedright\arraybackslash}p{3.45cm}>{\raggedright\arraybackslash}p{5.3cm}rr}',
       r'\caption{Observation contracts across all thirteen families. FS counts are saved functionality and focal witness passes; AST counts are distinct parsed syntax trees among those submissions. These measure observed acceptance diversity, not independently verified semantic equivalence.}\label{tab:observers}\\',
       r'\toprule',r'ID & Observed output or effect & Contract review finding & FS & AST\\',r'\midrule',r'\endfirsthead',r'\toprule',r'ID & Observed output or effect & Contract review finding & FS & AST\\',r'\midrule',r'\endhead']
for _,r in d.iterrows():
    lines.append(' & '.join([r.family,escape(r.observes),escape(r.review_finding),str(r.saved_FS_runs),str(r.distinct_saved_FS_syntax_trees)])+r'\\\addlinespace[3pt]')
lines += [r'\bottomrule',r'\end{longtable}']
(ROOT/'generated/observer_contract_review.tex').write_text('\n'.join(lines)+'\n')
print('Rendered 13 saved observer contract reviews.')
