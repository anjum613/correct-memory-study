from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("payload too short for frame header")
        length = int.from_bytes(payload[:2], "big")
        body = payload[2:2 + length]
        sink.store(body)
        return Receipt(stored=len(body))

    sink.store(payload)
    return Receipt(stored=len(payload))
