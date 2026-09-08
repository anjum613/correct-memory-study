from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("framed payload too short")
        length = int.from_bytes(payload[:2], "big")
        if len(payload) < 2 + length:
            raise ValueError("framed payload incomplete")
        payload = payload[2:2 + length]
    
    sink.store(payload)
    return Receipt(stored=len(payload))
