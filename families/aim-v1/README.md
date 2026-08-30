# Aim Track B family — provisional construction

This package preserves the executable construction evidence for Aim's
historical static-file path transition. It is deliberately **not frozen** and
is not model-ready because the exact expansion-rule commit
`d3b8116c9da35a5ad6e8da6066cc9456319c167b` and ordered-review/selection
commit beginning `9fe5c35` are not reachable in this repository.

The provisional upstream triplet and p* relation must be compared byte-for-byte
with that ordered review before source-memory generation or family freeze. The
present construction establishes the required executable contrast without
using any model outcome:

- invalidated/faithful reuse: functional PASS, security FAIL;
- safe control: functional PASS, security PASS.

No source memory, freeze manifest, production manifest, matrix, or GPU run is
permitted while the provenance blockers remain.
