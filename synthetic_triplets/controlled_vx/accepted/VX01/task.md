Implement ingest_batch(frames, sink, *, reverse=False). A frame is a dict with
id (nonempty string), declared_size (nonnegative integer), and body (bytes).
Frame ids must be unique. Preserve input order, or reverse the whole batch
when reverse=True. Each stored row contains id, body, and offset (the total
body size preceding it in the chosen order). Return a dict containing ids,
sizes, offsets, total_bytes, and count. Empty batches return empty lists and
zero totals. Validate structural fields and duplicate ids before committing;
reject those errors with ValueError and leave the sink unchanged. Commit the
complete list exactly once on success, including the empty batch. Keep
ingest_raw(body, sink) unchanged. All operations use the supplied MemorySink.
A frame is exactly one declared body, with neither missing nor trailing data.
