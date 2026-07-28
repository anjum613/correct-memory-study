# Codex Instructions for This Research Repository

This repository contains controlled experiments involving coding agents.

## General working rules

1. Work only inside this repository.
2. Explain the plan before changing multiple files.
3. Prefer small, reviewable changes.
4. Run relevant tests after every implementation change.
5. Show git status and git diff before finishing.
6. Do not download large model files.
7. Do not change system software or GPU drivers.

## Experimental-integrity rules

1. Codex builds the experiment infrastructure but is not the evaluated agent.
2. Never manually repair a patch produced by the evaluated agent.
3. Never edit completed raw experimental outputs.
4. Never select or remove runs because of their outcomes.
5. Keep pilot and confirmatory results separate.
6. Do not change hidden security witnesses after treatment outcomes are viewed.
7. Do not choose procedural memories based on target-run results.
8. Do not alter randomisation assignments after they are generated.
9. Preserve complete trajectories, patches, logs and oracle results.
10. Record exact versions of models, agents, prompts and dependencies.

## Protected paths

Do not modify files under these paths unless the user explicitly requests it:

- results/raw/
- runs/raw/
- memories/frozen/
- tasks/*/hidden_oracles/

## Verification

For Python changes:

- run pytest
- run formatting or type checks when configured
- show the final diff
- explain the change in simple language
