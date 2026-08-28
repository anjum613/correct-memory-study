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

This production family is frozen and model-ready. The exact external Track B
semantic review is imported byte-for-byte from its authoritative retrieval run.
The source-correct procedural memory was generated after the generic source-only
protocol was frozen, using its deterministic non-model extractive renderer, and
passed source-grounding validation before any scientific model launch.

The functional and security evaluators are external to the model-visible
working copy. They use controlled local dependency stubs and no live Pinot,
network listener, container, GPU, or model.
