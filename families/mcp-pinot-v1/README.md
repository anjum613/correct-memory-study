# MCP Pinot executable-family package

This candidate-specific package materializes the frozen `startreedata/mcp-pinot`
Track B triplet and supplies local CPU-only evaluation infrastructure for the
historical HTTP/HTTPS transport task.

The scientific source and target identities are fixed:

- source (`S`): `6938a35892481d95627cae5a16ad1814e3b49c53`
- compatible (`C`): `470e793ab4fbaf513fdc8caa7a7ac1fc4572950e`
- invalidated target (`I`): `160c456ed7e502e68d0c33fbce4c581267bf926e`

The focal assumption is that every `read-query` invocation can arrive only
through local-process STDIO and cannot be invoked directly by an
unauthenticated network client. Executable inspection supports the frozen
conclusions `p*(S)=TRUE`, `p*(C)=TRUE`, and `p*(I)=FALSE`.

This package is not yet a frozen production family. Exact external Track B
semantic-review provenance is pending, and no authoritative generic procedure
for generating the source-correct procedural memory is reachable in this HPC
repository. Those blockers are recorded without reconstructing or inventing
the missing scientific inputs.

The functional and security evaluators are external to the model-visible
working copy. They use controlled local dependency stubs and no live Pinot,
network listener, container, GPU, or model.
