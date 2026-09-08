from app.models import Receipt

def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        # Read the two-byte big-endian length
        length = int.from_bytes(payload[:2], "big")
        # Extract the payload based on the declared length
        actual_payload = payload[2:2+length]
        # Store only the payload portion
        sink.store(actual_payload)
        return Receipt(stored=length)
    
    sink.store(payload)
    return Receipt(stored=len(payload))
