from app.operations import validate_frames


def ingest_raw(body, sink):
    sink.commit([{"id": "raw", "body": body, "offset": 0}])
    return len(body)


def ingest_batch(frames, sink, *, reverse=False):
    frames = validate_frames(frames)
    ordered = list(reversed(frames)) if reverse else frames
    stored = []
    ids, sizes, offsets = [], [], []
    offset = 0
    for frame in ordered:
        body = frame["body"][:frame["declared_size"]]
        stored.append({"id": frame["id"], "body": body, "offset": offset})
        ids.append(frame["id"])
        sizes.append(len(body))
        offsets.append(offset)
        offset += len(body)
    sink.commit(stored)
    return {
        "ids": ids,
        "sizes": sizes,
        "offsets": offsets,
        "total_bytes": offset,
        "count": len(stored),
    }
