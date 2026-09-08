from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("framed payload is missing its length prefix")

        declared_length = int.from_bytes(payload[:2], "big")
        payload = payload[2:]
        if len(payload) != declared_length:
            raise ValueError("framed payload length does not match its length prefix")

    sink.store(payload)
    return Receipt(stored=len(payload))
