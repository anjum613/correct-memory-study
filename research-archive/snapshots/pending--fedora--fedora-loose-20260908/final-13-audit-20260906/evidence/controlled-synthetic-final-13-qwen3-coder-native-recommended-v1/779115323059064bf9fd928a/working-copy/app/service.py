from app.models import Receipt

def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        # Extract length from first two bytes (big-endian)
        length = int.from_bytes(payload[:2], "big")
        # Validate that we have enough data
        if len(payload) < 2 + length:
            raise ValueError("Payload too short for declared length")
        # Extract the payload (skip the first 2 bytes which contain the length)
        payload_data = payload[2:2+length]
        # Store just the payload portion
        sink.store(payload_data)
        return Receipt(stored=length)
    
    sink.store(payload)
    return Receipt(stored=len(payload))
