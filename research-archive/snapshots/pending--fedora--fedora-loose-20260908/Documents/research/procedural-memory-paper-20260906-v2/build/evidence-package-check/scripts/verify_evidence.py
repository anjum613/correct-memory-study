"""Verify public static evidence hashes and joins; never execute saved code."""
from pathlib import Path
import hashlib,json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
def main():
    receipt=json.loads((ROOT/'evidence/COVERAGE.json').read_text())
    d=pd.read_csv(ROOT/'data/outcomes.csv');assert len(d)==624
    entries=receipt['records_manifest'];assert {x['record'] for x in entries}==set(d.record)
    for x in entries:
        p=ROOT/x['file'];payload=p.read_bytes()
        assert len(payload)==x['bytes'] and hashlib.sha256(payload).hexdigest()==x['sha256']
        r=json.loads(payload);assert r['record']==x['record']
        assert bool(r['visible_events'])==x['trace_available']
        assert len(r['visible_events'])==x['visible_events']
        assert (r['saved_implementation_text'] is not None)==x['implementation_available']
    for f in sorted(d.family.unique()):
        j=json.loads((ROOT/f'evidence/families/{f}.json').read_text())
        assert j['family']==f
        for c,x in j['frozen_task_and_memory_records'].items():
            assert hashlib.sha256(x['memory_between_delimiters'].encode()).hexdigest()==x['memory_sha256']
            assert len(x['memory_between_delimiters'].encode())==x['memory_bytes_between_delimiters']
            if c!='N':
                a=x['task_and_context'].index('[BEGIN_MEMORY_CONTEXT]')
                b=x['task_and_context'].index('[END_MEMORY_CONTEXT]')+len('[END_MEMORY_CONTEXT]')
                assert x['task_and_context'][b:b+1]=='\n'
                assert len(x['task_and_context'][a:b+1].encode())==4096
    sample=pd.read_csv(ROOT/'data/behavior_sample.csv')
    for _,r in sample.iterrows():
        p=ROOT/f'annotation/reviewer/{r.packet}.md'
        assert hashlib.sha256(p.read_bytes()).hexdigest()==r.review_packet_sha256
    result={k:receipt[k] for k in ['records','traces_available','implementations_available','patches_available','task_prompts_available']}
    result.update(passed=True,annotation_packets_verified=len(sample),candidate_execution=False)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
