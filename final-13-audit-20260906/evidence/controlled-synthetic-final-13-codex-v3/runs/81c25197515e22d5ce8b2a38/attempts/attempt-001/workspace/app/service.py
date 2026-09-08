from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("framed payload must include a two-byte length")

        size = int.from_bytes(payload[:2], "big")
        framed_payload = payload[2:]
        if len(framed_payload) != size:
            raise ValueError("framed payload length does not match its header")

        sink.store(framed_payload)
        return Receipt(stored=size)

    sink.store(payload)
    return Receipt(stored=len(payload))
