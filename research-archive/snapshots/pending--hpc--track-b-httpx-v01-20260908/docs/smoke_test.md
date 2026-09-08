# Preparing the smoke repository

Run the preparation script from the repository root:

```fish
python scripts/prepare_smoke_repo.py
```

It copies `tasks/smoke_test/repository/` into a new temporary directory,
initializes that copy as a Git repository, and creates an initial commit. The
script prints the temporary working-copy path and the commit hash. It does not
modify the source template.

The copied calculator is intentionally unfinished. The smoke-test task is to
implement `add(a, b)` so the copied repository's tests pass.
