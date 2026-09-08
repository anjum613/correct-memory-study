"""Figures from recorded outcomes only; no experiment execution."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Rectangle, Patch

P=Path(__file__).resolve().parent;OUT=P/'figures';OUT.mkdir(exist_ok=True)
R=json.loads((P/'derived/records.json').read_text())
families=sorted({r['family'] for r in R});conditions=['N','C','I','B']
names={'GPT55':'GPT-5.5 Low','Luna':'Luna Medium','Terra':'Terra Medium','Spark':'Spark Medium (incomplete)',
       'Qwen30':'Qwen3-Coder 30B','QwenNext':'Qwen3-Coder-Next','Devstral':'Devstral Small 2507'}
plt.rcParams.update({'font.size':10,'pdf.fonttype':42})
colors=LinearSegmentedColormap.from_list('unsafe_rate',['#e3eee9','#edc498','#b94738'])
fig,axes=plt.subplots(1,3,figsize=(11,7.8),sharey=True,layout='constrained')
for ax,m in zip(axes,['GPT55','Luna','Terra']):
    for yi,f in enumerate(families):
        for xi,c in enumerate(conditions):
            a=[r for r in R if r['model']==m and r['family']==f and r['condition']==c and r['valid']]
            u=sum(r['unsafe'] for r in a);ff=sum(not r['functionality'] for r in a)
            face=colors(u/len(a)) if a else '#dadada'
            ax.add_patch(Rectangle((xi-.5,yi-.5),1,1,facecolor=face,edgecolor='white',linewidth=2,hatch='///' if not a else None))
            label=f'{u}/{len(a)}' if a else 'invalid'
            if ff:label+=f'\nf={ff}'
            ax.text(xi,yi,label,ha='center',va='center',fontsize=10,color='#172026')
    ax.set_xlim(-.5,3.5);ax.set_ylim(12.5,-.5);ax.set_xticks(range(4),conditions);ax.xaxis.tick_top()
    ax.set_yticks(range(13),families);ax.set_title(names[m],pad=31,weight='bold')
    ax.tick_params(length=0);ax.spines[:].set_visible(False)
fig.suptitle('Unsafe completions / technically valid runs',fontsize=15,weight='bold')
fig.supxlabel('Two attempts per cell. f = functionality failures among valid runs.\nN: no memory    C: correct memory    I: irrelevant memory    B: correct + applicability boundary',fontsize=10)
for ext in ['png','pdf']:fig.savefig(OUT/('codex_family_condition.'+ext),dpi=180,bbox_inches='tight')
plt.close(fig)

models=['GPT55','Luna','Terra','Qwen30','QwenNext','Devstral','Spark']
labels=['Functionality + security pass','Unsafe completion','Functionality fail, security pass','Both fail','Technical invalid','Unstarted']
palette=['#477b67','#b94738','#e5c384','#866c89','#aaaeb3','#ffffff']
fig,ax=plt.subplots(figsize=(12,6.5),layout='constrained')
for yi,m in enumerate(models):
    a=[r for r in R if r['model']==m];v=[r for r in a if r['valid']]
    counts=[sum(r['functionality'] and r['security'] for r in v),sum(r['unsafe'] for r in v),
            sum(not r['functionality'] and r['security'] for r in v),sum(not r['functionality'] and not r['security'] for r in v),
            len(a)-len(v),104-len(a)]
    left=0
    for k,n in enumerate(counts):
        if n:
            ax.barh(yi,n,left=left,color=palette[k],edgecolor='#ffffff' if k<5 else '#888888',height=.65,hatch='///' if k==5 else None)
            if n>=3:ax.text(left+n/2,yi,str(n),ha='center',va='center',fontsize=10,color='white' if k in [0,1,3] else '#202020')
        left+=n
ax.set_yticks(range(len(models)),[names[m] for m in models]);ax.invert_yaxis()
ax.set_xlim(0,104);ax.set_xticks([0,26,52,78,104]);ax.set_xlabel('Runs out of 104 planned per model')
ax.set_title('A security pass can coexist with an unimplemented feature',weight='bold',pad=18)
ax.axhline(2.5,color='#555555',ls=':',lw=1);ax.axhline(5.5,color='#555555',ls=':',lw=1)
ax.spines[['top','right','left']].set_visible(False);ax.tick_params(axis='y',length=0)
handles=[Patch(facecolor=palette[k],edgecolor='#777777' if k==5 else 'none',hatch='///' if k==5 else None,label=labels[k]) for k in range(6)]
ax.legend(handles=handles,ncol=2,loc='upper center',bbox_to_anchor=(.5,-.14),frameon=False)
fig.suptitle('Codex and MiniSWE cohorts use different agent envelopes and budgets; cross-harness differences are descriptive.',fontsize=9,y=1.01)
for ext in ['png','pdf']:fig.savefig(OUT/('joint_outcomes.'+ext),dpi=180,bbox_inches='tight')
plt.close(fig)
print('Created two PNG/PDF figure pairs in',OUT)
