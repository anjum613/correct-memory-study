from app.models import Receipt

def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("framed payload must be at least 2 bytes long")
        
        # Read the length from the first two bytes
        length = int.from_bytes(payload[:2], "big")
        
        # Extract the actual payload
        actual_payload = payload[2:2+length]
        
        # Verify the length matches the actual payload length
        if len(actual_payload) != length:
            raise ValueError("framed payload length does not match actual length")
        
        sink.store(actual_payload)
        return Receipt(stored=len(actual_payload))
    else:
        sink.store(payload)
        return Receipt(stored=len(payload))
