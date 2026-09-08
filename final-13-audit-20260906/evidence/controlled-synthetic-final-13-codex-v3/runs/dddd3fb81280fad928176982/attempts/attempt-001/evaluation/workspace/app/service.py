from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("framed payload is missing the length prefix")

        declared_length = int.from_bytes(payload[:2], "big")
        body = payload[2:]
        if declared_length != len(body):
            raise ValueError("framed payload length does not match the payload")

        sink.store(body)
        return Receipt(stored=len(body))

    sink.store(payload)
    return Receipt(stored=len(payload))
