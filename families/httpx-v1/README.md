# HTTPX Track B candidate

This directory is deliberately **not** a frozen executable family.

Frozen seed evidence identifies HTTPX candidate `GHSA-h8pj-cxx2-jfg2` and its
upstream security-fix boundary. The exact expansion rule commit
`d3b8116c9da35a5ad6e8da6066cc9456319c167b` and full ordered-review/selection
commit beginning `9fe5c35` are not reachable in this repository. Under the
Track B provenance gate, that prevents choosing or materializing final S/C/I
snapshots, freezing p*, generating source memory, defining target oracles and
references, or declaring the family model-ready.

`provenance/construction-status.json` records the fail-closed state.
`scripts/probe_httpx_fix_boundary.py` can reproduce the upstream advisory
boundary from a caller-supplied exact clone and qualified Python environment.
That probe is supporting evidence only; it does not select the Track B triplet
or establish the final scientific contrast.
