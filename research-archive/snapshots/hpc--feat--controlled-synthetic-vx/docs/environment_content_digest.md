# Environment content digest

`environment-content-digest-v1` is the authoritative byte-integrity record for
the frozen runtime. It is separate from `environment-fingerprint-v2`, which
records installed package names, exact versions, and Python identity.

The canonical document is UTF-8 JSON with sorted object keys, compact
separators, and one trailing LF. Content entries are sorted using Python
code-point order by normalized relative path, file type, content SHA-256, and
symlink target. Package entries are sorted by canonicalized distribution name
and exact installed version. Text is Unicode NFC and line endings are
normalized to LF.

Regular-file entries contain only:

- normalized relative path;
- `file` type;
- SHA-256 of the file bytes.

Symlink entries contain only:

- normalized relative path;
- `symlink` type;
- normalized link target.

The guided-backend runtime profile covers the files reported by the installed
vLLM, Outlines, pyairports, and lm-format-enforcer distributions, their exact
versions, the environment interpreter link, and the resolved interpreter
bytes. It does not depend on filesystem enumeration order.

`environment-metadata-observation-v1` is informational. It may record mode,
ownership, mtime, ctime, inode, and device number, but those fields cannot by
themselves declare an environment change. The authoritative content digest
never includes those fields, hostnames, locale values, temporary paths, or
environment variables.

Historical metadata digests are not rewritten. A matching content digest with
different metadata is classified
`ENVIRONMENT_CONTENT_UNCHANGED_METADATA_DIFFERED`; changed bytes, versions,
symlink targets, or selected file sets are classified
`ENVIRONMENT_CONTENT_CHANGED`.
