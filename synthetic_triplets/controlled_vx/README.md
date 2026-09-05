# VX: substantive-feature development cohort

Parent: `f65fca8b6d9a05aefe29b0bfc44996d37c826972`.
Branch: `feat/controlled-synthetic-vx`.

This is a new development cohort. Historical V2/V3 data is unchanged. The stable
V2 patch-application and isolated test-process utilities are reused; the
in-progress, untracked V3 implementation was not silently treated as a release.

Changes: six richer feature contracts; independently frozen B states; two
allowlisted implementation files; genuine behavior observations; separate
feature/security complexity diagnostics; exact input hashes; no line-count
selection; four fresh constructor attempts maximum per family; first valid
candidate retained; no evaluated-agent results used for construction.

The six cases concern frame completeness, deferred snapshots, virtual export
containment, literal status-table labels, principal-scoped caching and simulated
resource-marker scope. All effects are in-memory. These are bounded simulation
invariants, not validated security of a deployed parser, filesystem, browser or
network client. Documents/policy are immutable in the cache case, and no real
credential or real network transport appears in a stimulus.

Sources, tasks, memories, B, runtimes, public tests and sealed observations are
written and checked before constructors run. Constructors produce only the two
patches. They cannot choose B, modify tests or receive earlier-attempt feedback.
Memories retain the source-valid assumption; a harmful memory effect is not
presupposed. No evaluated agent is run by the construction commands.

Use `/opt/miniconda3/bin/python scripts/controlled_vx.py` with `materialize`,
`preflight`, `freeze`, `verify-release`, `generate --family VX01`, or `export`.
Repeat generate for VX01 through VX06. Freeze refuses scientific amendments.
Raw attempts live in `acquisitions/`; each records exact prompts, CLI version,
commands, input hashes, events, stderr, patches, validation and disposition.
Accepted exports include S, B, U and R material, raw patches and replay results.

The CLI termination handler preserves `turn.completed` evidence and terminates
only its own process group after a five-second exit grace. A process timeout
without a completed model turn cannot be accepted as a completed construction.

Passing the behavior matrix is necessary but does not certify semantic quality,
minimum useful complexity, or a treatment effect. Inspect generated changes
independently, retain all failed attempts, and report pilot results separately.
