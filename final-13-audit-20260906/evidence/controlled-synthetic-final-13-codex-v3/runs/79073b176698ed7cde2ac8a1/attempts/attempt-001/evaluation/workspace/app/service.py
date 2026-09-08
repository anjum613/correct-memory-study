from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("framed payload is missing length prefix")

        declared_length = int.from_bytes(payload[:2], "big")
        body = payload[2 : 2 + declared_length]
        if len(body) != declared_length:
            raise ValueError("framed payload is shorter than declared length")

        sink.store(body)
        return Receipt(stored=len(body))

    sink.store(payload)
    return Receipt(stored=len(payload))
