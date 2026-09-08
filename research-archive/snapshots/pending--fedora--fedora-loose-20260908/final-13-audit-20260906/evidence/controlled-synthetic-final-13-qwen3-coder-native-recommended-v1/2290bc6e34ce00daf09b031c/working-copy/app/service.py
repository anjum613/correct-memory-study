from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        length = int.from_bytes(payload[:2], "big")
        if len(payload) < 2 + length:
            raise ValueError("Incomplete frame")
        payload_data = payload[2:2+length]
        sink.store(payload_data)
        return Receipt(stored=length)

    sink.store(payload)
    return Receipt(stored=len(payload))
