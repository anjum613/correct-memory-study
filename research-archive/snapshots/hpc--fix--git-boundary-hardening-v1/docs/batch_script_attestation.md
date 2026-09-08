# Slurm controller batch-script attestation

Batch scripts are attested outside the compute job. The submission wrapper
hashes the exact source file, submits that same path once with a deferred start,
retrieves the controller copy with `scontrol write batch_script`, and hashes the
retrieved bytes. Execution is eligible only when both plain SHA-256 values and
both files match exactly. A retrieval or comparison failure is classified as
`CONTROLLER_BATCH_SCRIPT_ATTESTATION_FAILURE` and cancels that submitted job.

The canonical file digest is SHA-256 over exact file bytes. Its normalized
representation is exactly 64 lowercase hexadecimal characters with no filename,
prefix, or whitespace. Comparison evidence retains the original values, UTF-8
byte encodings, normalized observations, lengths, and first differing character
or byte. LF and CRLF files therefore have intentionally different digests.

The batch script never uses its own hash as an authoritative precondition. It
records `$0`, its resolved path, readability, hash, and hash exit status when
possible; inspection failure is informational. Hashes for the shared driver and
server-command plan remain strict pre-execution gates and use the same
project-owned Python digest implementation.

Job 25371 preserved identical source, submitted, and controller copies but did
not retain the exact compute-side operands. The evidence disproves script
mutation, but the precise old comparison defect remains classified as
`BATCH_SCRIPT_ATTESTATION_COMPARISON_CAUSE_UNCONFIRMED`.
