def ingest_raw(body, sink):
    sink.commit([{"id": "raw", "body": body, "offset": 0}])
    return len(body)

def ingest_batch(frames, sink, *, reverse=False):
    raise NotImplementedError("batch ingestion")
