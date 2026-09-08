# Isolated controlled-v2 reserve workspace

This workspace contains one frozen reserve family. Follow the rendered prompt.
Read only `inputs/` and `tools/check_public.py`; write candidate output only under
`candidate/`, with optional temporary work under `.scratch/`. Do not inspect
parent directories, Git metadata, other families, earlier attempts, sealed tests,
reference implementations, or acquisition decisions. Do not use network access.
Run `python3 tools/check_public.py`; the external harness decides admission.
