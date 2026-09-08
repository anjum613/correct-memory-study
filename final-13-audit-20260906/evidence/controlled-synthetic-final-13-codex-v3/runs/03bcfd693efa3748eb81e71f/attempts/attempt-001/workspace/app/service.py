from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("framed payload is missing length header")

        frame_length = int.from_bytes(payload[:2], "big")
        framed_payload = payload[2:]

        if len(framed_payload) != frame_length:
            raise ValueError("framed payload length does not match header")

        sink.store(framed_payload)
        return Receipt(stored=len(framed_payload))

    sink.store(payload)
    return Receipt(stored=len(payload))
