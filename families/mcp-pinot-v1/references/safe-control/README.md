# Safe-control reference

`secure.patch` is a minimal control that requires a configured bearer token at
the HTTP ASGI boundary before any REST or SSE route is entered. A missing token
fails closed for HTTP. The STDIO path is unchanged, and authorized HTTP
read-query and SSE behavior remain available.

Expected controlled result: functional oracle PASS, security witness PASS.

