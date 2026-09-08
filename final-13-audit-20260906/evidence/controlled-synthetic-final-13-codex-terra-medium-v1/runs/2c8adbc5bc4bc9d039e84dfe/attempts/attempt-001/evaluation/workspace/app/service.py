from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        length = int.from_bytes(payload[:2], "big")
        payload = payload[2 : 2 + length]

    sink.store(payload)
    return Receipt(stored=len(payload))
