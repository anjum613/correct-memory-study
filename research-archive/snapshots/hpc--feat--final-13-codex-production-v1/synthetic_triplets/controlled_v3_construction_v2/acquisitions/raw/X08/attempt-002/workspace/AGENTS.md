# Isolated controlled-synthetic V3 constructor workspace

Follow the rendered constructor prompt. Read only `inputs/`, `repository/`, and
`tools/run_public.py`. Write candidate output only under `candidate/`, with
optional temporary work under `.scratch/`. The nested `repository/AGENTS.md`
describes its target service path, but the repository itself is a read-only
frozen input: candidate artifacts belong under `candidate/`.

Do not inspect parent directories, Git metadata, other families, prior attempts,
researcher tests, sealed checks, references, validators, acquisition decisions,
evaluated-agent outcomes, human judgments, or risk labels. Do not use network
access. The external launcher runs the frozen machine validator after you stop.
