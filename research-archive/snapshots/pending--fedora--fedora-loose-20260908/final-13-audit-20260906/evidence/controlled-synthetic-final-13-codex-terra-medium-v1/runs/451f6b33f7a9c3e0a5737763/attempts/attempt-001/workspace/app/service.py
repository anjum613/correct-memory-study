from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("framed payload is missing its length prefix")

        payload_length = int.from_bytes(payload[:2], "big")
        payload = payload[2:]
        if len(payload) != payload_length:
            raise ValueError("framed payload length does not match its prefix")

    sink.store(payload)
    return Receipt(stored=len(payload))
