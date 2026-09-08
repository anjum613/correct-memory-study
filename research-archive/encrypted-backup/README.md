# Encrypted research history backup — 2026-09-08

This archive preserves the original Git objects, commit dates, branches, tags, and newly created pending-work snapshots collected from Fedora, the Deakin HPC, and the workstation. It includes histories held out of readable GitHub branches because third-party research captures contain credential-like values. Original experimental evidence has not been redacted or rewritten.

The 32-byte recovery key is stored separately on Fedora at `/home/anjum/.local/share/research-git-archive-20260908.key`. The key is deliberately absent from this repository. Save a separate secure copy of it; these files cannot be recovered without it. Encrypted parts are attached to the `research-archive-20260908` GitHub release; download all parts into the same directory as the manifest and recovery script.

To restore, install Python's `cryptography` package in an environment of your choice, then run:

```bash
python3 recover.py /path/to/research-git-archive-20260908.key /path/to/restored.bundle
git clone --mirror /path/to/restored.bundle restored.git
```

The backup commit has today's date. The Git commits inside the bundle retain their original dates. Standalone and previously uncommitted work has actual snapshot dates and source-file modification times recorded in provenance manifests. Working files, staging areas, and original branches were preserved. Generated caches, nested repositories, and excluded files are listed in the audit reports; this is a research Git archive, not a full machine image.
