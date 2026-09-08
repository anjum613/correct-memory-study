# Isolated repository copies

The project-owned `isolated-repository-copy-v1` policy separates source
fixture integrity from destination usability. A frozen fixture may be
read-only; the evaluated agent always works in a newly created, user-owned
copy.

## Content integrity

`isolated-repository-content-v1` hashes a canonical JSON inventory containing:

- normalized relative paths and entry types;
- exact SHA-256 values for regular-file bytes;
- literal targets for symlinks; and
- directory entries.

Unix modes, owners, timestamps, ACLs, extended attributes, enumeration order,
and the source `.git` directory are not content-authoritative. The source and
destination content digests must match before new Git metadata is created.

## Destination permissions

The recursive copy creates rather than metadata-copies each destination
entry:

- directories are `0700`;
- ordinary files are `0600`;
- files executable in the source are `0700`;
- ownership is that of the current process;
- source ownership, directory modes, timestamps, ACLs, and extended
  attributes are not copied.

Only the newly created destination is normalized or removed on copy failure.
The source fixture is never chmodded.

Relative symlinks are retained as symlinks when their resolved target remains
inside the source repository. Absolute or escaping symlinks are rejected.
Devices, sockets, FIFOs, and other special entries are rejected. Existing
top-level `.git` data is omitted, and `git init` creates fresh local metadata.

## Preparation record

After local Git initialization, every smoke run records
`repository-preparation.json` with:

- policy and content-digest schema versions;
- source and destination paths, root modes, owners, and mode inventories;
- source/destination digest equality;
- `.git` creation and the local initial commit; and
- clean initial Git status.

## CPU-gate command generation

The working-copy CPU gate builds the driver arguments as a Python tuple and
quotes each argument independently. Before `sbatch`, the project validates the
rendered script with `bash -n`, scans shell commands outside here-documents for
standalone `+` operands or patch markers, extracts the rendered driver argv,
and parses it with the driver's actual `argparse` configuration. A mismatch is
reported as `GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE`; no job is
submitted. This prevents copied diff markers or multiline-template artifacts
from becoming runtime arguments.
