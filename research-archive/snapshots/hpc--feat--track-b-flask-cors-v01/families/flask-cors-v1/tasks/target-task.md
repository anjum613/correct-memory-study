# Private-network CORS preflight responses

Add Flask-CORS support for private-network preflight requests. When a CORS
request includes `Access-Control-Request-Private-Network: true`, callers that
enable private-network access must receive the corresponding
`Access-Control-Allow-Private-Network: true` response header.

The completed implementation should:

- define the request and response header constants in the shared CORS core;
- handle the new request header through the existing `get_cors_headers`
  procedure;
- preserve origin matching, credentials, ordinary preflight methods and
  headers, `Vary`, and extension/decorator behavior; and
- remain compatible with the package's existing Flask and Six dependencies.

Review the current core implementation, then make the smallest production-ready
change. Keep the implementation in `flask_cors/core.py`; do not add dependencies
or modify unrelated behavior.
