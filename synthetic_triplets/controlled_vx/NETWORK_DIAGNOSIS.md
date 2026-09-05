# HPC Codex observations, 2026-09-05

Observed installation: `/home/s224049759/.local/bin/codex`, reporting
`codex-cli 0.153.3`. It points into the account's standalone Codex installation.
The configured model was `gpt-6-astra`, with `xhigh` reasoning. No credentials
were displayed, copied into this repository, or changed.

An authenticated `codex exec --ignore-user-config --strict-config --ephemeral
--json` smoke invocation returned the requested `VX_CONNECTION_OK` response and
emitted `turn.completed`. The outer 55-second timeout still expired because the
process remained alive. The recorded thread identifier was
`01a07014-ab8f-7fe0-aef2-f2a79620c631`. This was a technical connectivity check,
not a constructor or evaluated-agent outcome.

Unauthenticated HTTPS reached the Codex models endpoint: HEAD returned 405 and
GET returned 401. Those responses demonstrate reachable HTTP service, not an
authentication failure of the signed-in CLI. A request to the authentication
website returned a Cloudflare browser challenge; it does not establish that
model inference is blocked. `codex login status` also hung under a bounded
diagnostic. The underlying cause of that separate hang remains unresolved.

An initial diagnostic incorrectly placed `--ignore-user-config` before the
`login` subcommand. CLI help established that it is supported after `exec`, as
the existing V2 launcher already uses it. The earlier flag-compatibility theory
was rejected. No network restriction was bypassed and no global config changed.

VX reuses the existing terminal-event strategy: preserve the successful model
turn and artifacts, allow a bounded exit grace, then terminate only the launched
process group. A deadline without a successful terminal event remains a failed
attempt. Inference has been observed to work; the process-exit hang is handled
locally rather than described as a repaired network block.

Official authentication documentation consulted:
https://learn.chatgpt.com/docs/auth
