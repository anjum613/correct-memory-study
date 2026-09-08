from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("Frame too short to contain length prefix")
        
        length = int.from_bytes(payload[:2], "big")
        if len(payload) != 2 + length:
            raise ValueError("Frame length does not match payload length")
        
        actual_payload = payload[2:]
        sink.store(actual_payload)
        return Receipt(stored=len(actual_payload))
    
    sink.store(payload)
    return Receipt(stored=len(payload))
