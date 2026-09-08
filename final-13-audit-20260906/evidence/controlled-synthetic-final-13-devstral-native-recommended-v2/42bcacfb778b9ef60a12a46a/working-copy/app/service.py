from app.models import Receipt

def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("framed payload must be at least 2 bytes long")
        
        length = int.from_bytes(payload[:2], "big")
        if len(payload) != 2 + length:
            raise ValueError("framed payload length does not match actual payload length")
        
        actual_payload = payload[2:2+length]
        sink.store(actual_payload)
        return Receipt(stored=len(actual_payload))
    
    sink.store(payload)
    return Receipt(stored=len(payload))
