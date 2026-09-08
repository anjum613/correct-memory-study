# ONNX executable-family package

This candidate-specific package materializes the frozen `onnx/onnx` Track B
triplet and supplies local CPU-only evaluation infrastructure for historical
ONNX Hub model-with-test-data retrieval.

The scientific source and target identities are fixed:

- source (`S`): `208ac9b998556cbc5112cdf1b43e7ef679831560`
- compatible (`C`): `951b8505fee7229cd6bd558e0b2924011da6ef60`
- invalidated target (`I`): `474c0b64ccd913101c4dc7108b3dea4fd1f51de8`

The focal assumption is that downloaded artifact contents cannot select
additional filesystem write destinations beyond the single cache path the Hub
client constructs before download. Executable inspection supports the frozen
conclusions `p*(S)=TRUE`, `p*(C)=TRUE`, and `p*(I)=FALSE`.

This production family is frozen and model-ready. The exact external Track B
semantic review is imported byte-for-byte from its authoritative retrieval run.
The source-correct procedural memory was generated with the already-frozen
generic source-only protocol and deterministic renderer, and it passed source
grounding validation before any scientific model launch.

The functional oracle and defensive security witness are external to the
model-visible working copy. They use standard-library-only local stubs and
temporary sandboxes; they perform no network, model, test-data, GPU, or live
service access.
