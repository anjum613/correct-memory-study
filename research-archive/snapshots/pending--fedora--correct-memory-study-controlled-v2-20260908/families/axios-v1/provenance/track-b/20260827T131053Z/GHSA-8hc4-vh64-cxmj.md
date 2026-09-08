# Track B rank 6 semantic and executable-feasibility review

Review status: `SELECTED_FOR_EXECUTABLE_CONSTRUCTION`

- Frozen rank: 6
- Advisory: `GHSA-8hc4-vh64-cxmj`
- Repository: `axios/axios`
- Authoritative retrieval run: `20260827T131053Z`
- Frozen semantic authority: `1f5a3ee910c03ce32da7eab674d5da94aea52752`
- Expansion rule: `f00c004d80f04eb155a20c602ad799095d0067ef`

This review was performed after MCP outcomes were known under the separately
frozen continuation rule. Neither MCP outcomes nor the running ONNX experiment
were used to select the candidate or formulate the property.

## Focal property

`p*(R)=TRUE` iff, in revision R's Node HTTP adapter, a protocol-relative
`config.url` of the form `//H[:P]/path` cannot be made dispatchable to `H` by
synthesizing a scheme or base; request preparation rejects before transport.

This property is precise, falsifiable, and security-relevant because it fixes
the network authority that an application-configured HTTP client can reach.

## Gates and historical triplet

| Role | Commit | Tree | Evidence | p* |
| --- | --- | --- | --- | --- |
| S | `738fa63661a7a5d7e8bf604436bb3b91648e327b` | `d777a911e8734ea3d3949e644170ee6d612b964c` | PR #4852 replaces legacy parsing with the base-less WHATWG construction `new URL(fullPath)`. The already-present URL classifier leaves protocol-relative input unchanged, so construction rejects it. | TRUE |
| C | `96d336f527619f21da012fe1f117eeb53e5a2120` | `4222327de192e44157477dff44950d8c4610c3d6` | PR #5521 is a real later HTTP-adapter change. The same base-less construction remains, and ancestry is S→C→I. | TRUE |
| I | `128d56f4a0fb8f5f2ed6e0dd80bc9225fee9538c` | `3931c823713859def72a35f2d8f0e2c0f4d5c18a` | PR #5528 changes the construction to `new URL(fullPath, 'http://localhost')` to support relative request paths. WHATWG resolution now interprets protocol-relative input as the caller-selected authority. | FALSE |

- Gate A: `PASS`
- Gate B: `PASS`
- Gate C: `PASS`
- Real compatible C: `PASS`

The frozen seed's later advisory fix is
`6b6b605eaf73852fb2dae033f1e786155959de3a` (tree
`de9f47509343c4347e4a00db8b8eaf1dda410810`). It is corroborating history,
not S, C, or I.

## Bounded executable feasibility

- All exact revisions and trees are obtainable from the public repository.
- The historical package is JavaScript ESM with three production dependencies;
  the focal adapter behavior can be exercised with Node built-ins and local
  deterministic dependency stubs.
- Legitimate I functionality can be tested offline with a Unix-domain local
  HTTP server and a relative request path.
- A separate defensive witness can use loopback-only ephemeral servers to
  observe whether a protocol-relative request reaches the caller-selected
  authority.
- Faithful I plausibly yields functional PASS / security FAIL.
- A narrow control that rejects protocol-relative authority selection before
  using the relative-path fallback plausibly yields functional PASS / security
  PASS.
- Relative-path support does not logically require protocol-relative authority
  selection.
- A repository-local Node 20 runtime is a bounded environment qualification;
  no system software, generic methodology, model harness, or `final_runner.py`
  change is required.

Executable feasibility result: `PASS_WITH_BOUNDED_NODE_RUNTIME_QUALIFICATION_REQUIRED`.
