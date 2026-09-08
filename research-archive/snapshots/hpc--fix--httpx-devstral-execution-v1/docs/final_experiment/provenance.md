# Final experiment provenance

This branch was created for the final six-family experiment without modifying
the validated Qwen worktree.

## Starting state

- Branch: `feat/final-six-family-experiment`
- Starting commit: `ea215146e02762c0ce1ece060c99f1003e9fc99d`
- Source branch: `fix/qwen32b-protocol-hardening`
- Source worktree: `/home/s224049759/projects/worktrees/qwen32b-protocol-hardening`
- Source worktree status: clean
- Source worktree `git diff --check`: pass
- Qualified Qwen harness commit: `ba039a0eaddc358d6b7174260c3b3c36169c44c0`
- Qualified Qwen tag: `qwen32b-qualification-v1`
- Qualified Qwen model revision:
  `381fc969f78efac66bc87ff7ddeadb7e73c218a7`

The qualification commit is an ancestor of the starting commit. Existing
Qwen qualification manifests, launchers, environments, and run artifacts are
preserved and are not edited by this branch.

## Triplet/TPTM lineage status

An exhaustive read-only search of the Git common directory
`/home/s224049759/projects/correct-memory-study/.git` found no local branch,
remote-tracking ref, tag, stash, reflog, bundle, reachable commit, or dangling
commit containing the final TPTM implementation. In particular, the HPC has
no object for `feat/tptm-v1-prototype`, `trust_transition_rules.json`, the
G1–G8 ontology, promoted-family manifests, or the final six family IDs.

The newest local selection lineage is
`refs/canary-imports/b4bdd8156` at
`b4bdd8156b884ba9dfb9c08e1955a7e90a72bb09`. Its eight candidates remain in
the `DISCOVERED` state with zero automatic-gate passes. They are not selected
triplets and must not be substituted for the final six families.

The synthetic four-condition memory smoke is treatment-plumbing validation,
not final-study family or methodology evidence.

Before freezing the scientific manifest, import the exact tip of
`feat/tptm-v1-prototype` from the Fedora repository. Record the output of:

```bash
git rev-parse feat/tptm-v1-prototype
```

Then transfer that exact commit by authenticated fetch or Git bundle. Do not
reconstruct its selection, memories, witnesses, conditions, repetitions, or
seeds from memory.

## Devstral source status

The Fedora commits `cca9f28` and `e9cb806` are not present in the HPC Git
object database. The pinned Devstral revision is
`bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39`, but neither its model snapshot
nor a dedicated Devstral serving environment was present at branch creation.
Model-independent support may be developed here, but a GPU smoke cannot be
submitted until those immutable runtime inputs are staged and verified.
