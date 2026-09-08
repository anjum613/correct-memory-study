from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("framed payload is missing length prefix")

        declared_length = int.from_bytes(payload[:2], "big")
        frame_body = payload[2:]
        if len(frame_body) != declared_length:
            raise ValueError("framed payload length does not match prefix")

        sink.store(frame_body)
        return Receipt(stored=len(frame_body))

    sink.store(payload)
    return Receipt(stored=len(payload))
