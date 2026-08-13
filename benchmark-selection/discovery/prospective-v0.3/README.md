# Candidate-source protocol v0.3 pre-execution freeze

Status: `FROZEN_NOT_EXECUTED`

Protocol v0.3 is an additive, prospective amendment to the byte-preserved v0.2
specifications. Its effective specification is:

1. every file in `../prospective-v0.2/` at the hashes recorded in
   `amendment.json`;
2. every mandatory override and addition in `amendment.json`;
3. `source-record.schema.json` and `raw-capture-manifest.schema.json` in this
   directory.

If a v0.2 statement conflicts with v0.3, the narrow v0.3 override governs.
Unmentioned v0.2 rules remain in force. No v0.2 file is modified.

The amendment closes the final pre-execution gaps without changing any query
term based on an observed identity. It adds pre-repair snapshot identity,
deterministic created-at partitioning above GitHub's 1,000-result ceiling,
bounded request behavior, content-addressed raw capture, topology-safe repair
anchors, complete provenance, and explicit failure semantics.

Discovery remains mechanical and outcome-blind. It cannot assign a trust
family, `p*`, triplet feasibility, security relevance, benchmark inclusion,
model feasibility, or experimental status. It cannot use ML or heuristic
ranking.

No BugsInPy object, advisory, GitHub query, repository, issue, pull request,
commit, candidate identity, experiment artifact, or treatment result was
fetched or inspected while freezing this amendment.
