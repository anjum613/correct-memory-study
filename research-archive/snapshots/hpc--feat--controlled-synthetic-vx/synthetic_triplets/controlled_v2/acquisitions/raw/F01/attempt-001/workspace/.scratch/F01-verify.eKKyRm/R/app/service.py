from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        declared = int.from_bytes(payload[:2], "big")
        if len(payload) != 2 + declared:
            raise ValueError("frame length does not match its prefix")
        payload = payload[2 : 2 + declared]

    sink.store(payload)
    return Receipt(stored=len(payload))
