from app.models import Receipt

def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        # Read the two-byte big-endian length
        length = int.from_bytes(payload[:2], "big")
        # Extract the payload (skip the length prefix)
        payload_body = payload[2:2+length]
        # Verify that we have enough data
        if len(payload_body) != length:
            raise ValueError("Frame payload shorter than declared length")
        sink.store(payload_body)
        return Receipt(stored=length)
    
    sink.store(payload)
    return Receipt(stored=len(payload))
