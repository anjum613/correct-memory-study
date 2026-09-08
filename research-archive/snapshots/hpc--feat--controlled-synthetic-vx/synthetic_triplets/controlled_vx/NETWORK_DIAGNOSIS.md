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

## Further observations during construction

`codex doctor --summary --no-color --ascii` reported 19 OK, one idle,
one update note, and no warnings or failures. It reported configured auth,
reachable HTTP provider endpoints, and a WebSocket connection with HTTP 101.
The diagnostic printed its completed summary but still required its outer
timeout to end. An update was advertised; no installation update was made.

The bundled ripgrep reported version 15.2.0. A normal `rg --files` on the
bounded VX01 input directory stalled, including with `--threads 1`. An observed
diagnostic process was in Linux state D, with wait channel `autofs_wait`.
This is evidence of a filesystem/automount wait, not a blocked model request.
The strace was incomplete and did not identify the exact automount pathname.
Do not infer a specific mount configuration or the root cause of every CLI
hang from this one observation. Only the launched diagnostic process group
was terminated; existing user processes were left alone.

`rg --no-ignore --hidden --files synthetic_triplets/controlled_vx/inputs/VX01`
completed successfully. `--no-ignore-parent` alone did not resolve the stall.
Explicit `/bin/cat` of named input files and `/usr/bin/find inputs -type f`
also worked in constructor sessions. Constructors independently used those
fallbacks without amendments to their frozen prompts. Use the no-ignore
workaround only on an explicit bounded input directory: it changes search
semantics and includes files normally excluded by ignore rules.

The shell also lacks an unqualified `python` executable. `/usr/bin/python3`
is Python 3.10.12, whereas the host pipeline uses `/opt/miniconda3/bin/python`
(3.12.8). Public checks can use standard-library unittest, without installing
anything. No firewall, proxy, authentication, sandbox or global Codex setting
was changed. A site administrator would need to diagnose the underlying
automount wait; the separate login-status and shutdown hangs remain unresolved.

Official authentication documentation consulted:
https://learn.chatgpt.com/docs/auth
