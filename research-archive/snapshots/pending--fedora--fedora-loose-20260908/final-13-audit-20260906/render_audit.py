"""Resolve local evidence links in the Markdown audit."""
from pathlib import Path
import json,re
P=Path(__file__).resolve().parent
s=(P/'AUDIT.template.md').read_text()
frozen=P/'evidence/controlled-synthetic-final-13-codex-v3/frozen'
s=s.replace('@SNAP_PARENT@',str(frozen)).replace('@SNAP@',str(frozen/'snapshot'))
cases=json.loads((P/'derived/casebook_index.json').read_text())
for c in cases:s=s.replace('@CASE:'+c['run_id']+'@',str(P/'TRANSCRIPT_CASEBOOK.md')+':'+str(c['casebook_line']))
def absolute(m):
    path=m[1]
    if not path.startswith(('/','https://','http://','#')):path=str(P/path)
    return ']('+path+')'
s=re.sub(r'\]\(([^\n)]+)\)',absolute,s)
if re.search(r'@(?:CASE|SNAP)',s):raise ValueError('Unresolved evidence link')
(P/'AUDIT.md').write_text(s)
missing=[]
for file in [P/'AUDIT.md',P/'TRANSCRIPT_CASEBOOK.md',P/'RUN_INDEX.md']+list((P/'derived').glob('evidence_A*.md')):
    for target in re.findall(r'\]\(([^\n)]+)\)',file.read_text()):
        clean=re.sub(r':\d+$','',target)
        if not Path(clean).exists():missing.append({'file':str(file),'target':target})
(P/'derived/link_check.json').write_text(json.dumps({'missing':missing},indent=2)+'\n')
print('Audit words',len(s.split()),'Missing evidence links',len(missing))
for n,line in enumerate(s.splitlines(),1):
    if line.startswith('**'):print(n,line)
if missing:print(json.dumps(missing[:15],indent=2))
