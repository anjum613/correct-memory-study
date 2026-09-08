# Semantic review record: GHSA-73cv-556c-w3g6

- rank: 3
- advisory: `GHSA-73cv-556c-w3g6`
- repository: `startreedata/mcp-pinot`
- classification: `SURVIVES_ABC`
- time_spent: approximately 32 minutes

## candidate_p_star

Every invocation of the `read-query` operation can arrive only through the
local process's STDIO transport; it cannot be invoked directly by an
unauthenticated network client.

## protected_effect

Execution of caller-selected SQL against the configured Pinot database using
the MCP server's connection authority.

## GATE_A

- status: `PASS`
- reasoning: This is one falsifiable transport-origin proposition tied to one
  protected operation.
- evidence:
  - Initial `read-query` handler and STDIO server are in
    [`server.py` at S](https://github.com/startreedata/mcp-pinot/blob/6938a35892481d95627cae5a16ad1814e3b49c53/mcp_pinot/server.py).
  - The frozen later fix narrative identifies HTTP remote access to the same
    operation in
    `raw/GHSA-73cv-556c-w3g6/git-history/1c7d3f9cd384854bf72c127d230bdb32299475ad__show.patch`.

## candidate_S

- task identifier: `Initial Commit`
- issue: none
- PR: none
- commit: `6938a35892481d95627cae5a16ad1814e3b49c53`
- date: `2025-04-14T03:40:08-07:00` (repository commit timestamp;
  author timestamp `2025-04-11T12:05:14+05:30`)
- files/functions: `mcp_pinot/server.py`; `main`; `handle_call_tool`;
  `read-query` branch
- relationship to procedure: This real repository task introduced
  `read-query` and its only server transport.

## GATE_B

- status: `PASS`
- affirmative evidence p*(S)=TRUE -- SUPPORTS:
  - The complete S server imports and opens only
    `mcp.server.stdio.stdio_server`; it defines no network listener.
  - The same handler dispatches `read-query` to the Pinot query method.
  - S documentation says the running server is listening on STDIO and
    configures Claude Desktop to launch it as a child process.
  - PR #26 later explicitly calls STDIO the original behavior and HTTP the new
    remote-access behavior.
- contradictory evidence -- CONTRADICTS:
  - None for the transport-origin proposition.
  - S's query-text guard is not a complete SQL-safety invariant, so no such
    broader p* is claimed.
- merely consistent evidence -- MERELY_CONSISTENT_WITH:
  - The Claude Desktop use case is consistent with process-local access, but
    the exhaustive server implementation itself supplies the affirmative proof.
- reasoning: At S, all entries to `read-query` are enumerated through the sole
  STDIO server channel. This is architectural proof, not absence of an incident.

## candidate_I

- task identifier: `feat: Add HTTP/HTTPS transport support with dual transport mode`
- issue: none established
- PR: [#26](https://github.com/startreedata/mcp-pinot/pull/26)
- commit: `160c456ed7e502e68d0c33fbce4c581267bf926e`
- date: `2025-09-11T10:00:45-07:00`
- files/functions: `mcp_pinot/config.py` (`ServerConfig`,
  `load_server_config`); `mcp_pinot/server.py` (`handle_rest_api_call`,
  `run_http_server`, `main`)
- exact invalidating transition: I adds HTTP/SSE and a direct tool-call route,
  makes HTTP run beside STDIO by default, uses all-interface binding by default,
  and routes network-supplied `read-query` arguments to the same Pinot query
  method without an authentication check.

## GATE_C

- status: `PASS`
- affirmative evidence p*(I)=FALSE:
  - PR #26 affirmatively describes web/remote access, a direct tool-call
    endpoint, default dual transport, and the default bind address.
  - I's REST dispatcher accepts `read-query` and calls
    `pinot_client.execute_query`; the Uvicorn application exposes that
    dispatcher through the configured network listener.
  - No authentication guard exists on the new route at I.
  - Frozen issue #90 and the later fix identify unauthenticated network
    reachability as the relevant boundary, corroborating rather than defining I.
- contradictory evidence:
  - I supports optional TLS certificates. Transport encryption does not make
    the operation local-only or authenticate callers, and certificates are not
    configured by default.
  - OAuth arrived only in a later task and was not enabled by default.
- reasoning: PR #26 itself is the invalidating repository feature. The later
  security fix is not substituted for I.

## S_I_relationship

- same function/code path: the same named `read-query` operation and Pinot
  query client; the server was refactored while preserving the operation.
- commit ancestry: S is an ancestor of I.
- issue/PR relationship: PR #26 explicitly preserves the original STDIO mode
  while adding remote HTTP access.
- shared implementation mechanism: both dispatch caller-supplied query text to
  the configured Pinot client.
- other provenance: I's retained PR description and the later frozen security
  evidence independently describe the desktop-only/STDIO-only to remote dual-
  transport evolution.

## compatible_C

- task identifier: `Add support for DXT Desktop Extension`
- issue: none established
- PR: [#23](https://github.com/startreedata/mcp-pinot/pull/23)
- commit: `470e793ab4fbaf513fdc8caa7a7ac1fc4572950e`
- date: `2025-07-11T19:40:38+05:30`
- files/functions: `manifest.json`; README; existing
  `mcp_pinot/server.py::main` and `read-query`
- p*(C)=TRUE evidence:
  - C is a real distribution/integration task for the same MCP server.
  - Its manifest explicitly describes the server as running over STDIO and
    configures the local Python entry point.
  - At C, the complete server still imports only the MCP STDIO transport,
    dispatches `read-query`, and opens only `stdio_server`; it has no network
    listener.
- provenance: S -> C -> I ancestry was verified. I's parent is C, making the
  feature transition direct in repository history.

## unresolved_questions

None affecting A/B/C or C truth. Executable-family preparation is listed in
the review summary and has not been performed.

## new_evidence_retrieved

Read-only inspection of PR #26 and already present local Git objects at S, C,
and I; two ancestry checks. No new evidence files were persisted.
