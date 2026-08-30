# Flask-CORS Track B family

This package contains exact historical snapshots and CPU-only construction
artifacts for the Flask-CORS private-network authorization family.

An initial v1 renderer attempt used a source-only process input, but the
constructing agent had already inspected the target transition. That attempt is
preserved under `memories/rejected-attempt-1/` and is ineligible for treatment
use; it must not be called a frozen source memory. No replacement was generated.

The family is deliberately **not frozen** and is not model-ready: the exact
expansion-rule and ordered-review selection commits are not yet reachable, the
exact selected S/C/I from that review cannot be confirmed, and no
chronologically valid source memory exists.

Do not run model execution from this package until the candidate-specific CPU
validator reports that final freeze is permitted and a separate frozen family
commit exists.
