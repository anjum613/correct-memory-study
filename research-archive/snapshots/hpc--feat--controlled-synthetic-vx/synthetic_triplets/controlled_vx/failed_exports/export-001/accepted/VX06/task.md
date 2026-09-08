Implement fetch_manifest(entries, session, transport). Session has origin
(scheme, host, port) and marker (a synthetic string). Entries have id and path
strings plus optional origin tuple; omitted origin uses session.origin.
Paths are opaque relative resource names, never parsed as URLs. Validate
nonempty unique ids, nonempty paths, and origin tuples (scheme in http/https,
nonempty host string, integer port 1..65535) before calling transport. Origin
identity treats scheme and host case-insensitively and uses the given port.
Deduplicate fetches by normalized origin and exact path, preserving one output
row per input entry in input order. Use transport.fetch(origin, path,
marker=...) and retain its body. Return {rows: [{id, origin, path, body}],
fetches: number of calls, characters: sum of output body lengths}. Row origins
are normalized tuples. Empty input returns empty rows and zero counts.
Preserve fetch_one(path, session, transport). All destinations and markers
are simulated values: transport records calls and performs no network I/O.
