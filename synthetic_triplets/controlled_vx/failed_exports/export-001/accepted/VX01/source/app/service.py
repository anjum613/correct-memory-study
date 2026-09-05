def ingest_generated(rows, sink, *, reverse=False):
    frames = [{"id": row["id"], "declared_size": len(row["body"]),
               "body": row["body"]} for row in rows]
    seen = set()
    for frame in frames:
        if not isinstance(frame["id"], str) or not frame["id"] or frame["id"] in seen:
            raise ValueError("invalid or duplicate id")
        if not isinstance(frame["body"], bytes):
            raise ValueError("body must be bytes")
        seen.add(frame["id"])
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
    return {"ids": ids, "sizes": sizes, "offsets": offsets,
            "total_bytes": offset, "count": len(stored)}
