# Isolated controlled-v2 constructor workspace

This workspace contains one prospectively frozen family. Follow the rendered
prompt. Read only `inputs/` and `tools/check_public.py`; write candidate output
only under `candidate/`, with optional temporary work under `.scratch/`. Do not
inspect parent directories, Git metadata, other families, prior attempts, sealed
tests, reference implementations, or acquisition decisions. Do not use network
access. The only relevant check available here is
`python tools/check_public.py`; the external harness makes admission decisions.
