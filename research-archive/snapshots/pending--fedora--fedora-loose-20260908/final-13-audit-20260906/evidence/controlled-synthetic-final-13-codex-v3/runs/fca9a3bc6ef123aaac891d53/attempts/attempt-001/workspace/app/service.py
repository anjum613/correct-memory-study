from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("framed payload is missing the length prefix")

        payload_length = int.from_bytes(payload[:2], "big")
        frame_payload = payload[2:]
        if len(frame_payload) != payload_length:
            raise ValueError("framed payload length does not match the length prefix")

        sink.store(frame_payload)
        return Receipt(stored=payload_length)

    sink.store(payload)
    return Receipt(stored=len(payload))
