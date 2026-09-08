from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("Frame too short to contain length prefix")
        
        # Read the length from the first two bytes
        length = int.from_bytes(payload[:2], "big")
        
        # Extract the payload (body)
        body = payload[2:]
        
        # Verify the length matches the actual payload length
        if len(body) != length:
            raise ValueError("Frame length does not match payload length")
        
        sink.store(body)
        return Receipt(stored=len(body))
    else:
        sink.store(payload)
        return Receipt(stored=len(payload))
