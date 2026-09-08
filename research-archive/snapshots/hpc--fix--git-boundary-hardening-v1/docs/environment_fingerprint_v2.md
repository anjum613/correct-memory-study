# Environment fingerprint v2

`environment-fingerprint-v2` is the canonical schema for comparing Python runtime environments before submission and inside a Slurm job.

The canonical inventory is one UTF-8 JSON object followed by exactly one LF. JSON keys use Python code-point ordering, non-ASCII text is emitted directly, and the object contains only:

- `schema`: the literal `environment-fingerprint-v2`;
- `python.implementation` and `python.version`;
- `distributions`: objects containing canonical `name` and exact installed `version` strings.

All text has CRLF and CR converted to LF and is normalized to Unicode NFC. Distribution names additionally use lowercase and collapse every run of `-`, `_`, or `.` to `-`, matching the semantics of `packaging.utils.canonicalize_name`. Versions are otherwise unchanged. Distribution objects are ordered by the Python tuple `(canonical name, version)`. Duplicate records remain visible.

SHA-256 is calculated over the canonical bytes. The adjacent record stores the schema, canonical-inventory SHA-256, absolute interpreter path, Python implementation and version, and distribution count. Paths, locale values, timestamps, hosts, job IDs, cache metadata, and enumeration order are absent from the canonical inventory.

The load-gate comparator rejects records unless both explicitly declare v2. It compares the canonical hash and recorded runtime fields, returning `ENVIRONMENT_FINGERPRINT_MISMATCH` for a real difference and a distinct schema-mismatch classification for v1/v2 input. Historical v1 hashes remain historical evidence and are never rewritten or compared directly with v2.

Future Slurm scripts use the same project-owned Python entry point before submission and in the batch shell. They select `C.UTF-8` when installed and fall back to `C` for ancillary tools, but fingerprint correctness does not depend on either locale.
