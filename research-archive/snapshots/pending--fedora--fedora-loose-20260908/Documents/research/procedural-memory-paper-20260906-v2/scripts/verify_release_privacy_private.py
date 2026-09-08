"""Author-only identity scan; this script is excluded from all anonymous ZIPs."""
import json,re
from pathlib import Path
from qa import ROOT,public_paths,evidence_paths
patterns=[r'(?i)anjum',r's224049759',r'(?i)deakin',r'Workstation-Pro-E800-G4-WS950T']
violations=[]
for p in public_paths()+evidence_paths():
 if p.suffix=='.pdf':continue
 s=p.read_text()
 for pattern in patterns:
  if re.search(pattern,s):violations.append({'file':str(p.relative_to(ROOT)),'category':'author/account/institution'})
assert not violations, violations
(ROOT/'build/private-identity-scan.json').write_text(json.dumps({'passed':True,'files_checked':len(public_paths()+evidence_paths()),'private_identifier_matches':0},indent=2)+'\n')
print('Private identity scan passed for all release files.')
