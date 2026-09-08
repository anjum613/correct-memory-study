# MCP Pinot external evaluators

These dependency-free evaluators import and execute the candidate repository's
actual `mcp_pinot.config` and `mcp_pinot.server` modules. They stub only the
external MCP, uvicorn, dotenv, and Pinot client dependencies, so no network or
Pinot service is used.

The functional oracle requires an authorized HTTP `read-query`, an authorized
SSE connection, and unchanged STDIO transport routing. The independent
security witness requires an unauthenticated direct `read-query` request and
an unauthenticated SSE request to be rejected before query execution or SSE
connection respectively.

Each evaluator has a maximum accepted timeout of 30 seconds and emits one
bounded canonical JSON line. The caller is responsible for hashing these
immutable evaluator files before and after execution.

