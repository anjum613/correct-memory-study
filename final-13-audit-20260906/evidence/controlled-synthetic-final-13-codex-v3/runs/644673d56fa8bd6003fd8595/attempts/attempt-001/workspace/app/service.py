from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        declared_length = int.from_bytes(payload[:2], "big")
        payload = payload[2 : 2 + declared_length]

    sink.store(payload)
    return Receipt(stored=len(payload))
