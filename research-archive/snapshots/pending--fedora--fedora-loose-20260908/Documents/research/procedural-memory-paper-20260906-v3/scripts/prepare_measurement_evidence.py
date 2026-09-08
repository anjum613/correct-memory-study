"""Extract component-level observations without changing original validity or scores."""
from pathlib import Path
import hashlib,json
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
D=pd.read_csv(ROOT/'private/run-mapping.csv')
rows=[];private=[]
for _,r in D.iterrows():
    p=Path(r.original_result).parent
    raw=json.loads((p/'result.json').read_text())
    f=s=None
    category='valid_observation'
    failure='none'
    if r.revised_valid:
        f=bool(r.revised_F);s=bool(r.revised_S)
        basis='corrected_valid_row'
    else:
        if r.termination=='INTERRUPTED':category='external_interruption'
        elif r.termination=='TIMEOUT':category='session_budget_timeout'
        elif r.family=='X28' and r.harness=='Codex':category='candidate_execution_exception'
        elif r.family=='X02' and r.harness=='MiniSWE':category='evaluator_lowering_incompatibility'
        else:raise AssertionError((r.run_id,r.termination))
        if r.harness=='Codex':
            fr=json.loads((p/'functionality-evaluation.json').read_text())
            sr=json.loads((p/'security-witness-evaluation.json').read_text())
            if fr.get('complete') is True and type(fr.get('pass')) is bool:f=fr['pass']
            if sr.get('complete') is True and type(sr.get('pass')) is bool:s=sr['pass']
            basis='completed_saved_component_only; raw incomplete pass fields ignored'
            if f is False:failure='completed_feature_check_failed'
        else:
            evaluation=json.loads((p/'evaluation.json').read_text())
            assert set(evaluation['statuses'].values())=={'HARNESS_ERROR'}
            basis='all components stopped during lowering; no outcome observed'
            failure='submitted_program_not_accepted_by_evaluator'
        if category=='candidate_execution_exception':
            assert f is True and s is None
            failure='candidate_raised_on_existing_storage_error_fixture'
        private.append({'record':r.record,'run_id':r.run_id,'category':category,'result':str(p/'result.json'),
                        'result_sha256':hashlib.sha256((p/'result.json').read_bytes()).hexdigest(),
                        'functionality':str(p/'functionality-evaluation.json') if r.harness=='Codex' else str(p/'evaluation.json'),
                        'security':str(p/'security-witness-evaluation.json') if r.harness=='Codex' else str(p/'evaluation.json')})
    # Preserve all logical information, including known F=0 or S=1.
    options=[(ff,ss) for ff in [False,True] for ss in [False,True]
             if (f is None or ff==f) and (s is None or ss==s)]
    us=[int(ff and not ss) for ff,ss in options]
    rows.append({'record':r.record,'model':r.model,'harness':r.harness,'family':r.family,'condition':r.condition,
                 'rep':r.rep,'original_technical_validity':bool(r.revised_valid),'event_category':category,
                 'observed_F':f,'observed_S':s,'U_lower':min(us),'U_upper':max(us),'observed_implementation_event':failure,
                 'evidence_rule':basis})
E=pd.DataFrame(rows)
E.to_csv(ROOT/'data/measurement_components.csv',index=False)
(ROOT/'private/measurement-evidence-paths.json').write_text(json.dumps(private,indent=2))
bad=E[~E.original_technical_validity]
assert bad.event_category.value_counts().to_dict()=={'candidate_execution_exception':17,'external_interruption':4,'session_budget_timeout':4,'evaluator_lowering_incompatibility':4}
assert bad.observed_F.notna().sum()==21 and (bad.observed_F==False).sum()==1
assert bad.observed_S.notna().sum()==4 and bad.U_lower.eq(bad.U_upper).sum()==4
print('Observed components retained for bounds; original scores and eligibility unchanged.')
print(bad.groupby('event_category').agg(n=('record','size'),known_F=('observed_F','count'),known_S=('observed_S','count')).to_string())
