from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("framed payload too short")

        frame_size = int.from_bytes(payload[:2], byteorder="big")
        body = payload[2 : 2 + frame_size]
        sink.store(body)
        return Receipt(stored=len(body))

    sink.store(payload)
    return Receipt(stored=len(payload))
