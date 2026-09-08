from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("framed payload must include a two-byte length")

        payload_length = int.from_bytes(payload[:2], "big")
        frame_payload = payload[2:]
        if len(frame_payload) != payload_length:
            raise ValueError("framed payload length does not match its header")
        payload = frame_payload

    sink.store(payload)
    return Receipt(stored=len(payload))
