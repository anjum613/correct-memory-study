# Diffusers Track B candidate

This package preserves the exact frozen `huggingface/diffusers` historical
triplet and its authoritative Track B semantic review:

- source (`S`): `513f1fbfb0d116022b5d8519dd7e919a96e3155d`
- compatible (`C`): `e5902ed11a024036fa6fd1e858b48117cc92d5f5`
- invalidated (`I`): `d9c449ea30a4a3e8ed73883b45ae07a7177f60a5`

Exact snapshot and executable inspection confirms the frozen conclusions
`p*(S)=TRUE`, `p*(C)=TRUE`, and `p*(I)=FALSE`.

The candidate is rejected before task or evaluator construction. PR #744's
legitimate functionality is the ability for caller-selected external code to
supply the pipeline class, while the exact frozen property prohibits that same
capability. The required safe-control result (`FUNCTIONAL=PASS`,
`SECURITY=PASS`) is therefore logically incompatible without redefining either
the historical functionality or the property.

No task, source memory, functional oracle, security witness, reference,
backend, production manifest, matrix, or model outcome was created or used.
The property, functionality, and witness were not redefined. This candidate is
not model-ready; the canonical decision is recorded in
`validation/candidate-rejection.json`.
