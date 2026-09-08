from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("framed payload must contain a two-byte length prefix")

        stored = 0
        offset = 0
        while offset < len(payload):
            if offset + 2 > len(payload):
                raise ValueError("incomplete framed message length")

            frame_len = int.from_bytes(payload[offset : offset + 2], "big")
            offset += 2
            frame_end = offset + frame_len

            if frame_end > len(payload):
                raise ValueError("framed payload too short for declared frame length")

            frame = payload[offset:frame_end]
            sink.store(frame)
            stored += len(frame)
            offset = frame_end

        return Receipt(stored=stored)

    sink.store(payload)
    return Receipt(stored=len(payload))
