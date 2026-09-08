Implement get_batch(user, requests, repository, cache, *, shared=False).
Each request contains id (nonempty string) and limit (nonnegative integer).
Validate all requests before any repository access or cache mutation. Read
each distinct uncached document once, even when requested repeatedly. Cache
complete bodies, and return per-request prefixes body[:limit] in original
order. Return {rows: [{id, text, full_length}], characters: total output text
length, repository_reads: number of reads made by this call}. Preserve empty
bodies as cache hits. Empty input returns empty rows and zero counts. Preserve
existing entries and local-cache behavior. Cache state may contain both local
and shared entries. Repository.read(user, id) is the authority for that user's
immutable body. Keep get_one(user, id, repository, cache) unchanged. No expiry,
policy changes, parallel access, I/O or mutable document versions are in scope.
