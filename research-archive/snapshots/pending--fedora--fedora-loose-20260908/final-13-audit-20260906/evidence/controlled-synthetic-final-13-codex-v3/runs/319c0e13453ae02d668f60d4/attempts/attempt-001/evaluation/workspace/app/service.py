from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if not framed:
        sink.store(payload)
        return Receipt(stored=len(payload))

    frames = []
    offset = 0
    payload_size = len(payload)

    while offset < payload_size:
        if payload_size - offset < 2:
            raise ValueError("incomplete frame header")

        frame_size = int.from_bytes(payload[offset : offset + 2], "big")
        offset += 2

        frame_end = offset + frame_size
        if frame_end > payload_size:
            raise ValueError("incomplete frame payload")

        frames.append(payload[offset:frame_end])
        offset = frame_end

    for frame in frames:
        sink.store(frame)

    return Receipt(stored=sum(len(frame) for frame in frames))
