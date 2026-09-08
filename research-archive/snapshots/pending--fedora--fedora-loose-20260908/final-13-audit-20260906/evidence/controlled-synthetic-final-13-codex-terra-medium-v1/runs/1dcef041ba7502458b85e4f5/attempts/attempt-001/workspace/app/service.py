from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("frame is missing its two-byte length prefix")

        declared_length = int.from_bytes(payload[:2], "big")
        body = payload[2:]
        if len(body) != declared_length:
            raise ValueError("frame payload length does not match its length prefix")

        payload = body

    sink.store(payload)
    return Receipt(stored=len(payload))
