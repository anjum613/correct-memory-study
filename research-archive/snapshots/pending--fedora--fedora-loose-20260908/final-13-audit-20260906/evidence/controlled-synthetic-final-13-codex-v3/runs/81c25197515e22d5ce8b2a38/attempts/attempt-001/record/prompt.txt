The ingestion service currently accepts raw bytes. Add an optional `framed=True`
mode for frames containing a two-byte big-endian length followed by the payload.
Keep raw ingestion unchanged and return the number of stored payload bytes.
