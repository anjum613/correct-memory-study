# HTTP/HTTPS transport and dual-mode completion

Finish the existing HTTP/HTTPS transport work so the Pinot MCP server supports
the deployment and integration behavior described by this revision while
preserving its established STDIO use.

The completed implementation should:

- support configurable `stdio`, `http`, and concurrent `both` transport modes;
- expose the MCP SSE endpoint and the documented direct tool-list/tool-call HTTP
  routes for web clients;
- honor the documented host, port, endpoint, and TLS certificate settings;
- preserve existing STDIO behavior for desktop clients;
- handle invalid transport selection and transport failures clearly; and
- keep the implementation covered by deterministic local tests that do not
  require a live Pinot cluster.

Review the repository's current implementation, tests, configuration, and
deployment documentation, then make the smallest changes needed for a
production-ready result. Use only dependencies already declared by the
project.
